#!/usr/bin/env python3
"""
Render Figure1_layout_spec.json to editable SVG and PNG.

v4.3 adds node-class-aware text alignment defaults.

This is a compact renderer for the suite's standard node/edge schema.

Requirements for PNG rendering:
- cairosvg

Usage:
python render_layout_spec.py Figure1_layout_spec.json --svg out.svg --png out.png
python render_layout_spec.py Figure1_layout_spec.json --svg out.svg --png out_600dpi.png --final
"""

from __future__ import annotations
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

def text_baseline(y, h, n_lines, size, gap, shift=0):
    center = y + h / 2 + shift
    return center - ((n_lines - 1) * size * gap) / 2 + size * 0.34

def make_svg(spec):
    cw = spec["canvas"]["width_px"]
    ch = spec["canvas"]["height_px"]
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(cw),
            "height": str(ch),
            "viewBox": f"0 0 {cw} {ch}",
        },
    )

    defs = ET.SubElement(root, "defs")
    arrow_style = spec.get("styles", {}).get("arrowhead", {})
    arrow_len = float(arrow_style.get("length_px", 10.0))
    arrow_w = float(arrow_style.get("width_px", 8.0))
    marker_cache = {}

    def marker_for(color: str) -> str:
        # Arrowheads must match the connector stroke.  Build one marker per
        # distinct stroke color instead of using a fixed PowerPoint-like head.
        key = color.lower().replace("#", "")
        marker_id = f"arrow_{key}"
        if marker_id not in marker_cache:
            marker = ET.SubElement(
                defs,
                "marker",
                {
                    "id": marker_id,
                    "markerWidth": str(arrow_len),
                    "markerHeight": str(arrow_w),
                    "refX": str(arrow_len - 0.5),
                    "refY": str(arrow_w / 2),
                    "orient": "auto",
                    "markerUnits": "userSpaceOnUse",
                },
            )
            ET.SubElement(
                marker, "path",
                {"d": f"M0,0 L0,{arrow_w} L{arrow_len},{arrow_w/2} z", "fill": color},
            )
            marker_cache[marker_id] = True
        return marker_id

    ET.SubElement(
        root,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": str(cw),
            "height": str(ch),
            "fill": spec["canvas"].get("background", "#FFFFFF"),
        },
    )

    font_family = spec.get("styles", {}).get(
        "font_family", "Arial, Helvetica, sans-serif"
    )

    for edge in spec.get("edges", []):
        pts = edge["points"]
        attrs = {
            "points": " ".join(f"{x},{y}" for x, y in pts),
            "fill": "none",
            "stroke": edge.get("stroke", "#4F5B67"),
            "stroke-width": str(edge.get("stroke_width", spec.get("styles", {}).get("main_line", {}).get("width", 2.4))),
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "id": edge["id"],
        }
        if edge.get("dash"):
            attrs["stroke-dasharray"] = " ".join(map(str, edge["dash"]))
        if edge.get("arrow", False):
            marker_id = marker_for(attrs["stroke"])
            attrs["marker-end"] = f"url(#{marker_id})"
        ET.SubElement(root, "polyline", attrs)

    for node in spec.get("nodes", []):
        ET.SubElement(
            root,
            "rect",
            {
                "x": str(node["x"]),
                "y": str(node["y"]),
                "width": str(node["w"]),
                "height": str(node["h"]),
                "rx": str(node.get("radius", 18)),
                "ry": str(node.get("radius", 18)),
                "fill": node.get("fill", "#F6F7F9"),
                "stroke": node.get("stroke", "#98A2B1"),
                "stroke-width": str(node.get("stroke_width", 2)),
                "id": node["id"],
            },
        )

        for block in node.get("text_blocks", []):
            lines = block["lines"]
            size = float(block["font_size"])
            gap = float(block.get("line_gap", 1.15))

            # v4.3: information-rich cards default to one shared left anchor.
            # Older specs without node_class keep the historical centered default.
            node_class = node.get("node_class")
            align_policy = node.get("text_alignment")
            if align_policy is None:
                if node_class in {"information_card", "integration_card", "qualifier_card"}:
                    align_policy = "left"
                elif node_class in {"short_label", "cohort_banner", "external_capsule"}:
                    align_policy = "center"

            if align_policy == "left":
                pad_px = node.get("text_left_padding_px")
                if pad_px is None:
                    target_mm = float(spec.get("publication", {}).get("target_width_mm", 180))
                    pad_mm = float(spec.get("styles", {}).get("text_alignment", {}).get("left_padding_mm_target_low", 3.0))
                    pad_px = pad_mm / target_mm * float(cw)
                default_x = float(node["x"]) + float(pad_px)
                default_anchor = "start"
            else:
                default_x = float(node["x"]) + float(node["w"]) / 2
                default_anchor = "middle"

            x = float(block.get("x", default_x))
            y = float(
                block.get(
                    "y",
                    text_baseline(
                        node["y"], node["h"], len(lines), size, gap,
                        block.get("shift_y", 0)
                    ),
                )
            )
            resolved_anchor = block.get("text_anchor", default_anchor)
            if resolved_anchor == "left":
                resolved_anchor = "start"
            elif resolved_anchor in {"center", "centre"}:
                resolved_anchor = "middle"
            elif resolved_anchor == "right":
                resolved_anchor = "end"

            text = ET.SubElement(
                root,
                "text",
                {
                    "x": str(x),
                    "y": str(y),
                    "text-anchor": resolved_anchor,
                    "font-family": font_family,
                    "font-size": str(size),
                    "font-weight": str(block.get("font_weight", 400)),
                    "fill": block.get("fill", "#27323C"),
                    "id": block.get("id", f"{node['id']}_text"),
                },
            )
            for i, line in enumerate(lines):
                span = ET.SubElement(
                    text,
                    "tspan",
                    {
                        "x": str(x),
                        "dy": "0" if i == 0 else str(size * gap),
                    },
                )
                span.text = line

    return ET.tostring(root, encoding="unicode")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("layout_spec")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--png")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    spec = json.loads(Path(args.layout_spec).read_text(encoding="utf-8"))
    svg_text = make_svg(spec)
    Path(args.svg).write_text(svg_text, encoding="utf-8")

    if args.png:
        try:
            import cairosvg
        except ImportError:
            raise SystemExit("cairosvg is required for PNG rendering")

        if args.final:
            width_px = round(
                spec["publication"]["target_width_mm"]
                / 25.4
                * spec["publication"]["final_dpi"]
            )
            height_px = round(
                width_px
                * spec["canvas"]["height_px"]
                / spec["canvas"]["width_px"]
            )
        else:
            width_px = spec["canvas"]["width_px"]
            height_px = spec["canvas"]["height_px"]

        cairosvg.svg2png(
            url=args.svg,
            write_to=args.png,
            output_width=width_px,
            output_height=height_px,
        )

if __name__ == "__main__":
    main()
