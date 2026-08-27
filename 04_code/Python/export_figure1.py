#!/usr/bin/env python3
"""Export author-approved Figure 1 v02 from its single locked layout spec.

The script performs no biological or statistical analysis. It regenerates the
approved artwork through the pinned SQ5 renderer, writes immutable SVG, 600-dpi
PNG, and vector PDF outputs, and verifies actual PNG/PDF rendering.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageStat


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_new(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def run_capture(command: list[str], report_path: Path) -> dict:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    report = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    write_new(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {command}\n{completed.stdout}\n{completed.stderr}"
        )
    return report


def load_renderer(renderer_path: Path):
    module_spec = importlib.util.spec_from_file_location("sq5_render_layout_spec", renderer_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Unable to load renderer: {renderer_path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def set_svg_physical_size(svg_text: str, width_px: int, height_px: int, width_mm: float) -> tuple[str, float]:
    height_mm = width_mm * height_px / width_px
    pattern = rf'width="{width_px}" height="{height_px}"'
    replacement = f'width="{width_mm:.6f}mm" height="{height_mm:.6f}mm"'
    sized_svg, count = re.subn(pattern, replacement, svg_text, count=1)
    if count != 1:
        raise RuntimeError("Unable to set final SVG physical dimensions")
    return sized_svg, height_mm


def compare_exact(reference_path: Path, regenerated_path: Path) -> dict:
    reference = Image.open(reference_path).convert("RGBA")
    regenerated = Image.open(regenerated_path).convert("RGBA")
    if reference.size != regenerated.size:
        return {
            "exact": False,
            "reference_size": reference.size,
            "regenerated_size": regenerated.size,
            "reason": "size_mismatch",
        }
    diff = ImageChops.difference(reference, regenerated)
    bbox = diff.getbbox()
    extrema = diff.getextrema()
    return {
        "exact": bbox is None,
        "reference_size": reference.size,
        "regenerated_size": regenerated.size,
        "difference_bbox": bbox,
        "channel_extrema": extrema,
    }


def compare_near(reference_path: Path, rendered_path: Path) -> dict:
    reference = Image.open(reference_path).convert("RGB")
    rendered = Image.open(rendered_path).convert("RGB")
    if rendered.size != reference.size:
        rendered = rendered.resize(reference.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(reference, rendered)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / len(stat.mean)
    rms = math.sqrt(sum(value * value for value in stat.rms) / len(stat.rms))
    return {
        "reference_size": reference.size,
        "rendered_size_after_alignment": rendered.size,
        "mean_absolute_channel_difference": mean_abs,
        "rms_channel_difference": rms,
        "difference_bbox": diff.getbbox(),
    }


def render_pdf_with_fitz(pdf_path: Path, output_png: Path, target_width_px: int) -> dict:
    document = fitz.open(pdf_path)
    if document.page_count != 1:
        raise RuntimeError(f"Expected one-page Figure 1 PDF, found {document.page_count}")
    page = document[0]
    rect = page.rect
    scale = target_width_px / rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    if output_png.exists():
        raise FileExistsError(f"Refusing to overwrite: {output_png}")
    pix.save(str(output_png))
    result = {
        "page_count": document.page_count,
        "page_width_pt": rect.width,
        "page_height_pt": rect.height,
        "page_width_mm": rect.width * 25.4 / 72,
        "page_height_mm": rect.height * 25.4 / 72,
        "render_width_px": pix.width,
        "render_height_px": pix.height,
    }
    document.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--inkscape", required=True, type=Path)
    parser.add_argument("--author-visual-lock", required=True, choices=["APPROVED"])
    args = parser.parse_args()

    root = args.project_root.resolve()
    candidate = args.candidate_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty final directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    qc_dir = output / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    spec_source = candidate / "Figure1_layout_spec_v02.json"
    approved_png = candidate / "Figure1_visual_v02.png"
    build_qc_source = candidate / "qc/Figure1_candidate_build_QC_v02.json"
    visual_qc_source = candidate / "qc/Figure1_manual_visual_QC_v02.json"
    legend_source = candidate / "Figure1_legend_v02.md"
    source_manifest_source = candidate / "Figure1_source_manifest_v02.csv"
    environment_source = candidate / "Figure1_environment_v02.json"
    blueprint_source = candidate / "Figure1_design_blueprint_v02.md"
    generator_source = root / "04_code/Python/build_figure1.py"
    export_script = root / "04_code/Python/export_figure1.py"
    renderer_path = root / "04_code/vendor/figure_skills/sq5_v4.3/tools/render_layout_spec.py"

    required_files = [
        spec_source,
        approved_png,
        build_qc_source,
        visual_qc_source,
        legend_source,
        source_manifest_source,
        environment_source,
        blueprint_source,
        generator_source,
        export_script,
        renderer_path,
    ]
    for required in required_files:
        if not required.is_file():
            raise FileNotFoundError(required)

    build_qc = json.loads(build_qc_source.read_text(encoding="utf-8"))
    visual_qc = json.loads(visual_qc_source.read_text(encoding="utf-8"))
    if build_qc.get("status") != "PASS":
        raise RuntimeError("Candidate build QC is not PASS")
    if visual_qc.get("review_status") != "PASS_VISUAL_CANDIDATE_AWAITING_USER_LOCK":
        raise RuntimeError("Candidate visual QC is not ready for author lock")

    layout = json.loads(spec_source.read_text(encoding="utf-8"))
    if layout.get("candidate_version") != "v02":
        raise RuntimeError("Unexpected Figure 1 layout version")
    width_px = int(layout["canvas"]["width_px"])
    height_px = int(layout["canvas"]["height_px"])
    if (width_px, height_px) != (1900, 1860):
        raise RuntimeError(f"Unexpected locked canvas: {(width_px, height_px)}")

    target_width_mm = float(layout["publication"]["target_width_mm"])
    renderer = load_renderer(renderer_path)
    svg_text = renderer.make_svg(layout)
    svg_text, target_height_mm = set_svg_physical_size(
        svg_text, width_px, height_px, target_width_mm
    )

    svg_path = output / "Figure1_Study_Design_v02_final.svg"
    png_path = output / "Figure1_Study_Design_v02_600dpi.png"
    pdf_path = output / "Figure1_Study_Design_v02_final.pdf"
    pdf_render_path = qc_dir / "Figure1_Study_Design_v02_pdf_render.png"
    spec_final = output / "Figure1_layout_spec_v02_locked.json"
    legend_final = output / "Figure1_legend_v02_final.txt"
    write_new(svg_path, svg_text)
    copy_new(spec_source, spec_final)
    legend_text = legend_source.read_text(encoding="utf-8").replace("**", "").strip() + "\n"
    write_new(legend_final, legend_text)

    with tempfile.TemporaryDirectory(prefix="dfu_figure1_final_v02_") as temp_dir_name:
        regenerated_preview = Path(temp_dir_name) / "Figure1_regenerated_1900x1860.png"
        run_capture(
            [
                str(args.inkscape.resolve()),
                str(svg_path),
                "--export-type=png",
                f"--export-filename={regenerated_preview}",
                f"--export-width={width_px}",
                f"--export-height={height_px}",
                "--export-area-page",
            ],
            qc_dir / "Figure1_preview_regeneration_command_v02.json",
        )
        exact_comparison = compare_exact(approved_png, regenerated_preview)
        if not exact_comparison.get("exact"):
            raise RuntimeError(f"Final SVG does not exactly reproduce approved candidate: {exact_comparison}")

    run_capture(
        [
            str(args.inkscape.resolve()),
            str(svg_path),
            "--export-type=png",
            f"--export-filename={png_path}",
            "--export-dpi=600",
            "--export-area-page",
        ],
        qc_dir / "Figure1_600dpi_png_export_command_v02.json",
    )
    run_capture(
        [
            str(args.inkscape.resolve()),
            str(svg_path),
            "--export-type=pdf",
            f"--export-filename={pdf_path}",
            "--export-area-page",
            "--export-text-to-path=false",
        ],
        qc_dir / "Figure1_pdf_export_command_v02.json",
    )

    highres = Image.open(png_path)
    expected_width = round(target_width_mm / 25.4 * 600)
    expected_height = round(target_height_mm / 25.4 * 600)
    png_qc = {
        "width_px": highres.width,
        "height_px": highres.height,
        "expected_width_px": expected_width,
        "expected_height_px": expected_height,
        "reported_dpi": highres.info.get("dpi"),
        "mode": highres.mode,
    }
    if abs(highres.width - expected_width) > 1 or abs(highres.height - expected_height) > 1:
        raise RuntimeError(f"Unexpected 600-dpi PNG dimensions: {png_qc}")

    pdf_qc = render_pdf_with_fitz(pdf_path, pdf_render_path, width_px)
    if abs(pdf_qc["page_width_mm"] - target_width_mm) > 0.05:
        raise RuntimeError(f"Unexpected PDF width: {pdf_qc}")
    if abs(pdf_qc["page_height_mm"] - target_height_mm) > 0.05:
        raise RuntimeError(f"Unexpected PDF height: {pdf_qc}")
    pdf_visual_comparison = compare_near(approved_png, pdf_render_path)

    copy_new(source_manifest_source, output / "Figure1_source_manifest_v02.csv")
    copy_new(environment_source, output / "Figure1_environment_v02.json")
    copy_new(blueprint_source, output / "Figure1_design_blueprint_v02.md")
    copy_new(build_qc_source, qc_dir / "Figure1_candidate_build_QC_v02.json")
    copy_new(visual_qc_source, qc_dir / "Figure1_manual_visual_QC_v02.json")

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    final_qc = {
        "schema_version": "1.0",
        "created_at": created_at,
        "status": "PASS_RENDER_VERIFIED",
        "author_visual_lock": args.author_visual_lock,
        "single_source_layout": str(spec_source),
        "approved_candidate": str(approved_png),
        "preview_regeneration_exact": exact_comparison,
        "png_600dpi": png_qc,
        "pdf": pdf_qc,
        "pdf_render_comparison": pdf_visual_comparison,
        "final_exports": {
            "svg": str(svg_path),
            "png_600dpi": str(png_path),
            "pdf": str(pdf_path),
            "legend": str(legend_final),
        },
        "scientific_analysis_rerun": False,
        "submission_ready_pending_archive": True,
        "next_gate": "SQ8_FIGURE1_ARCHIVE_LOCK",
    }
    write_new(
        qc_dir / "Figure1_final_render_QC_v02.json",
        json.dumps(final_qc, ensure_ascii=False, indent=2),
    )

    readme = f"""Figure 1 final export v02

