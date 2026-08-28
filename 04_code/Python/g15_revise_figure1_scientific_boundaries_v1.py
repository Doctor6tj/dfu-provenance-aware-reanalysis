#!/usr/bin/env python3
"""Revise Figure 1 submission wording without recomputing any analysis.

The accepted G9 Figure 1 generator remains the geometry authority. This script
builds the same layout from the same frozen inputs, changes only the two
submission-facing wording blocks affected by the presubmission scientific
audit, and exports an immutable candidate or final bundle.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("g9_figure1_authority", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Figure 1 authority: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


def revise_layout(layout: dict) -> dict:
    layout["candidate_version"] = "G15_v03"
    layout["status"] = "Presubmission scientific-boundary revision"
    nodes = {node["id"]: node for node in layout["nodes"]}

    nodes["N_INPUT"]["text_blocks"][1]["lines"] = [
        "127 accession records mapped to 94 conservative analytic units",
        "Core bulk: GSE80178 | exact-reuse audit: GSE68183",
        "Supporting single-cell context: GSE165816",
        "Non-core context: GSE134431 (healing), GSE143735 (forearm),",
        "GSE199939 (specimen-level ulcer status unresolved)",
    ]
    nodes["N_INPUT"]["text_blocks"][1]["font_sizes"] = [28] * 5
    nodes["N_INPUT"]["text_blocks"][1]["font_weights"] = [400] * 5
    nodes["N_INPUT"]["text_blocks"][1]["line_gaps"] = [8] * 4

    nodes["N_BOUNDARY"]["text_blocks"][1]["lines"] = [
        "No cross-study gene or pathway robustness claim was estimable",
        "No single-cell association passed global correction",
        "Non-significance does not establish biological absence",
    ]
    nodes["N_BOUNDARY"]["text_blocks"][1]["font_sizes"] = [28, 28, 28]
    nodes["N_BOUNDARY"]["text_blocks"][1]["font_weights"] = [400, 400, 400]
    nodes["N_BOUNDARY"]["text_blocks"][1]["line_gaps"] = [8, 8]
    nodes["N_BOUNDARY"]["y"] = 1600
    nodes["N_BOUNDARY"]["h"] = 200
    nodes["N_BOUNDARY"]["text_blocks"][0]["y"] = 1658
    nodes["N_BOUNDARY"]["text_blocks"][1]["y"] = 1708
    for edge in layout["edges"]:
        if edge["id"] == "E_TO_BOUNDARY":
            edge["points"][-1][1] = 1600
    return layout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--inkscape", required=True, type=Path)
    parser.add_argument("--stage", choices=("candidate", "final"), required=True)
    args = parser.parse_args()

    root = args.project_root.resolve()
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)

    authority_path = root / "04_code/Python/g9_generate_figure1_visual_candidate_v2.py"
    authority = load_module(authority_path)
    fact_path = root / "07_manuscript/control_manifests/G7_MANUSCRIPT_CONTROL_v1_20260826/result_fact_ledger.csv"
    role_path = root / "07_manuscript/control_manifests/G7_MANUSCRIPT_CONTROL_v1_20260826/dataset_role_transform_manifest.csv"
    authority.assert_sources(fact_path, role_path)

    layout = revise_layout(authority.build_layout())
    tools_dir = root / "04_code/vendor/figure_skills/sq5_v4.3/tools"
    renderer = authority.load_renderer(tools_dir / "render_layout_spec.py")
    spec_path = out / "Figure1_layout_spec_G15_v03.json"
    write_new(spec_path, json.dumps(layout, ensure_ascii=False, indent=2))

    run([sys.executable, str(tools_dir / "validate_layout_spec.py"), str(spec_path), "--min-pt", "7.5"])
    run([sys.executable, str(tools_dir / "validate_visual_grammar.py"), str(spec_path)])
    run([
        sys.executable,
        str(tools_dir / "validate_rendered_output.py"),
        str(spec_path),
        "--regular-font", "C:\\Windows\\Fonts\\arial.ttf",
        "--bold-font", "C:\\Windows\\Fonts\\arialbd.ttf",
        "--report", str(out / "Figure1_text_fit_G15_v03.json"),
    ])

    svg_path = out / "Figure1_Study_Design_G15_v03.svg"
    write_new(svg_path, renderer.make_svg(layout))
    if args.stage == "candidate":
        png_path = out / "Figure1_Study_Design_G15_v03_candidate_300dpi.png"
        run([
            str(args.inkscape.resolve()), str(svg_path),
            "--export-type=png", f"--export-filename={png_path}",
            "--export-width=1900", "--export-height=1860",
        ])
    else:
        png_path = out / "Figure1_Study_Design_G15_v03_600dpi.png"
        pdf_path = out / "Figure1_Study_Design_G15_v03.pdf"
        run([
            str(args.inkscape.resolve()), str(svg_path),
            "--export-type=png", f"--export-filename={png_path}",
            "--export-width=4252", "--export-height=4162",
        ])
        run([
            str(args.inkscape.resolve()), str(svg_path),
            "--export-type=pdf", f"--export-filename={pdf_path}",
        ])

    legend = (
        "Figure 1. Provenance-aware study design and evidence hierarchy. Six public human "
        "diabetic-foot transcriptomic series were mapped from 127 accession records to 94 "
        "conservative analytic units. GSE80178 supplied the core within-study bulk contrasts, "
        "whereas GSE165816 supplied supporting participant-level single-cell context. GSE68183 "
        "was retained as an exact-reuse source; GSE134431, GSE143735, and GSE199939 remained "
        "outside the quantitative core. Specimen-level ulcer status was unresolved for GSE199939. "
        "Only one independent compatible core bulk study remained, so cross-study gene and pathway "
        "robustness were not estimable. No single-cell association passed global correction; this "
        "does not establish biological absence.\n"
    )
    write_new(out / "Figure1_legend_G15_v03.txt", legend)
    manifest = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "operation": "WORDING_ONLY_NO_ANALYSIS_RERUN",
        "stage": args.stage,
        "authority": str(authority_path),
        "frozen_inputs": [str(fact_path), str(role_path)],
        "changes": [
            "GSE199939 described as specimen-level ulcer status unresolved",
            "single-cell result described as no association passing global correction",
            "global registry count described as conservative analytic units",
        ],
        "output": str(png_path),
    }
    write_new(out / "Figure1_G15_v03_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
