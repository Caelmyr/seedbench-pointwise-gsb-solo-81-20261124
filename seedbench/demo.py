"""Generate a repeatable synthetic tray with scale, grains, chaff and a partial kernel."""

from math import cos, pi, sin
from random import Random

from PIL import Image, ImageDraw

from .model import DEFAULTS
from .photo import png


def kernel(draw, center, length, width, angle, colors, rng, damage):
    xc, yc = center
    ca, sa = cos(angle), sin(angle)
    points = []
    for n in range(44):
        theta = 2 * pi * n / 44
        radial = 1 + rng.uniform(-0.035, 0.035)
        x = length * cos(theta) * radial
        y = width * sin(theta) * (1 + 0.23 * cos(theta)) * radial
        points.append((xc + ca*x - sa*y, yc + sa*x + ca*y))
    draw.polygon(points, fill=colors[0])
    ridge = [(xc + ca*t*length, yc + sa*t*length) for t in (-0.72, -0.32, 0.18, 0.68)]
    draw.line(ridge, fill=colors[1], width=2)
    for _ in range(9):
        along, across = rng.uniform(-0.72, 0.75), rng.uniform(-0.55, 0.55)
        x = xc + ca*along*length - sa*across*width
        y = yc + sa*along*length + ca*across*width
        draw.ellipse((x-1.5, y-1, x+1.5, y+1), fill=colors[2])
    if damage:
        draw.ellipse((xc-5, yc-3, xc+5, yc+3), fill="#f4efd6")


def tray_photo():
    rng = Random(2047)
    image = Image.new("RGBA", (960, 620), "#232922")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 949, 605), 17, fill="#161e18", outline="#59604a", width=2)
    for _ in range(3400):
        x, y = rng.randrange(22, 937), rng.randrange(20, 555)
        draw.point((x, y), fill=rng.choice(("#172018", "#21261d", "#303129")))
    grain = ("#be9253", "#a47a40", "#d0a971")
    coated = ("#418aae", "#2c6a98", "#65aac4")
    for row in range(5):
        for col in range(9):
            if (row, col) in {(0, 7), (0, 8), (1, 8), (4, 0), (4, 8), (2, 5), (2, 2)}:
                continue
            x, y = 83 + col * 96 + rng.randrange(-19, 20), 85 + row * 93 + rng.randrange(-18, 18)
            index = row * 9 + col
            blue = index % 5 == 2 or index % 9 == 3
            kernel(draw, (x, y), rng.randrange(20, 28), rng.randrange(12, 18),
                   rng.uniform(-2.7, 2.7), coated if blue else grain, rng, index % 7 == 4)
    kernel(draw, (38, 315), 27, 15, 0.20, grain, rng, False)
    # Added grains use their own sequence so the layout above stays stable.
    detail = Random(747)
    # Naturally slender singles: ordinary grains in every count.
    kernel(draw, (851, 178), 31, 9, 0.9, grain, detail, False)
    kernel(draw, (70, 480), 30, 9, -1.1, grain, detail, False)
    # Lightly stuck pairs with a visible waist between the grains.
    kernel(draw, (733, 80), 25, 14, 1.55, grain, detail, False)
    kernel(draw, (762, 84), 24, 14, 1.55, grain, detail, False)
    kernel(draw, (272, 268), 24, 13, 1.52, grain, detail, False)
    kernel(draw, (301, 264), 25, 14, 1.58, grain, detail, False)
    # A firmer pair: only the fuller read of the photo separates it.
    kernel(draw, (838, 453), 25, 13, 0.12, grain, detail, False)
    kernel(draw, (878, 459), 24, 13, -0.08, grain, detail, False)
    # Pressed together without a visible edge: left for a new photograph.
    kernel(draw, (560, 269), 29, 18, 0.55, grain, detail, False)
    kernel(draw, (568, 274), 28, 17, -0.35, grain, detail, False)
    for x, y in ((781, 116), (875, 115), (80, 438), (715, 305)):
        draw.polygon([(x, y), (x+11, y-15), (x+25, y-8), (x+32, y+6),
                      (x+17, y+10), (x-2, y+7)], fill="#c2c1ad")
    for _ in range(27):
        x, y = rng.randrange(70, 900), rng.randrange(72, 525)
        draw.ellipse((x, y, x+1, y+2), fill="#aa9977")
    y = 582
    draw.line([(78, y), (270, y)], fill="#e4daba", width=2)
    for i in range(6):
        x = 78 + 192 * i / 5
        draw.line([(x, y-6), (x, y+6)], fill="#e4daba", width=2)
    draw.text((286, y-6), "25 mm · SYNTHETIC SAMPLE", fill="#d0c59f")
    return image


def create(library):
    image = tray_photo()
    options = {
        **DEFAULTS, "area": [0.047, 0.071, 0.951, 0.875],
        "reference": [[78/960, 582/620], [270/960, 582/620]],
    }
    return library.create("Pilot lot A", "synthetic-lot-a.png", png(image), *image.size, options, synthetic=True)
