from __future__ import annotations

import application.host_cpu as host_cpu


def test_filetime_seconds_combines_high_and_low() -> None:
    assert host_cpu._filetime_seconds(10_000_000, 0) == 1.0
    assert host_cpu._filetime_seconds(0, 1) == (1 << 32) / 10_000_000.0


def test_sample_cpu_pct_needs_two_samples(monkeypatch) -> None:
    host_cpu._cpu_cache.clear()
    samples = {7: [1.0, 1.5]}

    def fake_cpu_seconds(pid: int) -> float | None:
        values = samples.get(pid) or []
        return values.pop(0) if values else None

    monkeypatch.setattr(host_cpu, "_cpu_seconds", fake_cpu_seconds)
    monkeypatch.setattr(host_cpu, "_NCPU", 1)
    times = iter([10.0, 11.0])
    monkeypatch.setattr(host_cpu.time, "monotonic", lambda: next(times))

    first = host_cpu.sample_cpu_pct([7])
    second = host_cpu.sample_cpu_pct([7])

    assert first[7] is None
    assert second[7] == 50.0


def test_sample_cpu_pct_drops_missing_samples(monkeypatch) -> None:
    host_cpu._cpu_cache.clear()
    monkeypatch.setattr(host_cpu, "_cpu_seconds", lambda _pid: None)
    assert host_cpu.sample_cpu_pct([3, 0]) == {3: None}


def test_sample_system_cpu_pct_needs_two_samples(monkeypatch) -> None:
    host_cpu._system_cache = None
    readings = iter([(1.0, 4.0), (1.5, 6.0)])
    monkeypatch.setattr(host_cpu, "_system_cpu_times", lambda: next(readings))
    times = iter([1.0, 2.0])
    monkeypatch.setattr(host_cpu.time, "monotonic", lambda: next(times))

    assert host_cpu.sample_system_cpu_pct() is None
    assert host_cpu.sample_system_cpu_pct() == 75.0
