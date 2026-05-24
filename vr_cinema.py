import tkinter as tk
from tkinter import messagebox
import threading
import time
import subprocess
import sys
import os

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import mss
    MSS_OK = True
except ImportError:
    MSS_OK = False

import json

def _get_config_path():
    # Works for: .py script, PyInstaller .exe, double-click, terminal
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = os.getcwd()
    return os.path.join(base, "vr_cinema_config.json")

CONFIG_PATH = _get_config_path()

def _load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[vr_cinema] config save failed: {e}  path={CONFIG_PATH}")
        return False

def get_display_count():
    try:
        from screeninfo import get_monitors
        return len(get_monitors())
    except:
        return 1

def get_monitors_info():
    """Return list of (mss_index, label) for every detected monitor.
    The mss_index is guaranteed correct by matching Win32 position to mss monitor position."""
    try:
        import mss as _mss
        with _mss.mss() as sct:
            # sct.monitors[0] = virtual combined screen, [1..N] = real monitors
            mss_monitors = sct.monitors[1:]

        if sys.platform == "win32":
            import ctypes
            DISPLAY_DEVICE_ACTIVE         = 0x00000001
            DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
            ENUM_CURRENT_SETTINGS         = 0xFFFFFFFF
            class DISPLAY_DEVICEW(ctypes.Structure):
                _fields_ = [
                    ("cb",           ctypes.c_ulong),
                    ("DeviceName",   ctypes.c_wchar * 32),
                    ("DeviceString", ctypes.c_wchar * 128),
                    ("StateFlags",   ctypes.c_ulong),
                    ("DeviceID",     ctypes.c_wchar * 128),
                    ("DeviceKey",    ctypes.c_wchar * 128),
                ]
            class DEVMODEW(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName",         ctypes.c_wchar * 32),
                    ("dmSpecVersion",        ctypes.c_ushort),
                    ("dmDriverVersion",      ctypes.c_ushort),
                    ("dmSize",               ctypes.c_ushort),
                    ("dmDriverExtra",        ctypes.c_ushort),
                    ("dmFields",             ctypes.c_ulong),
                    ("dmPositionX",          ctypes.c_long),
                    ("dmPositionY",          ctypes.c_long),
                    ("dmDisplayOrientation", ctypes.c_ulong),
                    ("dmDisplayFixedOutput", ctypes.c_ulong),
                    ("dmColor",              ctypes.c_short),
                    ("dmDuplex",             ctypes.c_short),
                    ("dmYResolution",        ctypes.c_short),
                    ("dmTTOption",           ctypes.c_short),
                    ("dmCollate",            ctypes.c_short),
                    ("dmFormName",           ctypes.c_wchar * 32),
                    ("dmLogPixels",          ctypes.c_ushort),
                    ("dmBitsPerPel",         ctypes.c_ulong),
                    ("dmPelsWidth",          ctypes.c_ulong),
                    ("dmPelsHeight",         ctypes.c_ulong),
                    ("dmDisplayFlags",       ctypes.c_ulong),
                    ("dmDisplayFrequency",   ctypes.c_ulong),
                ]
            user32 = ctypes.windll.user32
            win32_monitors = []
            i = 0
            while True:
                dd = DISPLAY_DEVICEW()
                dd.cb = ctypes.sizeof(dd)
                if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                    break
                i += 1
                if not (dd.StateFlags & DISPLAY_DEVICE_ACTIVE):
                    continue
                dm = DEVMODEW()
                dm.dmSize = ctypes.sizeof(DEVMODEW)
                if not user32.EnumDisplaySettingsW(dd.DeviceName, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
                    continue
                is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE)
                win32_monitors.append({
                    "x": dm.dmPositionX, "y": dm.dmPositionY,
                    "w": dm.dmPelsWidth,  "h": dm.dmPelsHeight,
                    "primary": is_primary
                })

            # Match each Win32 monitor to its mss index by screen position
            result = []
            mon_num = 1
            for wm in win32_monitors:
                mss_idx = None
                for j, mm in enumerate(mss_monitors):
                    if mm["left"] == wm["x"] and mm["top"] == wm["y"]:
                        mss_idx = j + 1  # 1-based mss index
                        break
                if mss_idx is None:
                    mss_idx = mon_num  # fallback
                label = f"Monitor {mon_num}  ({wm['w']}\u00d7{wm['h']})"
                if wm["primary"]:
                    label += "  [primary]"
                result.append((mss_idx, label))
                mon_num += 1
            return result if result else [(1, "Monitor 1")]
        else:
            from screeninfo import get_monitors
            monitors = get_monitors()
            result = []
            for i, m in enumerate(monitors):
                # Match by position to mss index
                mss_idx = i + 1
                for j, mm in enumerate(mss_monitors):
                    if mm["left"] == m.x and mm["top"] == m.y:
                        mss_idx = j + 1
                        break
                label = f"Monitor {i + 1}  ({m.width}\u00d7{m.height})"
                if getattr(m, 'is_primary', False):
                    label += "  [primary]"
                result.append((mss_idx, label))
            return result if result else [(1, "Monitor 1")]
    except:
        return [(1, "Monitor 1"), (2, "Monitor 2")]


