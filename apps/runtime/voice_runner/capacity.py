"""Admission decisions are local and independent of API responsiveness."""

import asyncio
import time
from collections import deque

import psutil


class Capacity:
    def __init__(self, settings):
        self.settings = settings
        self.process = psutil.Process()
        self.process.cpu_percent()
        self.metrics = {}
        self.blocked = False
        self.draining = False
        self.samples = deque(maxlen=10)
        self.healthy = 0
        self.storage_healthy = True
        self.lag_samples = deque(maxlen=3)
        self.pressure = lambda: {}

    def sample(self, lag_ms):
        pressure = self.pressure()
        self.lag_samples.append(lag_ms)
        congested = max(pressure.values(), default=0) >= 0.8
        cpu = self.process.cpu_percent() / self.settings.runtime_cpu_budget
        rss = self.process.memory_info().rss
        memory_limit = psutil.virtual_memory().total
        try:
            from pathlib import Path

            limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
            if limit != "max":
                memory_limit = min(memory_limit, int(limit))
        except (OSError, ValueError):
            pass
        memory = rss / memory_limit * 100
        self.samples.append(cpu)
        overload = (
            (len(self.samples) == 10 and min(self.samples) > 80)
            or memory > 80
            or (
                len(self.lag_samples) == 3
                and min(self.lag_samples) > self.settings.runtime_max_loop_lag_ms
            )
            or congested
            or not self.storage_healthy
        )
        healthy = (
            cpu < 65 and memory < 70 and lag_ms < 10 and self.storage_healthy and not congested
        )
        self.healthy = self.healthy + 1 if healthy else 0
        if overload:
            self.blocked = True
        elif self.healthy >= 3:
            self.blocked = False
        self.metrics = {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "rss_bytes": rss,
            "loop_lag_ms": lag_ms,
            **pressure,
            "blocked": self.blocked,
            "draining": self.draining,
        }

    async def monitor(self):
        window = time.monotonic()
        lags = []
        while True:
            expected = time.monotonic() + 0.02
            await asyncio.sleep(0.02)
            lags.append(max(0, (time.monotonic() - expected) * 1000))
            if time.monotonic() - window >= 1:
                # p95 captures sustained starvation; retain maximum for diagnosis.
                ordered = sorted(lags)
                await asyncio.to_thread(self.sample, ordered[int((len(ordered) - 1) * 0.95)])
                self.metrics["loop_lag_max_ms"] = max(lags)
                window = time.monotonic()
                lags.clear()

    def allows(self, count):
        return not self.blocked and not self.draining and count < self.settings.max_concurrent_calls
