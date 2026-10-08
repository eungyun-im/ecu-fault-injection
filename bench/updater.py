"""The tester side of a firmware update over CAN, with the faults a test can put into it.

In a vehicle this role belongs to the gateway that received the image over
the air. The sequence:

    10 02                      programming session (the application restarts into the bootloader)
    31 01 FF 00 <version>      check preconditions: is this version acceptable?
    34 00 44 <address> <size>  request download: the bootloader erases
    36 <counter> <data> ...    transfer data, block by block
    37                         transfer exit
    31 01 FF 01 <crc32>        check the image in flash and activate it
    11 01                      reset: the new application starts

    python -m bench.updater --can-channel COM5 --image firmware/.pio/build/app_v100/firmware.bin --version 1.0.0
"""

import argparse
import random
import zlib
from pathlib import Path

from udsoncan import MemoryLocation

from bench import messages as m

APP_ADDRESS = 0x08004000
APP_MAX_SIZE = 0x1B800
ROUTINE_CHECK_PRECONDITIONS = 0xFF00
ROUTINE_CHECK_AND_ACTIVATE = 0xFF01
ROUTINE_ERASE_APPLICATION = 0xFF02
PROGRAMMING_SESSION = 2


def synthetic_image(version, size=7001):
    """Stand-in for a firmware image: fixed pseudo-random bytes per version.

    The length is deliberately not a multiple of 8, so the last block needs padding.
    """
    return random.Random(str(version)).randbytes(size)


def application_image(bench, version):
    """An image that can really be started on the target of this bench.

    In simulation nothing executes the image, so any data will do. On the board it
    is the binary PlatformIO built for the application slot.
    """
    if bench.is_sil:
        return synthetic_image(version)
    name = "app_v" + "".join(str(part) for part in version)
    path = Path(__file__).resolve().parent.parent / "firmware" / ".pio" / "build" / name / "firmware.bin"
    if not path.exists():
        raise FileNotFoundError(f"{path}: build it with  pio run -d firmware -e {name}")
    return path.read_bytes()


class Updater:
    def __init__(self, bench):
        self.bench = bench
        self.tester = bench.tester
        self.block_size = None

    def enter(self):
        """Programming session. Returns once the bootloader reports it."""
        self.tester.change_session(PROGRAMMING_SESSION)
        self.bench.wait_for_boot(lambda boot: boot.session == PROGRAMMING_SESSION, 3000)

    def check_preconditions(self, version):
        self.tester.start_routine(ROUTINE_CHECK_PRECONDITIONS, data=bytes(version))

    def request_download(self, size, address=APP_ADDRESS):
        location = MemoryLocation(address, size, address_format=32, memorysize_format=32)
        response = self.tester.request_download(location)
        self.block_size = response.service_data.max_length - 2
        return self.block_size

    def blocks(self, image):
        return [image[i : i + self.block_size] for i in range(0, len(image), self.block_size)]

    def transfer(self, image, corrupt_block=None, stop_after=None):
        """Send the image. Faults: flip a bit in one block, or stop after some blocks.

        Returns True when every block was sent.
        """
        for index, block in enumerate(self.blocks(image)):
            if stop_after is not None and index >= stop_after:
                return False
            if index == corrupt_block:
                block = bytes([block[0] ^ 0x01]) + block[1:]
            self.tester.transfer_data((index + 1) & 0xFF, block)
        return True

    def finish(self, image):
        self.tester.request_transfer_exit()
        crc = zlib.crc32(image).to_bytes(4, "big")
        self.tester.start_routine(ROUTINE_CHECK_AND_ACTIVATE, data=crc)

    def install(self, image, version, corrupt_block=None, stop_after=None):
        """The whole sequence up to activation. Returns False when it was cut short on purpose."""
        self.enter()
        self.check_preconditions(version)
        self.request_download(len(image))
        if not self.transfer(image, corrupt_block=corrupt_block, stop_after=stop_after):
            return False
        self.finish(image)
        return True

    def erase_application(self):
        """Test builds of the bootloader only: back to an ECU without an application."""
        self.enter()
        self.tester.start_routine(ROUTINE_ERASE_APPLICATION)


def main():
    from bench.hil import HilBench

    parser = argparse.ArgumentParser(description="Install an application image over CAN.")
    parser.add_argument("--can-interface", default="slcan")
    parser.add_argument("--can-channel", required=True)
    parser.add_argument("--bitrate", type=int, default=500000)
    parser.add_argument("--image", required=True, help="application binary linked for the application slot")
    parser.add_argument("--version", required=True, help="for example 1.0.0")
    args = parser.parse_args()

    with open(args.image, "rb") as handle:
        image = handle.read()
    version = tuple(int(part) for part in args.version.split("."))
    bench = HilBench(args.can_interface, args.can_channel, args.bitrate)
    bench.restbus.sending = False
    try:
        updater = Updater(bench)
        start = bench.now_ms
        updater.install(image, version)
        print(f"installed {len(image)} bytes, version {args.version}, in {(bench.now_ms - start) / 1000:.1f} s")
        bench.tester.ecu_reset(1)
        bench.restbus.sending = True
        bench.wait_for(lambda status: True, 3000, "status of the new application")
        print(f"application running, version {bench.read(m.DID_SW_VERSION)}")
    finally:
        bench.close()


if __name__ == "__main__":
    main()
