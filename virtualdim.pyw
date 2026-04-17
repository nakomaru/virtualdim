"""Multi-monitor click-through dimming overlay for Windows, tray edition.

Runs in the system tray with a moon icon. Left-click the tray icon to open
a small slider; right-click for presets and quick actions. Overlays stay
up in the background.

Self-bootstraps a venv at  ~/venvs/.venv_virtualdim  and installs
pystray + pillow on first run.
"""

import os
import sys
import subprocess
import venv
from pathlib import Path


def ensure_venv():
    if sys.prefix != sys.base_prefix:
        return

    venv_dir = Path.home() / "venvs" / ".venv_virtualdim"
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        py = venv_dir / "Scripts" / "python.exe"
        pyw = venv_dir / "Scripts" / "pythonw.exe"
    else:
        py = venv_dir / "bin" / "python"
        pyw = py

    if not py.exists():
        print(f"Creating virtual environment in {venv_dir}...")
        venv.create(venv_dir, with_pip=True)

    try:
        subprocess.check_call([str(py), "-c", "import pystray, PIL"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        print("Installing dependencies (pystray, pillow)...")
        subprocess.check_call([str(py), "-m", "pip", "install", "pystray", "pillow"])

    launcher = pyw if pyw.exists() else py
    script = str(Path(__file__).resolve())
    try:
        os.execv(str(launcher), [str(launcher), script] + sys.argv[1:])
    except (AttributeError, OSError):
        sys.exit(subprocess.call([str(launcher), script] + sys.argv[1:]))


ensure_venv()

import ctypes
from ctypes import wintypes
import threading
import tkinter as tk

from PIL import Image, ImageDraw
import pystray

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
user32.SetProcessDPIAware()

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x00000002

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # Windows 10 pre-20H1

GetWL = user32.GetWindowLongPtrW
SetWL = user32.SetWindowLongPtrW
GetWL.restype = ctypes.c_ssize_t
SetWL.restype = ctypes.c_ssize_t
GetWL.argtypes = [wintypes.HWND, ctypes.c_int]
SetWL.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

SetLayeredWindowAttributes = user32.SetLayeredWindowAttributes
SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF,
                                       wintypes.BYTE, wintypes.DWORD]
SetLayeredWindowAttributes.restype = wintypes.BOOL

GA_ROOT = 2
GetAncestor = user32.GetAncestor
GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
GetAncestor.restype = wintypes.HWND

dwmapi.DwmSetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


def enable_dark_titlebar(hwnd):
    val = ctypes.c_int(1)
    # Try the modern attribute first, fall back to the older one.
    if dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val), ctypes.sizeof(val)) != 0:
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(val), ctypes.sizeof(val))


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(RECT), wintypes.LPARAM)


def enumerate_monitors():
    monitors = []

    def _cb(hMon, hdc, lprc, lparam):
        r = lprc.contents
        monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
    return monitors


def root_hwnd(hwnd):
    r = GetAncestor(hwnd, GA_ROOT)
    return r or hwnd


def set_overlay_style(hwnd):
    style = GetWL(hwnd, GWL_EXSTYLE)
    SetWL(hwnd, GWL_EXSTYLE,
          style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)


def set_overlay_alpha(hwnd, alpha01):
    b = max(0, min(255, int(round(alpha01 * 255))))
    SetLayeredWindowAttributes(hwnd, 0, b, LWA_ALPHA)


def make_moon_icon(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 6
    d.ellipse((pad, pad, size - pad, size - pad), fill=(230, 230, 245, 255))
    off = size // 4
    d.ellipse((pad + off, pad - 2, size - pad + off, size - pad - 2),
              fill=(0, 0, 0, 0))
    return img


PRESETS = [0, 10, 20, 30, 40, 50, 60, 70, 80]


class Dimmer:
    def __init__(self):
        BG = "#151517"
        FG = "#d8d8df"
        ACC = "#2a2a30"

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("VirtualDim")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_slider)
        self.root.update_idletasks()
        enable_dark_titlebar(root_hwnd(self.root.winfo_id()))

        self.val = tk.DoubleVar(value=0.0)

        frm = tk.Frame(self.root, padx=12, pady=10, bg=BG)
        frm.pack()
        tk.Label(frm, text="Dim", bg=BG, fg=FG).grid(row=0, column=0, sticky="w")
        tk.Scale(frm, from_=0, to=85, orient="horizontal", length=260,
                 variable=self.val, command=self._on_change, showvalue=True,
                 bg=BG, fg=FG, troughcolor=ACC, highlightthickness=0,
                 activebackground=FG, borderwidth=0
                 ).grid(row=0, column=1, padx=8)
        tk.Button(frm, text="Off", command=lambda: self._set(0),
                  bg=ACC, fg=FG, activebackground=FG, activeforeground=BG,
                  borderwidth=0, padx=10).grid(row=0, column=2)

        self.overlays = []
        for x, y, w, h in enumerate_monitors():
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.configure(bg="black")
            ov.geometry(f"{w}x{h}+{x}+{y}")
            ov.update_idletasks()
            hwnd = root_hwnd(ov.winfo_id())
            set_overlay_style(hwnd)
            set_overlay_alpha(hwnd, 0.0)
            ov.after(50, lambda h=hwnd: (set_overlay_style(h),
                                          set_overlay_alpha(h, self._alpha())))
            self.overlays.append((ov, hwnd))

        def preset_item(p):
            return pystray.MenuItem(
                f"{p}%",
                lambda _i, _it, pp=p: self.root.after(0, lambda: self._set(pp)),
                checked=lambda _it, pp=p: int(round(self.val.get())) == pp,
                radio=True)

        self.tray = pystray.Icon(
            "virtualdim",
            make_moon_icon(),
            "VirtualDim",
            menu=pystray.Menu(
                pystray.MenuItem("Slider", self._tray_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Level",
                    pystray.Menu(*(preset_item(p) for p in PRESETS))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._tray_quit),
            ),
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _alpha(self):
        return float(self.val.get()) / 100.0

    def _on_change(self, _):
        a = self._alpha()
        for _ov, hwnd in self.overlays:
            set_overlay_alpha(hwnd, a)
        try:
            self.tray.update_menu()
        except Exception:
            pass

    def _set(self, v):
        self.val.set(v)
        self._on_change(None)

    def show_slider(self):
        self.root.deiconify()
        self.root.lift()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - 380}+{sh - 140}")

    def hide_slider(self):
        self.root.withdraw()

    def _tray_show(self, _icon, _item):
        self.root.after(0, self.show_slider)

    def _tray_quit(self, _icon, _item):
        self.root.after(0, self.quit)

    def quit(self):
        try:
            self.tray.stop()
        except Exception:
            pass
        for ov, _h in self.overlays:
            try:
                ov.destroy()
            except tk.TclError:
                pass
        self.overlays.clear()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Dimmer().run()
