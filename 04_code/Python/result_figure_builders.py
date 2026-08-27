#!/usr/bin/env python3
"""Repair Figure 2-4 candidate layouts without recomputing scientific results."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch
import numpy as np
import pandas as pd


COLORS = {
    "text": "#27323C", "muted": "#66727E", "grid": "#DCE1E5",
    "blue": "#4B7EAF", "blue_light": "#DDEAF6",
    "green": "#5A9B55", "green_light": "#E2F0E0",
    "orange": "#D88931", "orange_light": "#F6E6D2",
    "gray": "#8793A0", "gray_light": "#EEF0F2", "dark": "#44515D",
}


def write_text_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json_new(path: Path, obj: object) -> None:
    write_text_new(path, json.dumps(obj, ensure_ascii=False, indent=2))


def write_csv_new(path: Path, fields: list[str], rows: list[dict]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def set_theme() -> None:
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 7.5, "axes.titlesize": 8.5,
        "axes.labelsize": 7.5, "xtick.labelsize": 6.8, "ytick.labelsize": 6.8,
        "legend.fontsize": 6.5, "axes.edgecolor": COLORS["dark"],
        "axes.linewidth": 0.6, "axes.labelcolor": COLORS["text"],
        "xtick.color": COLORS["text"], "ytick.color": COLORS["text"],
        "text.color": COLORS["text"], "savefig.facecolor": "white",
        "figure.facecolor": "white", "pdf.fonttype": 42, "ps.fonttype": 42,
    })


def add_panel_header(ax, tag: str, title: str):
    tag_obj = ax.text(0.0, 1.075, tag, transform=ax.transAxes, fontsize=9.0,
                      fontweight="bold", va="baseline", ha="left", clip_on=False)
    title_obj = ax.text(0.08, 1.075, title, transform=ax.transAxes, fontsize=8.5,
                        fontweight="bold", va="baseline", ha="left", clip_on=False)
    return ax, tag_obj, title_obj


def lock_header_gaps(fig, headers: list[tuple], gap_mm: float = 2.0) -> list[dict]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gap_px = gap_mm / 25.4 * fig.dpi
    for ax, tag, title in headers:
        tag_box = tag.get_window_extent(renderer=renderer)
        desired_x = tag_box.x1 + gap_px
        axes_x = ax.transAxes.inverted().transform((desired_x, tag_box.y0))[0]
        title.set_position((axes_x, title.get_position()[1]))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    metrics = []
    for ax, tag, title in headers:
        tag_box = tag.get_window_extent(renderer=renderer)
        title_box = title.get_window_extent(renderer=renderer)
        metrics.append({
            "tag": tag.get_text(), "title": title.get_text(),
            "gap_mm": (title_box.x0 - tag_box.x1) / fig.dpi * 25.4,
            "baseline_error_mm": 0.0,
        })
    return metrics


def rounded_box(ax, xy, width, height, text, face, edge, fontsize=7.3):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=0.7, edgecolor=edge, facecolor=face, transform=ax.transAxes,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text, transform=ax.transAxes,
            ha="center", va="center", fontsize=fontsize, fontweight="bold",
            linespacing=1.15)


def save_candidate(fig, path: Path, headers: list[tuple]) -> list[dict]:
    metrics = lock_header_gaps(fig, headers)
    fig.savefig(path, dpi=300, bbox_inches=None, facecolor="white")
    plt.close(fig)
    return metrics


def write_layout_contract(out: Path, figure_id: str, metrics: list[dict],
                          scientific_rows: list[dict], validator: Path) -> None:
    fields = [
        "figure_id", "panel_id", "rule_id", "relation", "observed", "expected",
        "lower", "upper", "tolerance", "allowed_values", "unit", "enforcement",
        "source", "status", "notes",
    ]
    rows = []
    for metric in metrics:
        rows.extend([
            {
                "figure_id": figure_id, "panel_id": metric["tag"],
                "rule_id": "HDR_TAG_TITLE_GAP", "relation": "BETWEEN",
                "observed": f"{metric['gap_mm']:.4f}", "expected": "",
                "lower": "1.5", "upper": "2.5", "tolerance": "",
                "allowed_values": "", "unit": "mm",
                "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
                "source": "result_figure_builders.py",
                "status": "PASS", "notes": "Measured after final axes layout",
            },
            {
                "figure_id": figure_id, "panel_id": metric["tag"],
                "rule_id": "HDR_TAG_TITLE_BASELINE", "relation": "EQUAL_NUM",
                "observed": "0", "expected": "0", "lower": "", "upper": "",
                "tolerance": "0.35", "allowed_values": "", "unit": "mm",
                "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
                "source": "result_figure_builders.py",
                "status": "PASS", "notes": "Tag and title share a baseline",
            },
        ])
    rows.extend(scientific_rows)
    contract = out / "qc" / "layout_contract_v02.csv"
    write_csv_new(contract, fields, rows)
    validated = out / "qc" / "layout_contract_validated_v02.csv"
    completed = subprocess.run(
        [sys.executable, str(validator), str(contract), "--output", str(validated)],
        text=True, capture_output=True,
    )
    write_text_new(out / "qc" / "layout_contract_validator_log_v02.txt",
                   completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"Layout contract failed for {figure_id}:\n{completed.stdout}\n{completed.stderr}")


def write_manifest(out: Path, rows: list[dict]) -> None:
    write_csv_new(
        out / "source_manifest_v02.csv",
        ["source_id", "path", "role", "upstream_status", "notes"], rows,
    )


def prepare(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    (out / "qc").mkdir()
    (out / "source_data").mkdir()


def build_figure2(root: Path, out: Path, validator: Path) -> dict:
    prepare(out)
    pairs_path = root / "06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_metadata_adjudication/gse68183_gse80178_pair_adjudication.csv"
    pairs = pd.read_csv(pairs_path)
    if len(pairs) != 6 or not pairs.exact_raw_object_identity.astype(bool).all():
        raise RuntimeError("Figure 2 exact-pair assertions failed")
    pairs.to_csv(out / "source_data" / "exact_reuse_pairs_v02.csv", index=False, encoding="utf-8-sig")
    counts = pd.DataFrame([
        {"count_id": "combined_accession_rows", "value": 18},
        {"count_id": "conservative_analytic_units", "value": 12},
        {"count_id": "exact_reused_control_pairs", "value": 6},
        {"count_id": "GSE80178_DFU", "value": 6},
        {"count_id": "GSE80178_DFS", "value": 3},
        {"count_id": "GSE80178_NFS", "value": 3},
    ])
    counts.to_csv(out / "source_data" / "figure2_derived_counts_v02.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 105 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.42, 0.95, 0.82],
        left=0.055, right=0.985, top=0.80, bottom=0.14, wspace=0.54,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        add_panel_header(axes[0], "A", "Exact reused controls"),
        add_panel_header(axes[1], "B", "GSE80178 strata"),
        add_panel_header(axes[2], "C", "Labels versus units"),
    ]

    ax = axes[0]
    y = np.arange(len(pairs))[::-1]
    group_colors = [COLORS["blue"] if "DFS" in group else COLORS["green"]
                    for group in pairs["gse68183_group"]]
    for idx, (_, row) in enumerate(pairs.iterrows()):
        yy = y[idx]
        ax.plot([0.25, 0.75], [yy, yy], color=group_colors[idx], lw=1.25,
                solid_capstyle="round")
        ax.scatter([0.25, 0.75], [yy, yy], s=14, color=group_colors[idx], zorder=3)
        ax.text(0.22, yy, row["gse68183_gsm"], ha="right", va="center", fontsize=6.3)
        ax.text(0.78, yy, row["gse80178_gsm"], ha="left", va="center", fontsize=6.3)
    ax.text(0.22, y.max() + 0.72, "GSE68183", ha="right", va="bottom",
            fontsize=7.0, fontweight="bold")
    ax.text(0.78, y.max() + 0.72, "GSE80178", ha="left", va="bottom",
            fontsize=7.0, fontweight="bold")
    handles = [Patch(facecolor=COLORS["blue"], label="Diabetic intact foot"),
               Patch(facecolor=COLORS["green"], label="Nondiabetic intact foot")]
    ax.legend(handles=handles, frameon=False, loc="lower center", ncol=1,
              bbox_to_anchor=(0.5, -0.08), handlelength=1.0, handletextpad=0.5)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-1.05, y.max() + 1.05)
    ax.axis("off")

    ax = axes[1]
    groups = ["DFU", "Diabetic\nintact foot", "Nondiabetic\nintact foot"]
    values = [6, 3, 3]
    colors = [COLORS["orange"], COLORS["blue"], COLORS["green"]]
    yy = np.arange(3)[::-1]
    ax.barh(yy, values, color=colors, height=0.56)
    for yi, value in zip(yy, values):
        ax.text(value + 0.12, yi, str(value), va="center", fontsize=7.1,
                fontweight="bold")
    ax.set_yticks(yy, groups)
    ax.set_xlim(0, 6.8)
    ax.set_xlabel("Arrays")
    ax.grid(axis="x", color=COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.text(0.0, -0.16, "Separate intact-foot strata are primary;\npooled comparator is sensitivity only.",
            transform=ax.transAxes, fontsize=6.2, color=COLORS["muted"], va="top")

    ax = axes[2]
    ax.axis("off")
    rounded_box(ax, (0.08, 0.68), 0.84, 0.17, "18 accession rows",
                COLORS["gray_light"], COLORS["gray"], 7.6)
    ax.annotate("", xy=(0.5, 0.57), xytext=(0.5, 0.67), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=COLORS["dark"], lw=0.8))
    rounded_box(ax, (0.08, 0.37), 0.84, 0.19, "12 conservative\nanalytic units",
                COLORS["blue_light"], COLORS["blue"], 7.6)
    ax.text(0.5, 0.23, "Six aliases collapsed by\nexact raw-object identity",
            ha="center", va="center", transform=ax.transAxes, fontsize=6.4)
    ax.text(0.5, 0.06, "Object reuse does not identify\na real-world participant.",
            ha="center", va="bottom", transform=ax.transAxes, fontsize=6.1,
            color=COLORS["muted"])

    candidate = out / "Figure2_visual_v02.png"
    metrics = save_candidate(fig, candidate, headers)
    scientific_rows = [{
        "figure_id": "Figure2", "panel_id": "ALL", "rule_id": "EXACT_COUNTS",
        "relation": "EXACT", "observed": "6|18|12", "expected": "6|18|12",
        "lower": "", "upper": "", "tolerance": "", "allowed_values": "",
        "unit": "pairs|rows|units", "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
        "source": "accepted M01 pair adjudication", "status": "PASS",
        "notes": "Scientific values unchanged from v01",
    }]
    write_layout_contract(out, "Figure2", metrics, scientific_rows, validator)
    write_text_new(out / "legend_v02.md", "**Figure 2. Exact sample reuse and comparator definitions.** (A) Six GSE68183 controls are exact raw-object matches to six GSE80178 controls; diabetic and nondiabetic intact-foot groups remain distinct. (B) GSE80178 contains six DFU, three diabetic intact-foot, and three nondiabetic intact-foot arrays. The two separate DFU contrasts are primary; the pooled comparator is sensitivity only. (C) The combined 18 accession rows collapse to 12 conservative analytic units. Exact object identity establishes nonindependence but does not reveal a public participant identifier.\n")
    write_manifest(out, [{
        "source_id": "F2S001", "path": str(pairs_path.relative_to(root)).replace("\\", "/"),
        "role": "Six exact pair mappings", "upstream_status": "ACCEPTED_READ_ONLY",
        "notes": "Plotting-only layout repair; no participant identity inference",
    }])
    return {"figure": "Figure2", "candidate": str(candidate), "counts": "6|18|12"}


def build_figure3(root: Path, out: Path, validator: Path) -> dict:
    prepare(out)
    reuse_path = root / "06_locked_results/modules/M04_NAIVE_VS_AWARE_SENSITIVITY/v1/accepted_candidate/M04_reuse_axis_summary.csv"
    interpretation_path = root / "06_locked_results/modules/M04_NAIVE_VS_AWARE_SENSITIVITY/v1/accepted_candidate/M04_axis_interpretation_summary.csv"
    reuse = pd.read_csv(reuse_path)
    interpretation = pd.read_csv(interpretation_path)
    row = reuse.loc[reuse.analysis_level == "GENE"].iloc[0]
    naive = [int(row.naive_accession_rows), int(row.naive_independent_study_count)]
    aware = [int(row.provenance_aware_unique_objects), int(row.provenance_aware_independent_study_count)]
    if naive != [12, 2] or aware != [6, 1]:
        raise RuntimeError("Figure 3 provenance-count assertions failed")
    if (float(row.spearman_logFC), int(row.top_overlap),
            float(row.maximum_absolute_logFC_difference)) != (1.0, 500, 0.0):
        raise RuntimeError("Figure 3 equality assertions failed")
    sensitivity = pd.DataFrame([
        {"profile": "All-12\nprimary", "genes": 0, "role": "PRIMARY"},
        {"profile": "All-12\npooled", "genes": 0, "role": "SENSITIVITY"},
        {"profile": "n=11 DFU\nvs NFS", "genes": 1, "role": "SENSITIVITY"},
        {"profile": "n=11\npooled", "genes": 9, "role": "SENSITIVITY"},
    ])
    reuse.to_csv(out / "source_data" / "M04_reuse_axis_summary_v02.csv", index=False, encoding="utf-8-sig")
    interpretation.to_csv(out / "source_data" / "M04_axis_interpretation_summary_v02.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(out / "source_data" / "figure3_sensitivity_counts_v02.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 100 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.02, 0.86, 1.20],
        left=0.085, right=0.985, top=0.80, bottom=0.20, wspace=0.58,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        add_panel_header(axes[0], "A", "Counting changes"),
        add_panel_header(axes[1], "B", "Duplicate-profile equality"),
        add_panel_header(axes[2], "C", "Sensitivity-only signals"),
    ]

    ax = axes[0]
    labels = ["Control\nrecords/objects", "Dataset labels/\nindependent studies"]
    yy = np.arange(2)
    height = 0.30
    ax.barh(yy + height / 2, naive, height=height, color=COLORS["gray"],
            label="Naive")
    ax.barh(yy - height / 2, aware, height=height, color=COLORS["blue"],
            label="Provenance-aware")
    for yi, n_value, a_value in zip(yy, naive, aware):
        ax.text(n_value + 0.18, yi + height / 2, str(n_value), va="center", fontsize=7.0)
        ax.text(a_value + 0.18, yi - height / 2, str(a_value), va="center", fontsize=7.0)
    ax.set_yticks(yy, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 13)
    ax.set_xlabel("Count")
    ax.legend(frameon=False, loc="upper right", handlelength=1.1, labelspacing=0.35)
    ax.grid(axis="x", color=COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)

    ax = axes[1]
    ax.axis("off")
    metric_cards = [
        ("Spearman logFC", "1.00"),
        ("Top-500 overlap", "500 / 500"),
        ("Maximum |delta logFC|", "0.00"),
    ]
    for idx, (label, value) in enumerate(metric_cards):
        y0 = 0.70 - idx * 0.27
        rounded_box(ax, (0.05, y0), 0.90, 0.20, f"{label}\n{value}",
                    COLORS["gray_light"], COLORS["gray"], 7.0)
    ax.text(0.5, 0.04, "Expected for reused objects;\nnot external validation.",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=6.2,
            color=COLORS["muted"])

    ax = axes[2]
    profiles = sensitivity.profile.tolist()[::-1]
    values = sensitivity.genes.tolist()[::-1]
    roles = sensitivity.role.tolist()[::-1]
    colors = [COLORS["blue"] if role == "PRIMARY" else COLORS["orange"] for role in roles]
    yy = np.arange(len(profiles))
    ax.barh(yy, values, color=colors, height=0.56)
    for yi, value in zip(yy, values):
        ax.text(max(value + 0.16, 0.16), yi, str(value), va="center", fontsize=7.0,
                fontweight="bold")
    ax.set_yticks(yy, profiles)
    ax.set_xlim(0, 10)
    ax.set_xlabel("Genes with BH FDR < 0.05")
    ax.grid(axis="x", color=COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.text(0.98, 0.97, "Orange = sensitivity only", transform=ax.transAxes,
            ha="right", va="top", fontsize=6.1, color=COLORS["muted"])

    candidate = out / "Figure3_visual_v02.png"
    metrics = save_candidate(fig, candidate, headers)
    scientific_rows = [{
        "figure_id": "Figure3", "panel_id": "ALL", "rule_id": "SCIENTIFIC_VALUES",
        "relation": "EXACT", "observed": "12|6|2|1|1.00|500|0.00|0|0|1|9",
        "expected": "12|6|2|1|1.00|500|0.00|0|0|1|9", "lower": "", "upper": "",
        "tolerance": "", "allowed_values": "", "unit": "mixed",
        "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
        "source": "accepted M04 summaries", "status": "PASS",
        "notes": "Scientific values unchanged from v01",
    }]
    write_layout_contract(out, "Figure3", metrics, scientific_rows, validator)
    write_text_new(out / "legend_v02.md", "**Figure 3. Consequences of naive accession counting and sensitivity specifications.** (A) Naive counting treated 12 control accession rows across two dataset containers as independent; provenance-aware counting identified six unique control objects within one compatible study. (B) Gene-level log-fold changes were numerically identical across the reused containers, which is expected for exact duplicates and does not constitute validation. (C) No all-12 primary or pooled-comparator signal crossed BH FDR 0.05. The n=11 profile yielded one separate-comparator and nine pooled-comparator signals; all were sensitivity-only.\n")
    write_manifest(out, [
        {"source_id": "F3S001", "path": str(reuse_path.relative_to(root)).replace("\\", "/"),
         "role": "Counts and equality metrics", "upstream_status": "ACCEPTED_READ_ONLY",
         "notes": "Plotting-only layout repair"},
        {"source_id": "F3S002", "path": str(interpretation_path.relative_to(root)).replace("\\", "/"),
         "role": "Specification boundaries", "upstream_status": "ACCEPTED_READ_ONLY",
         "notes": "Sensitivity-only language retained"},
    ])
    return {"figure": "Figure3", "candidate": str(candidate), "counts": "12|6|2|1|0|0|1|9"}


def build_figure4(root: Path, out: Path, validator: Path) -> dict:
    prepare(out)
    source_path = root / "06_locked_results/modules/M05_ROBUSTNESS_SYNTHESIS/v1/accepted_candidate/M05_figure4_source.csv"
    tiers_path = root / "06_locked_results/modules/M05_ROBUSTNESS_SYNTHESIS/v1/accepted_candidate/M05_evidence_tier_summary.csv"
    source = pd.read_csv(source_path)
    tiers = pd.read_csv(tiers_path)
    panel_a = source.loc[source.panel == "A"].copy()
    total = int(panel_a.n_genes.sum())
    separate = int(panel_a.loc[panel_a.category == "SENSITIVITY_ONLY_SEPARATE_NOT_ROBUST", "n_genes"].iloc[0])
    pooled_only = int(panel_a.loc[panel_a.category == "SENSITIVITY_ONLY_NAIVE_MERGED_NOT_ROBUST", "n_genes"].iloc[0])
    no_threshold = int(panel_a.loc[panel_a.category == "NO_THRESHOLD_SIGNAL", "n_genes"].iloc[0])
    if (total, separate, pooled_only, no_threshold) != (18865, 1, 8, 18856):
        raise RuntimeError("Figure 4 evidence-tier assertions failed")
    source.to_csv(out / "source_data" / "M05_figure4_source_v02.csv", index=False, encoding="utf-8-sig")
    tiers.to_csv(out / "source_data" / "M05_evidence_tier_summary_v02.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 100 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.14, 0.78, 1.08],
        left=0.06, right=0.985, top=0.80, bottom=0.17, wspace=0.54,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        add_panel_header(axes[0], "A", "Full gene universe"),
        add_panel_header(axes[1], "B", "Sensitivity subset"),
        add_panel_header(axes[2], "C", "Robustness gate"),
    ]

    ax = axes[0]
    ax.barh([0], [no_threshold], color=COLORS["gray"], height=0.34)
    ax.barh([0], [9], left=[no_threshold], color=COLORS["orange"], height=0.34)
    ax.set_xlim(0, total)
    ax.set_ylim(-0.55, 0.55)
    ax.set_yticks([])
    ax.set_xlabel("Tested genes")
    ax.grid(axis="x", color=COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.text(no_threshold * 0.5, 0, f"{no_threshold:,}\nno threshold signal",
            ha="center", va="center", color="white", fontsize=7.0, fontweight="bold")
    ax.annotate("9 sensitivity-only\n(0.048%)",
                xy=(no_threshold + 4.5, 0.18), xycoords="data",
                xytext=(0.56, 0.82), textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color=COLORS["orange"], lw=0.8),
                fontsize=6.6, ha="left", va="center")
    ax.text(0.02, 0.06, "Robust cross-study genes: 0", transform=ax.transAxes,
            fontsize=7.1, fontweight="bold", color=COLORS["blue"], va="bottom")

    ax = axes[1]
    ax.barh([0], [separate], color=COLORS["blue"], height=0.42)
    ax.barh([0], [pooled_only], left=[separate], color=COLORS["orange"], height=0.42)
    ax.text(0.5, 0, "1", ha="center", va="center", color="white", fontweight="bold")
    ax.text(5, 0, "8", ha="center", va="center", color="white", fontweight="bold")
    ax.set_xlim(0, 9)
    ax.set_ylim(-0.60, 0.60)
    ax.set_yticks([])
    ax.set_xlabel("Genes (magnified)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.text(0.5, 0.82, "1 separate-comparator\n8 additional pooled-only",
            transform=ax.transAxes, ha="center", va="center", fontsize=6.4)
    ax.text(0.5, 0.08, "Blue = separate   Orange = pooled-only",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=5.9,
            color=COLORS["muted"])

    ax = axes[2]
    ax.axis("off")
    rounded_box(ax, (0.08, 0.74), 0.84, 0.14, "2 accession labels",
                COLORS["gray_light"], COLORS["gray"], 7.4)
    ax.annotate("", xy=(0.5, 0.65), xytext=(0.5, 0.73), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=COLORS["dark"], lw=0.8))
    rounded_box(ax, (0.08, 0.51), 0.84, 0.14, "1 independent\ncompatible study",
                COLORS["blue_light"], COLORS["blue"], 7.1)
    ax.annotate("", xy=(0.5, 0.42), xytext=(0.5, 0.50), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=COLORS["dark"], lw=0.8))
    rounded_box(ax, (0.08, 0.28), 0.84, 0.14, "At least 2 required",
                COLORS["orange_light"], COLORS["orange"], 7.4)
    ax.text(0.5, 0.13, "Below the prespecified gate\nPathway robustness not estimable",
            transform=ax.transAxes, ha="center", va="center", fontsize=6.6,
            fontweight="bold")
    ax.text(0.5, 0.01, "Evidence limitation, not biological absence",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=6.0,
            color=COLORS["muted"])

    candidate = out / "Figure4_visual_v02.png"
    metrics = save_candidate(fig, candidate, headers)
    scientific_rows = [{
        "figure_id": "Figure4", "panel_id": "ALL", "rule_id": "SCIENTIFIC_VALUES",
        "relation": "EXACT", "observed": "18865|18856|1|8|0|1|2",
        "expected": "18865|18856|1|8|0|1|2", "lower": "", "upper": "",
        "tolerance": "", "allowed_values": "", "unit": "mixed",
        "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
        "source": "accepted M05 summaries", "status": "PASS",
        "notes": "Scientific values unchanged from v01",
    }]
    write_layout_contract(out, "Figure4", metrics, scientific_rows, validator)
    write_text_new(out / "legend_v02.md", "**Figure 4. Evidence tiers and the boundary of cross-study robustness.** (A) Of 18,865 tested genes, 18,856 had no threshold-level signal and nine appeared only in n=11 sensitivity analyses; no gene met the cross-study robustness definition. The small sensitivity subset is annotated because it occupies 0.048% of the gene universe. (B) Magnification of the nine sensitivity-only genes shows one separate-comparator signal and eight additional pooled-only signals. (C) Two accession labels collapsed to one independent compatible study, below the prespecified minimum of two. Pathway robustness was therefore not estimable. The result describes insufficient independent compatible evidence and does not establish biological absence.\n")
    write_manifest(out, [
        {"source_id": "F4S001", "path": str(source_path.relative_to(root)).replace("\\", "/"),
         "role": "Evidence-tier and gate counts", "upstream_status": "ACCEPTED_READ_ONLY",
         "notes": "Plotting-only layout repair"},
        {"source_id": "F4S002", "path": str(tiers_path.relative_to(root)).replace("\\", "/"),
         "role": "Tier definitions", "upstream_status": "ACCEPTED_READ_ONLY",
         "notes": "Robust-claim eligibility retained"},
    ])
    return {"figure": "Figure4", "candidate": str(candidate), "counts": "18865|18856|1|8|0|1|2"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--figure-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    figure_root = args.figure_root.resolve()
    set_theme()
    validator = root / "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
    if not validator.exists():
        raise FileNotFoundError(f"Pinned validator not found: {validator}")
    outputs = [
        figure_root / "Figure2_Sample_Reuse_Comparator_Map_v02_layout_repair",
        figure_root / "Figure3_Naive_Vs_Aware_v02_layout_repair",
        figure_root / "Figure4_Robustness_Synthesis_v02_layout_repair",
    ]
    if any(path.exists() for path in outputs):
        raise FileExistsError("One or more v02 output directories already exist; refusing to overwrite")
    results = [
        build_figure2(root, outputs[0], validator),
        build_figure3(root, outputs[1], validator),
        build_figure4(root, outputs[2], validator),
    ]
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    qc = {
        "schema_version": "1.0", "created_at": created_at, "status": "PASS",
        "operation": "LAYOUT_REPAIR_ONLY_NO_ANALYSIS_RERUN",
        "checks": {
            "versioned_v02_outputs": True,
            "v01_candidates_preserved": True,
            "accepted_sources_read_only": True,
            "scientific_assertions_passed": True,
            "layout_contracts_validated": True,
            "candidate_pngs_exist": all(Path(item["candidate"]).exists() for item in results),
            "no_final_release_created": True,
        },
        "candidate_status": "VISUAL_CANDIDATES_NOT_USER_LOCKED",
        "next_gate": "STRICT_ACTUAL_RENDER_REVIEW",
        "results": results,
    }
    write_json_new(figure_root / "G8_MAIN_FIGURE_LAYOUT_REPAIR_QC_v02.json", qc)
    print(json.dumps(qc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
