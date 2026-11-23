"""Build marked source images and printable check tables."""

import csv
from io import StringIO
import math

from PIL import Image, ImageDraw

COLORS = {
    "grain": "#a3ed83", "retained": "#a3ed83", "coated": "#a3ed83", "clear": "#a3ed83",
    "through": "#62d3ed", "verify": "#ffc875", "mark": "#ffc875", "turn": "#ffc875",
    "foreign": "#ff9176", "partial": "#e1c9f2", "speck": "#bcb6a1",
}


def turn_marks(draw, result, outline):
    """Underline turnable grains with the bearing that fits the slot."""
    scale = result.get("mm_per_pixel") or 1
    for item in result["rows"]:
        if item["status"] != "turn" or item.get("turn_deg") is None:
            continue
        cx, cy = item["centre"]
        half = (item.get("length_mm") or 0) / scale / 2
        if half <= 0:
            continue
        theta = math.radians(item["turn_deg"])
        dx, dy = half * math.cos(theta), half * math.sin(theta)
        ends = (cx - dx, cy - dy, cx + dx, cy + dy)
        draw.line(ends, fill="#1d221d", width=outline + 2)
        draw.line(ends, fill="#f5f2e8", width=outline)


def overlay(source, result, numbered=True):
    image = Image.new("RGBA", source.size, (24, 30, 28, 255))
    image.alpha_composite(source)
    draw = ImageDraw.Draw(image)
    outline = max(1, round(max(image.size) / 700))
    ax, ay, bx, by = result["area"]
    draw.rectangle((ax, ay, bx-1, by-1), outline="#e0d8ab", width=outline)
    for item in result["rows"]:
        if item["status"] == "speck" and result["mode"] != "debris":
            continue
        x, y, w, h = item["box"]
        ink = COLORS[item["status"]]
        draw.rectangle((x, y, x+w-1, y+h-1), outline=ink, width=outline)
        if numbered:
            text = str(item["id"])
            label_y = max(0, y-13)
            label = draw.textbbox((x+1, label_y), text)
            draw.rectangle((x, label_y, label[2]+1, label[3]+1), fill="#1d221d")
            draw.text((x+1, label_y), text, fill=ink)
    if result["mode"] == "slot":
        turn_marks(draw, result, outline)
    for zone in result["zones"]:
        x, y, w, h = zone["box"]
        draw.rectangle((x, y, x+w-1, y+h-1), outline="#ffe095", width=outline)
        label = f"{zone['id']}  {zone['grains']}"
        length = draw.textlength(label)
        draw.rectangle((x+1, y+1, x+int(length)+8, y+17), fill="#262617")
        draw.text((x+4, y+3), label, fill="#ffe095")
    return image


def csv_text(result):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    if result["mode"] == "zones":
        writer.writerow(("zone", "grains", "observed_cm2", "grains_per_cm2", "x", "y", "width", "height"))
        for zone in result["zones"]:
            writer.writerow((zone["id"], zone["grains"], zone["observed_cm2"],
                             zone["grains_per_cm2"], *zone["box"]))
    elif result["mode"] == "slot":
        writer.writerow(("grain_id", "class", "status", "adopted", "turn_deg", "axis_deg",
                         "length_mm", "width_mm", "area_mm2", "x", "y", "width", "height"))
        for row in result["rows"]:
            writer.writerow((row["id"], row["kind"], row["status"], row.get("grade"),
                             row.get("turn_deg"), row.get("axis_deg"), row.get("length_mm"),
                             row["width_mm"], row["area_mm2"], *row["box"]))
    else:
        writer.writerow(("grain_id", "class", "status", "value", "area_mm2", "width_mm", "x", "y", "width", "height"))
        for row in result["rows"]:
            writer.writerow((row["id"], row["kind"], row["status"], row["value"],
                             row["area_mm2"], row["width_mm"], *row["box"]))
    return stream.getvalue()
