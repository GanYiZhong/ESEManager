"""Draw the ESEManager app icon (an original taiko-drum design) and write it to assets/.

Outputs:
  assets/icon.png  256x256 PNG
  assets/icon.ico  multi-size ICO (16, 32, 48, 256)

Qt's ICO writer only stores a single frame, so the ICO container is written here
with struct: each frame is a PNG-encoded image (supported by Windows Vista and later).

Run:  python scripts/make_icon.py
"""
import math
import os
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
PNG_PATH = os.path.join(ASSETS, "icon.png")
ICO_PATH = os.path.join(ASSETS, "icon.ico")
ICO_SIZES = (16, 32, 48, 256)

RED = QColor("#D8262B")
DARK = QColor("#2A2A2A")
WHITE = QColor("#FFF8EE")


def draw_drum(size):
    """Render the drum at `size` px. Geometry is designed on a 256 grid and scaled."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 256.0, size / 256.0)
    p.setPen(Qt.PenStyle.NoPen)
    center = QPointF(128, 128)

    def disc(radius, color, at=center):
        p.setBrush(color)
        p.drawEllipse(at, radius, radius)

    disc(124, DARK)                      # outer shell edge
    disc(112, RED)                       # red drum body
    for i in range(8):                   # tension tacks around the body
        a = math.radians(i * 45)
        disc(5, DARK, QPointF(128 + 99 * math.cos(a), 128 + 99 * math.sin(a)))
    disc(86, DARK)                       # head rim
    disc(82, WHITE)                      # drum head
    disc(34, RED)                        # striking center
    p.end()
    return img


def png_bytes(img):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not img.save(buf, "PNG"):
            raise RuntimeError("PNG encoding failed")
        return bytes(buf.data())
    finally:
        buf.close()


def write_ico(path, frames):
    """frames: list of (size, png_bytes). Writes an ICONDIR + ICONDIRENTRY table + blobs."""
    header = struct.pack("<HHH", 0, 1, len(frames))   # reserved, type=1 (icon), count
    entries = b""
    blobs = []
    offset = 6 + 16 * len(frames)
    for size, data in frames:
        w = 0 if size >= 256 else size                 # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + entries + b"".join(blobs))


def main():
    os.makedirs(ASSETS, exist_ok=True)
    if not draw_drum(256).save(PNG_PATH, "PNG"):
        raise SystemExit(f"failed to write {PNG_PATH}")
    frames = [(s, png_bytes(draw_drum(s))) for s in ICO_SIZES]
    write_ico(ICO_PATH, frames)
    print("wrote", PNG_PATH)
    print("wrote", ICO_PATH, "sizes", ICO_SIZES)


if __name__ == "__main__":
    main()
