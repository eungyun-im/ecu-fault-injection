"""Target selection and the bench fixture.

    pytest                                   software in the loop (default)
    pytest --target hil --can-channel COM5   the board, through a CANable adapter
    pytest --target hil --virtual-ecu        the HIL side of the bench against the ECU model
"""

import pytest

from bench import ecu_lib
from bench import messages as m


def pytest_addoption(parser):
    group = parser.getgroup("bench")
    group.addoption("--target", choices=("sil", "hil"), default="sil")
    group.addoption("--can-interface", default="slcan", help="python-can interface (hil)")
    group.addoption("--can-channel", default=None, help="python-can channel, e.g. COM5 (hil)")
    group.addoption("--bitrate", type=int, default=500000)
    group.addoption(
        "--timing-slack-ms",
        type=float,
        default=5.0,
        help="measurement uncertainty added to timing limits (hil)",
    )
    group.addoption(
        "--virtual-ecu",
        action="store_true",
        help="hil only: start the ECU model on a python-can virtual bus instead of using a board",
    )
    group.addoption("--manual", action="store_true", help="run tests that need a hand on the bench")


def pytest_configure(config):
    config.addinivalue_line("markers", "sil_only: needs access to the ECU code or the platform model")
    config.addinivalue_line("markers", "hil_only: only meaningful on the board")
    config.addinivalue_line("markers", "manual: needs a person at the bench, run with --manual")
    config.addinivalue_line("markers", "requirement(*ids): requirement IDs the test verifies")


def pytest_collection_modifyitems(config, items):
    target = config.getoption("--target")
    for item in items:
        if target == "hil" and "sil_only" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="software-in-the-loop only"))
        if target == "sil" and "hil_only" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="hardware-in-the-loop only"))
        if "manual" in item.keywords and not config.getoption("--manual"):
            item.add_marker(pytest.mark.skip(reason="manual test, run with --manual"))


@pytest.fixture(scope="session")
def _libraries(request):
    """Build the ECU code for the PC once per run."""
    if request.config.getoption("--target") == "hil" and not request.config.getoption("--virtual-ecu"):
        return False
    if ecu_lib.compiler() is None:
        pytest.skip("gcc not found: the software-in-the-loop target needs it")
    for variant in ecu_lib.VARIANTS:
        ecu_lib.build(variant)
    return True


@pytest.fixture(scope="session")
def _hil(request, _libraries):
    """One connection to the bus for the whole run."""
    from bench.hil import HilBench

    options = request.config
    virtual = None
    interface, channel = options.getoption("--can-interface"), options.getoption("--can-channel")
    if options.getoption("--virtual-ecu"):
        from bench.virtual_ecu import VirtualEcu

        interface, channel = "virtual", "ecu-fault-injection"
        virtual = VirtualEcu(interface, channel).start()
    elif channel is None:
        pytest.exit("--target hil needs --can-channel (or --virtual-ecu)", returncode=4)
    bench = HilBench(
        interface, channel, options.getoption("--bitrate"), options.getoption("--timing-slack-ms")
    )
    yield bench
    bench.close()
    if virtual is not None:
        virtual.stop()


@pytest.fixture
def bench(request, _libraries):
    """The bench with the ECU freshly started, in NORMAL, with an empty fault memory."""
    if request.config.getoption("--target") == "hil":
        return request.getfixturevalue("_hil").prepare()
    from bench.sil import SilBench

    return SilBench().prepare()


@pytest.fixture
def release_bench(_libraries):
    """The release build of the ECU code (software in the loop)."""
    from bench.sil import SilBench

    return SilBench(variant="release").prepare()


@pytest.fixture
def counter_check(bench):
    """Skip until the alive counter check (SAFE-03) is implemented in e2e.c."""
    if not bench.build_info() & m.BUILD_COUNTER_CHECK:
        pytest.skip("SAFE-03 not implemented: e2e_counter_ok() in firmware/lib/ecu/e2e.c")
    return bench


@pytest.fixture
def fault_injection(bench):
    """Skip on a build without fault injection routines."""
    if not bench.build_info() & m.BUILD_FAULT_INJECTION:
        pytest.skip("this ECU build has no fault injection routines")
    return bench
