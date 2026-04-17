"""Multi-monitor click-through dimming overlay for Windows, tray-only.

Runs in the system tray with a moon icon. Right-click for a list of dim
levels or to quit. Left-click sets dim to 0. Overlays run in the background.

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
user32.SetProcessDPIAware()

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x00000002

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


LEVELS = [80, 70, 60, 50, 40, 30, 20, 10, 0]


class Dimmer:
    def __init__(self):
        self.level = 0
        self.last_nonzero = 40
        self._anim_job = None
        self._current_alpha = 0.0

        self.root = tk.Tk()
        self.root.withdraw()

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
                                          set_overlay_alpha(h, self.level / 100.0)))
            self.overlays.append((ov, hwnd))

        def level_item(p):
            def on_click(_icon, _item):
                self.root.after(0, lambda: self._set(p))

            def is_checked(_item):
                return self.level == p

            label = "0% (disabled)" if p == 0 else f"{p}%"
            return pystray.MenuItem(label, on_click, checked=is_checked, radio=True)

        def on_toggle(_icon, _item):
            self.root.after(0, self._toggle)

        self.tray = pystray.Icon(
            "virtualdim",
            make_moon_icon(),
            "VirtualDim",
            menu=pystray.Menu(
                pystray.MenuItem("Toggle", on_toggle, default=True, visible=False),
                *(level_item(p) for p in LEVELS),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._tray_quit),
            ),
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _apply_alpha(self, a):
        self._current_alpha = a
        for _ov, hwnd in self.overlays:
            set_overlay_alpha(hwnd, a)

    def _set(self, p):
        self.level = p
        if p > 0:
            self.last_nonzero = p
        self._animate_to(p / 100.0, duration_ms=500)
        try:
            self.tray.update_menu()
        except Exception:
            pass

    def _animate_to(self, target, duration_ms=500, step_ms=16):
        if self._anim_job is not None:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

        start = self._current_alpha
        delta = target - start
        if abs(delta) < 1e-4 or duration_ms <= 0:
            self._apply_alpha(target)
            return

        steps = max(1, duration_ms // step_ms)
        i = {"n": 0}

        def ease(t):  # cubic in-out
            return 3 * t * t - 2 * t * t * t

        def tick():
            i["n"] += 1
            t = min(1.0, i["n"] / steps)
            self._apply_alpha(start + delta * ease(t))
            if t < 1.0:
                self._anim_job = self.root.after(step_ms, tick)
            else:
                self._anim_job = None

        self._anim_job = self.root.after(step_ms, tick)

    def _toggle(self):
        self._set(0 if self.level > 0 else self.last_nonzero)

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
