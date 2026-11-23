"""Build marked source images and printable check tables."""

import csv
from io import StringIO

from PIL import Image, ImageDraw

COLORS = {
    "grain": "#a3ed83", "retained": "#a3ed83", "coated": "#a3ed83", "clear": "#a3ed83",
    "through": "#62d3ed", "verify": "#ffc875", "mark": "#ffc875", "foreign": "#ff9176",
    "partial": "#e1c9f2", "speck": "#bcb6a1",
}

WINDOW_INKS = ("#54d1ff", "#ffb35c")
REVIEW_INK = "#ff5d8f"


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
    for zone in result["zones"]:
        x, y, w, h = zone["box"]
        draw.rectangle((x, y, x+w-1, y+h-1), outline="#ffe095", width=outline)
        label = f"{zone['id']}  {zone['grains']}"
        length = draw.textlength(label)
        draw.rectangle((x+1, y+1, x+int(length)+8, y+17), fill="#262617")
        draw.text((x+4, y+3), label, fill="#ffe095")
    for index, window in enumerate(result.get("windows", [])):
        x, y, w, h = window["box"]
        ink = WINDOW_INKS[index % len(WINDOW_INKS)]
        draw.rectangle((x, y, x+w-1, y+h-1), outline=ink, width=max(outline, 2))
        label = (f"{window['id']}  {window['grains']} grains · "
                 f"{window['observed_cm2']} cm²")
        length = draw.textlength(label)
        label_y = min(y + 2, image.size[1] - 18)
        draw.rectangle((x+2, label_y, x+int(length)+10, label_y+16), fill="#10212b")
        draw.text((x+5, label_y+2), label, fill=ink)
        for item in window.get("review", []):
            rx, ry, rw, rh = item["box"]
            draw.rectangle((rx, ry, rx+rw-1, ry+rh-1), outline=REVIEW_INK, width=max(outline, 2))
            tag = f"?{item['id']}"
            tag_w = draw.textlength(tag)
            draw.rectangle((rx, max(0, ry-13), rx+int(tag_w)+5, max(13, ry)), fill="#2b1320")
            draw.text((rx+2, max(0, ry-13)), tag, fill=REVIEW_INK)
    return image


def csv_text(result):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    if result["mode"] == "zones":
        writer.writerow(("zone", "grains", "observed_cm2", "grains_per_cm2", "x", "y", "width", "height"))
        for zone in result["zones"]:
            writer.writerow((zone["id"], zone["grains"], zone["observed_cm2"],
                             zone["grains_per_cm2"], *zone["box"]))
        windows = result.get("windows", [])
        if windows:
            summary = result.get("window_summary") or {}
            writer.writerow(())
            writer.writerow(("counting_window", "grains", "review_grains", "observed_cm2",
                             "supported_pct", "grains_per_cm2", "side_mm",
                             "x", "y", "width", "height"))
            for window in windows:
                writer.writerow((window["id"], window["grains"], window["review_grains"],
                                 window["observed_cm2"], window["supported_pct"],
                                 window["grains_per_cm2"], window["side_mm"], *window["box"]))
            writer.writerow(())
            writer.writerow(("two_window_summary", "combined_grains", "combined_cm2",
                             "combined_grains_per_cm2", "whole_tray_grains_per_cm2",
                             "deviation_pct", "center_distance_mm"))
            writer.writerow(("", summary.get("combined_grains"), summary.get("combined_cm2"),
                             summary.get("combined_per_cm2"), summary.get("tray_per_cm2"),
                             summary.get("deviation_pct"), summary.get("center_distance_mm")))
            writer.writerow(())
            writer.writerow(("window", "grain_id", "review_reason", "x", "y", "width", "height"))
            for window in windows:
                for item in window.get("review", []):
                    writer.writerow((window["id"], item["id"], item["reason"], *item["box"]))
    else:
        writer.writerow(("grain_id", "class", "status", "value", "area_mm2", "width_mm", "x", "y", "width", "height"))
        for row in result["rows"]:
            writer.writerow((row["id"], row["kind"], row["status"], row["value"],
                             row["area_mm2"], row["width_mm"], *row["box"]))
    return stream.getvalue()
