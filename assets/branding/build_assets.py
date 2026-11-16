"""Regenerate NewPat vector and raster branding with Pillow 12.3.0.

The SVGs and raster icons share the geometry below. This developer utility is
not used when building or running NewPat; generated assets are versioned.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
NAVY = "#142D4E"
TEAL = "#48D6C5"
WHITE = "#FFFFFF"
# Parallel strokes refer to paired sequence data; the main silhouette is N.
STROKES = [
    ([(72, 184), (72, 72), (184, 184), (184, 72)], WHITE, 22),
    ([(105, 72), (184, 151)], TEAL, 10),
]
# Outline lettering avoids font installation and substitution in SVG viewers.
GLYPHS = [
    "M0 78V0H13L45 55V0H59V78H46L14 23V78Z",  # N
    "M52 56H14C15 67 22 70 30 70C38 70 43 68 48 64L54 73C47 78 39 81 29 81C11 81 0 69 0 52C0 35 11 23 28 23C45 23 54 35 54 51V56ZM14 46H40C39 37 35 34 28 34C21 34 16 38 14 46Z",  # e
    "M0 25H14L23 62L34 25H47L58 62L67 25H81L65 78H51L40 42L29 78H15Z",  # w
    "M0 78V0H31C49 0 59 9 59 25C59 42 49 51 31 51H14V78ZM14 13V38H30C40 38 45 34 45 25C45 17 40 13 30 13Z",  # P
    "M1 30C9 25 18 23 28 23C45 23 54 31 54 47V78H42V71C36 77 30 80 22 80C8 80 0 73 0 62C0 50 10 44 27 44H40C40 37 36 34 28 34C20 34 13 36 7 40ZM40 54H28C18 54 13 57 13 62C13 67 17 70 24 70C33 70 40 64 40 57Z",  # a
    "M12 9H26V25H42V37H26V60C26 67 29 69 34 69C37 69 40 68 43 67V78C39 80 35 81 31 81C18 81 12 74 12 61V37H0V25H12Z",  # t
]
GLYPH_X = [0, 72, 139, 234, 306, 373]


def icon_markup() -> str:
    strokes = "\n".join(
        f'  <polyline points="{" ".join(f"{x},{y}" for x, y in points)}" '
        f'fill="none" stroke="{color}" stroke-width="{width}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        for points, color, width in STROKES
    )
    return f'  <rect x="8" y="8" width="240" height="240" rx="48" fill="{NAVY}"/>\n{strokes}'


def svg_document(body: str, viewbox: str, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" '
            f'aria-label="{label}">\n<title>{label}</title>\n{body}\n</svg>\n')


def raster_icon(size: int) -> Image.Image:
    scale = 4 * size / 256
    image = Image.new("RGBA", (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(tuple(round(v * scale) for v in (8, 8, 248, 248)),
                           radius=round(48 * scale), fill=NAVY)
    for points, color, width in STROKES:
        scaled = [(round(x * scale), round(y * scale)) for x, y in points]
        stroke = round(width * scale)
        draw.line(scaled, fill=color, width=stroke, joint="curve")
        radius = stroke / 2
        for x, y in scaled:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    (ROOT / "nipat-symbol.svg").write_text(
        svg_document(icon_markup(), "0 0 256 256", "NewPat"), encoding="utf-8")
    for name, color in (("nipat-logo.svg", NAVY), ("nipat-logo-dark.svg", WHITE)):
        lettering = "\n".join(
            f'<path transform="translate({x} 0)" d="{path}"/>'
            for x, path in zip(GLYPH_X, GLYPHS)
        )
        body = (f'<g transform="scale(0.625)">\n{icon_markup()}\n</g>\n'
                f'<g transform="translate(194 41)" fill="{color}" fill-rule="evenodd">\n'
                f'{lettering}\n</g>')
        (ROOT / name).write_text(svg_document(body, "0 0 627 160", "NewPat"), encoding="utf-8")
    raster_icon(512).save(ROOT / "nipat-icon.png", optimize=False, compress_level=9)
    # PNG-backed ICO frames retain their independently rendered small-size detail.
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    frames = []
    for size in sizes:
        buffer = io.BytesIO()
        raster_icon(size).save(buffer, format="PNG", optimize=False, compress_level=9)
        frames.append(buffer.getvalue())
    import struct
    offset = 6 + 16 * len(sizes)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    for size, payload in zip(sizes, frames):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                     1, 32, len(payload), offset))
        offset += len(payload)
    (ROOT / "nipat-icon.ico").write_bytes(bytes(directory) + b"".join(frames))


if __name__ == "__main__":
    main()
