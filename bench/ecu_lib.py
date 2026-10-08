"""Build the ECU code for the PC and load it, for the software-in-the-loop target.

    python -m bench.ecu_lib             # build every variant
    python -m bench.ecu_lib --coverage  # with gcov instrumentation

With ECU_COVERAGE=1 in the environment, the test run builds with instrumentation too.

The sources are the same files the board is flashed with: firmware/lib.
"""

import argparse
import ctypes
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = ROOT / "firmware" / "lib"
BUILD_DIR = ROOT / "build"
WARNINGS = ["-Wall", "-Wextra", "-Wpedantic", "-Wconversion", "-Wshadow", "-Werror"]

APPLICATION = ("common", "ecu")
BOOTLOADER = ("common", "boot")

# name: (source folders, preprocessor definitions)
VARIANTS = {
    # The application alone, as it is flashed for the fault injection tests
    "test": (APPLICATION, {"ECU_FAULT_INJECTION": 1}),
    "release": (APPLICATION, {"ECU_FAULT_INJECTION": 0}),
    # Two versions of the application for installation behind the bootloader
    "app_v100": (APPLICATION, {"ECU_FAULT_INJECTION": 1, "ECU_BOOTLOADER": 1, "SW_VERSION_MINOR": 0}),
    "app_v110": (APPLICATION, {"ECU_FAULT_INJECTION": 1, "ECU_BOOTLOADER": 1, "SW_VERSION_MINOR": 1}),
    "boot": (BOOTLOADER, {"BOOT_TEST_BUILD": 1}),
}


def compiler():
    return shutil.which("gcc")


def library_path(variant):
    return BUILD_DIR / f"lib{variant}.so"


def build(variant="test", coverage=False):
    """Compile one variant into a shared library and return its path."""
    folders, definitions = VARIANTS[variant]
    output_dir = BUILD_DIR / variant
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [compiler(), "-std=c99", *WARNINGS, "-O0", "-g", "-fPIC", "-shared"]
    command += [f"-D{name}={value}" for name, value in definitions.items()]
    command += [f"-I{LIB_DIR / folder}" for folder in folders]
    if coverage or os.environ.get("ECU_COVERAGE") == "1":
        command.append("--coverage")
    for folder in folders:
        command += [str(path) for path in sorted((LIB_DIR / folder).glob("*.c"))]
    command += ["-o", str(library_path(variant))]
    subprocess.run(command, check=True, cwd=output_dir)
    return library_path(variant)


def build_all(coverage=False):
    return [build(variant, coverage) for variant in VARIANTS]


class CanFrame(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("dlc", ctypes.c_uint8), ("data", ctypes.c_uint8 * 8)]


CAN_SEND = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.POINTER(CanFrame))
BOOL_QUERY = ctypes.CFUNCTYPE(ctypes.c_bool)
ACTION = ctypes.CFUNCTYPE(None)
SET_BOOL = ctypes.CFUNCTYPE(None, ctypes.c_bool)
GET_U8 = ctypes.CFUNCTYPE(ctypes.c_uint8)
GET_U32 = ctypes.CFUNCTYPE(ctypes.c_uint32)
SET_U32 = ctypes.CFUNCTYPE(None, ctypes.c_uint32)


class Port(ctypes.Structure):
    """ecu_port_t: the functions the application calls on its platform."""

    _fields_ = [
        ("can_send", CAN_SEND),
        ("can_bus_off", BOOL_QUERY),
        ("can_recover", ACTION),
        ("set_output", SET_BOOL),
        ("watchdog_feed", ACTION),
        ("reset_cause", GET_U8),
        ("nv_read", GET_U32),
        ("nv_write", SET_U32),
        ("system_reset", ACTION),
        ("halt", ACTION),
        ("block_ms", SET_U32),
    ]


def load(variant="test"):
    lib = ctypes.CDLL(str(library_path(variant)))
    lib.ecu_init.argtypes = [ctypes.POINTER(Port), ctypes.c_uint32]
    lib.ecu_init.restype = None
    lib.ecu_on_frame.argtypes = [ctypes.POINTER(CanFrame), ctypes.c_uint32]
    lib.ecu_on_frame.restype = None
    lib.ecu_step.argtypes = [ctypes.c_uint32]
    lib.ecu_step.restype = None
    lib.e2e_crc8.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
    lib.e2e_crc8.restype = ctypes.c_uint8
    lib.e2e_frame_crc.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
    lib.e2e_frame_crc.restype = ctypes.c_uint8
    lib.e2e_counter_ok.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
    lib.e2e_counter_ok.restype = ctypes.c_bool
    lib.e2e_counter_check_implemented.restype = ctypes.c_bool
    return lib


class BootInfo(ctypes.Structure):
    """boot_info_t: what the info page says about the installed application."""

    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("crc", ctypes.c_uint32),
        ("version", ctypes.c_uint8 * 3),
        ("reserved", ctypes.c_uint8),
    ]


FLASH_APP = ctypes.CFUNCTYPE(ctypes.c_void_p)
ERASE_PAGE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint32)
FLASH_WRITE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32)
INFO_READ = ctypes.CFUNCTYPE(None, ctypes.POINTER(BootInfo))
INFO_WRITE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.POINTER(BootInfo))


class BootPort(ctypes.Structure):
    """boot_port_t: the functions the bootloader calls on its platform."""

    _fields_ = [
        ("can_send", CAN_SEND),
        ("flash_app", FLASH_APP),
        ("flash_erase_page", ERASE_PAGE),
        ("flash_write", FLASH_WRITE),
        ("info_read", INFO_READ),
        ("info_erase", BOOL_QUERY),
        ("info_write", INFO_WRITE),
        ("nv_read", GET_U32),
        ("nv_write", SET_U32),
        ("system_reset", ACTION),
    ]


def load_boot():
    lib = ctypes.CDLL(str(library_path("boot")))
    lib.boot_start.argtypes = [ctypes.POINTER(BootPort)]
    lib.boot_start.restype = ctypes.c_bool
    lib.boot_init.argtypes = [ctypes.POINTER(BootPort), ctypes.c_uint32]
    lib.boot_init.restype = None
    lib.boot_on_frame.argtypes = [ctypes.POINTER(CanFrame), ctypes.c_uint32]
    lib.boot_on_frame.restype = None
    lib.boot_step.argtypes = [ctypes.c_uint32]
    lib.boot_step.restype = None
    lib.crc32_compute.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
    lib.crc32_compute.restype = ctypes.c_uint32
    return lib


def main():
    parser = argparse.ArgumentParser(description="Build the ECU code for the PC.")
    parser.add_argument("--coverage", action="store_true", help="instrument for gcov")
    args = parser.parse_args()
    for path in build_all(coverage=args.coverage):
        print(path)


if __name__ == "__main__":
    main()
