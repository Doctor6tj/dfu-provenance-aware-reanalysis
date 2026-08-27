#!/usr/bin/env python3
"""Build Figure 1 visual candidate v02 from frozen project interfaces.

This script never recomputes biological results. It validates the accepted fact
and dataset-role interfaces, writes a machine-readable layout specification,
runs SQ5 preflight checks, and creates a PNG-only review candidate. Submission
SVG/PDF/TIFF exports are intentionally deferred until visual lock.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv_new(path: Path, fields: list[str], rows: list[dict]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def text_block(
    block_id: str,
    lines: list[str],
    x: float,
    y: float,
    size: float,
    weight: int = 400,
    anchor: str = "start",
) -> dict:
    return {
        "id": block_id,
        "lines": lines,
        "x": x,
        "y": y,
        "font_size": size,
        "font_sizes": [size] * len(lines),
        "font_weight": weight,
        "font_weights": [weight] * len(lines),
        "line_gap": 1.18,
        "line_gaps": [8] * max(0, len(lines) - 1),
        "text_anchor": anchor,
    }


def card(
    node_id: str,
    node_class: str,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: list[str],
    stroke: str,
    fill: str,
    stage: str,
    sibling: str | None = None,
    body_size: float = 28,
) -> dict:
    result = {
        "id": node_id,
        "node_class": node_class,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "radius": 18,
        "fill": fill,
        "stroke": stroke,
        "stroke_width": 2.4,
        "stage_id": stage,
        "text_alignment": "left",
        "text_left_padding_px": 34,
        "text_blocks": [
            text_block(f"{node_id}_title", [title], x + 34, y + 58, 32, 700),
            text_block(f"{node_id}_body", body, x + 34, y + 108, body_size, 400),
        ],
    }
    if sibling:
        result["sibling_group"] = sibling
    return result


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


def assert_sources(fact_path: Path, role_path: Path) -> tuple[dict, dict]:
    facts = {
        row["fact_id"]: row
        for row in csv.DictReader(fact_path.open(encoding="utf-8-sig"))
    }
    roles = {
        row["dataset_id"]: row
        for row in csv.DictReader(role_path.open(encoding="utf-8-sig"))
    }
    required_facts = {
        "FACT_M02_INTERFACE": "127 accessions to 94 analytic participant units",
        "FACT_M05_STUDIES": "1",
        "FACT_M05_ROBUST_GENES": "0/18,865",
        "FACT_M05_PATHWAY": "Not estimable",
        "FACT_M07_INPUT": "14 libraries; 11 participants; 7 healers; 4 nonhealers; 45,514 cells",
        "FACT_M07_GLOBAL_NULL": "0 significant; minimum global FDR 0.308834036196974",
    }
    for fact_id, expected in required_facts.items():
        actual = facts.get(fact_id, {}).get("exact_value")
        if actual != expected:
            raise RuntimeError(
                f"Frozen Figure 1 fact mismatch: {fact_id}; expected={expected!r}; actual={actual!r}"
            )

    required_roles = {
        "GSE68183": "PROVENANCE_ALIAS_SOURCE_ONLY",
        "GSE80178": "CORE_PRIMARY_WITHIN_STUDY",
        "GSE134431": "DEFERRED_VALUE_ADD_M06",
        "GSE143735": "SYSTEMIC_CONTEXT_ONLY",
        "GSE199939": "BACKGROUND_OR_SEPARATELY_LABELLED_SENSITIVITY",
        "GSE165816": "PARTICIPANT_AWARE_VALUE_ADD",
    }
    if set(roles) != set(required_roles):
        raise RuntimeError(
            f"Dataset registry mismatch: expected={sorted(required_roles)}; actual={sorted(roles)}"
        )
    for dataset_id, expected_role in required_roles.items():
        actual_role = roles[dataset_id]["analysis_role"]
        if actual_role != expected_role:
            raise RuntimeError(
                f"Frozen dataset role mismatch: {dataset_id}; expected={expected_role}; actual={actual_role}"
            )
    return required_facts, required_roles


def build_layout() -> dict:
    text = "#27323C"
    connector = "#5F6B76"
    blue = "#4B7EAF"
    blue_fill = "#EDF4FB"
    green = "#5A9B55"
    green_fill = "#F1F7F0"
    synthesis = "#6E7F73"
    synthesis_fill = "#F4F7F4"
    boundary = "#7D858D"
    boundary_fill = "#FAFAF9"

    layout = {
        "schema_version": "1.2",
        "figure_id": "Figure1_Study_Design",
        "candidate_version": "v02",
        "status": "Visual candidate; not submission locked",
        "canvas": {"width_px": 1900, "height_px": 1860, "background": "#FFFFFF"},
        "publication": {"target_width_mm": 180, "stress_test_width_mm": 170, "final_dpi": 600},
        "styles": {
            "profile": "minimal_journal_workflow",
            "font_family": "Arial, Helvetica, sans-serif",
            "node_defaults": {"stroke_width": 2.4, "top_accent_line": False, "header_mode": "plain"},
            "section_header": {"underline": False, "decorative_rule": False},
            "main_line": {"width": 2.4},
            "arrowhead": {"length_px": 10, "width_px": 8},
            "text_alignment": {"left_padding_mm_target_low": 3.2, "shared_anchor_tolerance_mm": 0.5},
            "spacing_mm": {"major_stage_gap_min": 7.0},
            "palette": {
                "text": text,
                "connector": connector,
                "blue": blue,
                "blue_fill": blue_fill,
                "green": green,
                "green_fill": green_fill,
                "synthesis": synthesis,
                "synthesis_fill": synthesis_fill,
                "boundary": boundary,
                "boundary_fill": boundary_fill,
            },
        },
        "nodes": [],
        "edges": [],
    }

    input_node = card(
        "N_INPUT",
        "information_card",
        80,
        60,
        1740,
        290,
        "Six public human DFU transcriptomic series",
        [
            "127 accession records mapped to 94 analytic participant units",
            "Core bulk: GSE80178 | exact-reuse audit: GSE68183",
            "Supporting single-cell context: GSE165816",
            "Non-core context: GSE134431 (healing), GSE143735 (forearm),",
            "GSE199939 (foot-skin background)",
        ],
        "#8793A0",
        "#F7F8F8",
        "01_input",
        body_size=28,
    )
    layout["nodes"].append(input_node)

    layout["nodes"].extend(
        [
            card(
                "N_IDENTITY",
                "information_card",
                80,
                440,
                540,
                230,
                "Source-object identity",
                [
                    "Six GSE68183 controls exactly",
                    "matched GSE80178 raw objects",
                    "Duplicate labels remained",
                    "provenance, not added evidence",
                ],
                blue,
                blue_fill,
                "02_integrity",
                "integrity",
            ),
            card(
                "N_COMPARATOR",
                "information_card",
                680,
                440,
                540,
                230,
                "Comparator roles",
                [
                    "DFU, diabetic intact foot, and",
                    "nondiabetic intact foot skin",
                    "remained distinct strata",
                    "Other contexts stayed outside",
                ],
                blue,
                blue_fill,
                "02_integrity",
                "integrity",
            ),
            card(
                "N_UNIT",
                "information_card",
                1280,
                440,
                540,
                230,
                "Participant-level units",
                [
                    "Participants were the clinical",
                    "inferential units",
                    "Cells, libraries, and reused",
                    "objects were not independent n",
                ],
                blue,
                blue_fill,
                "02_integrity",
                "integrity",
            ),
        ]
    )

    layout["nodes"].extend(
        [
            card(
                "N_BULK",
                "information_card",
                140,
                810,
                760,
                350,
                "Core bulk inference",
                [
                    "GSE80178: 12 arrays",
                    "6 DFU, 3 diabetic intact foot,",
                    "3 nondiabetic intact foot",
                    "RMA plus limma; prespecified contrasts",
                    "Robustness required at least 2",
                    "independent compatible studies",
                ],
                blue,
                blue_fill,
                "03_streams",
                "streams",
            ),
            card(
                "N_SC",
                "information_card",
                1000,
                810,
                760,
                350,
                "Supporting single-cell context",
                [
                    "GSE165816: foot skin only",
                    "14 libraries from 11 participants",
                    "7 healers and 4 nonhealers",
                    "Outcome-blinded cell annotation",
                    "Participant-cell-type pseudobulk",
                    "One global BH correction",
                ],
                green,
                green_fill,
                "03_streams",
                "streams",
            ),
        ]
    )

    layout["nodes"].append(
        card(
            "N_SYNTHESIS",
            "integration_card",
            260,
            1290,
            1380,
            190,
            "Provenance-aware evidence assessment",
            [
                "One independent compatible core bulk study remained",
                "Single-cell outcome testing supplied participant-level context",
                "Cross-study robustness and supporting evidence remained distinct",
            ],
            synthesis,
            synthesis_fill,
            "04_synthesis",
        )
    )
    boundary_node = card(
        "N_BOUNDARY",
        "qualifier_card",
        310,
        1630,
        1280,
        170,
        "Interpretation boundary",
        [
            "No cross-study gene or pathway robustness claim was estimable",
            "Global null evidence does not establish biological absence or replication",
        ],
        boundary,
        boundary_fill,
        "05_boundary",
        body_size=28,
    )
    boundary_node["stroke_width"] = 1.8
    layout["nodes"].append(boundary_node)

    layout["edges"] = [
        {"id": "E_INPUT_STEM", "edge_type": "main_flow", "points": [[950, 350], [950, 395]], "stroke": connector, "stroke_width": 2.4, "arrow": False},
        {"id": "E_INPUT_DIST", "edge_type": "parallel_evidence_branch", "points": [[350, 395], [1550, 395]], "stroke": connector, "stroke_width": 2.4, "arrow": False},
        {"id": "E_TO_IDENTITY", "edge_type": "parallel_evidence_branch", "points": [[350, 395], [350, 440]], "stroke": connector, "stroke_width": 2.4, "arrow": True, "to": "N_IDENTITY"},
        {"id": "E_TO_COMPARATOR", "edge_type": "parallel_evidence_branch", "points": [[950, 395], [950, 440]], "stroke": connector, "stroke_width": 2.4, "arrow": True, "to": "N_COMPARATOR"},
        {"id": "E_TO_UNIT", "edge_type": "parallel_evidence_branch", "points": [[1550, 395], [1550, 440]], "stroke": connector, "stroke_width": 2.4, "arrow": True, "to": "N_UNIT"},
        {"id": "E_IDENTITY_DOWN", "edge_type": "evidence_convergence", "points": [[350, 670], [350, 730]], "stroke": "#7A8590", "stroke_width": 2.0, "arrow": False},
        {"id": "E_COMPARATOR_DOWN", "edge_type": "evidence_convergence", "points": [[950, 670], [950, 730]], "stroke": "#7A8590", "stroke_width": 2.0, "arrow": False},
        {"id": "E_UNIT_DOWN", "edge_type": "evidence_convergence", "points": [[1550, 670], [1550, 730]], "stroke": "#7A8590", "stroke_width": 2.0, "arrow": False},
        {"id": "E_INTEGRITY_DIST", "edge_type": "evidence_convergence", "points": [[350, 730], [1550, 730]], "stroke": "#7A8590", "stroke_width": 2.0, "arrow": False},
        {"id": "E_TO_BULK", "edge_type": "parallel_evidence_branch", "points": [[520, 730], [520, 810]], "stroke": blue, "stroke_width": 2.4, "arrow": True, "to": "N_BULK"},
        {"id": "E_TO_SC", "edge_type": "parallel_evidence_branch", "points": [[1380, 730], [1380, 810]], "stroke": green, "stroke_width": 2.4, "arrow": True, "to": "N_SC"},
        {"id": "E_BULK_CONVERGE", "edge_type": "evidence_convergence", "points": [[520, 1160], [520, 1220], [950, 1220]], "stroke": blue, "stroke_width": 2.0, "arrow": False},
        {"id": "E_SC_CONVERGE", "edge_type": "evidence_convergence", "points": [[1380, 1160], [1380, 1220], [950, 1220]], "stroke": green, "stroke_width": 2.0, "arrow": False},
        {"id": "E_TO_SYNTHESIS", "edge_type": "evidence_convergence", "points": [[950, 1220], [950, 1290]], "stroke": connector, "stroke_width": 2.4, "arrow": True, "to": "N_SYNTHESIS"},
        {"id": "E_TO_BOUNDARY", "edge_type": "qualifier_boundary", "points": [[950, 1480], [950, 1630]], "stroke": boundary, "stroke_width": 1.8, "dash": [8, 8], "arrow": False, "to": "N_BOUNDARY"},
    ]
    return layout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--inkscape", required=True, type=Path)
    args = parser.parse_args()

    root = args.project_root.resolve()
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty candidate directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    qc_dir = out / "qc"
    hotspot_dir = qc_dir / "hotspots"
    qc_dir.mkdir(parents=True, exist_ok=True)
    hotspot_dir.mkdir(parents=True, exist_ok=True)

    fact_path = root / "07_manuscript/control_manifests/G7_MANUSCRIPT_CONTROL_v1_20260826/result_fact_ledger.csv"
    role_path = root / "07_manuscript/control_manifests/G7_MANUSCRIPT_CONTROL_v1_20260826/dataset_role_transform_manifest.csv"
    claim_path = root / "07_manuscript/control_manifests/G7_MANUSCRIPT_CONTROL_v1_20260826/claim_evidence_map.csv"
    required_facts, required_roles = assert_sources(fact_path, role_path)

    layout = build_layout()
    spec_path = out / "Figure1_layout_spec_v02.json"
    png_path = out / "Figure1_visual_v02.png"
    write_new(spec_path, json.dumps(layout, ensure_ascii=False, indent=2))

    write_new(
        out / "Figure1_design_blueprint_v02.md",
        """# Figure 1 design blueprint v02

