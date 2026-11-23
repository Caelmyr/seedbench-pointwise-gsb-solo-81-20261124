"""Separate the grain census from screen, coating and tray checks."""

from collections import Counter

import cv2
import numpy as np

from .model import MODES


def classification(part, settings):
    red, green, blue = part["rgb"]
    if part["area"] < settings["min_seed_mm2"]:
        return "speck"
    if np.mean(part["rgb"]) > 175 and max(part["rgb"]) - min(part["rgb"]) < 22:
        return "foreign"
    if part["elongation"] > 4.6 and red - green < 30 and blue < green + 12:
        return "foreign"
    return "grain"


def coating(part, blue_margin):
    rgb = part["crop"].astype(np.int16)
    blue = (rgb[..., 2] - np.maximum(rgb[..., 0], rgb[..., 1])) >= blue_margin
    return 100 * float(np.count_nonzero(blue & part["mask"])) / part["pixels"]


def pale_marks(part, threshold):
    inside = cv2.erode(part["mask"].astype(np.uint8), np.ones((3, 3), np.uint8),
                       borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
    return int(np.count_nonzero((part["light"] >= threshold) & inside))


def readable(value, digits=2):
    return round(float(value), digits)


def region_counts(candidates, area, supported, scale):
    x0, y0, x1, y1 = area
    widths = np.linspace(x0, x1, 4).round().astype(int)
    heights = np.linspace(y0, y1, 4).round().astype(int)
    bins = []
    for row in range(3):
        for col in range(3):
            left, right = int(widths[col]), int(widths[col+1])
            top, bottom = int(heights[row]), int(heights[row+1])
            inside = [p for p in candidates if left <= p["centre"][0] < right
                      and top <= p["centre"][1] < bottom]
            observed = int(np.count_nonzero(supported[top-y0:bottom-y0, left-x0:right-x0]))
            area_cm2 = observed * scale * scale / 100
            bins.append({
                "id": f"{chr(65 + row)}{col+1}",
                "box": [left, top, right-left, bottom-top],
                "grains": len(inside),
                "observed_cm2": readable(area_cm2),
                "grains_per_cm2": readable(len(inside) / area_cm2) if area_cm2 else None,
            })
    return bins


def item_status(part, kind, mode, settings):
    if part["partial"]:
        return "partial", None
    if mode == "debris":
        return kind, readable(part["area"])
    if kind != "grain":
        return kind, None
    if mode == "grade":
        width = part["width"]
        return ("through" if width < settings["screen_mm"] else "retained"), readable(width)
    if mode == "coat":
        percent = coating(part, settings["blue_margin"])
        return ("coated" if percent >= 70 else "verify"), readable(percent, 1)
    if mode == "surface":
        pale = pale_marks(part, settings["pale_threshold"])
        return ("mark" if pale >= 5 else "clear"), pale
    return "grain", readable(part["area"])


def report(observation, mode, settings):
    counts = Counter()
    grains = []
    rows = []
    for part in observation["candidates"]:
        kind = classification(part, settings)
        if kind == "grain" and not part["partial"]:
            grains.append(part)
        status, value = item_status(part, kind, mode, settings)
        counts[status] += 1
        rows.append({
            "id": part["id"], "box": list(part["box"]),
            "centre": [readable(n) for n in part["centre"]],
            "kind": kind, "status": status, "value": value,
            "area_mm2": readable(part["area"]), "width_mm": readable(part["width"]),
        })
    zones = region_counts(grains, observation["area"], observation["supported"], observation["scale"]) if mode == "zones" else []
    return {
        "mode": mode, "title": MODES[mode], "area": list(observation["area"]),
        "mm_per_pixel": readable(observation["scale"], 6),
        "supported_pct": readable(100 * np.mean(observation["supported"]), 1),
        "visible_grains": len(grains), "counts": dict(counts), "rows": rows, "zones": zones,
        "settings": settings,
    }
