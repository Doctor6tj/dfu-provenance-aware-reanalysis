#!/usr/bin/env python3
"""Fail when a composite figure omits required SQ3 panel-header contracts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_RULES = {
    "HDR_TITLE_BODY_ANCHOR",
    "HDR_TAG_TITLE_BASELINE",
    "HDR_TAG_TITLE_GAP",
    "HDR_TAG_TITLE_SIZE_DELTA",
}
REQUIRED_ENFORCEMENT = {"BUILDER_ASSERTION", "GEOMETRY_QC", "ACTUAL_RENDER"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--panels", required=True, help="Comma-separated panel IDs")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    panels = [item.strip() for item in args.panels.split(",") if item.strip()]
    if not panels or len(panels) != len(set(panels)):
        raise SystemExit("Expected unique nonblank panel IDs")
    with args.contract.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    failures: list[str] = []
    panel_results: dict[str, dict[str, object]] = {}
    for panel in panels:
        panel_rows = [row for row in rows if row.get("panel_id", "").strip() == panel]
        rules = [row.get("rule_id", "").strip() for row in panel_rows]
        duplicates = sorted({rule for rule in rules if rules.count(rule) > 1})
        missing = sorted(REQUIRED_RULES - set(rules))
        incomplete_enforcement = []
        for row in panel_rows:
            if row.get("rule_id", "").strip() not in REQUIRED_RULES:
                continue
            enforcement = {item.strip() for item in row.get("enforcement", "").split("|") if item.strip()}
            if not REQUIRED_ENFORCEMENT <= enforcement:
                incomplete_enforcement.append(row.get("rule_id", "").strip())
        if missing:
            failures.append(f"{panel}:missing={','.join(missing)}")
        if duplicates:
            failures.append(f"{panel}:duplicates={','.join(duplicates)}")
        if incomplete_enforcement:
            failures.append(f"{panel}:incomplete_enforcement={','.join(sorted(incomplete_enforcement))}")
        panel_results[panel] = {
            "required_rules": sorted(REQUIRED_RULES),
            "observed_rules": sorted(set(rules) & REQUIRED_RULES),
            "missing_rules": missing,
            "duplicate_rules": duplicates,
            "incomplete_enforcement": sorted(incomplete_enforcement),
            "status": "PASS" if not (missing or duplicates or incomplete_enforcement) else "FAIL",
        }

    report = {
        "schema_version": "1.0",
        "contract": str(args.contract.resolve()),
        "status": "PASS" if not failures else "FAIL",
        "panels": panel_results,
        "failures": failures,
        "purpose": "SQ3 panel-header contract completeness gate; prevents partial contracts from passing",
    }
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
