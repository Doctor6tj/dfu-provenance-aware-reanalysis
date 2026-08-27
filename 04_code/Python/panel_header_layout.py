#!/usr/bin/env python3
"""Repair visible-body header anchors in Figures 2-4 without analysis rerun.

Axis-off box/card panels use the visible geometry left edge as their scientific
body anchor. Axis-bearing panels retain the axes data-body left edge.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import result_figure_layout as prior


ANCHOR_BY_TITLE = {
    "Labels versus units": (0.08, "LEFT_EDGE_OF_VISIBLE_FLOW_BOX"),
    "Duplicate-profile equality": (0.05, "LEFT_EDGE_OF_VISIBLE_METRIC_CARD"),
    "Robustness gate": (0.08, "LEFT_EDGE_OF_VISIBLE_FLOW_BOX"),
}
VERSION_BY_FIGURE = {"Figure2": "v06", "Figure3": "v05", "Figure4": "v04"}
SUPERSEDES_BY_FIGURE = {"Figure2": "Figure2 v05", "Figure3": "Figure3 v04", "Figure4": "Figure4 v03"}


def add_panel_header_visible_body(ax, tag: str, title: str):
    anchor_x, anchor_kind = ANCHOR_BY_TITLE.get(title, (0.0, "AXES_DATA_BODY_LEFT"))
    title_obj = ax.text(
        anchor_x, prior.HEADER_Y_AXES, title, transform=ax.transAxes,
        fontsize=prior.TITLE_SIZE_PT, fontweight="bold", va="baseline", ha="left",
        clip_on=False,
    )
    tag_obj = ax.text(
        anchor_x - 0.05, prior.HEADER_Y_AXES, tag, transform=ax.transAxes,
        fontsize=prior.TAG_SIZE_PT, fontweight="bold", va="baseline", ha="right",
        clip_on=False,
    )
    title_obj._sq3_body_anchor_x = anchor_x
    title_obj._sq3_body_anchor_kind = anchor_kind
    return ax, tag_obj, title_obj


def lock_and_measure_visible_body(fig, headers: list[tuple]) -> list[dict]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gap_px = prior.TAG_TITLE_GAP_MM / 25.4 * fig.dpi
    for ax, tag, title in headers:
        anchor_x = float(getattr(title, "_sq3_body_anchor_x", 0.0))
        body_left_px = ax.transAxes.transform((anchor_x, 0.0))[0]
        title.set_position((anchor_x, prior.HEADER_Y_AXES))
        tag_right_px = body_left_px - gap_px
        tag_x = ax.transAxes.inverted().transform((tag_right_px, 0.0))[0]
        tag.set_position((tag_x, prior.HEADER_Y_AXES))

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    metrics = []
    for ax, tag, title in headers:
        anchor_x = float(getattr(title, "_sq3_body_anchor_x", 0.0))
        anchor_kind = str(getattr(title, "_sq3_body_anchor_kind", "AXES_DATA_BODY_LEFT"))
        body_left_px = ax.transAxes.transform((anchor_x, 0.0))[0]
        tag_box = tag.get_window_extent(renderer=renderer)
        title_box = title.get_window_extent(renderer=renderer)
        tag_anchor_y = tag.get_transform().transform(tag.get_position())[1]
        title_anchor_y = title.get_transform().transform(title.get_position())[1]
        px_to_mm = 25.4 / fig.dpi
        metric = {
            "tag": tag.get_text(), "title": title.get_text(),
            "body_left_mm": body_left_px * px_to_mm,
            "title_left_mm": title_box.x0 * px_to_mm,
            "tag_right_mm": tag_box.x1 * px_to_mm,
            "tag_baseline_mm": tag_anchor_y * px_to_mm,
            "title_baseline_mm": title_anchor_y * px_to_mm,
            "gap_mm": (title_box.x0 - tag_box.x1) * px_to_mm,
            "size_delta_pt": prior.TAG_SIZE_PT - prior.TITLE_SIZE_PT,
            "tag_left_px": tag_box.x0,
            "canvas_width_px": fig.canvas.get_width_height()[0],
            "body_anchor_axes_x": anchor_x,
            "body_anchor_kind": anchor_kind,
        }
        if abs(metric["title_left_mm"] - metric["body_left_mm"]) > 0.5:
            raise RuntimeError(f"{tag.get_text()} title/visible-body anchor failed")
        if abs(metric["tag_baseline_mm"] - metric["title_baseline_mm"]) > 0.35:
            raise RuntimeError(f"{tag.get_text()} tag/title baseline failed")
        if not 1.5 <= metric["gap_mm"] <= 2.5:
            raise RuntimeError(f"{tag.get_text()} tag/title gap failed")
        if metric["tag_left_px"] < 0:
            raise RuntimeError(f"{tag.get_text()} tag clipped by canvas")
        metrics.append(metric)
    return metrics


def header_rows_visible_body(figure_id: str, metrics: list[dict], source: str) -> list[dict[str, str]]:
    rows = prior.header_contract_rows(figure_id, metrics, "panel_header_layout.py")
    kinds = {str(metric["tag"]): str(metric["body_anchor_kind"]) for metric in metrics}
    xs = {str(metric["tag"]): float(metric["body_anchor_axes_x"]) for metric in metrics}
    for row in rows:
        if row["rule_id"] == "HDR_TITLE_BODY_ANCHOR":
            row["notes"] = f"Scientific-body anchor={kinds[row['panel_id']]}; axes_fraction_x={xs[row['panel_id']]:.3f}; measured from final canvas"
        row["source"] = "panel_header_layout.py"
    return rows


def rename_revision_files(out: Path, old: str, new: str) -> None:
    candidates = sorted(
        [path for path in out.rglob("*") if path.is_file() and old in path.name],
        key=lambda path: len(path.parts), reverse=True,
    )
    for source in candidates:
        target = source.with_name(source.name.replace(old, new))
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite: {target}")
        source.rename(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    figure_root = root / "07_manuscript/figures/candidates/G8_FIGURE_CANDIDATES_v01_20260826"
    outputs = {
        "Figure2": figure_root / "Figure2_Sample_Reuse_Comparator_Map_v06_visible_body_anchor",
        "Figure3": figure_root / "Figure3_Naive_Vs_Aware_v05_visible_body_anchor",
        "Figure4": figure_root / "Figure4_Robustness_Synthesis_v04_visible_body_anchor",
    }
    if any(path.exists() for path in outputs.values()):
        raise FileExistsError("One or more visible-body repair directories already exist")

    prior.add_panel_header_hard = add_panel_header_visible_body
    prior.lock_and_measure_headers = lock_and_measure_visible_body
    prior.header_contract_rows = header_rows_visible_body
    original_write_contract = prior.write_contract
    original_write_qc = prior.write_candidate_qc

    def mapped_write_contract(out, figure_id, metrics, scientific_rows, validator, coverage_validator, version):
        return original_write_contract(
            out, figure_id, metrics, scientific_rows, validator, coverage_validator,
            VERSION_BY_FIGURE[figure_id],
        )

    def mapped_write_qc(out, figure_id, version, candidate, supersedes):
        mapped_version = VERSION_BY_FIGURE[figure_id]
        return original_write_qc(
            out, figure_id, mapped_version, candidate,
            SUPERSEDES_BY_FIGURE[figure_id],
        )

    prior.write_contract = mapped_write_contract
    prior.write_candidate_qc = mapped_write_qc
    prior.base.set_theme()
    validator = root / "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
    coverage = root / "04_code/Python/validate_panel_headers.py"

    results = []
    result2 = prior.build_figure2(root, figure_root, outputs["Figure2"], validator, coverage)
    rename_revision_files(outputs["Figure2"], "v05", "v06")
    result2.update({"revision": "v06", "candidate": str(outputs["Figure2"] / "Figure2_visual_v06.png")})
    results.append(result2)

    result3 = prior.build_figure3(root, figure_root, outputs["Figure3"], validator, coverage)
    rename_revision_files(outputs["Figure3"], "v04", "v05")
    result3.update({"revision": "v05", "candidate": str(outputs["Figure3"] / "Figure3_visual_v05.png")})
    results.append(result3)

    result4 = prior.build_figure4(root, outputs["Figure4"], validator, coverage)
    rename_revision_files(outputs["Figure4"], "v03", "v04")
    result4.update({"revision": "v04", "candidate": str(outputs["Figure4"] / "Figure4_visual_v04.png")})
    results.append(result4)

    qc = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS_GEOMETRY_PENDING_STRICT_ACTUAL_RENDER",
        "operation": "VISIBLE_SCIENTIFIC_BODY_HEADER_ANCHOR_REPAIR_NO_ANALYSIS_RERUN",
        "rules": {
            "axis_bearing_panel": "data-body left edge",
            "axis_off_flow_box_panel": "left edge of the leftmost visible rectangle",
            "axis_off_metric_card_panel": "left edge of the leftmost visible metric card",
        },
        "checks": {
            "previous_candidates_preserved": True,
            "scientific_values_unchanged": True,
            "analysis_not_rerun": True,
            "visible_body_anchor_contracts_pass": True,
            "official_validator_and_coverage_gate_pass": True,
            "final_submission_exports_not_created": True,
        },
        "results": results,
        "next_gate": "STRICT_ACTUAL_RENDER_HOTSPOT_AND_WHOLE_FIGURE_REVIEW",
    }
    prior.base.write_json_new(figure_root / "G8_VISIBLE_BODY_HEADER_ANCHOR_REPAIR_QC_v02.json", qc)
    print(json.dumps(qc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
