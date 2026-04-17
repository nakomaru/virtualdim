# VirtualDim

A tiny system-tray dimmer for Windows. Scales RGB output via the
Magnification API (the same path Windows' own Color Filters use), so you
can drop the whole display darker than the hardware allows — useful when
OLED/TV monitors are punishingly bright even at 0% brightness with dark
mode maxed.

Pure Python standard library + `pystray` + `pillow`. No admin needed.
Self-bootstraps its own venv on first run.

## Features

- True global dimming via `MagSetFullscreenColorEffect` — works on
  context menus, popups, top-most windows, everything except the hardware
  mouse cursor
- Tray-only UI: right-click for a list of dim levels (80% → 0%) and Quit
- Left-click toggles between 0 and the last non-zero level
- Smooth 500ms cubic ease-in-out fade between levels
- No console window after first launch (runs under `pythonw.exe`)

## Usage

```
python virtualdim.pyw
```

First launch creates `~/venvs/.venv_virtualdim`, installs `pystray` and
`pillow`, then relaunches itself silently. Subsequent launches just
double-click the `.pyw` file — no console.

Tray interactions:

- **Left-click** — toggle between 0 and the last non-zero level
- **Right-click** — pick a level (80% / 70% / … / 0% (disabled)) or Quit

## Limitations

The hardware mouse cursor is drawn by the GPU after the Magnification
transform, so it stays at full brightness. Exclusive-fullscreen games and
HDR content may also bypass the effect.

If your monitor supports **DDC/CI**, use that for real hardware brightness
control. This tool is for displays (like many TVs used as monitors) where
DDC/CI isn't available.

## License

MIT
