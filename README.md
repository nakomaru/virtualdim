# VirtualDim

A tiny system-tray dimming overlay for Windows. Drops a black, click-through,
always-on-top layer over every monitor so you can crank your displays darker
than their hardware allows — useful when OLED/TV monitors are punishingly
bright even at 0% brightness with dark mode maxed.

Pure Python standard library + `pystray` + `pillow`. No admin needed.
Self-bootstraps its own venv on first run.

## Features

- Multi-monitor, DPI-aware, click-through overlays
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

Anything that renders above a normal top-most window punches through the
overlay: the hardware cursor, context menus and popups, other always-on-top
apps, fullscreen games, HDR content, and video in apps like Teams. Regular
desktop, browser, and app windows dim fine.

If your monitor supports **DDC/CI**, use that instead for real hardware
brightness control. This tool is for displays (like many TVs used as
monitors) where DDC/CI isn't available.

## License

MIT
