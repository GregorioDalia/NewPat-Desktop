# NewPat artwork

The Intreccio wordmark integrates two strands into its initial N. The primary forest green is `#234E43`. The second strand uses `#709987` on light backgrounds and `#BCD9CA` on dark backgrounds. Wordmarks contain outlines and work offline without fonts.

| Vector master | Use |
| --- | --- |
| [Wordmark](newpat-logo.svg) | Light backgrounds, desktop navigation and README |
| [Symbol](newpat-symbol.svg) | Standalone letter N on light backgrounds |
| [Application icon](newpat-app-icon.svg) | Desktop shortcuts, packages and taskbars |
| [Small application icon](newpat-app-icon-small.svg) | Wider gap and thicker strokes for 16–24 px |

The [dark wordmark](newpat-logo-dark.svg) uses the icon’s white and mint colours. The Windows ICO has independently rendered frames at 16, 20, 24, 32, 40, 48, 64, 128 and 256 px. macOS packages use the 1024 px master and the optical 16-point variant for both display densities. Linux installs the scalable tile and the 16 and 24 px optical variants in its hicolor icon theme.

## Regenerate the assets

With Inkscape 1.4 on PATH and Pillow installed, run `python assets/branding/build_assets.py` from the repository root. It creates the web copy, dark wordmark and raster icons from the committed vectors. Installation and application startup use the packaged artwork directly.

The outlined letters `ewPat` derive from the [0.9.9 wordmark](https://github.com/GregorioDalia/NewPat-Desktop/tree/v0.9.9/assets/branding). The project’s [license](../../LICENSE) covers the artwork.
