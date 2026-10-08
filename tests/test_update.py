"""Firmware update over CAN, and the faults that can happen during one.

Every test starts with an ECU that has a bootloader and no application.
"""

import pytest
from udsoncan.exceptions import NegativeResponseException

from bench import messages as m
from bench.updater import APP_ADDRESS, APP_MAX_SIZE, Updater, application_image, synthetic_image

V100 = (1, 0, 0)
V110 = (1, 1, 0)


@pytest.fixture
def updater(update_bench):
    return Updater(update_bench)


def nrc(error):
    return error.value.response.code


def reset(bench):
    bench.tester.ecu_reset(1)
    bench.advance(100)


def application_running(bench):
    """Wait for the application and return its version."""
    bench.wait_for(lambda status: True, 2000, "status message of the application")
    return bench.read(m.DID_SW_VERSION)


def stays_in_bootloader(bench):
    """True when, over half a second, only the bootloader is heard and it reports no application."""
    start = bench.now_ms
    bench.advance(500)
    boot = bench.boot_status()
    return bench.statuses(start) == [] and boot.t_ms >= start and not boot.app_valid


def install_and_start(bench, updater, version):
    updater.install(application_image(bench, version), version)
    reset(bench)
    assert application_running(bench) == version


# The normal case


@pytest.mark.requirement("UPD-01")
def test_ecu_without_application_waits_in_the_bootloader(update_bench):
    assert stays_in_bootloader(update_bench)
    assert update_bench.read(m.DID_INSTALLED_APPLICATION) == (0, 0, 0, 0)
    assert update_bench.read(m.DID_BOOT_VERSION) == (1, 0, 0)


@pytest.mark.requirement("UPD-01", "UPD-03")
def test_installed_application_starts_and_works(update_bench, updater):
    install_and_start(update_bench, updater, V100)
    update_bench.wait_for_state(m.NORMAL, 1500)
    assert update_bench.build_info() & m.BUILD_BOOTLOADER


@pytest.mark.requirement("UPD-06")
def test_running_application_is_updated(update_bench, updater):
    install_and_start(update_bench, updater, V100)
    update_bench.wait_for_state(m.NORMAL, 1500)
    # The programming session is requested from the application, which hands over to the bootloader.
    install_and_start(update_bench, updater, V110)
    update_bench.wait_for_state(m.NORMAL, 1500)


@pytest.mark.requirement("UPD-06")
def test_erase_is_announced_with_response_pending(update_bench, updater):
    updater.enter()
    updater.check_preconditions(V100)
    update_bench.advance(20)
    start = update_bench.now_ms
    updater.request_download(7001)
    frames = update_bench.frames_of(m.DIAG_RESPONSE_ID, start)
    # The request spans two frames, so the first thing the ECU sends is a flow control frame.
    replies = [frame.data[:4] for frame in frames if frame.data[0] >> 4 != 3]
    assert replies[0] == bytes([0x03, 0x7F, 0x34, 0x78])
    assert replies[-1][:2] == bytes([0x04, 0x74])


# Faults during the update


@pytest.mark.requirement("UPD-03", "UPD-02")
def test_corrupted_data_is_not_activated(update_bench, updater):
    image = synthetic_image(V100)
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(len(image))
    updater.transfer(image, corrupt_block=3)
    with pytest.raises(NegativeResponseException) as error:
        updater.finish(image)
    assert nrc(error) == 0x72

    reset(update_bench)
    assert stays_in_bootloader(update_bench)
    # The ECU is not lost: the same update, sent correctly, succeeds.
    install_and_start(update_bench, updater, V100)


@pytest.mark.requirement("UPD-02")
@pytest.mark.parametrize("blocks_sent", [0, 1, 30])
def test_interrupted_update_leaves_no_application_and_can_be_repeated(update_bench, updater, blocks_sent):
    install_and_start(update_bench, updater, V100)
    assert updater.install(synthetic_image(V110), V110, stop_after=blocks_sent) is False

    reset(update_bench)
    assert stays_in_bootloader(update_bench)
    install_and_start(update_bench, updater, V110)


@pytest.mark.sil_only
@pytest.mark.requirement("UPD-02")
@pytest.mark.parametrize("blocks_sent", [0, 1, 30])
def test_reset_in_the_middle_of_an_update(update_bench, updater, blocks_sent):
    """A reset without warning, as a supply glitch causes it."""
    bench = update_bench
    install_and_start(bench, updater, V100)
    updater.install(synthetic_image(V110), V110, stop_after=blocks_sent)

    bench.ecu.reset(bench.now_ms)
    assert bench.ecu.mode == "bootloader"
    assert stays_in_bootloader(bench)
    install_and_start(bench, updater, V110)
    assert bench.ecu.flash_errors == []


@pytest.mark.requirement("UPD-06")
def test_silent_tester_ends_the_update(update_bench, updater):
    bench = update_bench
    image = synthetic_image(V100)
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(len(image))
    updater.transfer(image, stop_after=5)

    bench.advance(5300)
    boot = bench.boot_status()
    assert (boot.state, boot.session) == (m.BOOT_IDLE, 1)
    # The next block is refused, in a way that tells the tester to start over.
    assert bench.request(bytes([0x36, 0x06]) + bytes(8)) == bytes([0x7F, 0x36, 0x7F])


# Refused before anything is erased


