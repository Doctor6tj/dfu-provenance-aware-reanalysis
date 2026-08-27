#!/usr/bin/env python3
"""
Validate publication-style visual grammar for Figure1_layout_spec.json.

This complements scientific/layout validation. It focuses on the v4.3 default
`minimal_journal_workflow` profile and reports hard failures plus warnings.

Checks that can be automated without guessing semantic layers:
- no orphan node top accent/cap line in minimal profile
- no decorative section underline in minimal profile
- canvas outer margins around nodes at final publication width
- stroke weights converted to final pt
- arrowhead physical size
- information-card text alignment and shared left anchors

Layer spacing, connector/header clearance, sibling centering, and color semantics
remain mandatory rendered-output QC items unless the project spec explicitly
encodes layer/section metadata.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def px_to_mm(px: float, width_mm: float, canvas_width_px: float) -> float:
    return px * width_mm / canvas_width_px


def px_to_pt(px: float, width_mm: float, canvas_width_px: float) -> float:
    return px_to_mm(px, width_mm, canvas_width_px) / 25.4 * 72.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("layout_spec")
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()

    spec = json.loads(Path(args.layout_spec).read_text(encoding="utf-8"))
    canvas = spec.get("canvas", {})
    pub = spec.get("publication", {})
    styles = spec.get("styles", {})
    profile = args.profile or styles.get("profile", "minimal_journal_workflow")

    cw = float(canvas.get("width_px", 1900))
    ch = float(canvas.get("height_px", 1000))
    width_mm = float(pub.get("target_width_mm", 180))
    mm_per_px = width_mm / cw

    failures: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, object] = {}

    if profile == "minimal_journal_workflow":
        nd = styles.get("node_defaults", {})
        if nd.get("top_accent_line", False):
            failures.append("minimal_journal_workflow forbids orphan node top accent/cap lines")
        if nd.get("header_mode") not in (None, "plain"):
            warnings.append("non-plain node header mode: verify that this is a true full header band, not a cap line")

        sh = styles.get("section_header", {})
        if sh.get("underline", False) or sh.get("decorative_rule", False):
            failures.append("minimal_journal_workflow forbids decorative section underlines/rules by default")

    nodes = spec.get("nodes", [])
    if profile == "minimal_journal_workflow":
        for n in nodes:
            if n.get("top_accent_line", False):
                failures.append(f"node {n.get('id','?')} has an orphan top accent/cap line")

    # v4.3 information-card alignment rule.
    align_style = styles.get("text_alignment", {})
    anchor_tol_mm = float(align_style.get("shared_anchor_tolerance_mm", 0.5))
    for n in nodes:
        nclass = n.get("node_class")
        if nclass not in {"information_card", "integration_card", "qualifier_card"}:
            continue
        blocks = n.get("text_blocks", [])
        xs = []
        for b in blocks:
            anchor = b.get("text_anchor", n.get("text_alignment", "left"))
            if anchor == "left":
                anchor = "start"
            if anchor != "start":
                failures.append(f"{n.get('id','?')} is an information card but contains non-left-anchored text")
            if "x" in b:
                xs.append(float(b["x"]))
        if xs:
            spread_mm = (max(xs)-min(xs))*mm_per_px
            if spread_mm > anchor_tol_mm:
                failures.append(f"{n.get('id','?')} text anchors differ by {spread_mm:.2f} mm (> {anchor_tol_mm:.2f} mm)")

    if nodes:
        left = min(float(n["x"]) for n in nodes)
        top = min(float(n["y"]) for n in nodes)
        right = max(float(n["x"]) + float(n["w"]) for n in nodes)
        bottom = max(float(n["y"]) + float(n["h"]) for n in nodes)
        margins_mm = {
            "left": left * mm_per_px,
            "right": (cw - right) * mm_per_px,
            "top": top * mm_per_px,
            "bottom": (ch - bottom) * mm_per_px,
        }
        metrics["node_outer_margins_mm"] = {k: round(v, 2) for k, v in margins_mm.items()}
        for side in ("left", "right", "top"):
            if margins_mm[side] < 5.0:
                failures.append(f"{side} node outer margin {margins_mm[side]:.2f} mm < 5.0 mm")
        if margins_mm["bottom"] < 2.0:
            failures.append(f"bottom node outer margin {margins_mm['bottom']:.2f} mm < 2.0 mm")

        node_weights = []
        default_node_sw = float(styles.get("node_defaults", {}).get("stroke_width", 2.0))
        for n in nodes:
            sw = float(n.get("stroke_width", default_node_sw))
            node_weights.append(px_to_pt(sw, width_mm, cw))
        metrics["node_stroke_pt_range"] = [round(min(node_weights), 2), round(max(node_weights), 2)]
        if max(node_weights) > 1.2:
            warnings.append(f"node border reaches {max(node_weights):.2f} pt; verify that weight is semantic, not decorative")
        if min(node_weights) < 0.25:
            warnings.append(f"node border falls to {min(node_weights):.2f} pt; fine lines may reproduce poorly")

    edges = spec.get("edges", [])
    if edges:
        default_edge_sw = float(styles.get("main_line", {}).get("width", 2.4))
        edge_weights = [px_to_pt(float(e.get("stroke_width", default_edge_sw)), width_mm, cw) for e in edges]
        metrics["edge_stroke_pt_range"] = [round(min(edge_weights), 2), round(max(edge_weights), 2)]
        if max(edge_weights) > 1.2:
            warnings.append(f"connector reaches {max(edge_weights):.2f} pt; use a thick-spine exception only when route is the main visual object")
        if min(edge_weights) < 0.25:
            warnings.append(f"connector falls to {min(edge_weights):.2f} pt; may reproduce poorly")

    # Optional encoded semantic geometry checks. These become automatic when
    # nodes carry stage_id/sibling_group and edges carry a `to` target id.
    spacing = styles.get("spacing_mm", {})
    stage_groups = {}
    for n in nodes:
        sid = n.get("stage_id", n.get("stage"))
        if sid is not None:
            stage_groups.setdefault(str(sid), []).append(n)
    if len(stage_groups) >= 2:
        bands = []
        for sid, group in stage_groups.items():
            y0 = min(float(n["y"]) for n in group)
            y1 = max(float(n["y"]) + float(n["h"]) for n in group)
            bands.append((y0, y1, sid))
        bands.sort()
        gaps = []
        min_gap = float(spacing.get("major_stage_gap_min", 7.0))
        for (_, y1, sid1), (y2, _, sid2) in zip(bands, bands[1:]):
            gap_mm = (y2 - y1) * mm_per_px
            gaps.append({"from": sid1, "to": sid2, "gap_mm": round(gap_mm, 2)})
            if gap_mm < min_gap:
                failures.append(f"major stage gap {sid1}->{sid2} is {gap_mm:.2f} mm < {min_gap:.2f} mm")
        metrics["encoded_stage_gaps_mm"] = gaps

    sibling_groups = {}
    for n in nodes:
        gid = n.get("sibling_group")
        if gid is not None:
            sibling_groups.setdefault(str(gid), []).append(n)
    if sibling_groups:
        sibling_metrics = []
        for gid, group in sibling_groups.items():
            if len(group) < 2:
                continue
            tops = [float(n["y"]) for n in group]
            bottoms = [float(n["y"]) + float(n["h"]) for n in group]
            top_spread = (max(tops)-min(tops))*mm_per_px
            bottom_spread = (max(bottoms)-min(bottoms))*mm_per_px
            sibling_metrics.append({"group":gid,"top_spread_mm":round(top_spread,2),"bottom_spread_mm":round(bottom_spread,2)})
            if top_spread > 0.5 or bottom_spread > 0.5:
                warnings.append(f"sibling group {gid} edges differ by >0.5 mm; verify scientific need")
        metrics["sibling_alignment"] = sibling_metrics

    node_by_id = {str(n.get("id")): n for n in nodes if n.get("id") is not None}
    centered = []
    for e in edges:
        target_id = e.get("to")
        if not target_id or target_id not in node_by_id or not e.get("points"):
            continue
        n = node_by_id[target_id]
        end_x = float(e["points"][-1][0])
        cx = float(n["x"]) + float(n["w"])/2
        dev_mm = abs(end_x-cx)*mm_per_px
        centered.append({"edge":e.get("id"),"to":target_id,"x_deviation_mm":round(dev_mm,2)})
        if dev_mm > 0.5:
            failures.append(f"edge {e.get('id','?')} enters {target_id} {dev_mm:.2f} mm off center (>0.5 mm)")
    if centered:
        metrics["encoded_child_arrow_centering"] = centered

    arrow = styles.get("arrowhead", {})
    if arrow:
        length_mm = px_to_mm(float(arrow.get("length_px", 10)), width_mm, cw)
        width_head_mm = px_to_mm(float(arrow.get("width_px", 8)), width_mm, cw)
        metrics["arrowhead_mm"] = {"length": round(length_mm, 2), "width": round(width_head_mm, 2)}
        if length_mm > 1.5:
            warnings.append(f"arrowhead length {length_mm:.2f} mm is visually large for the minimal workflow profile")
        if length_mm < 0.6:
            warnings.append(f"arrowhead length {length_mm:.2f} mm may be too small at final size")

    report = {
        "layout_spec": str(args.layout_spec),
        "profile": profile,
        "hard_pass": not failures,
        "failures": failures,
        "warnings": warnings,
        "metrics": metrics,
        "manual_qc_still_required": [
            "major-layer clear spacing",
            "section-header connector-free breathing band",
            "sibling node alignment",
            "child-arrow centerline alignment",
            "color-role semantics and palette budget",
            "rendered text fit and final-width readability",
            "information-card shared left-anchor appearance",
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
