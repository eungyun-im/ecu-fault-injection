"""Faults injected inside the ECU: a stuck CPU, a late task, and what a reset leaves behind."""

import pytest

from bench import messages as m

RESTART_LIMIT_MS = 500


def longest_silence(bench, since_ms, until_ms):
    times = [since_ms] + [s.t_ms for s in bench.statuses(since_ms) if s.t_ms <= until_ms]
    return max(b - a for a, b in zip(times, times[1:] + [until_ms]))


@pytest.mark.requirement("SAFE-07", "SAFE-08")
def test_stuck_cpu_is_restarted_by_the_watchdog(fault_injection):
    bench = fault_injection
    resets_before = bench.read(m.DID_WATCHDOG_RESETS)

    bench.halt_cpu()
    injected = bench.now_ms
    restarted = bench.wait_for(
        lambda s: s.reset_cause == m.RESET_WATCHDOG, 2000, "status after a watchdog reset"
    )

    assert restarted.t_ms - injected <= RESTART_LIMIT_MS + bench.timing_slack_ms
    # The ECU really was gone: no status for most of the watchdog period.
    assert longest_silence(bench, injected, restarted.t_ms) >= m.WATCHDOG_TIMEOUT_MS / 2
    assert restarted.state == m.INIT
    assert restarted.applied == 0

    bench.wait_for_state(m.NORMAL, 1500)
    assert bench.read(m.DID_RESET_CAUSE) == m.RESET_WATCHDOG
    assert bench.read(m.DID_WATCHDOG_RESETS) == resets_before + 1
    assert m.DTC_WATCHDOG_RESET in bench.dtcs()


@pytest.mark.requirement("SAFE-10")
def test_short_delay_of_the_task_is_tolerated(fault_injection):
    bench = fault_injection
    bench.block_task(2)
    start = bench.now_ms
    bench.advance(200)
    assert {s.state for s in bench.statuses(start)} == {m.NORMAL}
    assert m.DTC_DEADLINE not in bench.dtcs()


@pytest.mark.requirement("SAFE-10", "SAFE-05")
def test_late_task_leads_to_the_safe_state_without_a_reset(fault_injection):
    bench = fault_injection
    cause_before = bench.status().reset_cause
    resets_before = bench.read(m.DID_WATCHDOG_RESETS)

    bench.block_task(20)
    safe = bench.wait_for_state(m.SAFE, 300)

    assert safe.flags & m.FAULT_DEADLINE
    assert safe.reset_cause == cause_before
    assert m.DTC_DEADLINE in bench.dtcs()
    assert bench.read(m.DID_WATCHDOG_RESETS) == resets_before
    bench.wait_for_state(m.NORMAL, 1500)


@pytest.mark.sil_only
@pytest.mark.requirement("SAFE-10")
@pytest.mark.parametrize("blocked_ms, violated", [(5, False), (6, True)])
def test_deadline_boundary(fault_injection, blocked_ms, violated):
    bench = fault_injection
    bench.block_task(blocked_ms)
    bench.advance(100)
    assert (m.DTC_DEADLINE in bench.dtcs()) is violated


@pytest.mark.requirement("SAFE-07")
def test_task_blocked_longer_than_the_watchdog_period_causes_a_reset(fault_injection):
    bench = fault_injection
    bench.block_task(300)
    bench.wait_for(lambda s: s.reset_cause == m.RESET_WATCHDOG, 2000, "status after a watchdog reset")


@pytest.mark.requirement("SAFE-08", "DIAG-05")
def test_requested_reset_is_not_recorded_as_a_watchdog_reset(bench):
    resets_before = bench.read(m.DID_WATCHDOG_RESETS)
    bench.tester.ecu_reset(1)
    bench.wait_for(lambda s: s.reset_cause == m.RESET_SOFTWARE, 2000, "status after a requested reset")
    bench.wait_for_state(m.NORMAL, 1500)
    assert bench.read(m.DID_WATCHDOG_RESETS) == resets_before
    assert m.DTC_WATCHDOG_RESET not in bench.dtcs()


@pytest.mark.requirement("SAFE-08")
def test_fault_memory_survives_a_reset(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    bench.restbus.sending = True
    bench.tester.ecu_reset(1)
    bench.wait_for(lambda s: s.state == m.INIT, 2000, "status after the reset")
    bench.wait_for_state(m.NORMAL, 1500)
    assert m.DTC_TIMEOUT in bench.dtcs()


@pytest.mark.requirement("DIAG-06")
def test_fault_injection_needs_the_extended_session(fault_injection):
    bench = fault_injection
    assert bench.request([0x31, 0x01, 0xF0, 0x01]) == bytes([0x7F, 0x31, 0x7F])
    bench.advance(300)
    assert bench.status().state == m.NORMAL


@pytest.mark.requirement("DIAG-06")
def test_unknown_routine_is_rejected(bench):
    bench.extended_session()
    assert bench.request([0x31, 0x01, 0xFF, 0xFF]) == bytes([0x7F, 0x31, 0x31])


@pytest.mark.sil_only
@pytest.mark.requirement("DIAG-06")
@pytest.mark.parametrize("routine", [m.ROUTINE_HALT_CPU, m.ROUTINE_BLOCK_TASK, m.ROUTINE_CORRUPT_STATUS])
def test_release_build_contains_no_fault_injection(release_bench, routine):
    bench = release_bench
    assert not bench.build_info() & m.BUILD_FAULT_INJECTION
    bench.extended_session()
    start = bench.now_ms
    for parameters in (b"", b"\x05", b"\x01\x2c"):
        request = bytes([0x31, 0x01]) + routine.to_bytes(2, "big") + parameters
        assert bench.request(request) == bytes([0x7F, 0x31, 0x31])
    bench.advance(500)
    assert {s.state for s in bench.statuses(start)} == {m.NORMAL}
    assert bench.ecu.resets == [m.RESET_POWER_ON, m.RESET_POWER_ON]
