"""Global screen dimmer for Windows using the Magnification API.

Runs in the system tray with a moon icon. Right-click for a list of dim
levels or to quit. Left-click toggles between 0 and the last level.

Uses MagSetFullscreenColorEffect to scale RGB output before scan-out,
which dims basically everything — including context menus, popups, and
top-most windows — except the hardware mouse cursor.

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


# Set per-monitor v2 DPI awareness BEFORE MagInitialize, otherwise
# Magnification forces the process to "system DPI aware" and Windows
# starts bitmap-scaling tray menus, popups, etc. (mud).
_user32 = ctypes.windll.user32
try:
    _user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    _user32.SetProcessDpiAwarenessContext.restype = ctypes.c_int
    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        _user32.SetProcessDPIAware()

magnification = ctypes.windll.Magnification


class MAGCOLOREFFECT(ctypes.Structure):
    _fields_ = [("transform", (ctypes.c_float * 5) * 5)]


magnification.MagInitialize.restype = wintypes.BOOL
magnification.MagUninitialize.restype = wintypes.BOOL
magnification.MagSetFullscreenColorEffect.argtypes = [
    ctypes.POINTER(MAGCOLOREFFECT)]
magnification.MagSetFullscreenColorEffect.restype = wintypes.BOOL


def _scale_matrix(s):
    m = MAGCOLOREFFECT()
    m.transform[0][0] = s
    m.transform[1][1] = s
    m.transform[2][2] = s
    m.transform[3][3] = 1.0
    m.transform[4][4] = 1.0
    return m


def mag_set_scale(s):
    """Scale all RGB output by s (0..1)."""
    m = _scale_matrix(max(0.0, min(1.0, s)))
    return bool(magnification.MagSetFullscreenColorEffect(ctypes.byref(m)))


def make_moon_icon(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 6
    d.ellipse((pad, pad, size - pad, size - pad), fill=(230, 230, 245, 255))
    off = size // 4
    d.ellipse((pad + off, pad - 2, size - pad + off, size - pad - 2),
              fill=(0, 0, 0, 0))
    return img


LEVELS = [90, 85, 80, 70, 60, 50, 40, 30, 20, 10, 0]


class Dimmer:
    def __init__(self):
        self.level = 0
        self.last_nonzero = 40
        self._anim_job = None
        self._current = 0.0  # current dim amount (0..1)

        # Hidden tk root — used only for its main-thread message pump and
        # after() scheduling. Magnification requires a message loop.
        self.root = tk.Tk()
        self.root.withdraw()

        if not magnification.MagInitialize():
            raise RuntimeError("MagInitialize failed")
        mag_set_scale(1.0)

        def level_item(p):
            def on_click(_icon, _item):
                self.root.after(0, lambda: self._set(p))

            def is_checked(_item):
                return self.level == p

            if p == 0:
                label = "0% (off)"
            elif p == max(LEVELS):
                label = f"{p}% (darkest)"
            else:
                label = f"{p}%"
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

    def _apply(self, a):
        self._current = a
        try:
            mag_set_scale(1.0 - a)
        except Exception:
            pass

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

        start = self._current
        delta = target - start
        if abs(delta) < 1e-4 or duration_ms <= 0:
            self._apply(target)
            return

        steps = max(1, duration_ms // step_ms)
        i = {"n": 0}

        def ease(t):  # cubic in-out
            return 3 * t * t - 2 * t * t * t

        def tick():
            i["n"] += 1
            t = min(1.0, i["n"] / steps)
            self._apply(start + delta * ease(t))
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
            mag_set_scale(1.0)
            magnification.MagUninitialize()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Dimmer().run()
