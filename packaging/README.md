# Packaging

- `icons/kalshi-hunter.svg` — the icon source (dark navy rounded square, teal crosshair, "K" whose upper arm
  rises and lower arm falls: research, not advice). PNGs 16–512 are rendered from it.
- `kalshi-hunter.desktop` — the menu entry. `Exec`/`Path` point at this checkout; the installer rewrites them.
- `install-desktop-entry.sh` — installs the entry and icons for the current user only (dry run by default),
  or removes them again. No sudo, nothing system-wide.

Regenerate the PNGs after editing the SVG (needs `rsvg-convert`, from `librsvg`):

```bash
cd packaging/icons
for s in 16 24 32 48 64 128 256 512; do rsvg-convert -w "$s" -h "$s" kalshi-hunter.svg -o "kalshi-hunter-$s.png"; done
```

Validate the entry before installing:

```bash
desktop-file-validate packaging/kalshi-hunter.desktop
```

Installing the menu entry has not been done. It is a user-visible change, so it waits for Dave's go-ahead:

```bash
packaging/install-desktop-entry.sh          # dry run, shows the exact paths
packaging/install-desktop-entry.sh --yes    # user-level install into ~/.local/share
```