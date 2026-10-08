"""Check that the built images sit where the flash layout says they do.

    python -m tools.check_images

Reads the binaries PlatformIO built (firmware/.pio/build) and checks, for the
bootloader and both applications, the size and the first two entries of the
vector table: the initial stack pointer and the reset handler. A wrong linker
script shows up here, before anything is flashed.
"""

import struct
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent.parent / "firmware" / ".pio" / "build"

BOOT_START, APP_START, INFO_PAGE = 0x08000000, 0x08004000, 0x0801F800
RAM_START, RAM_END = 0x20000000, 0x20008000

# image: (first address, end address)
IMAGES = {
    "bootloader": (BOOT_START, APP_START),
    "app_v100": (APP_START, INFO_PAGE),
    "app_v110": (APP_START, INFO_PAGE),
}


def check(name, start, end):
    data = (BUILD / name / "firmware.bin").read_bytes()
    stack, reset = struct.unpack_from("<II", data)
    problems = []
    if len(data) > end - start:
        problems.append(f"{len(data)} bytes do not fit into {end - start}")
    if not RAM_START < stack <= RAM_END:
        problems.append(f"initial stack pointer 0x{stack:08X} is not in RAM")
    if not start <= reset < start + len(data):
        problems.append(f"reset handler 0x{reset:08X} is outside the image")
    print(f"{name:11} {len(data):6} bytes at 0x{start:08X}, reset handler 0x{reset:08X}, stack 0x{stack:08X}")
    return [f"{name}: {problem}" for problem in problems]


def main():
    problems = [problem for name, (start, end) in IMAGES.items() for problem in check(name, start, end)]
    for problem in problems:
        print(problem, file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
