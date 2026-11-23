"""Separate the grain census from screen, coating and tray checks."""

from collections import Counter
import math

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


def slot_fit(length, width, axis, slot_length, slot_width):
    """Classify a grain against a slotted screen whose long side runs horizontally.

    Returns ("through", None) when the grain fits as it lies, ("turn", angle)
    with a usable long-axis bearing in degrees when a rotation makes it fit,
    and ("retained", None) when no bearing fits the slot.
    """
    a, b = max(length, width), min(length, width)

    def fits(bearing):
        c, s = math.cos(math.radians(bearing)), math.sin(math.radians(bearing))
        return a * c + b * s <= slot_length + 1e-9 and a * s + b * c <= slot_width + 1e-9

    if fits(axis):
        return "through", None
    step = 0.25
    feasible = [i * step for i in range(round(90 / step) + 1) if fits(i * step)]
    if not feasible:
        return "retained", None
    runs = []
    start = previous = feasible[0]
    for bearing in feasible[1:]:
        if bearing - previous > step * 1.5:
            runs.append((start, previous))
            start = bearing
        previous = bearing
    runs.append((start, previous))
    widest = max(runs, key=lambda run: (run[1] - run[0],
                                        -min(abs(axis - run[0]), abs(axis - run[1]))))
    return "turn", readable((widest[0] + widest[1]) / 2, 1)


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
    if mode == "slot":
        return slot_fit(part["length"], part["width"], part["axis"],
                        settings["slot_length_mm"], settings["slot_width_mm"])
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
    policy = settings.get("slot_policy", "dropped")
    for part in observation["candidates"]:
        kind = classification(part, settings)
        if kind == "grain" and not part["partial"]:
            grains.append(part)
        status, value = item_status(part, kind, mode, settings)
        counts[status] += 1
        row = {
            "id": part["id"], "box": list(part["box"]),
            "centre": [readable(n) for n in part["centre"]],
            "kind": kind, "status": status, "value": value,
            "area_mm2": readable(part["area"]), "width_mm": readable(part["width"]),
        }
        if mode == "slot":
            row["length_mm"] = None if part["partial"] else readable(part["length"])
            row["axis_deg"] = None if part["partial"] else readable(part["axis"], 1)
            row["turn_deg"] = value if status == "turn" else None
            if status in ("through", "turn", "retained"):
                adopted = status == "through" or (status == "turn" and policy == "turned")
                row["grade"] = "through" if adopted else "retained"
            else:
                row["grade"] = None
        rows.append(row)
    zones = region_counts(grains, observation["area"], observation["supported"], observation["scale"]) if mode == "zones" else []
    title = MODES[mode]
    adopted = None
    if mode == "slot":
        title += " · hand-turned" if policy == "turned" else " · as dropped"
        adopted = {"through": 0, "retained": 0}
        for row in rows:
            if row["grade"] in adopted:
                adopted[row["grade"]] += 1
    return {
        "mode": mode, "title": title, "area": list(observation["area"]),
        "mm_per_pixel": readable(observation["scale"], 6),
        "supported_pct": readable(100 * np.mean(observation["supported"]), 1),
        "visible_grains": len(grains), "counts": dict(counts), "rows": rows, "zones": zones,
        "adopted": adopted,
        "settings": settings,
    }
