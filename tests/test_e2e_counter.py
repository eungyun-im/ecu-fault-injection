"""Alive counter monitoring (SAFE-03).

These tests are the acceptance check for e2e_counter_ok() in
firmware/lib/ecu/e2e.c. They are skipped until that function is implemented.
"""

import pytest

from bench import messages as m


@pytest.mark.requirement("SAFE-03", "SAFE-05")
def test_frozen_counter_leads_to_the_safe_state(counter_check):
    bench = counter_check
    start = bench.now_ms
    bench.restbus.freeze_counter = True
    safe = bench.wait_for_state(m.SAFE, 300)
    # The first repeated frame leaves up to one cycle after the injection.
    assert safe.t_ms - start <= 50 + m.COMMAND_CYCLE_MS + bench.timing_slack_ms
    assert safe.flags & m.FAULT_COUNTER
    assert m.DTC_COUNTER in bench.dtcs()


@pytest.mark.requirement("SAFE-03")
def test_one_lost_frame_per_step_is_tolerated(counter_check):
    bench = counter_check
    start = bench.now_ms
    bench.restbus.counter_step = 2
    bench.advance(500)
    assert {s.state for s in bench.statuses(start)} == {m.NORMAL}
    assert bench.dtcs() == set()


@pytest.mark.requirement("SAFE-03", "SAFE-05")
def test_repeated_counter_jumps_lead_to_the_safe_state(counter_check):
    bench = counter_check
    bench.restbus.counter_step = 3
    safe = bench.wait_for_state(m.SAFE, 300)
    assert safe.flags & m.FAULT_COUNTER


@pytest.mark.requirement("SAFE-03")
def test_single_counter_jump_is_tolerated(counter_check):
    bench = counter_check
    start = bench.now_ms
    bench.restbus.counter = (bench.restbus.counter + 5) % 15
    bench.advance(300)
    assert {s.state for s in bench.statuses(start)} == {m.NORMAL}
