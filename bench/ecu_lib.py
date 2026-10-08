"""Build the ECU code for the PC and load it, for the software-in-the-loop target.

    python -m bench.ecu_lib             # build both variants
    python -m bench.ecu_lib --coverage  # with gcov instrumentation

With ECU_COVERAGE=1 in the environment, the test run builds with instrumentation too.

The sources are the same files the board is flashed with: firmware/lib/ecu.
"""

import argparse
import ctypes
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "firmware" / "lib" / "ecu"
BUILD_DIR = ROOT / "build"
WARNINGS = ["-Wall", "-Wextra", "-Wpedantic", "-Wconversion", "-Wshadow", "-Werror"]
VARIANTS = {"test": 1, "release": 0}


def compiler():
    return shutil.which("gcc")


def library_path(variant):
    return BUILD_DIR / f"libecu_{variant}.so"


def build(variant="test", coverage=False):
    """Compile firmware/lib/ecu into a shared library and return its path."""
    output_dir = BUILD_DIR / variant
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [compiler(), "-std=c99", *WARNINGS, "-O0", "-g", "-fPIC", "-shared"]
    command += [f"-DECU_FAULT_INJECTION={VARIANTS[variant]}", f"-I{SOURCE_DIR}"]
    if coverage or os.environ.get("ECU_COVERAGE") == "1":
        command.append("--coverage")
    command += [str(path) for path in sorted(SOURCE_DIR.glob("*.c"))]
    command += ["-o", str(library_path(variant))]
    subprocess.run(command, check=True, cwd=output_dir)
    return library_path(variant)


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
    """ecu_port_t: the functions the ECU code calls on its platform."""

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


def main():
    parser = argparse.ArgumentParser(description="Build the ECU code for the PC.")
    parser.add_argument("--coverage", action="store_true", help="instrument for gcov")
    args = parser.parse_args()
    for variant in VARIANTS:
        print(build(variant, coverage=args.coverage))


if __name__ == "__main__":
    main()