- Role: summarize the provenance-aware study design and evidence hierarchy; do not duplicate detailed result panels.
- Archetype: parallel core-bulk and supporting-single-cell streams with integrated interpretation and a claim boundary.
- Registered series: all six are named, but only GSE80178 is core bulk evidence and GSE165816 is supporting single-cell context.
- Provenance alias: GSE68183 is an exact-reuse audit source, not an independent cohort.
- Non-core context: GSE134431, GSE143735, and GSE199939 remain visibly outside the quantitative core.
- Inferential unit: participant-level throughout; cells, libraries, and reused objects are not independent sample size.
- Visual profile: SQ5 minimal journal workflow; blue for core bulk, green for supporting single-cell, neutral synthesis/boundary.
- Claim boundary: no cross-study gene/pathway robustness claim is estimable; global null evidence is not biological absence.
- Target width: 180 mm; stress test: 170 mm.
- Review status: PNG visual candidate only; submission exports are deferred until visual lock.
""",
    )
    write_new(
        out / "Figure1_legend_v02.md",
        """**Figure 1. Provenance-aware study design and evidence hierarchy.** Six public human diabetic-foot transcriptomic series were mapped from 127 accession records to 94 analytic participant units. Source-object identity, tissue and comparator roles, and participant-level inference were resolved before modeling. GSE80178 supplied the core within-study bulk contrasts, whereas GSE165816 supplied supporting participant-level single-cell context. GSE68183 was retained as an exact-reuse audit source, and GSE134431, GSE143735, and GSE199939 remained outside the quantitative core. Only one independent compatible core bulk study remained; therefore, cross-study gene and pathway robustness claims were not estimable. The globally null single-cell analysis was supporting context rather than independent replication and does not establish biological absence.