Status: PASS_RENDER_VERIFIED; author visual lock APPROVED
Single source: Figure1_layout_spec_v02_locked.json
Physical size: {target_width_mm:.3f} x {target_height_mm:.3f} mm
PNG: 600 dpi, {highres.width} x {highres.height} px
PDF: one-page vector export at final physical size
SVG: editable vector export at final physical size
Approved-preview regeneration: exact pixel identity at 1900 x 1860 px
Scientific/statistical analysis rerun: no
Next gate: SQ8 immutable Figure 1 source/code/QC archive lock
"""
    write_new(output / "README.txt", readme)
    environment = {
        "created_at": created_at,
        "python": sys.version,
        "platform": platform.platform(),
        "pymupdf": fitz.VersionBind,
        "pillow": Image.__version__,
        "inkscape": str(args.inkscape.resolve()),
        "renderer": str(renderer_path),
    }
    write_new(qc_dir / "Figure1_final_export_environment_v02.json", json.dumps(environment, ensure_ascii=False, indent=2))

    print(
        json.dumps(
            {
                "status": "PASS_RENDER_VERIFIED",
                "output_dir": str(output),
                "png_px": [highres.width, highres.height],
                "pdf_mm": [pdf_qc["page_width_mm"], pdf_qc["page_height_mm"]],
                "preview_exact": exact_comparison["exact"],
                "next_gate": "SQ8_FIGURE1_ARCHIVE_LOCK",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
