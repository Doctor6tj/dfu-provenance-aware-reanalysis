#!/usr/bin/env python3
"""
Generate magnified hotspot crops from a rendered preview.

Automatically selects:
- nodes with 3+ text lines
- minimum-font nodes
- highest width-ratio nodes from an optional validation report
- user-specified node IDs

Usage:
python make_hotspot_crops.py layout.json preview.png out_dir
python make_hotspot_crops.py layout.json preview.png out_dir --node N9 --node N10
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("layout_spec")
    parser.add_argument("preview_png")
    parser.add_argument("output_dir")
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--margin", type=int, default=36)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    spec = json.loads(Path(args.layout_spec).read_text(encoding="utf-8"))
    image = Image.open(args.preview_png).convert("RGB")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    selected = set(args.node)
    min_font = None

    for node in spec.get("nodes", []):
        for block in node.get("text_blocks", []):
            sizes = block.get("font_sizes", [])
            if sizes:
                local_min = min(sizes)
                min_font = local_min if min_font is None else min(min_font, local_min)
            if len(block.get("lines", [])) >= 3:
                selected.add(node["id"])

    if min_font is not None:
        for node in spec.get("nodes", []):
            for block in node.get("text_blocks", []):
                if min(block.get("font_sizes", [999])) == min_font:
                    selected.add(node["id"])

    manifest = []

    for node in spec.get("nodes", []):
        if node["id"] not in selected:
            continue

        x0 = max(0, round(node["x"] - args.margin))
        y0 = max(0, round(node["y"] - args.margin))
        x1 = min(image.width, round(node["x"] + node["w"] + args.margin))
        y1 = min(image.height, round(node["y"] + node["h"] + args.margin))

        crop = image.crop((x0, y0, x1, y1))
        if args.scale != 1:
            crop = crop.resize(
                (round(crop.width * args.scale), round(crop.height * args.scale)),
                Image.Resampling.LANCZOS,
            )

        crop = ImageOps.expand(crop, border=2, fill="black")
        filename = f"hotspot_{node['id']}.png"
        crop.save(out / filename)

        manifest.append({
            "node": node["id"],
            "file": filename,
            "source_box": [x0, y0, x1, y1],
        })

    (out / "hotspot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "output_dir": str(out),
        "hotspots": manifest,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
