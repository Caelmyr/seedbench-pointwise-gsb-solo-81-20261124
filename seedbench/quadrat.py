"""Two non-overlapping counting windows for the tray density view.

A window is a square quadrat of a user-given physical side.  Black tray
background counts as observed (empty) area, while pixels without photo
support do not.  Grains cut by a window edge or already partial because of
missing image support are listed for review and never counted as complete.
"""

import math

import cv2
import numpy as np

from image_lab.validation import Invalid

from .inspection import classification, readable

SIDE_MIN_MM = 1.0
SIDE_MAX_MM = 500.0
MIN_SUPPORT = 0.5
MAX_GRID = 27
DEVIATION_BAND = 0.05
WINDOW_IDS = ("W1", "W2")


def side_mm_value(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Invalid("Enter the quadrat side length in millimetres.")
    if not SIDE_MIN_MM <= float(value) <= SIDE_MAX_MM:
        raise Invalid(f"Enter a quadrat side from {SIDE_MIN_MM:g} to {SIDE_MAX_MM:g} mm.")
    return float(value)


def complete_grains(observation, settings):
    return [part for part in observation["candidates"]
            if classification(part, settings) == "grain" and not part["partial"]]


def candidate_grid(span, side):
    """Window start positions along one axis, always including the far edge."""
    limit = span - side
    step = max(1, math.ceil(limit / (MAX_GRID - 1)))
    return np.unique(np.append(np.arange(0, limit + 1, step), limit)).astype(int)


def suggest(observation, settings, side_mm):
    scale = observation["scale"]
    x0, y0, x1, y1 = observation["area"]
    width, height = x1 - x0, y1 - y0
    side = int(round(side_mm / scale))
    fit_mm = min(width, height) * scale
    if side < 2 or side > min(width, height):
        raise Invalid(f"Enter a quadrat side that fits the inspection rectangle "
                      f"(at most {readable(fit_mm, 1)} mm here).")

    grains = complete_grains(observation, settings)
    support = observation["supported"].astype(np.uint8)
    supported_px = int(np.count_nonzero(support))
    if not grains or supported_px == 0:
        raise Invalid("No complete grains are visible on supported photo area; "
                      "adjust the inspection settings before sampling windows.")
    px_to_cm2 = scale * scale / 100
    tray_density = len(grains) / (supported_px * px_to_cm2)

    xs = candidate_grid(width, side)
    ys = candidate_grid(height, side)
    integral = cv2.integral(support)

    # Exact supported-pixel rectangle sums from the integral image.
    support_grid = np.empty((len(ys), len(xs)), dtype=np.int64)
    for j, top in enumerate(ys):
        for i, left in enumerate(xs):
            support_grid[j, i] = int(
                integral[top + side, left + side] - integral[top, left + side]
                - integral[top + side, left] + integral[top, left])
    support_fraction = support_grid / float(side * side)

    local = np.array([_local_box(part, observation["area"]) for part in grains], dtype=float)
    gl, gt, gw, gh = local.T
    gr, gb = gl + gw - 1, gt + gh - 1
    left_ok = (xs[:, None] <= gl[None, :]) & (xs[:, None] + side - 1 >= gr[None, :])
    top_ok = (ys[:, None] <= gt[None, :]) & (ys[:, None] + side - 1 >= gb[None, :])
    counts = np.einsum("ig,jg->ji", left_ok.astype(np.uint8), top_ok.astype(np.uint8))

    valid = support_fraction >= MIN_SUPPORT
    positions = np.argwhere(valid)
    if len(positions) < 2:
        raise Invalid("Not enough well-supported room for two windows of this side; "
                      "use a smaller quadrat.")
    jj, ii = positions[:, 0], positions[:, 1]
    lefts, tops = xs[ii], ys[jj]
    cand_counts = counts[jj, ii].astype(float)
    cand_area = support_grid[jj, ii] * px_to_cm2

    first, second = np.triu_indices(len(positions), k=1)
    apart = (np.abs(lefts[first] - lefts[second]) >= side) | \
            (np.abs(tops[first] - tops[second]) >= side)
    first, second = first[apart], second[apart]
    if not len(first):
        raise Invalid("No room for two non-overlapping windows of this side; "
                      "use a smaller quadrat.")

    combined_area = cand_area[first] + cand_area[second]
    combined_counts = cand_counts[first] + cand_counts[second]
    populated = combined_counts > 0
    first, second = first[populated], second[populated]
    if not len(first):
        raise Invalid("Windows this small contain no complete grains together; "
                      "enter a larger quadrat side.")
    combined_area = cand_area[first] + cand_area[second]
    combined_density = (cand_counts[first] + cand_counts[second]) / combined_area
    deviation = combined_density / tray_density - 1.0
    diagonal = math.hypot(width, height)
    distance = np.hypot(lefts[first] - lefts[second], tops[first] - tops[second]) / diagonal

    abs_dev = np.abs(deviation)
    band = abs_dev <= max(abs_dev.min(), DEVIATION_BAND)
    chosen = int(np.argmax(np.where(band, distance, -1.0)))
    f, s = int(first[chosen]), int(second[chosen])
    placements = [(int(lefts[f]), int(tops[f])), (int(lefts[s]), int(tops[s]))]
    return build(observation, settings, side, placements, side_mm, tray_density)


def _local_box(part, area):
    x, y, w, h = part["box"]
    return x - area[0], y - area[1], w, h


def reading(observation, settings, left, top, side, label):
    x0, y0, x1, y1 = observation["area"]
    right, bottom = left + side, top + side
    if left < 0 or top < 0 or right > x1 - x0 or bottom > y1 - y0:
        raise Invalid("A saved window no longer fits the inspection rectangle. "
                      "Redraw the rectangle or choose new windows.")
    scale = observation["scale"]
    supported = int(np.count_nonzero(observation["supported"][top:bottom, left:right]))
    complete = []
    review = []
    for part in observation["candidates"]:
        l, t, w, h = _local_box(part, observation["area"])
        r, b = l + w, t + h
        if r <= left or l >= right or b <= top or t >= bottom:
            continue
        if classification(part, settings) != "grain":
            continue
        inside = l >= left and t >= top and r <= right and b <= bottom
        if inside and not part["partial"]:
            complete.append(part)
            continue
        reason = "edge" if not inside else "partial"
        review.append({"id": part["id"], "box": [int(v) for v in part["box"]], "reason": reason})
    area_cm2 = supported * scale * scale / 100
    return {
        "id": label,
        "box": [x0 + left, y0 + top, side, side],
        "side_mm": readable(side * scale, 2),
        "grains": len(complete),
        "review_grains": len(review),
        "review": review,
        "observed_cm2": readable(area_cm2),
        "supported_pct": readable(100 * supported / (side * side), 1),
        "grains_per_cm2": readable(len(complete) / area_cm2) if area_cm2 else None,
    }


def build(observation, settings, side, placements, requested_side_mm, tray_density=None):
    windows = [reading(observation, settings, left, top, side, label)
               for (left, top), label in zip(placements, WINDOW_IDS)]
    total_grains = sum(w["grains"] for w in windows)
    total_area = sum(w["observed_cm2"] for w in windows)
    if tray_density is None:
        supported_px = int(np.count_nonzero(observation["supported"]))
        tray_density = len(complete_grains(observation, settings)) / \
            (supported_px * observation["scale"] ** 2 / 100) if supported_px else None
    combined = total_grains / total_area if total_area else None
    centers = [((w["box"][0] + w["box"][2] / 2), (w["box"][1] + w["box"][3] / 2)) for w in windows]
    distance_mm = math.hypot(centers[0][0] - centers[1][0], centers[0][1] - centers[1][1]) * \
        observation["scale"]
    summary = {
        "side_mm": readable(side * observation["scale"], 2),
        "requested_side_mm": readable(requested_side_mm, 2) if requested_side_mm is not None else None,
        "combined_grains": total_grains,
        "combined_cm2": readable(total_area),
        "combined_per_cm2": readable(combined) if combined is not None else None,
        "tray_per_cm2": readable(tray_density) if tray_density is not None else None,
        "deviation_pct": readable(100 * (combined / tray_density - 1))
        if combined is not None and tray_density else None,
        "center_distance_mm": readable(distance_mm, 1),
        "min_supported_pct": readable(100 * MIN_SUPPORT, 1),
    }
    return {"windows": windows, "window_summary": summary}


def parse_windows(value, observation):
    """Validate adopted window boxes and return local (left, top, side) placements."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise Invalid("Adopt exactly the two suggested windows.")
    x0, y0, x1, y1 = observation["area"]
    width, height = x1 - x0, y1 - y0
    placements = []
    sides = []
    declared_sides = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("box"), list) or len(item["box"]) != 4:
            raise Invalid("Each adopted window needs a pixel box.")
        try:
            coords = [float(v) for v in item["box"]]
        except (TypeError, ValueError) as error:
            raise Invalid("Window boxes must be pixel coordinates.") from error
        if not all(math.isfinite(v) for v in coords):
            raise Invalid("Window boxes must be finite pixel coordinates.")
        left, top, w, h = (int(round(v)) for v in coords)
        if w != h or w < 2 or left < x0 or top < y0 or left + w > x1 or top + h > y1:
            raise Invalid("An adopted window must be a square inside the inspection rectangle.")
        local = (left - x0, top - y0)
        placements.append(local)
        sides.append(w)
        declared_sides.append(item.get("side_mm"))
    if sides[0] != sides[1]:
        raise Invalid("The two windows must share one side length.")
    side = sides[0]
    (l1, t1), (l2, t2) = placements
    if not (abs(l1 - l2) >= side or abs(t1 - t2) >= side):
        raise Invalid("The two windows overlap; keep them apart.")
    expected_mm = side * observation["scale"]
    for declared in declared_sides:
        if type(declared) in (int, float) and math.isfinite(float(declared)):
            if abs(float(declared) - expected_mm) > max(0.5, 0.05 * expected_mm):
                raise Invalid("The window side does not match the current ruler calibration.")
    return [(l, t, side) for l, t in placements]
