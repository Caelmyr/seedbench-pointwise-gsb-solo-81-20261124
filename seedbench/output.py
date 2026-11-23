"""Build marked source images and printable check tables."""

import csv
from io import StringIO

from PIL import Image, ImageDraw

COLORS = {
    "grain": "#a3ed83", "retained": "#a3ed83", "coated": "#a3ed83", "clear": "#a3ed83",
    "through": "#62d3ed", "verify": "#ffc875", "mark": "#ffc875", "foreign": "#ff9176",
    "partial": "#e1c9f2", "speck": "#bcb6a1", "split": "#62d3ed", "clump": "#ffc875",
}


def active_rows(result):
    if result["mode"] == "tally":
        return result["variants"][result.get("policy") or "cautious"]["rows"]
    return result["rows"]


def overlay(source, result, numbered=True):
    image = Image.new("RGBA", source.size, (24, 30, 28, 255))
    image.alpha_composite(source)
    draw = ImageDraw.Draw(image)
    outline = max(1, round(max(image.size) / 700))
    ax, ay, bx, by = result["area"]
    draw.rectangle((ax, ay, bx-1, by-1), outline="#e0d8ab", width=outline)
    for item in active_rows(result):
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
    else:
        writer.writerow(("grain_id", "class", "status", "value", "area_mm2", "width_mm", "x", "y", "width", "height"))
        for row in active_rows(result):
            writer.writerow((row["id"], row["kind"], row["status"], row["value"],
                             row["area_mm2"], row["width_mm"], *row["box"]))
    return stream.getvalue()
