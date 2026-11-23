"""Photo decoding, foreground support and calibrated connected regions."""

from io import BytesIO
import math

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from image_lab.validation import Invalid

from .model import MAX_PIXELS, MAX_SIDE, MAX_UPLOAD, pixel_scale


def decode(data):
    if not data or len(data) > MAX_UPLOAD:
        raise Invalid("Choose a photo smaller than 20 MiB.")
    try:
        with Image.open(BytesIO(data)) as src:
            if src.format not in {"PNG", "JPEG", "WEBP"} or getattr(src, "n_frames", 1) != 1:
                raise Invalid("Use a single PNG, JPEG or WebP photo.")
            if src.width * src.height > MAX_PIXELS or max(src.size) > MAX_SIDE or min(src.size) < 40:
                raise Invalid("Use a photo 40–4000 pixels per side and at most 9 megapixels.")
            return ImageOps.exif_transpose(src).convert("RGBA")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
        raise Invalid("This upload could not be decoded as a photo.") from error


def png(image):
    data = BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def photo_box(frame, size):
    width, height = size
    x0, y0, x1, y1 = frame
    return (math.floor(x0 * width), math.floor(y0 * height),
            min(width, math.ceil(x1 * width)), min(height, math.ceil(y1 * height)))


def narrow_width(component):
    points = cv2.findNonZero(component.astype(np.uint8))
    if points is None or len(points) < 3:
        return 1.0
    return float(min(cv2.minAreaRect(points)[1])) + 1.0


def luminance(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def frame_view(image, settings):
    """Crop an aligned same-size companion photo to the inspection rectangle."""
    x0, y0, x1, y1 = photo_box(settings["area"], image.size)
    frame = np.asarray(image)[y0:y1, x0:x1]
    rgb = frame[..., :3].copy()
    return {"rgb": rgb, "light": luminance(rgb), "supported": frame[..., 3] >= 205}


def observe(image, settings):
    """Return source-coordinate grain candidates inside the inspection rectangle."""
    scale = pixel_scale(settings, image.size)
    x0, y0, x1, y1 = photo_box(settings["area"], image.size)
    frame = np.asarray(image)[y0:y1, x0:x1]
    rgb = frame[..., :3].copy()
    supported = frame[..., 3] >= 205
    light = luminance(rgb)
    mask = (light >= settings["threshold"]) & supported
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if count > 30_001:
        raise Invalid("Too many foreground flecks. Raise the brightness floor or reduce the inspection area.")

    candidates = []
    minimum_pixels = max(4, math.ceil(0.15 / (scale * scale)))
    inner = cv2.erode(supported.astype(np.uint8), np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT)
    for label in range(1, count):
        x, y, w, h, pixels = map(int, stats[label])
        if pixels < minimum_pixels:
            continue
        if len(candidates) >= 600:
            raise Invalid("Inspect at most 600 visible objects per photo. Reduce the area or raise the brightness floor.")
        selection = labels[y:y+h, x:x+w] == label
        boundary = x == 0 or y == 0 or x+w == mask.shape[1] or y+h == mask.shape[0]
        partial = bool(boundary or np.any(inner[y:y+h, x:x+w][selection] == 0))
        candidate_rgb = rgb[y:y+h, x:x+w]
        crop_light = light[y:y+h, x:x+w]
        average = candidate_rgb[selection].mean(axis=0)
        cx, cy = centers[label]
        candidates.append({
            "id": len(candidates) + 1,
            "box": (x+x0, y+y0, w, h),
            "centre": (float(cx+x0), float(cy+y0)),
            "pixels": pixels,
            "area": pixels * scale * scale,
            "width": narrow_width(selection) * scale,
            "elongation": max(w, h) / max(1, min(w, h)),
            "rgb": tuple(map(float, average)),
            "mask": selection,
            "crop": candidate_rgb,
            "light": crop_light,
            "partial": partial,
        })
    return {"scale": scale, "area": (x0, y0, x1, y1), "rgb": rgb,
            "candidates": candidates, "supported": supported, "light": light}
