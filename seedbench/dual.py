"""Cross-check two aligned photos of one tray for the blue coating view."""

import cv2
import numpy as np

SPREAD_RATIO = 0.28      # low-colour pixels brighter than the glare floor read as glare
BLOWN_CHANNEL = 245      # pixels with every channel this high read as blown out
MIN_CLUSTER_MM2 = 0.08   # smallest cluster kept as exposed or recheck evidence
RECHECK_GRAIN = 0.55     # grains judgeable below this fraction stay for recheck
EXPOSED_MIN_MM2 = 0.3    # exposed call needs this much base-colour evidence ...
EXPOSED_MIN_FRACTION = 0.04  # ... or this share of the judgeable area


def reliable(view, settings):
    """Pixels whose colour reading can be trusted in one photo."""
    rgb = view["rgb"].astype(np.int16)
    light = view["light"].astype(np.int16)
    top = rgb.max(axis=2)
    spread = top - rgb.min(axis=2)
    glare = (light >= settings["glare_floor"]) & (spread <= SPREAD_RATIO * top)
    blown = rgb.min(axis=2) >= BLOWN_CHANNEL
    shadow = light <= settings["shadow_ceiling"]
    return view["supported"] & ~glare & ~blown & ~shadow


def blue_mask(rgb, margin):
    values = rgb.astype(np.int16)
    return (values[..., 2] - np.maximum(values[..., 0], values[..., 1])) >= margin


def evidence(mask, minimum):
    """Keep clusters with a solid core; thin rims and specks are not evidence."""
    core = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(mask.shape, bool)
    boxes = []
    for label in range(1, count):
        x, y, w, h, pixels = (int(value) for value in stats[label])
        if pixels < minimum:
            continue
        window = (slice(y, y + h), slice(x, x + w))
        selection = labels[window] == label
        if not np.any(core[window][selection]):
            continue
        keep[window][selection] = True
        boxes.append([x, y, w, h])
    return keep, boxes


def fuse(observation, companion, settings):
    """Fuse both readings inside the foreground mask of the tray photo.

    A pixel is judgeable when at least one photo reads it cleanly. Reliable
    base-colour in either photo counts as exposed evidence, so a true chip is
    not lost when the second lighting makes it look blue; glare and shadow
    pixels read as unreliable instead of as bare base.
    """
    foreground = (observation["light"] >= settings["threshold"]) & observation["supported"]
    sure = [reliable(view, settings) for view in (observation, companion)]
    judgeable = foreground & (sure[0] | sure[1])
    base = foreground & ((sure[0] & ~blue_mask(observation["rgb"], settings["blue_margin"]))
                         | (sure[1] & ~blue_mask(companion["rgb"], settings["blue_margin"])))
    minimum = max(3, round(MIN_CLUSTER_MM2 / (observation["scale"] ** 2)))
    exposed, _ = evidence(base, minimum)
    _, patches = evidence(foreground & ~judgeable, minimum)
    return {"judgeable": judgeable, "exposed": exposed, "patches": patches,
            "foreground": int(np.count_nonzero(foreground))}
