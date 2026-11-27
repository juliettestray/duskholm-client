"""Draws sanctuary.ico (a crescent moon over a green prompt) at every size Windows asks for.

    python make_icon.py

Needs Pillow; only for redrawing the icon. The result, sanctuary.ico, is committed, and nothing else needs Pillow."""
import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = (16, 24, 32, 48, 64, 128, 256)

SS = 4  # supersample


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(n, r):
    m = Image.new("L", (n, n), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, n - 1, n - 1], r, fill=255)
    return m


def sky(n, top, bottom):
    im = Image.new("RGB", (n, n))
    d = ImageDraw.Draw(im)
    for y in range(n):
        d.line([(0, y), (n, y)], fill=lerp(top, bottom, y / (n - 1)))
    return im


def draw(n):
    """Terminal-flavoured: dark screen, glowing S as a crescent, prompt cursor."""
    N = n * SS
    im = sky(N, (20, 22, 40), (44, 30, 78)).convert("RGBA")
    d = ImageDraw.Draw(im)
    # big crescent moon, filling the tile
    cx, cy, r = N * 0.5, N * 0.46, N * 0.33
    moon = Image.new("L", (N, N), 0)
    md = ImageDraw.Draw(moon)
    md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    md.ellipse([cx - r * 0.62, cy - r * 1.2, cx + r * 1.38, cy + r * 0.8], fill=0)
    glow = moon.filter(ImageFilter.GaussianBlur(N * 0.04))
    im.paste((255, 214, 120, 255), mask=glow.point(lambda v: int(v * 0.5)))
    im.paste((255, 232, 160, 255), mask=moon)
    # prompt cursor underscore and caret
    y = N * 0.86
    d.rectangle([N * 0.5, y, N * 0.76, y + N * 0.06], fill=(120, 230, 160))
    d.line([(N * 0.24, y - N * 0.035), (N * 0.34, y + N * 0.03), (N * 0.24, y + N * 0.095)], fill=(120, 230, 160), width=int(N * 0.05), joint="curve")
    im = im.resize((n, n), Image.LANCZOS)
    im.putalpha(rounded_mask(n, n // 5))
    return im


def main():
    out = os.path.join(HERE, "sanctuary.ico")
    draw(256).save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    print("Wrote", out)


if __name__ == "__main__":
    main()
