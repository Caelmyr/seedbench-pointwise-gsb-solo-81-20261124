"""Input validation and the persisted grading settings."""

import math
from pathlib import Path
from uuid import uuid4

from image_lab.validation import Invalid

MODES = {
    "count": "Visible count",
    "grade": "Screen widths",
    "slot": "Slot screen",
    "coat": "Blue coating",
    "debris": "Foreign material",
    "surface": "Pale surface marks",
    "zones": "Tray density",
}

POLICIES = {
    "dropped": "Graded as dropped",
    "turned": "Hand-turned grains count through",
}

DEFAULTS = {
    "area": [0.045, 0.07, 0.955, 0.93],
    "reference": [[0.06, 0.97], [0.26, 0.97]],
    "reference_mm": 25,
    "threshold": 66,
    "min_seed_mm2": 2,
    "screen_mm": 4.4,
    "slot_length_mm": 6.5,
    "slot_width_mm": 3.5,
    "slot_policy": "dropped",
    "blue_margin": 15,
    "pale_threshold": 208,
}

MAX_PHOTOS = 24
MAX_PROOFS = 30
MAX_UPLOAD = 20 * 1024 * 1024
MAX_PIXELS = 9_000_000
MAX_SIDE = 4000


def identity():
    return uuid4().hex


def key(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise Invalid("This tray or saved check was not found.")
    return value


def document(value):
    if not isinstance(value, dict):
        raise Invalid("Enter the check settings first.")
    return value


def name(value, kind="tray name"):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        raise Invalid(f"Enter a {kind} between 1 and 100 characters.")
    return value.strip()


def filename(value):
    return name(Path(value or "photo.png").name[:100], "photo filename")


def number(value, label, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise Invalid(f"Enter {label} from {lower} to {upper}.")
    return value


def coordinates(values, length, label):
    if not isinstance(values, list) or len(values) != length:
        raise Invalid(f"Mark {label} on the photo.")
    return [number(value, label, 0, 1) for value in values]


def settings(values, base=None):
    value = {**DEFAULTS, **(base or {}), **document(values)}
    area = coordinates(value["area"], 4, "the inspection rectangle")
    if area[2] - area[0] < 0.025 or area[3] - area[1] < 0.025:
        raise Invalid("Draw a larger inspection rectangle.")
    reference = value["reference"]
    if not isinstance(reference, list) or len(reference) != 2:
        raise Invalid("Mark the two ends of the reference.")
    reference = [coordinates(pt, 2, "the ruler reference") for pt in reference]
    if math.dist(reference[0], reference[1]) < 0.01:
        raise Invalid("Mark two spaced ends of the reference.")
    slot_length = number(value["slot_length_mm"], "the slot length in mm", 0.1, 100)
    slot_width = number(value["slot_width_mm"], "the slot width in mm", 0.1, 100)
    if slot_length < slot_width:
        raise Invalid("Enter a slot length at least as large as the slot width.")
    if value.get("slot_policy") not in POLICIES:
        raise Invalid("Choose whether hand-turned grains count as through.")
    return {
        "area": area,
        "reference": reference,
        "reference_mm": number(value["reference_mm"], "the reference length in mm", 0.1, 1000),
        "threshold": number(value["threshold"], "the foreground brightness floor", 5, 250),
        "min_seed_mm2": number(value["min_seed_mm2"], "the minimum grain area in mm²", 0.05, 300),
        "screen_mm": number(value["screen_mm"], "the screen opening in mm", 0.1, 100),
        "slot_length_mm": slot_length,
        "slot_width_mm": slot_width,
        "slot_policy": value["slot_policy"],
        "blue_margin": number(value["blue_margin"], "the blue excess", 1, 150),
        "pale_threshold": number(value["pale_threshold"], "the pale mark brightness", 60, 250),
    }


def mode(value):
    if not isinstance(value, str) or value not in MODES:
        raise Invalid("Choose an available inspection view.")
    return value


def pixel_scale(settings, size):
    width, height = size
    first, last = settings["reference"]
    pixels = math.hypot((last[0] - first[0]) * width, (last[1] - first[1]) * height)
    if pixels < 2:
        raise Invalid("Mark a longer ruler segment.")
    return settings["reference_mm"] / pixels
