"""Separate the grain census from screen, coating and tray checks."""

from collections import Counter

import cv2
import numpy as np

from . import dual
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


def exposed_marks(window, selection, offset):
    """Bounding boxes of the exposed-base clusters inside one grain."""
    found, _, stats, _ = cv2.connectedComponentsWithStats(
        (window & selection).astype(np.uint8), connectivity=8)
    marks = []
    for label in range(1, found):
        x, y, w, h, pixels = (int(value) for value in stats[label])
        if pixels >= 2:
            marks.append([x + offset[0], y + offset[1], w, h])
    return marks


def coat_reading(part, fused, observation, row):
    """Fill one grain row with judgeable area, coverage and exposed evidence."""
    scale = observation["scale"]
    x0, y0 = observation["area"][:2]
    bx, by, w, h = part["box"]
    window = (slice(by - y0, by - y0 + h), slice(bx - x0, bx - x0 + w))
    selection = part["mask"]
    judged = int(np.count_nonzero(fused["judgeable"][window][selection]))
    exposed = int(np.count_nonzero(fused["exposed"][window][selection]))
    total = part["pixels"]
    exposed_mm2 = exposed * scale * scale
    row["coverage"] = readable(100 * (judged - exposed) / judged, 1) if judged else None
    row["judgeable_mm2"] = readable(judged * scale * scale)
    row["exposed_mm2"] = readable(exposed_mm2)
    row["recheck_pct"] = readable(100 * (total - judged) / total, 1)
    row["marks"] = exposed_marks(fused["exposed"][window], selection, (bx, by))
    if judged < dual.RECHECK_GRAIN * total:
        return "recheck"
    if exposed_mm2 >= dual.EXPOSED_MIN_MM2 or exposed >= dual.EXPOSED_MIN_FRACTION * max(judged, 1):
        return "exposed"
    return "coated" if row["coverage"] >= 70 else "verify"


def dual_report(observation, settings, companion):
    """One coating check from two aligned photos of the same tray."""
    fused = dual.fuse(observation, companion, settings)
    x0, y0 = observation["area"][:2]
    counts = Counter()
    grains = []
    rows = []
    for part in observation["candidates"]:
        kind = classification(part, settings)
        row = {
            "id": part["id"], "box": list(part["box"]),
            "centre": [readable(n) for n in part["centre"]],
            "kind": kind, "area_mm2": readable(part["area"]),
            "width_mm": readable(part["width"]), "coverage": None,
            "judgeable_mm2": None, "exposed_mm2": None, "recheck_pct": None, "marks": [],
        }
        if kind == "grain" and not part["partial"]:
            grains.append(part)
            status = coat_reading(part, fused, observation, row)
        elif part["partial"]:
            status = "partial"
        else:
            status = kind
        row.update(status=status, value=row["coverage"])
        counts[status] += 1
        rows.append(row)
    judged = np.count_nonzero(fused["judgeable"])
    return {
        "mode": "coat", "title": MODES["coat"], "paired": True,
        "area": list(observation["area"]),
        "mm_per_pixel": readable(observation["scale"], 6),
        "supported_pct": readable(100 * np.mean(observation["supported"]), 1),
        "judged_pct": readable(100 * judged / fused["foreground"], 1) if fused["foreground"] else None,
        "visible_grains": len(grains), "counts": dict(counts), "rows": rows,
        "patches": [[x + x0, y + y0, w, h] for x, y, w, h in fused["patches"]],
        "zones": [], "settings": settings,
    }


def report(observation, mode, settings, companion=None):
    if mode == "coat" and companion is not None:
        return dual_report(observation, settings, companion)
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
