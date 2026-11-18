# NewPat artwork

The two parallel strokes in the N symbol represent paired sequence data.
The palette uses navy (`#142D4E`), white, and teal (`#48D6C5`).
Use the wordmark on its intended background so the lettering stays legible.

| File | Use |
| --- | --- |
| [nipat-symbol.svg](nipat-symbol.svg) | Standalone vector symbol and Linux desktop shortcut |
| [nipat-logo.svg](nipat-logo.svg) | Wordmark for light backgrounds |
| [nipat-logo-dark.svg](nipat-logo-dark.svg) | Wordmark for dark backgrounds |
| [nipat-icon.png](nipat-icon.png) | Transparent 512 × 512 raster icon |
| [nipat-icon.ico](nipat-icon.ico) | Windows icon at 16, 20, 24, 32, 40, 48, 64, 128, and 256 pixels |

The SVG wordmarks use outlines and require no additional fonts. The Windows
installer embeds the ICO. The Linux desktop entry uses the installed SVG.

## Regenerate the files

From the repository root, use Python 3.12 in a development environment:

```sh
python -m pip install Pillow==12.3.0
python assets/branding/build_assets.py
```

[build_assets.py](build_assets.py) uses the same geometry for the SVGs and raster
icons and omits timestamps. Application packages use the committed artwork.
The original artwork is covered by the [project license](../../LICENSE).
