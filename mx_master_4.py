import logging
import time
from enum import IntEnum

import hid  # pip install hidapi

LOGITECH_VID     = 0x046D
FEATURE_ID_HAPTIC = 0x0B4E

# HID++ report IDs
REPORT_SHORT = 0x10   #  7 bytes total (not used for haptic on BT)
REPORT_LONG  = 0x11   # 20 bytes total — required for haptic via Bluetooth

# Device index for direct Bluetooth connection
BT_DEVICE_IDX = 0xFF


class ConnectionType(IntEnum):
    Unknown  = 0
    Receiver = 1
    USB      = 2
    BT       = 3


class MXMaster4:

    def __init__(self, path: bytes, device_idx: int,
                 connection: ConnectionType = ConnectionType.Unknown):
        self.path        = path
        self.device_idx  = device_idx
        self.connection  = connection
        self._device     = None

    # ── Discovery ─────────────────────────────────────────────────────────────

    @classmethod
    def find(cls):
        all_devices = hid.enumerate(LOGITECH_VID)

        if not all_devices:
            logging.warning("No Logitech HID devices found.")
            return None

        logging.info("── Logitech devices ────────────────────────────────────")
        for d in all_devices:
            logging.info(
                "  %-32s  PID=%04X  page=0x%04X  iface=%s",
                d.get("product_string", "?"),
                d["product_id"],
                d["usage_page"],
                d.get("interface_number", "?"),
            )
        logging.info("────────────────────────────────────────────────────────")

        # 1. Bluetooth HID++ (page 0xFF43) — direct connection, long reports work
        for d in all_devices:
            if d["usage_page"] == 0xFF43:
                logging.info("Found via Bluetooth: %s", d.get("product_string"))
                return cls(d["path"], BT_DEVICE_IDX, ConnectionType.BT)

        # 2. Bolt/Unifying receiver — Col01 is the responsive interface
        ff00 = [d for d in all_devices if d["usage_page"] == 0xFF00]
        # Probe each path; take the first that gives any response
        for d in ff00:
            if cls._path_responds(d["path"]):
                logging.info("Found via USB receiver: %s", d.get("product_string"))
                return cls(d["path"], 0x01, ConnectionType.Receiver)

        # 3. Direct USB cable fallback
        for iface in (1, 2, 0):
            for d in ff00:
                if d.get("interface_number") == iface:
                    logging.info("Found via USB cable (iface %d): %s",
                                 iface, d.get("product_string"))
                    return cls(d["path"], BT_DEVICE_IDX, ConnectionType.USB)

        logging.error("No MX Master 4 found.")
        return None

    @staticmethod
    def _path_responds(path: bytes) -> bool:
        """Return True if this HID path gives any reply to a test packet."""
        try:
            d = hid.device()
            d.open_path(path)
            d.set_nonblocking(False)
            d.write(bytes([0x10, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00]))
            resp = d.read(20, timeout_ms=500)
            d.close()
            return bool(resp)
        except Exception:
            return False

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        try:
            self._device = hid.device()
            self._device.open_path(self.path)
            self._device.set_nonblocking(True)   # fire-and-forget; never block on read
        except Exception as e:
            raise OSError(
                f"Could not open device ({self.connection.name}): {e}\n"
                f"Try running as Administrator."
            ) from e
        logging.info("Opened %s", self.connection.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    # ── Haptic trigger ────────────────────────────────────────────────────────

    def trigger_haptic(self, pattern: int):
        """
        Send a haptic pattern.

        Uses a 20-byte long report (0x11) — confirmed working via Bluetooth.
        Fire-and-forget: no response is expected or waited for.

        packet layout:
          [0]    0x11          — long HID++ report ID
          [1]    device_idx   — 0xFF for direct BT/USB
          [2]    feat_hi      — 0x0B  (high byte of feature ID 0x0B4E)
          [3]    feat_lo      — 0x4E  (low byte)
          [4]    pattern      — 0–14
          [5-19] 0x00 padding
        """
        if not self._device:
            raise RuntimeError("Device not open")

        hi  = (FEATURE_ID_HAPTIC >> 8) & 0xFF   # 0x0B
        lo  =  FEATURE_ID_HAPTIC & 0xFF          # 0x4E

        pkt = bytes([REPORT_LONG, self.device_idx, hi, lo, pattern & 0xFF]
                    + [0x00] * 15)               # pad to 20 bytes

        logging.debug("Haptic TX: %s", pkt.hex())
        try:
            self._device.write(pkt)
        except Exception as e:
            logging.error("Haptic write failed: %s", e)


# ── Demo ──────────────────────────────────────────────────────────────────────

def demo():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    mx = MXMaster4.find()
    if not mx:
        return
    with mx as dev:
        for i in range(15):
            logging.info("Pattern %d", i)
            dev.trigger_haptic(i)
            time.sleep(2)


if __name__ == "__main__":
    demo()