@pytest.mark.requirement("UPD-05")
def test_older_version_is_refused_and_the_installed_one_keeps_running(update_bench, updater):
    install_and_start(update_bench, updater, V110)
    updater.enter()
    with pytest.raises(NegativeResponseException) as error:
        updater.check_preconditions(V100)
    assert nrc(error) == 0x31
    with pytest.raises(NegativeResponseException) as error:
        updater.request_download(7001)
    assert nrc(error) == 0x24

    reset(update_bench)
    assert application_running(update_bench) == V110


@pytest.mark.requirement("UPD-05")
@pytest.mark.parametrize(
    "address, size",
    [(APP_ADDRESS, APP_MAX_SIZE + 1), (APP_ADDRESS, 0), (0x08000000, 7001), (APP_ADDRESS + 8, 7001)],
)
def test_download_outside_the_application_slot_is_refused(update_bench, updater, address, size):
    install_and_start(update_bench, updater, V100)
    updater.enter()
    updater.check_preconditions(V110)
    with pytest.raises(NegativeResponseException) as error:
        updater.request_download(size, address=address)
    assert nrc(error) == 0x31
    assert update_bench.boot_status().app_valid

    reset(update_bench)
    assert application_running(update_bench) == V100


# Order of the sequence


@pytest.mark.requirement("UPD-04")
def test_download_needs_checked_preconditions(update_bench, updater):
    updater.enter()
    with pytest.raises(NegativeResponseException) as error:
        updater.request_download(7001)
    assert nrc(error) == 0x24


@pytest.mark.requirement("UPD-04")
@pytest.mark.parametrize(
    "request_bytes",
    [bytes([0x36, 0x01]) + bytes(8), bytes([0x37]), bytes([0x31, 0x01, 0xFF, 0x01, 0, 0, 0, 0])],
)
def test_transfer_services_need_a_started_download(update_bench, updater, request_bytes):
    updater.enter()
    assert update_bench.request(request_bytes) == bytes([0x7F, request_bytes[0], 0x24])


@pytest.mark.requirement("UPD-04")
@pytest.mark.parametrize("counter", [0, 2, 3])
def test_wrong_block_counter_is_refused(update_bench, updater, counter):
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(7001)
    assert update_bench.request(bytes([0x36, counter]) + bytes(128)) == bytes([0x7F, 0x36, 0x73])
    # The block with the expected counter is still accepted afterwards.
    assert update_bench.request(bytes([0x36, 0x01]) + bytes(128)) == bytes([0x76, 0x01])


@pytest.mark.requirement("UPD-04")
def test_repeated_block_is_refused(update_bench, updater):
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(7001)
    block = bytes([0x36, 0x01]) + bytes(128)
    assert update_bench.request(block) == bytes([0x76, 0x01])
    assert update_bench.request(block) == bytes([0x7F, 0x36, 0x73])


@pytest.mark.requirement("UPD-04")
def test_more_data_than_announced_is_refused(update_bench, updater):
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(16)
    assert update_bench.request(bytes([0x36, 0x01]) + bytes(24)) == bytes([0x7F, 0x36, 0x31])


@pytest.mark.requirement("UPD-04")
def test_exit_before_all_data_is_refused(update_bench, updater):
    image = synthetic_image(V100)
    updater.enter()
    updater.check_preconditions(V100)
    updater.request_download(len(image))
    updater.transfer(image, stop_after=10)
    assert update_bench.request([0x37]) == bytes([0x7F, 0x37, 0x24])


@pytest.mark.requirement("UPD-06")
@pytest.mark.parametrize(
    "request_bytes",
    [
        bytes([0x31, 0x01, 0xFF, 0x00, 1, 0, 0]),
        bytes([0x34, 0x00, 0x44]) + APP_ADDRESS.to_bytes(4, "big") + (7001).to_bytes(4, "big"),
        bytes([0x36, 0x01]) + bytes(8),
        bytes([0x37]),
    ],
)
def test_programming_services_need_the_programming_session(update_bench, request_bytes):
    assert update_bench.request(request_bytes) == bytes([0x7F, request_bytes[0], 0x7F])


# What the start check is for


@pytest.mark.sil_only
@pytest.mark.requirement("UPD-01")
def test_application_that_changed_in_flash_is_not_started(update_bench, updater):
    bench = update_bench
    install_and_start(bench, updater, V100)
    bench.ecu.corrupt_flash(4000)
    bench.ecu.reset(bench.now_ms)
    assert bench.ecu.mode == "bootloader"
    assert stays_in_bootloader(bench)


@pytest.mark.sil_only
@pytest.mark.requirement("UPD-03")
def test_flash_is_only_programmed_after_erasing(update_bench, updater):
    bench = update_bench
    install_and_start(bench, updater, V100)
    install_and_start(bench, updater, V110)
    install_and_start(bench, updater, V110)
    assert bench.ecu.flash_errors == []
    assert bytes(bench.ecu.flash[:7001]) == synthetic_image(V110)


@pytest.mark.sil_only
@pytest.mark.requirement("UPD-03")
def test_bootloader_and_bench_compute_the_same_crc32(_libraries):
    import zlib

    from bench import ecu_lib

    lib = ecu_lib.load_boot()
    for version in (V100, V110):
        image = synthetic_image(version)
        assert lib.crc32_compute(image, len(image)) == zlib.crc32(image)
    assert lib.crc32_compute(b"123456789", 9) == 0xCBF43926
