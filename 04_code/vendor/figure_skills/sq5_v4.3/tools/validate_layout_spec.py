#!/usr/bin/env python3
"""
Validate Figure1_layout_spec.json.

Checks:
- required fields
- unique node/edge IDs
- node bounds inside canvas
- known edge types
- qualifier_boundary has no arrow
- final publication font size
- rough text width and padding
- v4.3 node-class text-alignment policy
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import ImageFont
except Exception:
    ImageFont = None

KNOWN_EDGE_TYPES = {
    "main_flow",
    "parallel_evidence_branch",
    "evidence_convergence",
    "supportive_input",
    "qualifier_boundary",
    "context_link",
}

def font_width(text: str, font_px: float) -> float:
    if ImageFont is not None:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", max(1, round(font_px)))
            box = font.getbbox(text)
            return box[2] - box[0]
        except Exception:
            pass
    return len(text) * font_px * 0.58

def final_pt(font_px: float, width_mm: float, canvas_width_px: float) -> float:
    return font_px * width_mm / canvas_width_px / 25.4 * 72

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("layout_spec")
    parser.add_argument("--min-pt", type=float, default=7.5)
    parser.add_argument("--min-padding-mm", type=float, default=2.5)
    args = parser.parse_args()

    spec = json.loads(Path(args.layout_spec).read_text(encoding="utf-8"))
    canvas = spec["canvas"]
    cw = float(canvas["width_px"])
    ch = float(canvas["height_px"])
    target_mm = float(spec["publication"]["target_width_mm"])
    min_padding_px = args.min_padding_mm / target_mm * cw

    failures = []
    seen = set()

    nodes = spec.get("nodes", [])
    schema_version = str(spec.get("schema_version", "1.0"))
    try:
        schema_num = float(schema_version)
    except Exception:
        schema_num = 1.0
    allowed_node_classes = {
        "information_card", "short_label", "cohort_banner", "external_capsule",
        "integration_card", "qualifier_card"
    }
    text_align_style = spec.get("styles", {}).get("text_alignment", {})
    anchor_tol_mm = float(text_align_style.get("shared_anchor_tolerance_mm", 0.5))
    anchor_tol_px = anchor_tol_mm / target_mm * cw
    for node in nodes:
        node_id = node["id"]
        if node_id in seen:
            failures.append(f"Duplicate ID: {node_id}")
        seen.add(node_id)

        x, y = float(node["x"]), float(node["y"])
        w, h = float(node["w"]), float(node["h"])

        if x < 0 or y < 0 or x + w > cw or y + h > ch:
            failures.append(f"Node outside canvas: {node_id}")

        node_class = node.get("node_class")
        if schema_num >= 1.2:
            if node_class not in allowed_node_classes:
                failures.append(f"Missing/unknown node_class in schema v1.2+: {node_id}: {node_class}")

        blocks = node.get("text_blocks", [])
        if node_class in {"information_card", "integration_card", "qualifier_card"} and blocks:
            anchors = []
            for block in blocks:
                anchor = block.get("text_anchor", node.get("text_alignment", "left"))
                if anchor == "left":
                    anchor = "start"
                if anchor != "start":
                    failures.append(f"Information-card text must be left anchored: {node_id}/{block.get('id','text')}")
                if "x" in block:
                    anchors.append(float(block["x"]))
            if anchors and max(anchors) - min(anchors) > anchor_tol_px:
                failures.append(
                    f"Information-card text blocks do not share a left anchor within {anchor_tol_mm:.2f} mm: {node_id}"
                )

        for block in blocks:
            lines = block.get("lines", [])
            if "font_size" in block:
                sizes = [float(block["font_size"])] * max(1, len(lines))
            elif block.get("font_sizes"):
                raw_sizes = [float(v) for v in block.get("font_sizes", [])]
                if len(raw_sizes) == 1 and len(lines) > 1:
                    sizes = raw_sizes * len(lines)
                else:
                    sizes = raw_sizes
            else:
                failures.append(f"Missing font size: {node_id}/{block.get('id','text')}")
                continue

            if not sizes:
                continue
            for size in sizes:
                pt = final_pt(size, target_mm, cw)
                if pt < args.min_pt:
                    failures.append(
                        f"Font below minimum: {node_id}/{block.get('id','text')} = {pt:.2f} pt"
                    )

            for i, line in enumerate(lines):
                size = sizes[min(i, len(sizes)-1)]
                width = font_width(line, size)
                if width > w - 2 * min_padding_px:
                    failures.append(
                        f"Possible text overflow/padding failure: {node_id}: {line}"
                    )

    for edge in spec.get("edges", []):
        edge_id = edge["id"]
        if edge_id in seen:
            failures.append(f"Duplicate ID: {edge_id}")
        seen.add(edge_id)

        edge_type = edge.get("edge_type")
        if edge_type not in KNOWN_EDGE_TYPES:
            failures.append(f"Unknown edge type: {edge_id}: {edge_type}")

        if edge_type == "qualifier_boundary" and edge.get("arrow", False):
            failures.append(f"Qualifier boundary must not have arrow: {edge_id}")

    report = {
        "layout_spec": str(args.layout_spec),
        "hard_pass": not failures,
        "failures": failures,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if not failures else 2)

if __name__ == "__main__":
    main()
