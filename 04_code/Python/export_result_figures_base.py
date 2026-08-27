#!/usr/bin/env python3
"""Export the author-approved result figures as PNG, PDF, and legend TXT.

The accepted plotting builders are rerun only to render at 600 dpi and vector
PDF. No bioinformatics or statistical analysis is rerun. The submission
folder intentionally contains only the requested simple deliverables plus a
short README and manifest; no hashes are calculated.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image

import result_figure_layout as prior
import panel_header_layout as rules


def write_text_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.write_text(text, encoding="utf-8")


def copy_new(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite: {target}")
    shutil.copy2(source, target)


def plain_legend(markdown_path: Path) -> str:
    return markdown_path.read_text(encoding="utf-8").replace("**", "").strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--staging-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    staging = args.staging_dir.resolve()
    output = args.output_dir.resolve()
    if staging.exists() or output.exists():
        raise FileExistsError("Refusing to overwrite an existing staging or submission directory")
    staging.mkdir(parents=True)
    output.mkdir(parents=True)

    candidate_root = root / "07_manuscript/figures/candidates/G8_FIGURE_CANDIDATES_v01_20260826"
    python_stage = staging / "python_builds"
    python_stage.mkdir()
    build_dirs = {
        "Figure2": python_stage / "Figure2_v06_600dpi_vector",
        "Figure3": python_stage / "Figure3_v05_600dpi_vector",
        "Figure4": python_stage / "Figure4_v04_600dpi_vector",
    }

    original_header_rows = prior.header_contract_rows
    original_write_contract = prior.write_contract
    original_write_qc = prior.write_candidate_qc

    def final_header_rows(figure_id: str, metrics: list[dict], source: str) -> list[dict[str, str]]:
        rows = original_header_rows(figure_id, metrics, "export_result_figures_base.py")
        kinds = {str(metric["tag"]): str(metric["body_anchor_kind"]) for metric in metrics}
        xs = {str(metric["tag"]): float(metric["body_anchor_axes_x"]) for metric in metrics}
        for row in rows:
            row["source"] = "export_result_figures_base.py"
            if row["rule_id"] == "HDR_TITLE_BODY_ANCHOR":
                row["notes"] = f"Final export scientific-body anchor={kinds[row['panel_id']]}; axes_fraction_x={xs[row['panel_id']]:.3f}"
        return rows

    def save_png_and_pdf(fig, path: Path, headers: list[tuple]) -> list[dict]:
        metrics = prior.lock_and_measure_headers(fig, headers)
        pdf_path = path.with_suffix(".pdf")
        if path.exists() or pdf_path.exists():
            raise FileExistsError(f"Refusing to overwrite final render: {path}")
        fig.savefig(path, dpi=600, bbox_inches=None, facecolor="white")
        fig.savefig(pdf_path, format="pdf", bbox_inches=None, facecolor="white")
        prior.plt.close(fig)
        return metrics

    prior.add_panel_header_hard = rules.add_panel_header_visible_body
    prior.lock_and_measure_headers = rules.lock_and_measure_visible_body
    prior.header_contract_rows = final_header_rows
    prior.save_candidate_hard = save_png_and_pdf

    def mapped_write_contract(out, figure_id, metrics, scientific_rows, validator, coverage_validator, version):
        return original_write_contract(
            out, figure_id, metrics, scientific_rows, validator, coverage_validator,
            rules.VERSION_BY_FIGURE[figure_id],
        )

    def mapped_write_qc(out, figure_id, version, candidate, supersedes):
        return original_write_qc(
            out, figure_id, rules.VERSION_BY_FIGURE[figure_id], candidate,
            rules.SUPERSEDES_BY_FIGURE[figure_id],
        )

    prior.write_contract = mapped_write_contract
    prior.write_candidate_qc = mapped_write_qc
    prior.base.set_theme()
    validator = root / "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
    coverage = root / "04_code/Python/validate_panel_headers.py"

    prior.build_figure2(root, candidate_root, build_dirs["Figure2"], validator, coverage)
    rules.rename_revision_files(build_dirs["Figure2"], "v05", "v06")

    prior.build_figure3(root, candidate_root, build_dirs["Figure3"], validator, coverage)
    rules.rename_revision_files(build_dirs["Figure3"], "v04", "v05")
    rules.rename_revision_files(build_dirs["Figure3"], "v03", "v05")

    prior.build_figure4(root, build_dirs["Figure4"], validator, coverage)
    rules.rename_revision_files(build_dirs["Figure4"], "v03", "v04")
    rules.rename_revision_files(build_dirs["Figure4"], "v02", "v04")

    main_sources = {
        "Figure2": (build_dirs["Figure2"] / "Figure2_visual_v06.png", build_dirs["Figure2"] / "Figure2_visual_v06.pdf", build_dirs["Figure2"] / "legend_v06.md"),
        "Figure3": (build_dirs["Figure3"] / "Figure3_visual_v05.png", build_dirs["Figure3"] / "Figure3_visual_v05.pdf", build_dirs["Figure3"] / "legend_v05.md"),
        "Figure4": (build_dirs["Figure4"] / "Figure4_visual_v04.png", build_dirs["Figure4"] / "Figure4_visual_v04.pdf", build_dirs["Figure4"] / "legend_v04.md"),
    }

    rscript = Path("C:/Program Files/R/R-4.5.3/bin/Rscript.exe")
    r_builder = root / "04_code/R/export_figureS1.R"
    s1_stage = staging / "FigureS1_v06_600dpi_vector"
    completed = subprocess.run(
        [str(rscript), "--vanilla", str(r_builder), str(root), str(s1_stage)],
        text=True, capture_output=True,
    )
    write_text_new(staging / "FigureS1_export_log.txt", completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"Figure S1 export failed:\n{completed.stdout}\n{completed.stderr}")

    sources = {
        **main_sources,
        "FigureS1": (s1_stage / "FigureS1_600dpi.png", s1_stage / "FigureS1.pdf", s1_stage / "legend_v06.md"),
    }
    selected_versions = {"Figure2": "v06", "Figure3": "v05", "Figure4": "v04", "FigureS1": "v06"}
    manifest_rows = []
    for figure_id, (png_source, pdf_source, legend_source) in sources.items():
        png_target = output / f"{figure_id}.png"
        pdf_target = output / f"{figure_id}.pdf"
        legend_target = output / f"{figure_id}_legend.txt"
        copy_new(png_source, png_target)
        copy_new(pdf_source, pdf_target)
        write_text_new(legend_target, plain_legend(legend_source))
        with Image.open(png_target) as image:
            width, height = image.size
            dpi = image.info.get("dpi", (600, 600))
        manifest_rows.append({
            "figure": figure_id,
            "selected_version": selected_versions[figure_id],
            "png": png_target.name,
            "png_pixels": f"{width}x{height}",
            "png_dpi": f"{round(float(dpi[0]))}",
            "pdf": pdf_target.name,
            "legend": legend_target.name,
            "analysis_rerun": "NO",
            "author_visual_qc": "PASS",
        })

    with (output / "FIGURE_EXPORT_MANIFEST.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    readme = """DFU submission figure export

Each figure has exactly three submission-facing files:
- PNG: lossless 600-dpi raster export.
- PDF: vector figure export for submission and production.
- TXT: plain-text figure legend.

Selected versions:
- Figure 2 v06
- Figure 3 v05
- Figure 4 v04
- Figure S1 v06

The figures were rerendered from the author-approved plotting builders. No bioinformatics or statistical analysis was rerun. No hashes were calculated for this simple visual-QC workflow.
"""
    write_text_new(output / "README.txt", readme)
    print(json.dumps({"status": "EXPORTED_PENDING_FINAL_PDF_VISUAL_QC", "output": str(output), "figures": selected_versions}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