""",
    )

    source_rows = [
        {"source_id": "F1S001", "path": str(fact_path.relative_to(root)), "role": "Accepted numerical and estimability facts", "status": "READ_ONLY_ACCEPTED", "notes": "127 to 94; one compatible core study; supporting single-cell input and global null"},
        {"source_id": "F1S002", "path": str(role_path.relative_to(root)), "role": "Six-series role and boundary registry", "status": "READ_ONLY_ACCEPTED", "notes": "Core, provenance-alias, supporting, deferred, context-only, and background roles"},
        {"source_id": "F1S003", "path": str(claim_path.relative_to(root)), "role": "Claim hierarchy and prohibited extensions", "status": "READ_ONLY_ACCEPTED", "notes": "Primary, supporting, and limitation claims"},
        {"source_id": "F1S004", "path": "04_code/Python/build_figure1.py", "role": "Deterministic project-specific Figure 1 generator", "status": "VERSIONED_SCRIPT", "notes": "Validates frozen inputs; writes spec; renders PNG-only review candidate"},
        {"source_id": "F1S005", "path": "04_code/vendor/figure_skills/sq5_v4.3/tools", "role": "Pinned SQ5 rendering and QC utilities", "status": "PINNED_VENDOR", "notes": "Layout, visual-grammar, rendered-output, and hotspot checks"},
    ]
    write_csv_new(
        out / "Figure1_source_manifest_v02.csv",
        ["source_id", "path", "role", "status", "notes"],
        source_rows,
    )
    write_new(
        out / "Figure1_language_routing_card_v02.md",
        """# Figure 1 language routing card v02

