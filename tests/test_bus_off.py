"""CAN bus-off: the controller takes itself off the bus after too many transmit errors."""

import pytest

from bench import messages as m

RESUME_LIMIT_MS = 1000


@pytest.mark.sil_only
@pytest.mark.requirement("SAFE-09")
def test_ecu_rejoins_the_bus_after_bus_off(bench):
    start = bench.now_ms
    bench.ecu.short_bus(300)
    bench.advance(300)
    assert bench.statuses(start + 1) == []

    fault_ended = bench.now_ms
    first = bench.wait_for(lambda s: True, RESUME_LIMIT_MS, "status after the bus fault")
    assert first.t_ms - fault_ended <= RESUME_LIMIT_MS
    assert first.state == m.SAFE
    assert first.flags & m.FAULT_BUS_OFF

    bench.wait_for_state(m.NORMAL, 1500)
    assert bench.read(m.DID_BUS_OFF_COUNT) >= 1
    assert m.DTC_BUS_OFF in bench.dtcs()


@pytest.mark.hil_only
@pytest.mark.manual
@pytest.mark.requirement("SAFE-09")
def test_ecu_rejoins_the_bus_after_a_short_circuit(bench, capsys):
    """Needs a jumper wire and `pytest -s --manual`."""
    count_before = bench.read(m.DID_BUS_OFF_COUNT)
    with capsys.disabled():
        print("\n  Connect CANH to CANL with a jumper wire for about one second,")
        print("  remove it, then press Enter.")
        input()
    bench.wait_for_state(m.NORMAL, RESUME_LIMIT_MS + m.RECOVERY_MS + 1000)
    assert bench.read(m.DID_BUS_OFF_COUNT) > count_before
    assert m.DTC_BUS_OFF in bench.dtcs()
