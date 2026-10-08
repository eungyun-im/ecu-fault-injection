"""Faults injected into the command message from outside the ECU."""

import pytest

from bench import e2e
from bench import messages as m


def first_bad_command(bench, since_ms):
    """Time of the first command frame with a wrong CRC that the bench sent."""
    for frame in bench.frames_of(m.COMMAND_ID, since_ms):
        if not e2e.crc_ok(m.COMMAND_ID, frame.data):
            return frame.t_ms
    raise AssertionError("the bench sent no corrupted command")


def states_since(bench, since_ms):
    return {s.state for s in bench.statuses(since_ms)}


# Timeout


@pytest.mark.requirement("SAFE-01", "SAFE-05")
def test_missing_command_leads_to_the_safe_state(bench):
    start = bench.now_ms
    bench.restbus.sending = False
    safe = bench.wait_for_state(m.SAFE, 300)
    elapsed = safe.t_ms - start
    # The last command left up to one cycle before the injection.
    assert elapsed >= m.COMMAND_TIMEOUT_MS - m.COMMAND_CYCLE_MS - bench.timing_slack_ms
    assert elapsed <= m.COMMAND_TIMEOUT_MS + 2 + bench.timing_slack_ms
    assert safe.flags & m.FAULT_TIMEOUT
    assert safe.applied == 0
    assert m.DTC_TIMEOUT in bench.dtcs()


@pytest.mark.requirement("SAFE-01")
def test_short_interruption_is_tolerated(bench):
    start = bench.now_ms
    bench.restbus.sending = False
    bench.advance(25)
    bench.restbus.sending = True
    bench.advance(200)
    assert states_since(bench, start) == {m.NORMAL}
    assert bench.dtcs() == set()


@pytest.mark.requirement("SAFE-01")
def test_frame_with_wrong_length_does_not_count_as_a_command(bench):
    bench.restbus.dlc = 7
    safe = bench.wait_for_state(m.SAFE, 300)
    assert safe.flags & m.FAULT_TIMEOUT


# CRC


@pytest.mark.requirement("SAFE-02")
@pytest.mark.parametrize("corrupted", [1, 2])
def test_isolated_crc_errors_are_tolerated(bench, corrupted):
    start = bench.now_ms
    bench.restbus.corrupt_frames = corrupted
    bench.advance(200)
    assert states_since(bench, start) == {m.NORMAL}
    assert bench.status().applied == 40
    assert bench.dtcs() == set()


@pytest.mark.requirement("SAFE-02", "SAFE-05")
def test_three_crc_errors_in_a_row_lead_to_the_safe_state(bench):
    start = bench.now_ms
    bench.restbus.corrupt_frames = 3
    safe = bench.wait_for_state(m.SAFE, 300)
    assert safe.t_ms - first_bad_command(bench, start) <= 50 + bench.timing_slack_ms
    assert safe.flags & m.FAULT_CRC
    assert safe.applied == 0
    assert m.DTC_CRC in bench.dtcs()


@pytest.mark.requirement("SAFE-02")
def test_corrupted_command_value_is_never_applied(bench):
    start = bench.now_ms
    bench.restbus.demand = 90
    bench.restbus.corrupt_frames = 1000
    bench.wait_for_state(m.SAFE, 300)
    bench.advance(100)
    assert 90 not in {s.applied for s in bench.statuses(start)}


# Value range


@pytest.mark.requirement("SAFE-04")
def test_highest_valid_demand_is_accepted(bench):
    start = bench.now_ms
    bench.restbus.demand = 100
    bench.wait_for(lambda s: s.applied == 100, 50 + bench.timing_slack_ms, "applied demand of 100")
    bench.advance(100)
    assert states_since(bench, start) == {m.NORMAL}


@pytest.mark.requirement("SAFE-04", "SAFE-05")
@pytest.mark.parametrize("enable, demand", [(1, 101), (1, 255), (2, 40)])
def test_out_of_range_command_leads_to_the_safe_state(bench, enable, demand):
    start = bench.now_ms
    bench.restbus.enable, bench.restbus.demand = enable, demand
    safe = bench.wait_for_state(m.SAFE, 300)
    assert safe.t_ms - start <= 50 + bench.timing_slack_ms
    assert safe.flags & m.FAULT_RANGE
    assert m.DTC_RANGE in bench.dtcs()
    assert all(s.applied <= 100 for s in bench.statuses(start))


# Recovery


@pytest.mark.requirement("SAFE-06")
def test_output_returns_after_500_ms_of_valid_commands(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    resumed = bench.now_ms
    bench.restbus.sending = True
    normal = bench.wait_for_state(m.NORMAL, 1500)
    elapsed = normal.t_ms - resumed
    assert elapsed >= m.RECOVERY_MS - bench.timing_slack_ms
    assert elapsed <= m.RECOVERY_MS + m.COMMAND_CYCLE_MS + 2 + bench.timing_slack_ms
    assert normal.flags == 0
    assert all(s.applied == 0 for s in bench.statuses(resumed) if s.t_ms < normal.t_ms)


@pytest.mark.requirement("SAFE-06")
def test_fault_during_recovery_restarts_the_waiting_time(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    bench.restbus.sending = True
    bench.advance(300)
    second_fault = bench.now_ms
    bench.restbus.corrupt_frames = 3
    normal = bench.wait_for_state(m.NORMAL, 2000)
    assert normal.t_ms - second_fault >= m.RECOVERY_MS - bench.timing_slack_ms


@pytest.mark.requirement("DIAG-03")
def test_dtc_stays_stored_after_recovery(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    bench.restbus.sending = True
    bench.wait_for_state(m.NORMAL, 1500)
    assert m.DTC_TIMEOUT in bench.dtcs()
