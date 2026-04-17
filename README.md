# VirtualDim

A tiny system-tray dimming overlay for Windows. Drops a black, click-through,
always-on-top layer over every monitor so you can crank your displays darker
than their hardware allows — useful when OLED/TV monitors are punishingly
bright even at 0% brightness with dark mode maxed.

Pure Python standard library + `pystray` + `pillow`. No admin needed.
Self-bootstraps its own venv on first run.

## Features

- Multi-monitor, DPI-aware, click-through overlays
- Tray icon with a slider window and quick-preset submenu (0–80%)
- Dark-themed slider window with a dark titlebar
- No console window after first launch (runs under `pythonw.exe`)

## Usage

```
python virtualdim.pyw
```

First launch creates `~/venvs/.venv_virtualdim`, installs `pystray` and
`pillow`, then relaunches itself silently. Subsequent launches just
double-click the `.pyw` file — no console.

Tray interactions:

- **Left-click** — opens the slider window
- **Right-click → Level** — jump to a preset (0/10/…/80%)
- **Right-click → Quit** — clean exit

## Limitations

A software overlay cannot dim:

- The hardware cursor
- Exclusive-fullscreen games
- HDR content
- Some fullscreen video players

Everything else (desktop, browsers, windowed apps, windowed video) dims fine.

If your monitor supports **DDC/CI**, use that instead for real hardware
brightness control. This tool is for displays (like many TVs used as
monitors) where DDC/CI isn't available.

## License

MIT
