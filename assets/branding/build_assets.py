"""Build desktop and web assets from the Intreccio vector masters (development only)."""

from __future__ import annotations

import io
from pathlib import Path
import struct
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parent
WEB = ROOT.parents[1] / "src/nipat/gui/web"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png(source: str, size: int) -> bytes:
    result = subprocess.run([
        "inkscape", str(ROOT / source), "--export-type=png", "--export-filename=-",
        f"--export-width={size}", f"--export-height={size}",
    ], check=True, stdout=subprocess.PIPE)
    # Write only pixels so editor metadata, including timestamps, is excluded.
    buffer = io.BytesIO()
    with Image.open(io.BytesIO(result.stdout)) as image:
        image.convert("RGBA").save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def main() -> None:
    wordmark = (ROOT / "nipat-logo.svg").read_bytes()
    (WEB / "newpat-wordmark.svg").write_bytes(wordmark)
    (ROOT / "nipat-logo-dark.svg").write_bytes(
        wordmark.replace(b"#234E43", b"#FFFFFF").replace(b"#709987", b"#BCD9CA"))
    normal = "newpat-app-icon.svg"
    small = "newpat-app-icon-small.svg"
    (ROOT / "nipat-icon.png").write_bytes(png(normal, 1024))
    # Finder's 16-point slot also has a 32-device-pixel Retina representation.
    (ROOT / "newpat-icon-small.png").write_bytes(png(small, 32))
    frames = [png(small if size <= 24 else normal, size) for size in SIZES]
    offset = 6 + 16 * len(SIZES)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(SIZES)))
    for size, frame in zip(SIZES, frames):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                     1, 32, len(frame), offset))
        offset += len(frame)
    (ROOT / "nipat-icon.ico").write_bytes(bytes(directory) + b"".join(frames))


if __name__ == "__main__":
    main()
