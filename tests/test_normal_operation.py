"""The fault-free case: what the ECU does when nothing is wrong."""

import pytest

from bench import e2e
from bench import messages as m


@pytest.mark.requirement("SAFE-06")
def test_output_stays_off_until_commands_were_valid_for_500_ms(bench):
    start = bench.now_ms
    bench.reset_ecu()
    normal = bench.wait_for_state(m.NORMAL, 1500)
    since_reset = bench.statuses(start)
    first_init = next(s for s in since_reset if s.state == m.INIT)
    elapsed = normal.t_ms - first_init.t_ms
    assert m.RECOVERY_MS - 10 - bench.timing_slack_ms <= elapsed
    assert elapsed <= m.RECOVERY_MS + 10 + bench.timing_slack_ms
    before_normal = [s for s in since_reset if first_init.t_ms <= s.t_ms < normal.t_ms]
    assert all(s.applied == 0 for s in before_normal)


@pytest.mark.requirement("FUNC-01")
def test_applied_demand_follows_the_command(bench):
    assert bench.status().applied == 40
    bench.restbus.demand = 75
    bench.wait_for(lambda s: s.applied == 75, 50 + bench.timing_slack_ms, "applied demand of 75")


@pytest.mark.requirement("FUNC-01")
def test_demand_is_not_applied_without_enable(bench):
    bench.restbus.enable = 0
    status = bench.wait_for(lambda s: s.applied == 0, 50 + bench.timing_slack_ms, "applied demand of 0")
    assert status.state == m.NORMAL


@pytest.mark.requirement("NET-02")
def test_status_message_is_end_to_end_protected(bench):
    start = bench.now_ms
    bench.advance(1000)
    statuses = bench.statuses(start)
    assert len(statuses) > 50
    assert all(e2e.crc_ok(m.STATUS_ID, s.data) for s in statuses)
    steps = {e2e.counter_step(a.counter, b.counter) for a, b in zip(statuses, statuses[1:])}
    assert steps == {1}


@pytest.mark.requirement("NET-01")
def test_status_message_cycle_time(bench):
    start = bench.now_ms
    bench.advance(1000)
    times = [s.t_ms for s in bench.statuses(start)]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert max(gaps) <= m.STATUS_CYCLE_MS * 1.1 + bench.timing_slack_ms


@pytest.mark.sil_only
@pytest.mark.requirement("SAFE-05", "SAFE-06")
def test_enable_output_pin_follows_the_state(bench):
    assert bench.ecu.output is True
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 200)
    assert bench.ecu.output is False
