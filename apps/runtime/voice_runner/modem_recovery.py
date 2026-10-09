"""Verify stopped execution and idle hardware without dialing or hanging up a live call."""

import asyncio
from dataclasses import asdict

import serial
from voice_runtime.telephony.sim7600 import Sim7600Modem


def blocked(reason, message, status=None):
    return {"verified": False, "reason": reason, "message": message, "status": status}


def verify_audio_port(body):
    # On Windows, successful serial open proves no other process holds this port.
    with serial.Serial(body.audio_port, body.baudrate, timeout=0.1, write_timeout=1):
        pass


async def verify_modem_recovery(manager, body):
    if not manager.settings.local:
        return blocked("not_local", "Modem recovery is only available on the local runtime.")
    ports = {body.at_port.casefold(), body.audio_port.casefold()}
    if len(ports) != 2:
        return blocked("invalid_ports", "AT and audio ports must differ.")
    target = None
    async with manager.lock:
        if ports & manager.probe_ports:
            return blocked(
                "probe_in_progress", "A modem check is already running. Try again shortly."
            )
        if body.session:
            target = manager.sessions.get(str(body.session.run_id))
            if target and (
                target.generation != str(body.session.generation)
                or target.boot_id != str(body.session.boot_id)
                or target.modem_ports != ports
            ):
                return blocked(
                    "identity_mismatch", "Runtime ownership changed. Refresh before recovering."
                )
        for owner in manager.sessions.values():
            if owner.request.channel != "sim7600" or not ports & owner.modem_ports:
                continue
            stopped = owner.closed.is_set() and (owner.task is None or owner.task.done())
            if not stopped or (owner is not target and owner.state != "ended"):
                return blocked(
                    "execution_active",
                    "The runtime still owns these ports. Stop the previous call or runtime, then retry recovery.",
                )
        manager.probe_ports.update(ports)
    modem = Sim7600Modem(body.at_port, body.baudrate, command_timeout=min(body.at_timeout_secs, 1))
    status = None
    try:
        async with asyncio.timeout(15):
            snapshot = await modem.probe_status()
            status = asdict(snapshot)
            status.pop("available_transports", None)
            status["call_state"] = snapshot.call_state.value
            if not snapshot.alive or not snapshot.serial_connected or snapshot.last_error:
                return blocked(
                    "probe_failed",
                    "Modem commands did not all succeed; ownership remains blocked.",
                    status,
                )
            if snapshot.active_call or status["call_state"] not in {"idle", "disconnected"}:
                return blocked(
                    "call_active",
                    "The modem still has a dialing, ringing or connected call. End it before recovery.",
                    status,
                )
            if snapshot.usb_audio_active:
                await modem.stop_usb_audio()
                snapshot = await modem.probe_status()
                status = asdict(snapshot)
                status.pop("available_transports", None)
                status["call_state"] = snapshot.call_state.value
                if (
                    not snapshot.alive
                    or not snapshot.serial_connected
                    or snapshot.last_error
                    or snapshot.usb_audio_active
                    or snapshot.active_call
                    or status["call_state"] not in {"idle", "disconnected"}
                ):
                    return blocked(
                        "audio_active", "Modem audio release could not be confirmed.", status
                    )
            # Do not abandon a serial-open thread if the HTTP request is cancelled.
            audio_check = asyncio.create_task(asyncio.to_thread(verify_audio_port, body))
            try:
                await asyncio.shield(audio_check)
            except asyncio.CancelledError:
                await audio_check
                raise
        await modem.close()
        if target:
            target.state = "ended"
        return {
            "verified": True,
            "reason": "idle_verified",
            "message": "Execution stopped; modem idle and ports released.",
            "status": status,
        }
    except Exception as exc:
        from voice_shared.logging import exception_event

        exception_event("voice-runtime", exc)
        return blocked(
            "hardware_unavailable",
            "Could not verify modem and audio port access. Check USB connection and runtime logs.",
            status,
        )
    finally:
        try:
            await modem.close()
        finally:
            async with manager.lock:
                manager.probe_ports.difference_update(ports)
