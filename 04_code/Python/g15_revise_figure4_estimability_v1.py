#!/usr/bin/env python3
"""Revise Figure 4 to distinguish non-estimability from a zero result.

Only accepted M05 source tables are read. No differential-expression,
meta-analysis, or pathway analysis is rerun.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd


COLORS = {
    "text": "#27323C", "muted": "#66727E", "grid": "#DCE1E5",
    "blue": "#4B7EAF", "blue_light": "#DDEAF6",
    "orange": "#D88931", "orange_light": "#F6E6D2",
    "gray": "#8793A0", "gray_light": "#EEF0F2", "dark": "#44515D",
}


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def add_header(ax, tag: str, title: str):
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
    return [
        {
            "panel": tag.get_text(),
            "gap_mm": (title.get_window_extent(renderer=renderer).x0 -
                       tag.get_window_extent(renderer=renderer).x1) / fig.dpi * 25.4,
            "baseline_error_mm": 0.0,
        }
        for _, tag, title in headers
    ]


def rounded_box(ax, xy, width, height, text, face, edge, fontsize=7.3):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=0.7, edgecolor=edge, facecolor=face, transform=ax.transAxes,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text, transform=ax.transAxes,
            ha="center", va="center", fontsize=fontsize, fontweight="bold",
            linespacing=1.15)


def build_figure(root: Path):
    source_path = root / "06_locked_results/modules/M05_ROBUSTNESS_SYNTHESIS/v1/accepted_candidate/M05_figure4_source.csv"
    source = pd.read_csv(source_path)
    panel_a = source.loc[source.panel == "A"].copy()
    total = int(panel_a.n_genes.sum())
    separate = int(panel_a.loc[panel_a.category == "SENSITIVITY_ONLY_SEPARATE_NOT_ROBUST", "n_genes"].iloc[0])
    pooled_only = int(panel_a.loc[panel_a.category == "SENSITIVITY_ONLY_NAIVE_MERGED_NOT_ROBUST", "n_genes"].iloc[0])
    no_threshold = int(panel_a.loc[panel_a.category == "NO_THRESHOLD_SIGNAL", "n_genes"].iloc[0])
    if (total, separate, pooled_only, no_threshold) != (18865, 1, 8, 18856):
        raise RuntimeError("Accepted Figure 4 counts do not match the locked source")

    fig = plt.figure(figsize=(180 / 25.4, 100 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.14, 0.78, 1.08],
        left=0.06, right=0.985, top=0.80, bottom=0.17, wspace=0.54,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        add_header(axes[0], "A", "Within-study gene universe"),
        add_header(axes[1], "B", "Sensitivity subset"),
        add_header(axes[2], "C", "Independent-study gate"),
    ]

    ax = axes[0]
    ax.barh([0], [no_threshold], color=COLORS["gray"], height=0.34)
    ax.barh([0], [separate + pooled_only], left=[no_threshold], color=COLORS["orange"], height=0.34)
    ax.set_xlim(0, total)
    ax.set_ylim(-0.55, 0.55)
    ax.set_yticks([])
    ax.set_xlabel("Genes tested within GSE80178")
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
    ax.text(0.02, 0.06, "Cross-study robustness: not estimable", transform=ax.transAxes,
            fontsize=7.1, fontweight="bold", color=COLORS["blue"], va="bottom")

    ax = axes[1]
    ax.barh([0], [separate], color=COLORS["blue"], height=0.42)
    ax.barh([0], [pooled_only], left=[separate], color=COLORS["orange"], height=0.42)
    ax.text(0.5, 0, "1", ha="center", va="center", color="white", fontweight="bold")
    ax.text(5, 0, "8", ha="center", va="center", color="white", fontweight="bold")
    ax.set_xlim(0, 9)
    ax.set_ylim(-0.60, 0.60)
    ax.set_yticks([])
    ax.set_xlabel("Sensitivity-only genes (magnified)")
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
    rounded_box(ax, (0.08, 0.28), 0.84, 0.14, "Minimum 2 studies required",
                COLORS["orange_light"], COLORS["orange"], 7.2)
    ax.text(0.5, 0.13, "Gene and pathway robustness\nnot estimable",
            transform=ax.transAxes, ha="center", va="center", fontsize=6.6,
            fontweight="bold")
    ax.text(0.5, 0.01, "Evidence limitation, not biological absence",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=6.0,
            color=COLORS["muted"])
    metrics = lock_header_gaps(fig, headers)
    return fig, metrics, source_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--stage", choices=("candidate", "final"), required=True)
    args = parser.parse_args()

    root = args.project_root.resolve()
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    set_theme()
    fig, metrics, source_path = build_figure(root)

    if args.stage == "candidate":
        output = out / "Figure4_Robustness_G15_v03_candidate_300dpi.png"
        fig.savefig(output, dpi=300, facecolor="white")
    else:
        output = out / "Figure4_Robustness_G15_v03_600dpi.png"
        pdf = out / "Figure4_Robustness_G15_v03.pdf"
        fig.savefig(output, dpi=600, facecolor="white")
        fig.savefig(pdf, format="pdf", facecolor="white")
    plt.close(fig)

    legend = (
        "Figure 4. Within-study signals and the boundary of cross-study robustness. "
        "(A) Of 18,865 genes tested within GSE80178, 18,856 had no threshold-level signal "
        "and nine appeared only after exclusion of the sole multi-metric QC outlier; these "
        "were sensitivity findings. Cross-study robustness was not estimable because only one "
        "compatible independent study remained. (B) The nine sensitivity-only genes comprised "
        "one separate-comparator signal and eight additional pooled-only signals. (C) The two "
        "accession labels represented one compatible independent study, below the minimum of "
        "two required for gene or pathway robustness assessment.\n"
    )
    write_new(out / "Figure4_legend_G15_v03.txt", legend)
    report = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "operation": "PLOTTING_ONLY_NO_ANALYSIS_RERUN",
        "stage": args.stage,
        "locked_source": str(source_path),
        "scientific_values": {"tested": 18865, "no_threshold": 18856, "separate": 1, "pooled_only": 8},
        "header_geometry": metrics,
        "interpretation": "cross-study gene and pathway robustness not estimable",
        "output": str(output),
    }
    write_new(out / "Figure4_G15_v03_manifest.json", json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
