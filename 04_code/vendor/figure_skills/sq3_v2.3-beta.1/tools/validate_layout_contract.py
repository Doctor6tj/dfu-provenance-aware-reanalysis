#!/usr/bin/env python3
"""Validate Skill 3 v2.3 executable geometry contracts.

The validator recomputes PASS/FAIL from declared observations. A prose rule or a
manually typed PASS is not accepted as machine evidence.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

REQUIRED = [
    "figure_id", "panel_id", "rule_id", "relation", "observed", "expected",
    "lower", "upper", "tolerance", "allowed_values", "unit", "enforcement",
    "source", "status", "notes",
]
RELATIONS = {"EQUAL_NUM", "BETWEEN", "GT", "LT", "EXACT", "ONE_OF", "MANUAL_PASS"}
ENFORCEMENTS = {"BUILDER_ASSERTION", "GEOMETRY_QC", "ACTUAL_RENDER"}


def number(value: str, name: str) -> float:
    try:
        result = float((value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{name} is not numeric: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite: {value!r}")
    return result


def evaluate(row: dict[str, str]) -> tuple[str, str]:
    relation = (row["relation"] or "").strip().upper()
    if relation not in RELATIONS:
        return "FAIL", f"unknown_relation={relation}"
    enforcement = {x.strip().upper() for x in (row["enforcement"] or "").split("|") if x.strip()}
    if not enforcement or not enforcement <= ENFORCEMENTS:
        return "FAIL", "invalid_or_missing_enforcement"
    if not (row["source"] or "").strip():
        return "FAIL", "missing_source"
    # Numeric relations cannot be certified only by visual review.
    if relation != "MANUAL_PASS" and enforcement == {"ACTUAL_RENDER"}:
        return "FAIL", "machine_relation_lacks_builder_or_geometry_enforcement"

    try:
        if relation == "EQUAL_NUM":
            observed = number(row["observed"], "observed")
            expected = number(row["expected"], "expected")
            tolerance = number(row["tolerance"] or "0", "tolerance")
            passed = abs(observed - expected) <= tolerance
            reason = f"abs_diff={abs(observed - expected):.8g};tol={tolerance:.8g}"
        elif relation == "BETWEEN":
            observed = number(row["observed"], "observed")
            lower = number(row["lower"], "lower")
            upper = number(row["upper"], "upper")
            passed = lower <= observed <= upper
            reason = f"observed={observed:.8g};range=[{lower:.8g},{upper:.8g}]"
        elif relation == "GT":
            observed = number(row["observed"], "observed")
            expected = number(row["expected"], "expected")
            passed = observed > expected
            reason = f"observed={observed:.8g};must_be_gt={expected:.8g}"
        elif relation == "LT":
            observed = number(row["observed"], "observed")
            expected = number(row["expected"], "expected")
            passed = observed < expected
            reason = f"observed={observed:.8g};must_be_lt={expected:.8g}"
        elif relation == "EXACT":
            observed = (row["observed"] or "").strip()
            expected = (row["expected"] or "").strip()
            passed = observed == expected
            reason = f"observed={observed!r};expected={expected!r}"
        elif relation == "ONE_OF":
            observed = (row["observed"] or "").strip()
            allowed = [x.strip() for x in (row["allowed_values"] or "").split("|") if x.strip()]
            passed = bool(allowed) and observed in allowed
            reason = f"observed={observed!r};allowed={allowed!r}"
        else:
            observed = (row["observed"] or "").strip().upper()
            passed = observed == "PASS" and "ACTUAL_RENDER" in enforcement
            reason = "manual_actual_render=" + observed
    except ValueError as exc:
        return "FAIL", str(exc)
    return ("PASS" if passed else "FAIL"), reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    source = Path(args.csv_file)
    output = Path(args.output) if args.output else source.with_name(source.stem + "_validated.csv")

    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED if column not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise SystemExit("No layout-contract rows")

    seen: set[tuple[str, str, str]] = set()
    validated: list[dict[str, str]] = []
    failures = 0
    for row in rows:
        if None in row:
            raise SystemExit("Malformed CSV row contains more fields than the header")
        key = (row["figure_id"].strip(), row["panel_id"].strip(), row["rule_id"].strip())
        if not all(key):
            computed, reason = "FAIL", "blank_figure_panel_or_rule_id"
        elif key in seen:
            computed, reason = "FAIL", "duplicate_contract_key"
        else:
            seen.add(key)
            computed, reason = evaluate(row)
        declared = (row.get("status") or "").strip().upper()
        if declared and declared != computed:
            computed, reason = "FAIL", f"declared_status_mismatch={declared};{reason}"
        if computed == "FAIL":
            failures += 1
        out_row = dict(row)
        out_row["validator_status"] = computed
        out_row["validator_reason"] = reason
        validated.append(out_row)
        print(f"{key[0]} {key[1]} {key[2]}: {computed} — {reason}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED + ["validator_status", "validator_reason"])
        writer.writeheader()
        writer.writerows(validated)
    print(f"LAYOUT_CONTRACT_SUMMARY total={len(validated)} pass={len(validated)-failures} fail={failures}")
    print(f"OUTPUT={output}")
    raise SystemExit(2 if failures else 0)


if __name__ == "__main__":
    main()
