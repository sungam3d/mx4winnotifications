"""
diagnose.py v4 — focused haptic testing across all paths and formats.

IMPORTANT: Switch the mouse connection button (bottom of mouse) to the
Bolt receiver slot BEFORE running this, if it isn't already.

python diagnose.py
"""
import time, hid

LOGITECH_VID = 0x046D

all_devs = hid.enumerate(LOGITECH_VID)

# ── Helper ────────────────────────────────────────────────────────────────────
def open_path(path):
    d = hid.device()
    d.open_path(path)
    d.set_nonblocking(False)
    return d

def wr(dev, label, pkt, timeout_ms=500):
    try:
        dev.write(pkt)
    except Exception as e:
        print(f"  WRITE ERR [{label}]: {e}")
        return None
    resp = dev.read(20, timeout_ms=timeout_ms)
    data = bytes(resp) if resp else None
    ok   = "(no response)" if not data else data.hex(' ')
    print(f"  {label:45s}  TX: {pkt.hex(' ')}  RX: {ok}")
    return data

def find_path(usage_page, iface=None, col=None):
    for d in all_devs:
        if d["usage_page"] != usage_page:
            continue
        if iface is not None and d.get("interface_number") != iface:
            continue
        if col is not None and f"Col{col:02d}" not in d["path"].decode():
            continue
        return d["path"]
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — Bolt receiver Col01 (known working path)
# ══════════════════════════════════════════════════════════════════════════════
col01 = find_path(0xFF00, iface=2, col=1)
print(f"=== Part 1: Bolt receiver Col01 ===")
print(f"Path: {col01}\n")

if col01:
    dev = open_path(col01)

    # Try different ASE (function index) variants for the haptic feature
    # Maybe function 0 or 1 works even if function 4 (0x4E) says Unsupported
    print("-- Haptic with different function indices (dev_idx=0x01) --")
    print("WATCH/FEEL the mouse during this section!\n")
    for ase in [0x01, 0x11, 0x21, 0x31, 0x41]:
        for pattern in [0, 1, 2]:
            pkt = bytes([0x10, 0x01, 0x0B, ase, pattern, 0x00, 0x00])
            wr(dev, f"haptic ase=0x{ase:02X} pat={pattern}", pkt, timeout_ms=300)
        time.sleep(0.3)

    print()

    # Try with long report (0x11) — some Bolt devices require long format
    print("-- Haptic as long report 0x11 (dev_idx=0x01) --")
    print("WATCH/FEEL the mouse during this section!\n")
    for pattern in range(5):
        pkt = bytes([0x11, 0x01, 0x0B, 0x4E, pattern, 0x00, 0x00,
                     0,0,0,0,0,0,0,0,0,0,0,0,0])  # 20 bytes
        wr(dev, f"long haptic pat={pattern}", pkt, timeout_ms=300)
        time.sleep(0.3)

    print()

    # Try higher device indices — Bolt might use a different slot number
    print("-- Scanning device_idx 0x00-0x0F for the mouse --")
    for dev_idx in range(0x10):
        pkt  = bytes([0x10, dev_idx, 0x00, 0x01, 0x00, 0x01, 0x00])
        resp = wr(dev, f"IRoot.GetFeature(0x0001) dev={dev_idx:#04x}", pkt, timeout_ms=400)
        if resp and resp[2] != 0x8F:
            print(f"  *** LIVE DEVICE at dev_idx=0x{dev_idx:02X}! ***")

    dev.close()
    print()


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — 0xFFBC interface (Bolt proprietary channel)
# ══════════════════════════════════════════════════════════════════════════════
ffbc = find_path(0xFFBC)
print(f"=== Part 2: 0xFFBC path (Bolt proprietary) ===")
print(f"Path: {ffbc}\n")

if ffbc:
    try:
        dev2 = open_path(ffbc)

        print("-- Ping attempts --")
        for dev_idx in [0x00, 0x01, 0xFF]:
            for ase in [0x01, 0x11]:
                pkt = bytes([0x10, dev_idx, 0x00, ase, 0x00, 0x00, 0xAA])
                wr(dev2, f"ping dev={dev_idx:#04x} ase={ase:#04x}", pkt)

        print()
        print("-- Haptic via 0xFFBC --")
        print("WATCH/FEEL the mouse!\n")
        for dev_idx in [0x00, 0x01, 0xFF]:
            for pattern in [0, 1]:
                pkt = bytes([0x10, dev_idx, 0x0B, 0x4E, pattern, 0x00, 0x00])
                wr(dev2, f"haptic dev={dev_idx:#04x} pat={pattern}", pkt, timeout_ms=300)
                time.sleep(0.4)

        dev2.close()
    except Exception as e:
        print(f"  Could not open 0xFFBC path: {e}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — Bluetooth direct (0xFF43) — fire and forget, no read
# ══════════════════════════════════════════════════════════════════════════════
bt_path = find_path(0xFF43)
print(f"=== Part 3: Bluetooth HID++ direct (0xFF43) ===")
print(f"Path: {bt_path}\n")
print("NOTE: Windows blocks reads on BT HID, so no RX shown.")
print("      FEEL THE MOUSE — if it vibrates here the BT path works!\n")

if bt_path:
    try:
        bt = hid.device()
        bt.open_path(bt_path)
        bt.set_nonblocking(True)   # non-blocking — we never try to read

        for pattern in range(15):
            pkt = bytes([0x10, 0xFF, 0x0B, 0x4E, pattern, 0x00, 0x00])
            try:
                bt.write(pkt)
                print(f"  BT write pattern {pattern:2d}: {pkt.hex(' ')}  (sent)")
            except Exception as e:
                print(f"  BT write pattern {pattern:2d}: FAILED — {e}")
            time.sleep(1.0)

        # Also try long report via BT
        print()
        print("  -- BT long report (0x11) patterns 0-4 --")
        for pattern in range(5):
            pkt = bytes([0x11, 0xFF, 0x0B, 0x4E, pattern,
                         0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
            try:
                bt.write(pkt)
                print(f"  BT long pattern {pattern}: {pkt[:8].hex(' ')}...  (sent)")
            except Exception as e:
                print(f"  BT long pattern {pattern}: FAILED — {e}")
            time.sleep(1.0)

        bt.close()
    except Exception as e:
        print(f"  Could not open BT path: {e}")
    print()

print("Done — paste the full output and tell us which (if any) sections made the mouse vibrate.")
