"""Diagnostic access to the fault memory, and how the ECU treats bad requests."""

import random

import pytest
from udsoncan.exceptions import NegativeResponseException

from bench import messages as m


@pytest.mark.requirement("DIAG-02")
def test_read_vin_over_multiple_frames(bench):
    assert bench.read(m.DID_VIN) == "KMUFAULTBENCH0001"


@pytest.mark.requirement("DIAG-02")
def test_read_software_version(bench):
    assert bench.read(m.DID_SW_VERSION) == (1, 0, 0)


@pytest.mark.requirement("DIAG-02")
def test_unknown_identifier_is_rejected(bench):
    assert bench.request([0x22, 0x12, 0x34]) == bytes([0x7F, 0x22, 0x31])


@pytest.mark.requirement("DIAG-01")
def test_session_change_reports_server_timing(bench):
    response = bench.tester.change_session(3)
    assert response.service_data.p2_server_max == pytest.approx(0.050)
    assert response.service_data.p2_star_server_max == pytest.approx(5.0)


@pytest.mark.requirement("DIAG-01")
def test_session_falls_back_after_five_seconds_of_silence(bench):
    bench.extended_session()
    bench.advance(5200)
    # An unknown routine is answered with 0x31 in the extended session, with 0x7F outside it.
    assert bench.request([0x31, 0x01, 0xFF, 0xFF]) == bytes([0x7F, 0x31, 0x7F])


@pytest.mark.requirement("DIAG-01")
def test_tester_present_keeps_the_session(bench):
    bench.extended_session()
    for _ in range(3):
        bench.advance(3000)
        bench.tester.tester_present()
    assert bench.request([0x31, 0x01, 0xFF, 0xFF]) == bytes([0x7F, 0x31, 0x31])


@pytest.mark.requirement("DIAG-03")
def test_read_and_clear_dtcs(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    bench.restbus.sending = True
    bench.wait_for_state(m.NORMAL, 1500)
    assert bench.dtcs() == {m.DTC_TIMEOUT}
    bench.clear_dtcs()
    assert bench.dtcs() == set()


@pytest.mark.requirement("DIAG-03")
def test_dtc_of_a_present_fault_is_stored_again_after_clearing(bench):
    bench.restbus.sending = False
    bench.wait_for_state(m.SAFE, 300)
    bench.clear_dtcs()
    bench.advance(50)
    assert m.DTC_TIMEOUT in bench.dtcs()


@pytest.mark.requirement("DIAG-04")
def test_unknown_service_is_rejected(bench):
    assert bench.request([0x99, 0x00]) == bytes([0x7F, 0x99, 0x11])


@pytest.mark.requirement("DIAG-04")
@pytest.mark.parametrize(
    "request_bytes",
    [[0x10], [0x22, 0xF1], [0x3E, 0x00, 0x00], [0x19, 0x02], [0x14, 0xFF, 0xFF], [0x11]],
)
def test_wrong_length_is_rejected(bench, request_bytes):
    assert bench.request(request_bytes) == bytes([0x7F, request_bytes[0], 0x13])


@pytest.mark.requirement("DIAG-04")
def test_segmented_request_is_received(bench):
    # 20 bytes do not fit one frame. TesterPresent with that length is malformed, and says so.
    assert bench.request([0x3E] + [0x00] * 19) == bytes([0x7F, 0x3E, 0x13])


@pytest.mark.requirement("DIAG-04")
def test_request_that_is_too_long_is_refused_by_flow_control(bench):
    bench.advance(20)
    start = bench.now_ms
    bench.send(m.DIAG_REQUEST_ID, bytes([0x10, 0x64, 0x3E, 0, 0, 0, 0, 0]))  # first frame, 100 bytes
    bench.advance(50)
    replies = bench.frames_of(m.DIAG_RESPONSE_ID, start)
    assert [frame.data[0] for frame in replies] == [0x32]  # flow control: overflow


@pytest.mark.requirement("DIAG-01")
def test_response_time(bench):
    worst = 0.0
    for _ in range(20):
        start = bench.now_ms
        bench.tester.tester_present()
        request = bench.frames_of(m.DIAG_REQUEST_ID, start)[0]
        response = bench.frames_of(m.DIAG_RESPONSE_ID, start)[0]
        worst = max(worst, response.t_ms - request.t_ms)
        bench.advance(20)
    assert worst <= 50 + bench.timing_slack_ms


@pytest.mark.requirement("DIAG-04", "NET-01")
def test_random_requests_are_all_answered_and_do_not_disturb_the_function(bench):
    rng = random.Random(20261008)
    start = bench.now_ms
    for _ in range(200):
        payload = [rng.randrange(256) for _ in range(rng.randrange(1, 21))]
        if payload[0] in (0x11, 0x31):
            # A reset or an injected fault would be a correct reaction, not a robustness problem.
            payload[0] = 0x3E
        assert bench.request(payload, timeout_ms=500) is not None, payload
    statuses = bench.statuses(start)
    assert {s.state for s in statuses} == {m.NORMAL}
    gaps = [b.t_ms - a.t_ms for a, b in zip(statuses, statuses[1:])]
    assert max(gaps) <= m.STATUS_CYCLE_MS * 1.1 + bench.timing_slack_ms


@pytest.mark.requirement("DIAG-04")
def test_ecu_answers_after_random_frames_on_the_request_identifier(bench):
    rng = random.Random(8)
    for _ in range(300):
        bench.send(m.DIAG_REQUEST_ID, bytes(rng.randrange(256) for _ in range(rng.randrange(1, 9))))
        bench.advance(1)
    bench.advance(50)
    bench.tester.tester_present()
    assert bench.status().state == m.NORMAL


@pytest.mark.requirement("NET-02")
def test_bench_detects_a_corrupted_status_message(fault_injection):
    """Test of the test bench: a CRC error made by the ECU must not go unnoticed."""
    from bench import e2e

    bench = fault_injection
    bench.corrupt_status(5)
    start = bench.now_ms
    bench.advance(300)
    bad = [s for s in bench.statuses(start - 30) if not e2e.crc_ok(m.STATUS_ID, s.data)]
    assert len(bad) == 5


def test_negative_response_raises_in_the_standard_client(bench):
    with pytest.raises(NegativeResponseException) as error:
        bench.tester.start_routine(0xFFFF)
    assert error.value.response.code == 0x7F