- Scientific family: study-design and evidence-hierarchy workflow.
- Authoritative inputs: locked language-neutral CSV interfaces.
- Authoritative implementation: saved Python project generator plus pinned SQ5 v4.3 utilities.
- Statistical recomputation: none.
- Renderer: deterministic SVG geometry rendered to a PNG review image through Inkscape; temporary SVG is not retained.
- Migration restriction: do not redraw manually or in another language after visual lock; create a new version instead.
- Status: AUTO_NATIVE, Python selected for deterministic geometry.
""",
    )

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tools_dir = root / "04_code/vendor/figure_skills/sq5_v4.3/tools"
    renderer_path = tools_dir / "render_layout_spec.py"
    environment = {
        "created_at": created_at,
        "python": sys.version,
        "platform": platform.platform(),
        "inkscape": str(args.inkscape.resolve()),
        "stochastic": False,
        "statistical_recomputation": False,
        "renderer": str(renderer_path.resolve()),
        "preview_policy": "PNG_ONLY_UNTIL_VISUAL_LOCK",
    }
    write_new(out / "Figure1_environment_v02.json", json.dumps(environment, ensure_ascii=False, indent=2))

    run_capture(
        [args.python, str(tools_dir / "validate_layout_spec.py"), str(spec_path), "--min-pt", "7.5"],
        qc_dir / "Figure1_layout_spec_preflight_v02.json",
    )
    run_capture(
        [args.python, str(tools_dir / "validate_visual_grammar.py"), str(spec_path)],
        qc_dir / "Figure1_visual_grammar_preflight_v02.json",
    )
    run_capture(
        [
            args.python,
            str(tools_dir / "validate_rendered_output.py"),
            str(spec_path),
            "--regular-font",
            "C:\\Windows\\Fonts\\arial.ttf",
            "--bold-font",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "--report",
            str(qc_dir / "Figure1_real_font_fit_v02.json"),
        ],
        qc_dir / "Figure1_real_font_fit_command_v02.json",
    )

    renderer = load_renderer(renderer_path)
    svg_text = renderer.make_svg(layout)
    with tempfile.TemporaryDirectory(prefix="dfu_figure1_v02_") as temp_dir:
        temp_svg = Path(temp_dir) / "Figure1_visual_v02_working.svg"
        temp_svg.write_text(svg_text, encoding="utf-8")
        run_capture(
            [
                str(args.inkscape.resolve()),
                str(temp_svg),
                "--export-type=png",
                f"--export-filename={png_path}",
                "--export-width=1900",
                "--export-height=1860",
            ],
            qc_dir / "Figure1_png_render_v02.json",
        )

    run_capture(
        [
            args.python,
            str(tools_dir / "make_hotspot_crops.py"),
            str(spec_path),
            str(png_path),
            str(hotspot_dir),
            "--node",
            "N_INPUT",
            "--node",
            "N_IDENTITY",
            "--node",
            "N_COMPARATOR",
            "--node",
            "N_UNIT",
            "--node",
            "N_BULK",
            "--node",
            "N_SC",
            "--node",
            "N_SYNTHESIS",
            "--node",
            "N_BOUNDARY",
        ],
        qc_dir / "Figure1_hotspot_generation_v02.json",
    )

    build_qc = {
        "schema_version": "1.0",
        "created_at": created_at,
        "status": "PASS",
        "candidate_status": "VISUAL_CANDIDATE_NOT_SUBMISSION_LOCKED",
        "frozen_facts_checked": required_facts,
        "frozen_dataset_roles_checked": required_roles,
        "output_png": str(png_path),
        "output_svg": None,
        "submission_ready": False,
        "next_gate": "ACTUAL_RENDER_VISUAL_QC_THEN_USER_VISUAL_LOCK",
    }
    write_new(
        qc_dir / "Figure1_candidate_build_QC_v02.json",
        json.dumps(build_qc, ensure_ascii=False, indent=2),
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "candidate": str(png_path),
                "submission_vector_exported": False,
                "next_gate": build_qc["next_gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
