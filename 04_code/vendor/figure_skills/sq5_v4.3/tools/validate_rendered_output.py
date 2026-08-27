#!/usr/bin/env python3
"""
Real-font horizontal and vertical text-fit validation.

Reads a Figure1 layout specification and measures every line with PIL using
regular/bold fonts. Checks safe width and complete text-block height.

Usage:
python validate_rendered_output.py Figure1_layout_spec.json
python validate_rendered_output.py Figure1_layout_spec.json \
  --regular-font /path/Arial.ttf --bold-font /path/Arial-Bold.ttf
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEFAULT_REGULAR = "/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf"
DEFAULT_BOLD = "/usr/share/fonts/truetype/croscore/Arimo-Bold.ttf"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("layout_spec")
    parser.add_argument("--regular-font", default=DEFAULT_REGULAR)
    parser.add_argument("--bold-font", default=DEFAULT_BOLD)
    parser.add_argument("--horizontal-padding", type=float, default=24.0)
    parser.add_argument("--vertical-padding", type=float, default=12.0)
    parser.add_argument("--report")
    args = parser.parse_args()

    spec = json.loads(Path(args.layout_spec).read_text(encoding="utf-8"))
    scratch = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(scratch)

    failures = []
    rows = []

    for node in spec.get("nodes", []):
        safe_width = float(node["w"]) - 2 * args.horizontal_padding
        safe_height = float(node["h"]) - 2 * args.vertical_padding

        for block in node.get("text_blocks", []):
            lines = block.get("lines", [])
            sizes = block.get("font_sizes", [block.get("font_size", 28)] * len(lines))
            weights = block.get("font_weights", block.get("font_weight", [400] * len(lines)))
            if isinstance(weights, (int, float, str)):
                weights = [weights] * len(lines)

            widths = []
            heights = []

            for line, size, weight in zip(lines, sizes, weights):
                font_path = args.bold_font if float(weight) >= 700 else args.regular_font
                font = ImageFont.truetype(font_path, round(float(size)))
                bbox = draw.textbbox((0, 0), line, font=font)
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                widths.append(width)
                heights.append(height)

                if width > safe_width:
                    failures.append(
                        f"{node['id']}: horizontal overflow: "
                        f"{width}px > {safe_width:.1f}px | {line}"
                    )

            gaps = block.get(
                "line_gaps",
                block.get("line_gaps_px", [8] * max(0, len(lines) - 1))
            )
            text_height = sum(heights) + sum(float(g) for g in gaps)

            if text_height > safe_height:
                failures.append(
                    f"{node['id']}: vertical overflow: "
                    f"{text_height}px > {safe_height:.1f}px"
                )

            rows.append({
                "node": node["id"],
                "block": block.get("id", ""),
                "max_line_width": max(widths) if widths else 0,
                "safe_width": safe_width,
                "text_height": text_height,
                "safe_height": safe_height,
                "line_gaps": gaps,
            })

    result = {
        "layout_spec": str(args.layout_spec),
        "hard_pass": not failures,
        "failures": failures,
        "measurements": rows,
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)

    if args.report:
        Path(args.report).write_text(output, encoding="utf-8")

    raise SystemExit(0 if not failures else 2)

if __name__ == "__main__":
    main()
