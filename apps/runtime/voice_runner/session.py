"""One isolated execution owner, durable evidence, and bounded HTTP delivery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from pydantic import SecretStr
from voice_runtime.execution.evidence_client import EvidenceDeliveryError
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import DurableSpool
from voice_runtime.execution.termination import CallTermination
from voice_shared.logging import _subscribers, emit, exception_event


class Session:
    def __init__(self, manager, request):
        self.manager, self.request = manager, request
        self.run_id = str(request.run_id)
        self.generation = str(request.generation)
        self.boot_id = str(manager.boot_id)
        self.state = "prepared"
        self.created = time.monotonic()
        self.lease_until = self.created + 30
        self.task = None
        self.host = self.driver = self.media = None
        self.termination = CallTermination()
        self.ticket_hash = None
        self.ticket_until = 0
        self.connected = False
        self.call_sid = None
        self.spool = None
        self.delivery_task = None
        self.lease_task = None
        self.pending_updates = []
        self.pending_logs = []
        self.log_sequence = 0
        self.outcome = None
        self.next_heartbeat = 0
        self.closed = asyncio.Event()
        self.send_lock = asyncio.Lock()
        self.aux_lock = asyncio.Lock()
        self.persistence_lock = asyncio.Lock()
        self.finalize_lock = asyncio.Lock()
        self.aux_path = Path(manager.settings.runtime_spool_dir) / f"{self.run_id}.control.json"
        self.synced_aux = False
        self.wake = asyncio.Event()
        self.cleanup_pending = False
        self.pipeline_logging_enabled = bool(
            request.snapshot.get("_resolved", {}).get("pipeline_logs_enabled")
        )
        self.admitted_records = self.admitted_bytes = 0
        self.text = None

    def identity(self):
        return {
            "run_id": self.run_id,
            "generation": self.generation,
            "boot_id": self.boot_id,
            "grant": self.request.grant.get_secret_value(),
        }

    def provider_settings(self):
        keys = {k: v.get_secret_value() for k, v in self.request.credentials.items()}
        return SimpleNamespace(
            provider_stage_keys=keys,
            jev_api_key=keys.get("classifier"),
            debug_perf=self.manager.settings.debug_perf,
            env=self.manager.settings.env,
        )

    async def persist_aux(self):
        async with self.persistence_lock:
            write_task = asyncio.create_task(self._persist_aux())
            try:
                await asyncio.shield(write_task)
            except asyncio.CancelledError:
                # to_thread work survives cancellation; keep the lock until rename finishes.
                await write_task
                raise

    async def _persist_aux(self):
        # Credential-free checkpoint; fsync then atomic replacement outside audio loop.
        data = json.dumps(
            {
                "context_updates": self.pending_updates,
                "diagnostics": self.pending_logs,
                "diagnostic_sequence": self.log_sequence,
                "text_records": self.text.records if self.text else [],
                "text_checkpoint": self.text.checkpoint if self.text else None,
                "lifecycle": self.outcome
                or {
                    "runtime_state": self.state,
                    "provider_call_id": self.call_sid,
                    **(
                        {"chat_state": "connected" if self.connected else "paused"}
                        if self.text
                        else {}
                    ),
                },
            },
            separators=(",", ":"),
        )

        def write():
            import os

            temp = self.aux_path.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            for attempt in range(5):
                try:
                    temp.replace(self.aux_path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.025 * (attempt + 1))

        await asyncio.to_thread(write)

    def on_admit(self, size, kind):
        self.admitted_records += 1
        self.admitted_bytes += size
        if (
            self.admitted_records >= 100
            or self.admitted_bytes >= 256 * 1024
            or kind in {"diagnostic", "flow_visit"}
        ):
            self.loop.call_soon_threadsafe(self.wake.set)

    async def context_update(self, update):
        async with self.aux_lock:
            self.pending_updates.append(update)
            await self.persist_aux()
            self.wake.set()

    async def tool(self, name, arguments, invocation_id):
        body = {
            **self.identity(),
            "invocation_id": str(invocation_id or uuid4()),
            "name": name,
            "arguments": arguments,
        }
        try:
            response = await self.manager.control_client.post(
                "/api/v1/runtime/tools", json=body, timeout=15
            )
            response.raise_for_status()
            envelope = response.json()
            for span in envelope.get("debug_trace", []):
                emit({**span, "origin_service": "voice-api"}, forward=False)
            return envelope["result"]
        except (httpx.HTTPError, ValueError):
            # Never retry an external business write automatically.
            return {
                "status": "uncertain",
                "message": "The business operation could not be confirmed. Do not retry automatically.",
            }

    def on_log(self, event):
        if event.get("run_id") != self.run_id:
            return
        self.diagnostic_capture.submit(event)
        if len(self.pending_logs) < 100:
            self.pending_logs.append(event)
        else:
            self.manager.dropped_logs += 1

    async def sync(self, records=None):
        async with self.send_lock:
            async with self.aux_lock:
                updates = list(self.pending_updates[:100])
                logs = list(self.pending_logs[:100])
                seq = self.log_sequence + 1 if logs else self.log_sequence
                if logs:
                    await self.persist_aux()
            metrics = self.manager.metrics() if time.monotonic() >= self.next_heartbeat else {}
            if self.text:
                async with self.text.lock:
                    text_records = list(self.text.records[:100])
            else:
                text_records = []
            text_checkpoint = (
                self.text.checkpoint if self.text and self.text.checkpoint_dirty else None
            )
            body = {
                **self.identity(),
                "text_records": text_records,
                "text_checkpoint": text_checkpoint,
                "records": records or [],
                "context_updates": updates,
                "diagnostics": logs,
                "diagnostic_sequence": seq,
                "metrics": metrics,
                "lifecycle": self.outcome
                or {
                    "runtime_state": self.state,
                    "provider_call_id": self.call_sid,
                    **(
                        {"chat_state": "connected" if self.connected else "paused"}
                        if self.text
                        else {}
                    ),
                },
            }
            try:
                response = await self.manager.control_client.post(
                    "/api/v1/runtime/sync", json=body, timeout=18
                )
            except httpx.HTTPError as exc:
                if self.text:
                    self.text.emit({"type": "persistence", "state": "delayed"})
                raise EvidenceDeliveryError(retryable=True) from exc
            if response.status_code >= 400:
                if self.text:
                    self.text.emit({"type": "persistence", "state": "delayed"})
                raise EvidenceDeliveryError(retryable=response.status_code >= 500)
            reply = response.json()
            if reply.get("accepted") != len(records or []):
                raise EvidenceDeliveryError(retryable=False)
            if self.text:
                accepted = reply.get("text_accepted", 0)
                if accepted != len(text_records):
                    raise EvidenceDeliveryError(retryable=False)
                if text_checkpoint is self.text.checkpoint:
                    self.text.checkpoint_dirty = False
                del self.text.records[:accepted]
                self.text.emit(
                    {
                        "type": "persistence",
                        "state": "saved" if not self.text.records else "saving",
                        "ids": [r["id"] for r in text_records],
                    }
                )
            if reply.get("renewed"):
                self.lease_until = time.monotonic() + 30
            if reply.get("stop") and self.task and not self.task.done():
                self.termination.request("cancelled")
                self.task.cancel()
            if self.host:
                for event in reply.get("context_events", []):
                    self.host.pending_context.setdefault(event["id"], event)
            async with self.aux_lock:
                del self.pending_updates[: reply.get("context_accepted", len(updates))]
                del self.pending_logs[: len(logs)]
                self.log_sequence = seq
                await self.persist_aux()
            self.next_heartbeat = time.monotonic() + 10
            self.synced_aux = self.outcome is not None
            return len(records or [])

    async def ingest(self, records):
        await self.sync(records)

    async def deliver(self):
        while True:
            if self.state == "prepared":
                await asyncio.sleep(0.1)
                continue
            count = 0
            try:
                self.spool.check()
                count = await self.spool.deliver_once(self)
                if not count and (
                    self.pending_updates
                    or (self.text and self.text.records)
                    or self.pending_logs
                    or time.monotonic() >= self.next_heartbeat
                ):
                    await self.sync()
            except EvidenceDeliveryError as exc:
                if not exc.retryable:
                    if self.task:
                        self.task.cancel()
                    raise
            except (OSError, RuntimeError):
                self.manager.capacity.storage_healthy = False
                if self.task:
                    self.task.cancel()
                raise
            if count:
                self.admitted_records = self.admitted_bytes = 0
                await asyncio.sleep(0)
            else:
                try:
                    await asyncio.wait_for(self.wake.wait(), 2)
                except TimeoutError:
                    pass
                self.wake.clear()

    async def watch(self):
        while not self.closed.is_set():
            await asyncio.sleep(1)
            if self.state == "closing":
                continue
            if (
                time.monotonic() > self.lease_until or time.time() > self.request.expires_at
            ) and self.state != "prepared":
                self.termination.request("cancelled")
                if self.task:
                    self.task.cancel()
                elif not self.connected:
                    await self.finish({"status": "failed", "error": "Execution lease expired"})
                return
            if (
                self.state in {"prepared", "starting", "waiting_media"}
                and not self.connected
                and time.monotonic() - self.created > 60
            ):
                if self.task:
                    self.task.cancel()
                else:
                    await self.finish(
                        {"status": "failed", "error": "Media connection deadline expired"}
                    )
                return

    async def initialize(self):
        from voice_runner.diagnostics import DiagnosticCapture

        self.diagnostic_capture = await asyncio.to_thread(
            DiagnosticCapture,
            Path(self.manager.settings.recordings_dir) / self.run_id / "runtime.log",
        )
        self.aux_path.parent.mkdir(parents=True, exist_ok=True)
        self.loop = asyncio.get_running_loop()
        self.spool = await asyncio.to_thread(
            DurableSpool,
            Path(self.manager.settings.runtime_spool_dir) / f"{self.run_id}.jsonl",
            on_admit=self.on_admit,
        )
        credentials = tuple(
            v.get_secret_value()
            for v in [
                *self.request.credentials.values(),
                *self.request.telephony_credentials.values(),
            ]
        )
        self.tracker = ExchangeTracker(
            self.run_id, self.spool, secrets=(*credentials, self.request.grant.get_secret_value())
        )
        if self.request.channel == "text_test":
            from voice_runner.text import EvidenceMirror, TextState

            self.text = TextState(self)
            self.tracker.sink = EvidenceMirror(self.spool, self.text)
        from voice_shared.logging import run_id

        token = run_id.set(self.run_id)
        try:
            self.delivery_task = asyncio.create_task(self.deliver(), name=f"delivery-{self.run_id}")
            self.lease_task = asyncio.create_task(self.watch(), name=f"lease-{self.run_id}")
        finally:
            run_id.reset(token)
        _subscribers.add(self.on_log)

    def make_host(self):
        from voice_runtime.execution.native_host import NativePipelineHost

        self.host = NativePipelineHost(
            self.run_id,
            Path(self.manager.settings.recordings_dir),
            self.provider_settings(),
            termination=self.termination,
        )
        self.host.broker = self
        return self.host

    async def run_pipeline(self, transport=None, media=None):
        from voice_shared.logging import run_id

        scope_token = run_id.set(self.run_id)
        self.task = asyncio.current_task()
        self.connected = True
        self.state = "running"
        outcome = {}
        try:
            host = self.make_host()
            limit = min(
                self.manager.settings.call_max_duration_seconds,
                self.request.snapshot.get("call_limits", {}).get("max_duration_secs", 600),
            )
            async with asyncio.timeout(limit):
                if self.request.channel == "sim7600":
                    from voice_runtime.telephony.driver import Sim7600CallDriver

                    self.driver = Sim7600CallDriver(host)
                    await self.driver.prepare(self.request.snapshot, self.tracker)
                    outcome = await self.driver.call(self.request.destination)
                else:
                    await host.prepare(
                        self.request.snapshot,
                        self.tracker,
                        transport=transport,
                        enable_rtvi=self.request.channel == "browser",
                    )
                    outcome = await host.converse(media)
        except asyncio.CancelledError:
            self.termination.request("cancelled")
        except Exception as exc:
            self.termination.request("pipeline_failure")
            exception_event("voice-runtime", exc)
        finally:
            await asyncio.shield(self.finish(outcome))
            run_id.reset(scope_token)

    async def finish(self, outcome):
        async with self.finalize_lock:
            if self.closed.is_set():
                return
            self.state = "closing"
            try:
                try:
                    if self.driver:
                        await self.driver.close()
                    elif self.host:
                        await self.host.close()
                    if self.media:
                        await self.media.close()
                    elif self.call_sid:
                        from voice_runtime.telephony.twilio import (
                            TwilioCallController,
                            TwilioCredentials,
                        )

                        creds = TwilioCredentials(
                            **{
                                k: v.get_secret_value()
                                for k, v in self.request.telephony_credentials.items()
                            }
                        )
                        await TwilioCallController(creds).hangup(self.call_sid)
                    self.termination.summary.cleanup_status = (
                        "uncertain"
                        if outcome.get("dispatch_uncertain") and not self.call_sid
                        else "confirmed"
                    )
                except Exception as exc:
                    self.termination.summary.cleanup_status = "uncertain"
                    exception_event("voice-runtime", exc)
                if self.text and self.text.pending_tasks:
                    await asyncio.gather(*tuple(self.text.pending_tasks), return_exceptions=True)
                self.request.credentials.clear()
                self.request.telephony_credentials.clear()
                self.tracker._secrets = ()
                if self.host:
                    self.host.settings = None
                self.delivery_task.cancel()
                await asyncio.gather(self.delivery_task, return_exceptions=True)
                artifacts_incomplete = False
                await asyncio.to_thread(self.diagnostic_capture.close)
                if self.request.channel != "text_test" and (
                    self.host or self.diagnostic_capture.path.stat().st_size
                ):
                    try:
                        async with self.manager.upload_semaphore:
                            await self.upload_artifacts()
                    except Exception as exc:
                        artifacts_incomplete = True
                        exception_event("voice-runtime", exc)
                self.outcome = {
                    **outcome,
                    "status": self.termination.summary.execution_status,
                    "termination": self.termination.snapshot(),
                    "provider_call_id": self.call_sid,
                    "artifacts_incomplete": artifacts_incomplete,
                }
                await self.persist_aux()
                incomplete = False
                try:
                    async with asyncio.timeout(30):
                        await self.spool.flush()
                        while await self.spool.deliver_once(self):
                            pass
                        await self.sync()
                        while self.text and self.text.records:
                            await self.sync()
                except Exception:
                    incomplete = True
                await self.spool.close()
                self.cleanup_pending = incomplete or artifacts_incomplete
                self.state = (
                    "uncertain"
                    if self.termination.summary.cleanup_status == "uncertain"
                    else "ended"
                )
                self.closed.set()
                _subscribers.discard(self.on_log)
                self.request.credentials.clear()
                self.request.telephony_credentials.clear()
                if self.host:
                    self.host.settings = None
                self.tracker._secrets = ()
                self.host = self.driver = self.media = None
                if not self.cleanup_pending:
                    self.request.grant = SecretStr("")
                self.request.snapshot = {}
                self.ticket_hash = None
                # Retain IDs for duplicate-start fencing, but never credentials after cleanup.
                if self.lease_task is not asyncio.current_task():
                    self.lease_task.cancel()
                if incomplete:
                    emit(
                        {
                            "event": "evidence_incomplete",
                            "run_id": self.run_id,
                            "service": "voice-runtime",
                        }
                    )
            except Exception as exc:
                self.cleanup_pending = True
                self.state = "uncertain"
                exception_event("voice-runtime", exc)
            finally:
                self.closed.set()
                _subscribers.discard(self.on_log)
                self.request.credentials.clear()
                self.request.telephony_credentials.clear()
                if not self.cleanup_pending:
                    self.request.grant = SecretStr("")
                self.request.snapshot = {}
                self.tracker._secrets = ()
                self.host = self.driver = self.media = None
                self.ticket_hash = None
                if self.cleanup_pending:
                    task = asyncio.create_task(self.reconcile(), name=f"cleanup-{self.run_id}")
                    self.manager.cleanup_tasks.add(task)
                    task.add_done_callback(self.manager.cleanup_tasks.discard)
                if self.lease_task is not asyncio.current_task():
                    self.lease_task.cancel()

    async def reconcile(self):
        """Bounded cleanup retries cannot execute pipelines, tools, or dialing."""
        try:
            while time.time() < self.request.expires_at:
                await asyncio.sleep(10)
                try:
                    async with self.manager.upload_semaphore:
                        await self.upload_artifacts()
                    if self.outcome:
                        self.outcome["artifacts_incomplete"] = False
                        while await self.spool.deliver_once(self):
                            pass
                        await self.sync()
                        self.cleanup_pending = False
                        return
                except Exception as exc:
                    exception_event("voice-runtime", exc, forward=False)
        finally:
            self.request.grant = SecretStr("")

    async def upload_artifacts(self):
        import wave

        for kind, filename in [
            ("input", "input.wav"),
            ("output", "output.wav"),
            ("mixed", "mixed.wav"),
            ("pipeline_log", "pipeline.log"),
            ("runtime_log", "runtime.log"),
        ]:
            directory = (
                self.host.directory
                if self.host
                else Path(self.manager.settings.recordings_dir) / self.run_id
            )
            path = directory / filename
            if kind == "pipeline_log" and not self.pipeline_logging_enabled:
                continue
            if not path.is_file() or path.stat().st_size == 0:
                continue

            if kind == "pipeline_log":
                from voice_shared.logging import redact

                def sanitize(path=path):
                    safe = []
                    for line in path.read_text(encoding="utf-8").splitlines():
                        try:
                            safe.append(json.dumps(redact(json.loads(line)), separators=(",", ":")))
                        except ValueError:
                            safe.append(json.dumps({"event": "untrusted_log"}))
                    path.write_text("\n".join(safe) + "\n", encoding="utf-8")

                await asyncio.to_thread(sanitize)

            def metadata(path=path, kind=kind):
                digest = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        digest.update(chunk)
                result = {"sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}
                if kind not in {"pipeline_log", "runtime_log"}:
                    with wave.open(str(path), "rb") as f:
                        result.update(
                            sample_rate=f.getframerate(),
                            channels=f.getnchannels(),
                            sample_width=f.getsampwidth(),
                            duration_seconds=f.getnframes() / f.getframerate(),
                        )
                return result

            body = {
                **self.identity(),
                "artifact_id": str(uuid5(NAMESPACE_URL, f"{self.run_id}/{kind}")),
                "kind": kind,
                **await asyncio.to_thread(metadata),
            }
            for attempt in range(3):
                try:
                    response = await self.manager.upload_client.post(
                        "/api/v1/runtime/artifacts/grant", json=body
                    )
                    response.raise_for_status()
                    grant = response.json()
                    if not grant.get("available"):
                        if grant["provider"] == "local":

                            async def chunks(path=path):
                                f = await asyncio.to_thread(path.open, "rb")
                                try:
                                    while chunk := await asyncio.to_thread(f.read, 65536):
                                        yield chunk
                                finally:
                                    await asyncio.to_thread(f.close)

                            response = await self.manager.upload_client.put(
                                grant["upload_url"],
                                headers={
                                    "X-Voice-Runtime-Token": self.manager.settings.runtime_service_token.get_secret_value(),
                                    "X-Voice-Session-Grant": self.request.grant.get_secret_value(),
                                    "X-Voice-Generation": self.generation,
                                    "X-Voice-Boot": self.boot_id,
                                    "Content-Type": "application/octet-stream",
                                },
                                content=chunks(),
                            )
                        elif grant["provider"] == "cloudinary":
                            # Multipart file reads run outside the audio loop in a bounded uploader thread.
                            def send(path=path, grant=grant, filename=filename):
                                with path.open("rb") as f, httpx.Client(timeout=60) as client:
                                    return client.post(
                                        grant["upload_url"],
                                        data=grant["fields"],
                                        files={"file": (filename, f, "audio/wav")},
                                    )

                            response = await asyncio.to_thread(send)
                        else:
                            data = await asyncio.to_thread(path.read_bytes)
                            response = await self.manager.storage_client.put(
                                grant["upload_url"],
                                content=data,
                                headers={"Content-Type": "application/octet-stream"},
                            )
                        # Existing provider identities are verified by completion, including uncertain uploads.
                        if response.status_code >= 400 and response.status_code not in {400, 409}:
                            response.raise_for_status()
                    response = await self.manager.upload_client.post(
                        "/api/v1/runtime/artifacts/complete", json=body
                    )
                    response.raise_for_status()
                    break
                except (httpx.HTTPError, OSError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
            await asyncio.to_thread(path.unlink)
