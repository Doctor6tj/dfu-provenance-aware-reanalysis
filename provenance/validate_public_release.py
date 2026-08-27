#!/usr/bin/env python3
"""Validate the curated public derivative without running scientific analyses."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


TEXT_SUFFIXES = {".py", ".r", ".md", ".txt", ".csv", ".tsv", ".json", ".cff", ".gitignore"}
SENSITIVE_PATTERNS = {
    "windows_user_home": re.compile(r"[A-Z]:[\\/]Users[\\/][^\\/]+[\\/]", re.IGNORECASE),
    "unix_user_home": re.compile(r"/" + r"Users/" + r"[^/]+/", re.IGNORECASE),
    "private_skill_path": re.compile(r"Desktop[\\/]sq(?:[\\/]|$)", re.IGNORECASE),
    "email_address": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
    "github_token": re.compile(r"(?:github_pat_|ghp_)[A-Za-z0-9_]+"),
    "openai_token": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add(checks: list[dict[str, object]], name: str, passed: bool, details: object) -> None:
    checks.append({"check": name, "status": "PASS" if passed else "FAIL", "details": details})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--rscript", type=Path)
    parser.add_argument("--output", type=Path, default=Path("provenance/RELEASE_QC.json"))
    args = parser.parse_args()

    root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    checks: list[dict[str, object]] = []

    mandatory = [
        "README.md", "DATA_ACCESS.md", "RUN_ORDER.md", "MANUSCRIPT_CODE_MAP.csv",
        "requirements-python.txt", "requirements-r.txt", ".gitignore",
        "provenance/PUBLIC_RELEASE_TRANSFORMATIONS.md",
        "provenance/M01_PARTICIPANT_MAP_EQUIVALENCE_QC.json",
    ]
    missing = [path for path in mandatory if not (root / path).is_file()]
    add(checks, "mandatory_release_files", not missing, {"missing": missing})

    python_files = sorted((root / "04_code").rglob("*.py"))
    python_errors: list[str] = []
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:  # syntax/decode diagnostics belong in the QC output
            python_errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    add(checks, "python_syntax", not python_errors, {"files": len(python_files), "errors": python_errors})

    r_files = sorted((root / "04_code").rglob("*.R"))
    r_errors: list[str] = []
    if args.rscript:
        if not args.rscript.is_file():
            r_errors.append("Supplied Rscript executable does not exist")
        else:
            expression = "files<-commandArgs(TRUE); for (f in files) parse(file=f); cat(length(files))"
            completed = subprocess.run(
                [str(args.rscript), "--vanilla", "-e", expression, *map(str, r_files)],
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                r_errors.append((completed.stdout + "\n" + completed.stderr).strip())
    else:
        r_errors.append("Rscript was not supplied")
    add(checks, "r_syntax", not r_errors, {"files": len(r_files), "errors": r_errors})

    json_errors: list[str] = []
    json_files = sorted(path for path in root.rglob("*.json") if path != output)
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            json_errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    add(checks, "json_readability", not json_errors, {"files": len(json_files), "errors": json_errors})

    csv_errors: list[str] = []
    csv_files = sorted(root.rglob("*.csv"))
    for path in csv_files:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                next(reader, None)
                for _ in reader:
                    pass
        except Exception as exc:
            csv_errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    add(checks, "csv_readability", not csv_errors, {"files": len(csv_files), "errors": csv_errors})

    sensitive_hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == output or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                sensitive_hits.append(f"{path.relative_to(root).as_posix()}: {label}")
    add(checks, "sensitive_path_and_token_scan", not sensitive_hits, {"hits": sensitive_hits})

    map_path = root / "MANUSCRIPT_CODE_MAP.csv"
    mapping_errors: list[str] = []
    mapped_paths: set[str] = set()
    if map_path.is_file():
        with map_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                relative = row["public_path"]
                mapped_paths.add(relative)
                path = root / relative
                if not path.is_file():
                    mapping_errors.append(f"missing public file: {relative}")
                elif sha256(path) != row["public_sha256"]:
                    mapping_errors.append(f"public hash mismatch: {relative}")
    script_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "04_code").rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".r"}
    }
    for relative in sorted(script_paths - mapped_paths):
        mapping_errors.append(f"unmapped public script: {relative}")
    add(checks, "manuscript_code_map", not mapping_errors, {"mapped_scripts": len(mapped_paths), "errors": mapping_errors})

    history_names = [
        path.relative_to(root).as_posix()
        for path in (root / "04_code").rglob("*")
        if path.is_file() and re.search(r"(?:repair|compare|populate|archive)", path.name, re.IGNORECASE)
    ]
    add(checks, "curated_final_script_names", not history_names, {"history_style_names": history_names})

    large_files = [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
        for path in root.rglob("*")
        if path.is_file() and path.stat().st_size > 50 * 1024 * 1024
    ]
    add(checks, "repository_file_size", not large_files, {"limit_bytes": 50 * 1024 * 1024, "large_files": large_files})

    raw_dir = root / "03_data/raw_external_READ_ONLY"
    raw_files = [path.relative_to(root).as_posix() for path in raw_dir.rglob("*") if path.is_file()] if raw_dir.exists() else []
    add(checks, "raw_data_excluded", not raw_files, {"raw_files": raw_files})

    status = "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL"
    payload = {
        "schema_version": "1.0",
        "release_derivative": "dfu-provenance-aware-reanalysis",
        "status": status,
        "scientific_analysis_rerun": False,
        "validation_scope": "syntax, readability, sensitive strings, provenance mapping, script naming, size, and raw-data exclusion",
        "checks": checks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output": output.relative_to(root).as_posix()}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
