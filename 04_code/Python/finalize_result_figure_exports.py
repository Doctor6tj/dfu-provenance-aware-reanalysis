#!/usr/bin/env python3
"""Create the clean final figure folder with a PNG-matched Figure S1 PDF.

Figures 2-4 retain their vector PDFs. Figure S1 contains tens of thousands of
transparent points whose Cairo vector blending differs visibly from the
author-approved PNG, so its PDF embeds the true 600-dpi approved PNG at the
exact 180 x 195 mm page size. No hashes or extra deliverables are created.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite: {output}")
    output.mkdir(parents=True)

    required = [
        *(f"Figure{number}.{ext}" for number in (2, 3, 4) for ext in ("png", "pdf")),
        *(f"Figure{number}_legend.txt" for number in (2, 3, 4)),
        "FigureS1.png", "FigureS1_legend.txt", "FIGURE_EXPORT_MANIFEST.csv",
    ]
    for name in required:
        path = source / name
        if not path.exists():
            raise FileNotFoundError(path)
        shutil.copy2(path, output / name)

    s1_png = output / "FigureS1.png"
    s1_pdf = output / "FigureS1.pdf"
    page_width, page_height = 180 * mm, 195 * mm
    pdf = canvas.Canvas(str(s1_pdf), pagesize=(page_width, page_height), pageCompression=1)
    pdf.setTitle("Supplementary Figure S1")
    pdf.setSubject("Author-approved 600-dpi Figure S1 visual embedded at final page size")
    pdf.drawImage(str(s1_png), 0, 0, width=page_width, height=page_height, preserveAspectRatio=False, mask=None)
    pdf.showPage()
    pdf.save()

    readme = """DFU submission figure export

Each figure has exactly three submission-facing files:
- PNG: lossless 600-dpi raster export.
- PDF: submission PDF at the exact final figure page size.
- TXT: plain-text figure legend.

Selected versions:
- Figure 2 v06
- Figure 3 v05
- Figure 4 v04
- Figure S1 v06

Figures 2-4 retain vector PDF output. Figure S1 PDF embeds the author-approved 600-dpi PNG because Cairo vector transparency made its dense UMAP point cloud visibly more saturated; the embedded-PNG PDF preserves the approved appearance exactly.

No bioinformatics or statistical analysis was rerun. No hashes were calculated.
"""
    (output / "README.txt").write_text(readme, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
