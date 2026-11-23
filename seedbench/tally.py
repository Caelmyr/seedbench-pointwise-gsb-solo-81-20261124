"""Split lightly touching grains and set aside clumps that need a new photo."""

from string import ascii_lowercase

import cv2
import numpy as np

from .inspection import classification, readable
from .model import MODES
from .photo import narrow_width

AREA_RATIO = 1.6
PLUMP_AREA_RATIO = 1.15
PLUMP_WIDTH_RATIO = 1.45
MAX_PARTS = 6

RULES = {
    "cautious": {"erosion": 0.22, "min_part": 0.45, "max_part": 1.9, "max_width": 1.35},
    "thorough": {"erosion": 0.36, "min_part": 0.35, "max_part": 2.4, "max_width": None},
}


def typical_size(grains):
    """Estimate the single-grain area and narrow width from the clearer regions."""
    areas = sorted(part["area"] for part in grains)
    median = areas[len(areas) // 2]
    singles = [part for part in grains if part["area"] <= AREA_RATIO * median] or grains
    return (float(np.median([part["area"] for part in singles])),
            float(np.median([part["width"] for part in singles])))


def suspect(part, typical_area, typical_width):
    if part["area"] > AREA_RATIO * typical_area:
        return True
    return (part["area"] > PLUMP_AREA_RATIO * typical_area
            and part["width"] > PLUMP_WIDTH_RATIO * typical_width)


def split_region(part, scale, typical_area, typical_width, rules):
    """Return single-grain pieces when the region separates under this policy."""
    mask = part["mask"].astype(np.uint8)
    radius = max(1, round(rules["erosion"] * typical_width / scale))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    eroded = cv2.erode(mask, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0)
    count, labels = cv2.connectedComponents(eroded, connectivity=8)
    if not 2 <= count - 1 <= MAX_PARTS:
        return None
    best = np.full(mask.shape, np.inf)
    assign = np.zeros(mask.shape, np.int32)
    for core in range(1, count):
        dist = cv2.distanceTransform((labels != core).astype(np.uint8), cv2.DIST_L2, 3)
        closer = dist < best
        best[closer] = dist[closer]
        assign[closer] = core
    pieces = []
    for core in range(1, count):
        region = (assign == core) & (mask > 0)
        pixels = int(np.count_nonzero(region))
        if pixels < 4:
            return None
        ys, xs = np.nonzero(region)
        component = np.zeros(mask.shape, np.uint8)
        component[region] = 1
        pieces.append({
            "area": pixels * scale * scale,
            "width": narrow_width(component) * scale,
            "box": (int(xs.min()), int(ys.min()),
                    int(xs.max()) - int(xs.min()) + 1, int(ys.max()) - int(ys.min()) + 1),
            "centre": (float(xs.mean()), float(ys.mean())),
        })
    areas = [piece["area"] for piece in pieces]
    if min(areas) < rules["min_part"] * typical_area or max(areas) > rules["max_part"] * typical_area:
        return None
    if (rules["max_width"] is not None
            and max(piece["width"] for piece in pieces) > rules["max_width"] * typical_width):
        return None
    return pieces


def build_variant(candidates, settings, rules, typical, scale):
    typical_area, typical_width = typical
    rows = []
    confirmed = singles = split = clumps = 0
    for part in candidates:
        kind = classification(part, settings)
        row = {
            "id": part["id"], "box": list(part["box"]),
            "centre": [readable(n) for n in part["centre"]],
            "kind": kind, "area_mm2": readable(part["area"]), "width_mm": readable(part["width"]),
        }
        if part["partial"] or kind != "grain":
            row.update(status="partial" if part["partial"] else kind, value=None)
            rows.append(row)
            continue
        if not suspect(part, typical_area, typical_width):
            row.update(status="grain", value=readable(part["area"]))
            rows.append(row)
            singles += 1
            confirmed += 1
            continue
        pieces = split_region(part, scale, typical_area, typical_width, rules)
        if pieces is None:
            row.update(status="clump", value=max(2, round(part["area"] / typical_area)))
            rows.append(row)
            clumps += 1
            continue
        x0, y0 = part["box"][:2]
        for letter, piece in zip(ascii_lowercase, pieces):
            bx, by, bw, bh = piece["box"]
            rows.append({
                "id": f"{part['id']}{letter}",
                "box": [bx + x0, by + y0, bw, bh],
                "centre": [readable(piece["centre"][0] + x0), readable(piece["centre"][1] + y0)],
                "kind": "grain", "status": "split",
                "value": readable(piece["area"]),
                "area_mm2": readable(piece["area"]), "width_mm": readable(piece["width"]),
            })
            split += 1
            confirmed += 1
    return {"confirmed": confirmed, "singles": singles, "split": split,
            "clumps": clumps, "rows": rows}


def report(observation, settings, policy=None):
    grains = [part for part in observation["candidates"]
              if classification(part, settings) == "grain" and not part["partial"]]
    typical = typical_size(grains) if grains else (1.0, 1.0)
    variants = {
        name: build_variant(observation["candidates"], settings, rules, typical, observation["scale"])
        for name, rules in RULES.items()
    }
    return {
        "mode": "tally", "title": MODES["tally"], "area": list(observation["area"]),
        "mm_per_pixel": readable(observation["scale"], 6),
        "supported_pct": readable(100 * np.mean(observation["supported"]), 1),
        "policy": policy, "variants": variants, "zones": [],
        "settings": settings,
    }
