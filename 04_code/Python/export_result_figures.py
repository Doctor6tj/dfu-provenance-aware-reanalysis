#!/usr/bin/env python3
"""Export the locked result figures from accepted source data."""

from pathlib import Path


base = Path(__file__).with_name("export_result_figures_base.py")
if not base.exists():
    raise FileNotFoundError(base)
code = base.read_text(encoding="utf-8")
exec(compile(code, str(base), "exec"), {"__name__": "__main__", "__file__": str(base)})
