#!/usr/bin/env python3
"""
MX Master 4 Haptics GUI
pip install customtkinter hidapi
"""

import json
import logging
import sys
import threading
import time
from pathlib import Path

import customtkinter as ctk

for _candidate in [Path(__file__).parent, Path(__file__).parent / "src"]:
    if (_candidate / "mx_master_4.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from mx_master_4 import ConnectionType, MXMaster4  # noqa: E402

CONFIG_FILE = Path.home() / ".mx4haptics" / "config.json"

PATTERN_NAMES = {
    0:  "Soft Click",    1:  "Double Click",  2:  "Triple Click",
    3:  "Long Buzz",     4:  "Short Pulse",   5:  "Rapid Burst",
    6:  "Wave",          7:  "Deep Thump",    8:  "Light Tap",
    9:  "Alert",         10: "Success",       11: "Error",
    12: "Notification",  13: "Gentle Pulse",  14: "Strong Buzz",
}

PAT_OPTIONS = [f"{name}  (#{idx})" for idx, name in PATTERN_NAMES.items()]

CONN_LABELS = {
    ConnectionType.Receiver: ("USB Receiver", "#f59e0b"),
    ConnectionType.USB:      ("USB Cable",    "#3b82f6"),
    ConnectionType.BT:       ("Bluetooth",    "#8b5cf6"),
    ConnectionType.Unknown:  ("Unknown",      "gray"),
}

DEFAULT_CONFIG = {
    "appearance":       "Dark",
    "custom_patterns":  [],   # [{name, steps: [{pattern, delay_ms}]}]
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── Device manager ────────────────────────────────────────────────────────────

class DeviceManager:
    def __init__(self):
        self._device   = None
        self._handle   = None
        self._lock     = threading.Lock()
        self.conn_type = None

    def connect(self):
        with self._lock:
            if self._handle:
                try:
                    self._device.__exit__(None, None, None)
                except Exception:
                    pass
                self._handle = None
            found = MXMaster4.find()
            if found:
                self._device   = found
                self._handle   = found.__enter__()
                self.conn_type = found.connection
                return True, found.connection
            return False, None

    def disconnect(self):
        with self._lock:
            if self._device and self._handle:
                try:
                    self._device.__exit__(None, None, None)
                except Exception:
                    pass
                self._handle = None

    def trigger(self, pattern: int):
        with self._lock:
            if self._handle:
                try:
                    self._handle.trigger_haptic(pattern)
                except Exception as e:
                    logging.error("Haptic failed: %s", e)

    def play_sequence(self, steps: list[dict], stop_event: threading.Event):
        """Play a list of {pattern, delay_ms} steps in a background thread."""
        for step in steps:
            if stop_event.is_set():
                break
            self.trigger(step["pattern"])
            stop_event.wait(timeout=step["delay_ms"] / 1000)


# ── Main window ───────────────────────────────────────────────────────────────

class MX4App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg    = load_config()
        self.device = DeviceManager()
        self._seq_stop = threading.Event()   # cancels any running sequence

        ctk.set_appearance_mode(self.cfg.get("appearance", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title("MX Master 4 Haptics")
        self.geometry("660x700")
        self.minsize(600, 500)
        self.resizable(True, True)
        self._build()
        self._connect()
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, height=56, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        ctk.CTkLabel(header, text="MX Master 4  Haptics",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     ).grid(row=0, column=0, padx=20, sticky="w")

        sf = ctk.CTkFrame(header, fg_color="transparent")
        sf.grid(row=0, column=1, sticky="e", padx=10)
        self._dot        = ctk.CTkLabel(sf, text="●", text_color="gray",
                                         font=ctk.CTkFont(size=14))
        self._dot.grid(row=0, column=0, padx=(0, 5))
        self._status_lbl = ctk.CTkLabel(sf, text="Not connected",
                                         text_color="gray",
                                         font=ctk.CTkFont(size=13))
        self._status_lbl.grid(row=0, column=1)
        self._conn_lbl   = ctk.CTkLabel(sf, text="",
                                         font=ctk.CTkFont(size=12),
                                         text_color="gray")
        self._conn_lbl.grid(row=0, column=2, padx=(8, 0))

        ctk.CTkButton(header, text="Reconnect", width=100, height=30,
                      command=self._connect,
                      ).grid(row=0, column=2, padx=10)
        ctk.CTkOptionMenu(header, values=["Dark", "Light", "System"],
                          width=90, height=30, command=self._set_appearance,
                          ).grid(row=0, column=3, padx=(0, 16))

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        body.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")

        # ── Pattern Lab ───────────────────────────────────────────────────────
        ctk.CTkLabel(body, text="Pattern Lab",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ctk.CTkLabel(body,
                     text="Tap a button to feel the haptic. Names are approximate.",
                     text_color="gray", justify="left",
                     ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        self._pat_btns: dict[int, ctk.CTkButton] = {}
        for i, (idx, name) in enumerate(PATTERN_NAMES.items()):
            col   = i % 3
            row_n = (i // 3) + 2
            btn   = ctk.CTkButton(
                body, text=f"{name}\n#{idx}", height=68, corner_radius=10,
                font=ctk.CTkFont(size=13),
                fg_color=("gray82", "gray23"),
                hover_color=("gray72", "gray33"),
                text_color=("gray10", "gray90"),
                command=lambda p=idx: self._fire(p),
            )
            btn.grid(row=row_n, column=col, padx=5, pady=5, sticky="ew")
            self._pat_btns[idx] = btn

        self._pat_last_row = ((len(PATTERN_NAMES) - 1) // 3) + 3

        # ── Custom Patterns ───────────────────────────────────────────────────
        div_row = self._pat_last_row
        ctk.CTkFrame(body, height=1, fg_color=("gray80", "gray30")).grid(
            row=div_row, column=0, columnspan=3, sticky="ew", pady=18)

        ctk.CTkLabel(body, text="Custom Patterns",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     ).grid(row=div_row + 1, column=0, columnspan=2,
                            sticky="w", pady=(0, 4))
        ctk.CTkLabel(body,
                     text="Chain patterns together with delays to make your own sequence.",
                     text_color="gray", justify="left",
                     ).grid(row=div_row + 2, column=0, columnspan=3,
                            sticky="w", pady=(0, 12))

        # Saved patterns list
        self._saved_frame = ctk.CTkFrame(body, fg_color="transparent")
        self._saved_frame.grid(row=div_row + 3, column=0, columnspan=3,
                               sticky="ew", pady=(0, 10))
        self._saved_frame.grid_columnconfigure(0, weight=1)
        self._refresh_saved()

        ctk.CTkButton(body, text="＋ New Custom Pattern", height=38,
                      command=self._open_builder,
                      ).grid(row=div_row + 4, column=0, columnspan=3,
                             sticky="ew", pady=(0, 4))

    # ── Saved patterns ─────────────────────────────────────────────────────────

    def _refresh_saved(self):
        for w in self._saved_frame.winfo_children():
            w.destroy()

        patterns = self.cfg.get("custom_patterns", [])
        if not patterns:
            ctk.CTkLabel(self._saved_frame, text="No custom patterns saved yet.",
                         text_color="gray").grid(row=0, column=0, sticky="w", pady=4)
            return

        for i, cp in enumerate(patterns):
            row = ctk.CTkFrame(self._saved_frame, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)

            # Name + step summary
            steps     = cp.get("steps", [])
            step_desc = "  →  ".join(
                f"{PATTERN_NAMES.get(s['pattern'], s['pattern'])} ({s['delay_ms']} ms)"
                for s in steps
            )
            ctk.CTkLabel(row, text=cp.get("name", "Unnamed"),
                         font=ctk.CTkFont(size=14, weight="bold"),
                         ).grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")
            ctk.CTkLabel(row, text=step_desc or "(empty)",
                         text_color="gray", font=ctk.CTkFont(size=11),
                         wraplength=500, justify="left",
                         ).grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

            btn_frame = ctk.CTkFrame(row, fg_color="transparent")
            btn_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=8)

            ctk.CTkButton(btn_frame, text="▶ Play", width=70, height=30,
                          command=lambda s=steps: self._play_sequence(s),
                          ).grid(row=0, column=0, padx=(0, 6))
            ctk.CTkButton(btn_frame, text="Edit", width=55, height=30,
                          fg_color="transparent",
                          border_width=1,
                          command=lambda idx=i: self._open_builder(idx),
                          ).grid(row=0, column=1, padx=(0, 6))
            ctk.CTkButton(btn_frame, text="✕", width=32, height=30,
                          fg_color="transparent",
                          hover_color=("gray70", "gray30"),
                          command=lambda idx=i: self._delete_pattern(idx),
                          ).grid(row=0, column=2)

    def _delete_pattern(self, idx: int):
        self.cfg["custom_patterns"].pop(idx)
        save_config(self.cfg)
        self._refresh_saved()

    # ── Sequence playback ─────────────────────────────────────────────────────

    def _play_sequence(self, steps: list[dict]):
        self._seq_stop.set()
        self._seq_stop = threading.Event()
        stop = self._seq_stop
        threading.Thread(
            target=self.device.play_sequence, args=(steps, stop), daemon=True
        ).start()

    # ── Builder window ────────────────────────────────────────────────────────

    def _open_builder(self, edit_idx: int | None = None):
        """Open the pattern builder in a Toplevel window."""
        existing = None
        if edit_idx is not None:
            existing = self.cfg["custom_patterns"][edit_idx]

        win = ctk.CTkToplevel(self)
        win.title("Custom Pattern Builder")
        win.geometry("560x560")
        win.resizable(True, True)
        win.grab_set()   # modal
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)

        # Name row
        name_frame = ctk.CTkFrame(win, fg_color="transparent")
        name_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        name_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(name_frame, text="Name:", width=50).grid(row=0, column=0)
        name_var = ctk.StringVar(value=existing["name"] if existing else "My Pattern")
        ctk.CTkEntry(name_frame, textvariable=name_var).grid(
            row=0, column=1, sticky="ew", padx=(10, 0))

        # Help text
        ctk.CTkLabel(win,
                     text="Each step fires a pattern then waits for the delay before the next one.",
                     text_color="gray", font=ctk.CTkFont(size=12),
                     ).grid(row=1, column=0, padx=20, sticky="w", pady=(0, 8))

        # Steps scroll area
        steps_scroll = ctk.CTkScrollableFrame(win)
        steps_scroll.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
        steps_scroll.grid_columnconfigure(0, weight=1)

        step_rows: list[dict] = []   # [{pattern_var, delay_var, frame}]

        def add_step(pattern: int = 0, delay_ms: int = 300):
            idx    = len(step_rows)
            sf     = ctk.CTkFrame(steps_scroll, corner_radius=8)
            sf.grid(row=idx, column=0, sticky="ew", pady=4)
            sf.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(sf, text=f"Step {idx + 1}",
                         font=ctk.CTkFont(weight="bold"), width=52,
                         ).grid(row=0, column=0, padx=(12, 8), pady=10)

            pat_var = ctk.StringVar(value=PAT_OPTIONS[pattern])
            ctk.CTkOptionMenu(sf, values=PAT_OPTIONS, variable=pat_var,
                              width=200,
                              ).grid(row=0, column=1, pady=10, sticky="w")

            ctk.CTkLabel(sf, text="Delay:").grid(row=0, column=2, padx=(12, 4))

            delay_var = ctk.StringVar(value=str(delay_ms))
            ctk.CTkEntry(sf, textvariable=delay_var, width=68,
                         ).grid(row=0, column=3, pady=10)
            ctk.CTkLabel(sf, text="ms").grid(row=0, column=4, padx=(4, 4))

            # Test this single step
            def test_step(pv=pat_var):
                p = PAT_OPTIONS.index(pv.get()) if pv.get() in PAT_OPTIONS else 0
                threading.Thread(target=lambda: self.device.trigger(p),
                                 daemon=True).start()

            ctk.CTkButton(sf, text="▶", width=30,
                          command=test_step,
                          ).grid(row=0, column=5, padx=(4, 4))

            def remove(frame=sf, row_dict=None):
                frame.destroy()
                if row_dict in step_rows:
                    step_rows.remove(row_dict)
                _reindex()

            rm_btn = ctk.CTkButton(sf, text="✕", width=30,
                                   fg_color="transparent",
                                   hover_color=("gray70", "gray30"),
                                   )
            rm_btn.grid(row=0, column=6, padx=(0, 8))
            entry = {"frame": sf, "pattern": pat_var, "delay": delay_var}
            rm_btn.configure(command=lambda e=entry: remove(e["frame"], e))
            step_rows.append(entry)

        def _reindex():
            """Renumber step labels after a deletion."""
            for i, row in enumerate(step_rows):
                if row["frame"].winfo_exists():
                    for w in row["frame"].winfo_children():
                        if isinstance(w, ctk.CTkLabel) and w.cget("text").startswith("Step"):
                            w.configure(text=f"Step {i + 1}")

        # Load existing steps or add a default first step
        if existing and existing.get("steps"):
            for s in existing["steps"]:
                add_step(s["pattern"], s["delay_ms"])
        else:
            add_step(0, 300)

        # Bottom buttons
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        bottom.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(bottom, text="＋ Add Step", width=110,
                      command=add_step,
                      ).grid(row=0, column=0)

        def play_all():
            steps = _collect_steps()
            if steps:
                self._play_sequence(steps)

        ctk.CTkButton(bottom, text="▶ Play All", width=100,
                      command=play_all,
                      ).grid(row=0, column=2, padx=(0, 8))

        def _collect_steps():
            steps = []
            for row in step_rows:
                if not row["frame"].winfo_exists():
                    continue
                pat_str = row["pattern"].get()
                pat     = PAT_OPTIONS.index(pat_str) if pat_str in PAT_OPTIONS else 0
                try:
                    delay = max(0, int(row["delay"].get()))
                except ValueError:
                    delay = 300
                steps.append({"pattern": pat, "delay_ms": delay})
            return steps

        def save():
            steps = _collect_steps()
            name  = name_var.get().strip() or "Unnamed"
            entry = {"name": name, "steps": steps}
            if edit_idx is not None:
                self.cfg["custom_patterns"][edit_idx] = entry
            else:
                self.cfg.setdefault("custom_patterns", []).append(entry)
            save_config(self.cfg)
            self._refresh_saved()
            win.destroy()

        ctk.CTkButton(bottom, text="Save", width=90,
                      command=save,
                      ).grid(row=0, column=3)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _connect(self):
        self._set_status(False, "Connecting…", "gray", "")
        def do():
            ok, conn = self.device.connect()
            if ok and conn is not None:
                label, color = CONN_LABELS.get(conn, ("Connected", "#22c55e"))
                self.after(0, lambda: self._set_status(
                    True, "Connected", color, f"via {label}"))
            else:
                self.after(0, lambda: self._set_status(
                    False, "Not connected", "gray", ""))
        threading.Thread(target=do, daemon=True).start()

    def _set_status(self, ok: bool, text: str, color: str, conn: str):
        self._dot.configure(text_color=color)
        self._status_lbl.configure(text=text, text_color=color)
        self._conn_lbl.configure(text=conn, text_color=color)

    def _fire(self, pattern: int):
        btn = self._pat_btns.get(pattern)
        if btn:
            btn.configure(fg_color="#3b82f6", text_color="white")
            self.after(350, lambda: btn.configure(
                fg_color=("gray82", "gray23"),
                text_color=("gray10", "gray90"),
            ))
        threading.Thread(
            target=lambda: self.device.trigger(pattern), daemon=True).start()

    def _set_appearance(self, value: str):
        ctk.set_appearance_mode(value.lower())
        self.cfg["appearance"] = value
        save_config(self.cfg)

    def _quit(self):
        self._seq_stop.set()
        self.device.disconnect()
        self.destroy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = MX4App()
    app.mainloop()