class VRCinemaWindow:
    def __init__(self, parent_log):
        self.log = parent_log
        self.win = None
        self.running = False
        self.thread = None
        self.canvas = None
        self.show_grid = True
        self.show_crosshair = True
        self.source_monitor = 1
        self.custom_w = None   # None = use default ratio (80% of half-width)
        self.custom_h = None   # None = use default ratio (68% of height)

    def open(self):
        if self.win and self.win.winfo_exists():
            return
        self.win = tk.Toplevel()
        self.win.title("VR Cinema")
        self.win.configure(bg="black")
        self._position_on_output_monitor()
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-topmost", True)
        self.win.bind("<Escape>", lambda e: self.close())
        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.running = True
        if PIL_OK and MSS_OK:
            self.thread = threading.Thread(target=self._render_loop, daemon=True)
            self.thread.start()
        else:
            self.win.after(200, self._draw_placeholder)
        self.log("VR Cinema opened — press ESC to close")

    def _position_on_output_monitor(self):
        try:
            from screeninfo import get_monitors
            monitors = get_monitors()
            target = next((m for m in monitors if not getattr(m, 'is_primary', False)), None)
            if target is None:
                return
            self.win.geometry(f"1x1+{target.x}+{target.y}")
            self.win.update_idletasks()
        except Exception:
            pass

    def close(self):
        self.running = False
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.log("VR Cinema closed")

    def _get_cursor_pos_on_monitor(self, monitor):
        try:
            if sys.platform == "win32":
                import ctypes
                pt = ctypes.wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                rx = pt.x - monitor["left"]
                ry = pt.y - monitor["top"]
            else:
                from Xlib import display as Xdisplay
                d = Xdisplay.Display()
                root = d.screen().root
                data = root.query_pointer()._data
                rx = data["root_x"] - monitor["left"]
                ry = data["root_y"] - monitor["top"]
            if 0 <= rx < monitor["width"] and 0 <= ry < monitor["height"]:
                return (rx, ry)
        except Exception:
            pass
        return None

    def _draw_cursor_on_image(self, img, cx, cy):
        from PIL import ImageDraw as ID
        d = ID.Draw(img)
        pts = [
            (cx,      cy),
            (cx,      cy + 20),
            (cx + 4,  cy + 14),
            (cx + 10, cy + 24),
            (cx + 13, cy + 22),
            (cx + 7,  cy + 12),
            (cx + 14, cy + 9),
        ]
        d.polygon(pts, fill=(0, 0, 0))
        pts2 = [
            (cx + 1,  cy + 1),
            (cx + 1,  cy + 18),
            (cx + 4,  cy + 13),
            (cx + 10, cy + 22),
            (cx + 12, cy + 21),
            (cx + 7,  cy + 11),
            (cx + 13, cy + 8),
        ]
        d.polygon(pts2, fill=(255, 255, 255))

    def _render_loop(self):
        import mss
        with mss.mss() as sct:
            while self.running:
                try:
                    idx = max(1, min(self.source_monitor, len(sct.monitors) - 1))
                    monitor = sct.monitors[idx]
                    shot = sct.grab(monitor)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    if self.show_crosshair:
                        pos = self._get_cursor_pos_on_monitor(monitor)
                        if pos:
                            self._draw_cursor_on_image(img, pos[0], pos[1])
                    self.win.after(0, lambda i=img: self._draw_frame(i))
                    time.sleep(1 / 30)
                except Exception:
                    time.sleep(0.1)

    def _make_vignette(self, w, h):
        vig = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(vig)
        steps = 35
        for i in range(steps):
            alpha = int((i / steps) ** 1.8 * 240)
            m = i * (min(w, h) // (steps * 2))
            draw.rectangle([m, m, w - m, h - m], outline=(0, 0, 0, alpha))
        return vig

    def _draw_frame(self, img):
        if not self.running or not self.win.winfo_exists():
            return
        W = self.win.winfo_width()
        H = self.win.winfo_height()
        if W < 2 or H < 2:
            return
        half = W // 2
        sw = self.custom_w if self.custom_w is not None else int(half * 0.80)
        sh = self.custom_h if self.custom_h is not None else int(H * 0.68)
        sw = max(10, min(sw, half))
        sh = max(10, min(sh, H))
        sx = (half - sw) // 2
        sy = (H - sh) // 2
        img_r = img.resize((sw, sh), Image.LANCZOS)
        frame = Image.new("RGB", (W, H), (0, 0, 0))
        vig = self._make_vignette(half, H)
        for ex in [0, half]:
            frame.paste(img_r, (ex + sx, sy))
            if self.show_grid:
                frame.paste(vig, (ex, 0), vig)
        from PIL import ImageDraw as ID
        d = ID.Draw(frame)
        if self.show_grid:
            d.line([(half, 0), (half, H)], fill=(15, 15, 15), width=3)
        tk_img = ImageTk.PhotoImage(frame)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
        self.canvas._img = tk_img

    def _draw_placeholder(self):
        if not self.win or not self.win.winfo_exists():
            return
        self.win.update_idletasks()
        W = self.win.winfo_width() or 1080
        H = self.win.winfo_height() or 2388
        half = W // 2
        c = self.canvas
        c.delete("all")
        c.configure(bg="black")
        for ex in [0, half]:
            cx = ex + half // 2
            sw, sh = int(half * 0.78), int(H * 0.65)
            sx = ex + (half - sw) // 2
            sy = (H - sh) // 2
            c.create_rectangle(sx, sy, sx + sw, sy + sh, fill="#05050f",
                               outline="#00e5ff" if self.show_grid else "#05050f", width=1)
            c.create_text(cx, H // 2 - 30, text="\U0001f3ac", font=("Segoe UI Emoji", 36), fill="#00e5ff")
            c.create_text(cx, H // 2 + 20, text="VR CINEMA", font=("Courier New", 13, "bold"), fill="#00e5ff")
            c.create_text(cx, H // 2 + 48,
                          text="pip install Pillow mss\nfor live screen capture",
                          font=("Courier New", 9), fill="#223344", justify=tk.CENTER)
            if self.show_grid:
                for g in range(12, 0, -1):
                    alpha_hex = format(g * 8, '02x')
                    c.create_rectangle(sx - g*3, sy - g*2, sx + sw + g*3, sy + sh + g*2,
                                       outline=f"#00{alpha_hex}ff", width=1)
        if self.show_grid:
            c.create_line(half, 0, half, H, fill="#111122", width=3)
        c.create_text(W // 2, H - 20, text="ESC  to close", font=("Courier New", 8), fill="#1a1a33")


class VRCinemaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VR Cinema")
        self.root.resizable(False, False)
        self.root.configure(bg="#080810")
        self.cinema = VRCinemaWindow(self._log)
        self.display_count = 1
        self.monitoring = True
        self._cfg = _load_config()
        # Restore saved window position+size, or use default
        self.root.geometry(self._cfg.get("window_geometry", "440x760"))
        self._build_ui()
        # Restore saved display size from config
        if "display_w" in self._cfg and "display_h" in self._cfg:
            self.cinema.custom_w = self._cfg["display_w"]
            self.cinema.custom_h = self._cfg["display_h"]
        self._update_size_indicator()
        self._check_deps()
        self._refresh_displays()
        self._refresh_monitor_lists()
        threading.Thread(target=self._monitor_displays, daemon=True).start()

    def _build_ui(self):
        r = self.root
        hf = tk.Frame(r, bg="#080810")
        hf.pack(fill=tk.X, padx=24, pady=(24, 2))
        tk.Label(hf, text="VR", font=("Courier New", 30, "bold"), fg="#00e5ff", bg="#080810").pack(side=tk.LEFT)
        tk.Label(hf, text=" CINEMA", font=("Courier New", 30, "bold"), fg="#ffffff", bg="#080810").pack(side=tk.LEFT)
        tk.Label(r, text="Spacedesk  \u00b7  VR Box  \u00b7  Poco C65",
                 font=("Courier New", 9), fg="#282840", bg="#080810").pack(anchor=tk.W, padx=26)
        tk.Frame(r, bg="#141428", height=1).pack(fill=tk.X, padx=22, pady=14)

        # Status
        card = tk.Frame(r, bg="#0c0c1c", highlightbackground="#141428", highlightthickness=1)
        card.pack(fill=tk.X, padx=22, pady=(0, 12))
        row1 = tk.Frame(card, bg="#0c0c1c")
        row1.pack(fill=tk.X, padx=14, pady=(10, 2))
        tk.Label(row1, text="HEADSET STATUS", font=("Courier New", 8, "bold"), fg="#282840", bg="#0c0c1c").pack(side=tk.LEFT)
        tk.Button(row1, text="\u21bb refresh", font=("Courier New", 8), fg="#282840", bg="#0c0c1c",
                  activeforeground="#00e5ff", activebackground="#0c0c1c",
                  borderwidth=0, cursor="hand2", command=self._refresh_displays).pack(side=tk.RIGHT)
        dot_row = tk.Frame(card, bg="#0c0c1c")
        dot_row.pack(fill=tk.X, padx=14, pady=(2, 10))
        self.dot = tk.Label(dot_row, text="\u25cf", font=("Courier New", 11), fg="#ff3366", bg="#0c0c1c")
        self.dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(dot_row, text=" Connect Spacedesk on Poco C65",
                                    font=("Courier New", 9), fg="#333355", bg="#0c0c1c")
        self.status_lbl.pack(side=tk.LEFT)

        tk.Frame(r, bg="#141428", height=1).pack(fill=tk.X, padx=22, pady=(0, 10))

        # Cinema
        self.cinema_btn = tk.Button(r, text="\u25b6   LAUNCH VR CINEMA",
                                     font=("Courier New", 12, "bold"),
                                     fg="#00e5ff", bg="#001418",
                                     activeforeground="#fff", activebackground="#001e28",
                                     height=2, borderwidth=0, cursor="hand2",
                                     command=self._launch_cinema)
        self.cinema_btn.pack(fill=tk.X, padx=22, pady=(0, 6))
        tk.Label(r, text="Side-by-side cinema view for VR Box  \u00b7  ESC to close",
                 font=("Courier New", 8), fg="#1e1e36", bg="#080810").pack(padx=22, anchor=tk.W)

        tk.Frame(r, bg="#141428", height=1).pack(fill=tk.X, padx=22, pady=12)

        # Monitor Selector
        mon_card = tk.Frame(r, bg="#0c0c1c", highlightbackground="#141428", highlightthickness=1)
        mon_card.pack(fill=tk.X, padx=22, pady=(0, 10))

        mon_hdr = tk.Frame(mon_card, bg="#0c0c1c")
        mon_hdr.pack(fill=tk.X, padx=14, pady=(8, 4))
        tk.Label(mon_hdr, text="MONITOR ROUTING", font=("Courier New", 8, "bold"),
                 fg="#282840", bg="#0c0c1c").pack(side=tk.LEFT)
        tk.Button(mon_hdr, text="\u21bb", font=("Courier New", 9), fg="#282840", bg="#0c0c1c",
                  activeforeground="#00e5ff", activebackground="#0c0c1c",
                  borderwidth=0, cursor="hand2", command=self._refresh_monitor_lists).pack(side=tk.RIGHT)

        src_row = tk.Frame(mon_card, bg="#0c0c1c")
        src_row.pack(fill=tk.X, padx=14, pady=(0, 6))
        tk.Label(src_row, text="CAPTURE", font=("Courier New", 8), fg="#444466", bg="#0c0c1c",
                 width=8, anchor=tk.W).pack(side=tk.LEFT)
        self.src_var = tk.StringVar()
        self.src_menu = tk.OptionMenu(src_row, self.src_var, "Monitor 1")
        self.src_menu.config(font=("Courier New", 8), fg="#00e5ff", bg="#0c0c1c",
                             activeforeground="#fff", activebackground="#001418",
                             highlightthickness=0, borderwidth=0, width=30)
        self.src_menu["menu"].config(font=("Courier New", 8), fg="#00e5ff",
                                     bg="#0c0c1c", activebackground="#001418")
        self.src_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # PRIMARY indicator row
        pri_row = tk.Frame(mon_card, bg="#0c0c1c")
        pri_row.pack(fill=tk.X, padx=14, pady=(4, 10))
        tk.Label(pri_row, text="PRIMARY", font=("Courier New", 8), fg="#444466", bg="#0c0c1c",
                 width=8, anchor=tk.W).pack(side=tk.LEFT)
        # bordered box around the indicator value
        pri_box = tk.Frame(pri_row, bg="#0c0c1c",
                           highlightbackground="#ffaa00", highlightthickness=1)
        pri_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.pri_indicator = tk.Label(pri_box, text="detecting...",
                                      font=("Courier New", 8), fg="#ffaa00", bg="#0c0c1c",
                                      anchor=tk.W, padx=6, pady=2)
        self.pri_indicator.pack(fill=tk.X)

        self._monitor_map = {}

        # Display Size card
        size_card = tk.Frame(r, bg="#0c0c1c", highlightbackground="#141428", highlightthickness=1)
        size_card.pack(fill=tk.X, padx=22, pady=(0, 10))

        size_hdr = tk.Frame(size_card, bg="#0c0c1c")
        size_hdr.pack(fill=tk.X, padx=14, pady=(8, 4))
        tk.Label(size_hdr, text="DISPLAY SIZE", font=("Courier New", 8, "bold"),
                 fg="#282840", bg="#0c0c1c").pack(side=tk.LEFT)
        tk.Button(size_hdr, text="↻ default", font=("Courier New", 8), fg="#282840", bg="#0c0c1c",
                  activeforeground="#00e5ff", activebackground="#0c0c1c",
                  borderwidth=0, cursor="hand2", command=self._reset_display_size).pack(side=tk.RIGHT)

        spin_row = tk.Frame(size_card, bg="#0c0c1c")
        spin_row.pack(fill=tk.X, padx=14, pady=(0, 8))

        tk.Label(spin_row, text="W", font=("Courier New", 8), fg="#444466",
                 bg="#0c0c1c", width=2, anchor=tk.W).pack(side=tk.LEFT)
        self.size_w_var = tk.IntVar(value=self._cfg.get("display_w", 640))
        w_spin = tk.Spinbox(spin_row, from_=100, to=4000, increment=10,
                            textvariable=self.size_w_var, width=6,
                            font=("Courier New", 9), fg="#00e5ff", bg="#080810",
                            buttonbackground="#0c0c1c", relief=tk.FLAT,
                            highlightthickness=1, highlightbackground="#141428",
                            command=self._apply_display_size)
        w_spin.bind("<Return>", lambda e: self._apply_display_size())
        w_spin.bind("<FocusOut>", lambda e: self._apply_display_size())
        w_spin.pack(side=tk.LEFT, padx=(2, 4))
        tk.Label(spin_row, text="px", font=("Courier New", 7), fg="#282840",
                 bg="#0c0c1c").pack(side=tk.LEFT, padx=(0, 14))

        tk.Label(spin_row, text="H", font=("Courier New", 8), fg="#444466",
                 bg="#0c0c1c", width=2, anchor=tk.W).pack(side=tk.LEFT)
        self.size_h_var = tk.IntVar(value=self._cfg.get("display_h", 420))
        h_spin = tk.Spinbox(spin_row, from_=100, to=4000, increment=10,
                            textvariable=self.size_h_var, width=6,
                            font=("Courier New", 9), fg="#00e5ff", bg="#080810",
                            buttonbackground="#0c0c1c", relief=tk.FLAT,
                            highlightthickness=1, highlightbackground="#141428",
                            command=self._apply_display_size)
        h_spin.bind("<Return>", lambda e: self._apply_display_size())
        h_spin.bind("<FocusOut>", lambda e: self._apply_display_size())
        h_spin.pack(side=tk.LEFT, padx=(2, 4))
        tk.Label(spin_row, text="px", font=("Courier New", 7), fg="#282840",
                 bg="#0c0c1c").pack(side=tk.LEFT)

        # size_hint inline — no button, auto-saves on every change
        self.size_hint = tk.Label(spin_row, text="",
                                   font=("Courier New", 7), fg="#ffaa00", bg="#0c0c1c")
        self.size_hint.pack(side=tk.LEFT, padx=(10, 0))

        # Live update indicator — always reflects last saved value
        def _update_indicator(*_):
            try:
                sw = self._cfg.get("display_w")
                sh = self._cfg.get("display_h")
                if sw is not None and sh is not None:
                    self.size_hint.config(text=f"● {sw}×{sh}", fg="#ffaa00")
                else:
                    self.size_hint.config(text="default", fg="#333355")
            except Exception:
                pass
        self._update_size_indicator = _update_indicator
        self.size_w_var.trace_add("write", _update_indicator)
        self.size_h_var.trace_add("write", _update_indicator)

        # Settings toggles
        def make_toggle(parent, label_text, initial=True, command=None):
            row = tk.Frame(parent, bg="#080810")
            state = [initial]
            box = tk.Canvas(row, width=14, height=14, bg="#080810",
                            highlightthickness=0, cursor="hand2")
            def _draw():
                box.delete("all")
                if state[0]:
                    box.create_rectangle(1, 1, 13, 13, fill="#00e5ff", outline="#00e5ff")
                    box.create_rectangle(4, 4, 10, 10, fill="#080810", outline="")
                else:
                    box.create_rectangle(1, 1, 13, 13, fill="", outline="#282840")
            def _toggle(event=None):
                state[0] = not state[0]
                _draw()
                if command:
                    command(state[0])
            box.bind("<Button-1>", _toggle)
            _draw()
            lbl = tk.Label(row, text=label_text, font=("Courier New", 9),
                           fg="#333355", bg="#080810", cursor="hand2")
            lbl.bind("<Button-1>", _toggle)
            lbl.pack(side=tk.LEFT)
            box.pack(side=tk.RIGHT)
            def get_val(): return state[0]
            def set_val(v):
                state[0] = v
                _draw()
            return row, get_val, set_val

        auto_row, self._auto_get, self._auto_set = make_toggle(
            r, "Auto-connect when Poco C65 detected", initial=True)
        auto_row.pack(fill=tk.X, padx=22)

        grid_row, self._grid_get, self._grid_set = make_toggle(
            r, "Show vignette grid overlay", initial=True,
            command=lambda v: self._on_grid_toggle(v))
        grid_row.pack(fill=tk.X, padx=22, pady=(8, 0))

        crosshair_row, self._crosshair_get, self._crosshair_set = make_toggle(
            r, "Show crosshair (for head-mounted use)", initial=True,
            command=lambda v: self._on_crosshair_toggle(v))
        crosshair_row.pack(fill=tk.X, padx=22, pady=(8, 0))

        self.deps_lbl = tk.Label(r, text="", font=("Courier New", 8),
                                  fg="#cc5533", bg="#080810", wraplength=400, justify=tk.LEFT)
        self.deps_lbl.pack(padx=22, pady=(8, 0), anchor=tk.W)

        self.log_var = tk.StringVar(value="Ready.")
        tk.Label(r, textvariable=self.log_var, font=("Courier New", 8),
                 fg="#1e1e36", bg="#080810", wraplength=400).pack(anchor=tk.W, padx=22, pady=(6, 0))
        btn_row = tk.Frame(r, bg="#080810")
        btn_row.pack(side=tk.BOTTOM, pady=(4, 8))
        tk.Button(btn_row, text="\u2665  SUPPORT THE DEVELOPER",
                  font=("Courier New", 8), fg="#ff3366", bg="#080810",
                  activeforeground="#fff", activebackground="#1a0010",
                  borderwidth=0, cursor="hand2",
                  command=self._show_donation).pack()
        tk.Label(r, text="vr-cinema v1.0  \u00b7  vr box  \u00b7  spacedesk  \u00b7  poco c65",
                 font=("Courier New", 7), fg="#101018", bg="#080810").pack(side=tk.BOTTOM, pady=(0, 2))

    def _apply_display_size(self):
        try:
            w = int(self.size_w_var.get())
            h = int(self.size_h_var.get())
            self.cinema.custom_w = max(100, w)
            self.cinema.custom_h = max(100, h)
            self._cfg["display_w"] = self.cinema.custom_w
            self._cfg["display_h"] = self.cinema.custom_h
            ok = _save_config(self._cfg)
            self._update_size_indicator()
            if ok:
                self._log(f"Saved {w}×{h} px  →  {os.path.basename(CONFIG_PATH)}")
            else:
                self._log(f"Save FAILED — check console for details")
        except (ValueError, tk.TclError):
            pass

    def _reset_display_size(self):
        self.cinema.custom_w = None
        self.cinema.custom_h = None
        self.size_w_var.set(640)
        self.size_h_var.set(420)
        self._cfg.pop("display_w", None)
        self._cfg.pop("display_h", None)
        _save_config(self._cfg)
        self._update_size_indicator()
        self._log("Display size reset to default")

    def _show_donation(self):
        win = tk.Toplevel(self.root)
        win.title("Support Kairu Kumaneko")
        win.configure(bg="#080810")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        self.root.update_idletasks()
        px = self.root.winfo_x() + self.root.winfo_width() // 2
        py = self.root.winfo_y() + self.root.winfo_height() // 2
        win.geometry(f"360x560+{px - 180}+{py - 280}")
        tk.Button(win, text="\u2715", font=("Courier New", 10, "bold"),
                  fg="#333355", bg="#080810", activeforeground="#ff3366",
                  activebackground="#080810", borderwidth=0, cursor="hand2",
                  command=win.destroy).place(relx=1.0, x=-14, y=10, anchor=tk.NE)
        hf = tk.Frame(win, bg="#080810")
        hf.pack(pady=(28, 4))
        tk.Label(hf, text="SUPPORT DEVELOPER", font=("Courier New", 18, "bold"), fg="#00e5ff", bg="#080810").pack(side=tk.LEFT)
        tk.Label(win, text="Kairu Kumaneko",
                 font=("Courier New", 13, "bold"), fg="#ffffff", bg="#080810").pack()
        tk.Frame(win, bg="#141428", height=1).pack(fill=tk.X, padx=24, pady=10)
        msg = (
            "I'm a digital artist and a beginner\n"
            "programmer. Please support me and\n"
            "thank you for using this program!\n\n"
            "If you'd like to donate, scan the QR\n"
            "below \u2014 any amount is appreciated. \u2665"
        )
        tk.Label(win, text=msg, font=("Courier New", 9), fg="#444466",
                 bg="#080810", justify=tk.CENTER).pack(padx=20)
        tk.Frame(win, bg="#141428", height=1).pack(fill=tk.X, padx=24, pady=10)
        try:
            from PIL import Image, ImageTk
            # Works both as .py script and PyInstaller .exe
            if getattr(sys, "frozen", False):
                # _MEIPASS = bundled assets temp folder
                base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            assets_dir = os.path.join(base_dir, "assets")
            qr_path = os.path.join(assets_dir, "gcash-qr.png")
            img = Image.open(qr_path).convert("RGB")
            img = img.resize((200, 200), Image.LANCZOS)
            bordered = Image.new("RGB", (208, 208), (0, 229, 255))
            bordered.paste(img, (4, 4))
            tk_img = ImageTk.PhotoImage(bordered)
            lbl = tk.Label(win, image=tk_img, bg="#080810")
            lbl.image = tk_img
            lbl.pack(pady=(0, 6))
        except Exception:
            tk.Label(win, text="[ QR code ]\n(place gcash-qr.png in assets/ folder)",
                     font=("Courier New", 9), fg="#333355", bg="#080810").pack(pady=20)
        tk.Label(win, text="GCash  \u00b7  InstaPay",
                 font=("Courier New", 8), fg="#282840", bg="#080810").pack()
        tk.Label(win, text="Thank you very much! \U0001f64f",
                 font=("Courier New", 9, "bold"), fg="#00e5ff", bg="#080810").pack(pady=(8, 16))

    def _log(self, msg):
        try:
            self.log_var.set(f"\u203a {msg}")
        except:
            pass

    def _refresh_monitor_lists(self, monitors=None):
        """Rebuild the CAPTURE dropdown and PRIMARY indicator only when data changed."""
        if monitors is None:
            monitors = get_monitors_info()
        labels = [label for _, label in monitors]

        # Only rebuild dropdown if the list actually changed
        if labels != getattr(self, "_last_labels", None):
            self._last_labels = labels
            self._monitor_map = {label: idx for idx, label in monitors}
            menu = self.src_menu["menu"]
            menu.delete(0, "end")
            for lbl in labels:
                menu.add_command(label=lbl,
                                 command=lambda v=lbl: (self.src_var.set(v),
                                                        self._apply_monitor_selection()))
            if not self.src_var.get() or self.src_var.get() not in labels:
                self.src_var.set(labels[0])
                self._apply_monitor_selection()

        # Update PRIMARY indicator only if text changed
        primary_label = next((l for l in labels if "[primary]" in l), None)
        pri_text = primary_label.replace("  [primary]", "  \u2605 primary") if primary_label else "not detected"
        if pri_text != getattr(self, "_last_pri_text", None):
            self._last_pri_text = pri_text
            self.pri_indicator.config(text=pri_text)
    def _apply_monitor_selection(self):
        src_lbl = self.src_var.get()
        # _monitor_map now stores guaranteed-correct mss indices from get_monitors_info
        mss_idx = self._monitor_map.get(src_lbl, 1)
        self.cinema.source_monitor = mss_idx
        self._log(f"Capture: Monitor {mss_idx}  \u2192  VR output")
    def _check_deps(self):
        missing = []
        if not PIL_OK: missing.append("Pillow")
        if not MSS_OK: missing.append("mss")
        if missing:
            self.deps_lbl.config(text=f"\u26a0  pip install {' '.join(missing)}   (needed for live screen capture)")

    def _refresh_displays(self):
        self.display_count = get_display_count()
        if self.display_count >= 2:
            self.dot.config(fg="#00e5ff")
            self.status_lbl.config(text=f" Poco C65 detected via Spacedesk \u2713", fg="#00e5ff")
            if self._auto_get():
                self._log("Poco C65 connected \u2014 ready.")
        else:
            self.dot.config(fg="#ff3366")
            self.status_lbl.config(text=" Connect Spacedesk on Poco C65", fg="#333355")


    def _on_grid_toggle(self, value):
        self.cinema.show_grid = value
        self._log(f"Vignette grid overlay {'on' if value else 'off'}")
        if self.cinema.win and self.cinema.win.winfo_exists() and not MSS_OK:
            self.cinema._draw_placeholder()

    def _on_crosshair_toggle(self, value):
        self.cinema.show_crosshair = value
        self._log(f"Cursor overlay {'on' if value else 'off'}")

    def _launch_cinema(self):
        if self.cinema.win and self.cinema.win.winfo_exists():
            self.cinema.close()
            self.cinema_btn.config(text="\u25b6   LAUNCH VR CINEMA", fg="#00e5ff", bg="#001418")
        else:
            self.cinema.open()
            self.cinema_btn.config(text="\u25a0   CLOSE VR CINEMA", fg="#ff3366", bg="#12080e")

    def _monitor_displays(self):
        prev_count = self.display_count
        prev_monitors = get_monitors_info()
        while self.monitoring:
            time.sleep(0.5)
            try:
                cur_count = get_display_count()
                cur_monitors = get_monitors_info()
                # Always refresh status dot + primary indicator (cheap label updates)
                # _refresh_displays and _refresh_monitor_lists both guard against unnecessary redraws
                self.root.after(0, self._refresh_displays)
                self.root.after(0, lambda m=cur_monitors: self._refresh_monitor_lists(m))
                prev_count = cur_count
                prev_monitors = cur_monitors
            except:
                pass
    def on_close(self):
        self.monitoring = False
        self.cinema.running = False
        # Save window position before closing
        try:
            self._cfg["window_geometry"] = self.root.geometry()
            _save_config(self._cfg)
        except Exception:
            pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    # Set window icon from assets/icon.ico
    try:
        if getattr(sys, "frozen", False):
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "assets", "icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception:
        pass
    app = VRCinemaApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()