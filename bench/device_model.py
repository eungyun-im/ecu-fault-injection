"""A whole ECU on the PC: bootloader, application slot and the flash they share.

The bootloader and the application are the real C code. Modeled are the
things an update depends on:

    flash       the application slot and the info page. A write only succeeds
                on erased bytes, as on the MCU, so a bootloader that programs
                without erasing is caught here.
    start       at every reset the bootloader runs first and decides whether
                the application may start
    reset       loses RAM, keeps flash and the word in the backup register

The model cannot execute what is in the application slot. When the bootloader
starts the application, the model runs the application library whose version
matches the info page. The image a test installs is therefore arbitrary data:
the bootloader treats it exactly like a real one, and that is what is tested.
"""

import ctypes

from bench import ecu_lib
from bench import messages as m
from bench.ecu_model import EcuModel

APP_MAX_SIZE = 0x1B800
PAGE_SIZE = 2048
INFO_SIZE = ctypes.sizeof(ecu_lib.BootInfo)
ERASED = 0xFF


class DeviceModel:
    def __init__(self, transmit):
        """transmit(can_id, data) is called for every frame the ECU sends."""
        self._transmit = transmit
        self._boot = ecu_lib.load_boot()
        self.flash = (ctypes.c_uint8 * APP_MAX_SIZE)(*([ERASED] * APP_MAX_SIZE))
        self.info = bytearray([ERASED] * INFO_SIZE)
        self.nv = 0
        self.flash_errors = []
        self.resets = []
        self.mode = None
        self.app = None
        self._apps = {}
        self._port = ecu_lib.BootPort(
            can_send=ecu_lib.CAN_SEND(self._can_send),
            flash_app=ecu_lib.FLASH_APP(lambda: ctypes.addressof(self.flash)),
            flash_erase_page=ecu_lib.ERASE_PAGE(self._erase_page),
            flash_write=ecu_lib.FLASH_WRITE(self._write),
            info_read=ecu_lib.INFO_READ(self._info_read),
            info_erase=ecu_lib.BOOL_QUERY(self._info_erase),
            info_write=ecu_lib.INFO_WRITE(self._info_write),
            nv_read=ecu_lib.GET_U32(lambda: self.nv),
            nv_write=ecu_lib.SET_U32(self._nv_write),
            system_reset=ecu_lib.ACTION(self._request_reset),
        )
        self.power_on(0)

    # Life cycle

    def power_on(self, now_ms):
        """Cold start: the backup register is lost, the flash is not."""
        self.nv = 0
        self._start(now_ms, m.RESET_POWER_ON)

    def reset(self, now_ms):
        """Reset at any moment, as a supply glitch or the reset pin causes it."""
        if self.app is not None:
            self.nv = self.app.nv
        self._start(now_ms, m.RESET_PIN)

    def _start(self, now_ms, cause):
        self.now_ms = now_ms
        self.resets.append(cause)
        self._reset_requested = False
        if self._boot.boot_start(ctypes.byref(self._port)):
            self.mode, self.app = "bootloader", None
            self._boot.boot_init(ctypes.byref(self._port), now_ms)
        else:
            self.mode = "application"
            self.app = self._application(tuple(self.info[12:15]))
            self.app.nv = self.nv
            self.app.start(now_ms, cause)

    def _application(self, version):
        if version not in self._apps:
            variant = "app_v" + "".join(str(part) for part in version)
            app = EcuModel(self._transmit, variant)
            app.on_reset = self._application_reset
            self._apps[version] = app
        return self._apps[version]

    def _application_reset(self, cause):
        self.nv = self.app.nv
        self._start(self.now_ms, cause)

    @property
    def output(self):
        return self.app.output if self.app is not None else False

    # Called by the bench

    def receive(self, can_id, data, now_ms):
        self.now_ms = now_ms
        if self.app is not None:
            self.app.receive(can_id, data, now_ms)
        else:
            frame = ecu_lib.CanFrame(can_id, len(data), (ctypes.c_uint8 * 8)(*data))
            self._boot.boot_on_frame(ctypes.byref(frame), now_ms)

    def tick(self, now_ms):
        """One millisecond of ECU time."""
        self.now_ms = now_ms
        if self.app is not None:
            self.app.tick(now_ms)
        else:
            self._boot.boot_step(now_ms)
            if self._reset_requested:
                self._start(now_ms, m.RESET_SOFTWARE)

    def corrupt_flash(self, offset, mask=0x01):
        """Change bits of the installed application, as failing flash would."""
        self.flash[offset] ^= mask

    # Called by the bootloader

    def _can_send(self, frame_pointer):
        frame = frame_pointer.contents
        self._transmit(frame.id, bytes(frame.data[: frame.dlc]))
        return True

    def _erase_page(self, page):
        start = page * PAGE_SIZE
        if start + PAGE_SIZE > APP_MAX_SIZE:
            self.flash_errors.append(f"erase of page {page} outside the application slot")
            return False
        ctypes.memset(ctypes.addressof(self.flash) + start, ERASED, PAGE_SIZE)
        return True

    def _write(self, offset, data, length):
        if offset % 8 or length % 8 or offset + length > APP_MAX_SIZE:
            self.flash_errors.append(f"write of {length} bytes at {offset}: not aligned or out of range")
            return False
        if any(self.flash[offset + i] != ERASED for i in range(length)):
            self.flash_errors.append(f"write at {offset} to flash that was not erased")
            return False
        for i in range(length):
            self.flash[offset + i] = data[i]
        return True

    def _info_read(self, info_pointer):
        ctypes.memmove(info_pointer, bytes(self.info), INFO_SIZE)

    def _info_erase(self):
        self.info[:] = bytes([ERASED] * INFO_SIZE)
        return True

    def _info_write(self, info_pointer):
        if any(byte != ERASED for byte in self.info):
            self.flash_errors.append("write to an info page that was not erased")
            return False
        self.info[:] = ctypes.string_at(info_pointer, INFO_SIZE)
        return True

    def _nv_write(self, value):
        self.nv = value

    def _request_reset(self):
        self._reset_requested = True
