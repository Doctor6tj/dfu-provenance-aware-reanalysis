#!/usr/bin/env python3
"""Validate the minimum Figure 1 submission reproducibility package.

Usage:
    python validate_reproducibility_package.py <project_root>
    python validate_reproducibility_package.py <project_root> --manifest custom.json

This is a structural gate. A real regeneration run is still recommended.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

PLACEHOLDER_MARKERS = (
    "template only",
    "replace with the project-specific",
    "todo",
)


def fail_if_missing(root: Path, rel: str, failures: list[str], label: str) -> Path:
    p = root / rel
    if not p.exists():
        failures.append(f"Missing {label}: {rel}")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root")
    ap.add_argument("--manifest", default="Figure1_reproducibility_manifest.json")
    args = ap.parse_args()

    root = Path(args.project_root).resolve()
    manifest_path = root / args.manifest
    failures: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, object] = {}

    if not manifest_path.exists():
        failures.append(f"Missing reproducibility manifest: {manifest_path.name}")
        report = {"hard_pass": False, "failures": failures, "warnings": warnings}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        failures.append(f"Cannot parse reproducibility manifest: {e}")
        print(json.dumps({"hard_pass": False, "failures": failures}, indent=2, ensure_ascii=False))
        return 2

    visual_status = str(m.get("visual_status", "")).strip().lower()
    if visual_status != "render verified":
        failures.append("visual_status must be 'Render verified' before submission-ready QC")

    entry = str(m.get("entry_script", "")).strip()
    if not entry:
        failures.append("entry_script is not declared")
        entry_path = None
    else:
        entry_path = fail_if_missing(root, entry, failures, "project-specific generator")
        if entry_path.exists():
            if entry_path.suffix.lower() not in (".py", ".r"):
                failures.append("entry_script must be a .py or .R file")
            txt = entry_path.read_text(encoding="utf-8", errors="ignore")
            if len(txt.strip()) < 120:
                failures.append("entry_script is too small to be a credible project-specific generator")
            low = txt.lower()
            if any(marker in low for marker in PLACEHOLDER_MARKERS):
                failures.append("entry_script still contains template/placeholder markers")
            metrics["entry_script_bytes"] = entry_path.stat().st_size

    layout = str(m.get("layout_spec", "")).strip()
    source_manifest = str(m.get("source_manifest", "")).strip()
    environment_file = str(m.get("environment_file", "")).strip()
    run_command = str(m.get("run_command", "")).strip()

    if not layout:
        failures.append("layout_spec is not declared")
    else:
        fail_if_missing(root, layout, failures, "layout spec")

    if not source_manifest:
        failures.append("source_manifest is not declared")
    else:
        sm = fail_if_missing(root, source_manifest, failures, "source manifest")
        if sm.exists() and sm.stat().st_size < 20:
            failures.append("source manifest appears empty")

    if not environment_file:
        failures.append("environment_file is not declared")
    else:
        ef = fail_if_missing(root, environment_file, failures, "environment snapshot")
        if ef.exists() and ef.stat().st_size < 20:
            warnings.append("environment snapshot is very small; verify package versions are recorded")

    if not run_command:
        failures.append("run_command is not declared")

    stochastic = m.get("stochastic", None)
    if stochastic is None:
        failures.append("stochastic must be explicitly true or false")
    elif stochastic is True and m.get("seed", None) in (None, ""):
        failures.append("stochastic=true but no seed is declared")

    if m.get("manual_post_edit_required", False):
        failures.append("manual_post_edit_required=true: final geometry is not fully replayable")

    helpers = m.get("helper_scripts", [])
    if helpers is not None:
        if not isinstance(helpers, list):
            failures.append("helper_scripts must be a list when declared")
        else:
            for rel in helpers:
                hp = root / str(rel)
                if not hp.exists():
                    failures.append(f"Missing declared helper script: {rel}")

    outputs = m.get("declared_outputs", [])
    if not isinstance(outputs, list) or not outputs:
        failures.append("declared_outputs must contain final Figure 1 files")
    else:
        missing_outputs = []
        for rel in outputs:
            p = root / str(rel)
            if not p.exists():
                missing_outputs.append(str(rel))
        if missing_outputs:
            failures.append("Missing declared outputs: " + ", ".join(missing_outputs))
        metrics["declared_output_count"] = len(outputs)

    report = {
        "project_root": str(root),
        "manifest": str(manifest_path),
        "hard_pass": not failures,
        "submission_ready": not failures,
        "failures": failures,
        "warnings": warnings,
        "metrics": metrics,
        "manual_follow_up": [
            "execute the declared run_command in the documented environment",
            "compare regenerated visual output with the immutable render-verified version",
            "confirm no GUI-only post-edit is required",
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
