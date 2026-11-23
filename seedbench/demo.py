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


def tray_canvas():
    rng = Random(2047)
    image = Image.new("RGBA", (960, 620), "#232922")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 949, 605), 17, fill="#161e18", outline="#59604a", width=2)
    for _ in range(3400):
        x, y = rng.randrange(22, 937), rng.randrange(20, 555)
        draw.point((x, y), fill=rng.choice(("#172018", "#21261d", "#303129")))
    grain = ("#be9253", "#a47a40", "#d0a971")
    coated = ("#418aae", "#2c6a98", "#65aac4")
    grains = []
    for row in range(5):
        for col in range(9):
            if (row, col) in {(0, 7), (0, 8), (1, 8), (4, 0), (4, 8), (2, 5)}:
                continue
            x, y = 83 + col * 96 + rng.randrange(-19, 20), 85 + row * 93 + rng.randrange(-18, 18)
            index = row * 9 + col
            blue = index % 5 == 2 or index % 9 == 3
            kernel(draw, (x, y), rng.randrange(18, 29), rng.randrange(11, 19),
                   rng.uniform(-2.7, 2.7), coated if blue else grain, rng, index % 7 == 4)
            grains.append((x, y, blue))
    kernel(draw, (38, 315), 29, 17, 0.20, grain, rng, False)
    for x, y in ((781, 116), (875, 115), (80, 438), (672, 312)):
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
    return image, grains


def lighting_pair():
    """Two aligned photos of one tray under different lighting directions."""
    base, grains = tray_canvas()
    primary, companion = base.copy(), base.copy()
    first, second = ImageDraw.Draw(primary), ImageDraw.Draw(companion)
    coated = [(x, y) for x, y, blue in grains if blue]
    # a chip that reads as bare base in the first photo and blue in the second
    x, y = coated[0]
    first.ellipse((x-4, y-3, x+4, y+3), fill="#c8a26e")
    second.ellipse((x-4, y-3, x+4, y+3), fill="#4f86ad")
    # a chip that reads as bare base in both photos
    x, y = coated[1]
    first.ellipse((x-4, y-3, x+4, y+3), fill="#c8a26e")
    second.ellipse((x-4, y-3, x+4, y+3), fill="#c8a26e")
    # a bright rim only in the first photo: a thin edge, not a chip
    x, y = coated[2]
    first.arc((x-10, y-10, x+10, y+10), start=290, end=80, fill="#d8c9a8")
    # white glare patches only in the first photo
    for cx, cy, rx, ry in ((*coated[3], 22, 15), (*coated[6], 16, 11)):
        first.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), fill="#f7fafd")
    # a soft shadow band only in the second photo
    layer = Image.new("RGBA", companion.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon([(30, 290), (400, 250), (430, 330), (60, 370)],
                                  fill=(12, 16, 12, 180))
    return primary, Image.alpha_composite(companion, layer)


def create(library):
    primary, companion = lighting_pair()
    options = {
        **DEFAULTS, "area": [0.047, 0.071, 0.951, 0.875],
        "reference": [[78/960, 582/620], [270/960, 582/620]],
    }
    tray = library.create("Pilot lot A", "synthetic-lot-a.png", png(primary), *primary.size,
                          options, synthetic=True)
    return library.attach(tray["id"], tray["revision"], "synthetic-lot-b.png",
                          png(companion), *companion.size)
