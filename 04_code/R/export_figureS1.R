#!/usr/bin/env Rscript

# Direct final export of the visually accepted Figure S1 v06. This reproduces
# the accepted shared-header and title-descent corrections, removes the base
# builder's single terminal q() statement before evaluation, and writes a true
# 600-dpi PNG plus vector PDF. No analysis is rerun.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("Usage: Rscript export_figureS1.R <project_root> <staging_dir>")
}
if (.Platform$OS.type != "windows") stop("This recorded exporter is specific to the Windows project runtime")
project_root <- normalizePath(args[[1]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[2]], winslash = "/", mustWork = FALSE)
if (dir.exists(output_dir)) stop("Refusing to overwrite staging directory: ", output_dir)

builder_v04 <- file.path(project_root, "04_code/R/build_figureS1.R")
if (!file.exists(builder_v04)) stop("Missing complete Figure S1 builder: ", builder_v04)
code_lines <- readLines(builder_v04, warn = FALSE, encoding = "UTF-8")

block_start <- grep("^  tag_grob <- \\.skill3_baseline_text_grob\\($", code_lines)
block_end <- grep("^  g <- gtable_add_grob\\(g, subtitle_grob,", code_lines)
if (length(block_start) != 1L || length(block_end) != 1L || block_end <= block_start) {
  stop("Rendered-baseline patch target is not unique")
}

shared_header_block <- c(
  "  header_x <- sum(g$widths[seq_len(panel_l - 1L)])",
  "  title_grob <- .skill3_baseline_text_grob(",
  "    title, x = header_x, baseline = first_baseline, just_x = \"left\",",
  "    gp = gpar(fontfamily = \"Arial\", fontsize = 8.5, fontface = \"bold\")",
  "  )",
  "  title_descent_compensation <- grobDescent(title_grob)",
  "  tag_grob <- .skill3_baseline_text_grob(",
  "    tag, x = header_x - unit(2.0, \"mm\"),",
  "    baseline = first_baseline - title_descent_compensation, just_x = \"right\",",
  "    gp = gpar(fontfamily = \"Arial\", fontsize = 9.0, fontface = \"bold\")",
  "  )",
  "  subtitle_grob <- .skill3_baseline_text_grob(",
  "    subtitle, x = header_x, baseline = subtitle_baseline, just_x = \"left\",",
  "    gp = gpar(fontfamily = \"Arial\", fontsize = 7.0, fontface = \"plain\", col = \"#66727E\")",
  "  )",
  "  shared_header_grob <- grobTree(tag_grob, title_grob, subtitle_grob)",
  "  g <- gtable_add_grob(",
  "    g, shared_header_grob, t = 1, l = 1, r = ncol(g), clip = \"off\",",
  "    name = paste0(\"sq3-shared-rendered-header-\", panel_id)",
  "  )"
)
code_lines <- c(
  code_lines[seq_len(block_start - 1L)],
  shared_header_block,
  code_lines[(block_end + 1L):length(code_lines)]
)
code_text <- paste(code_lines, collapse = "\n")
code_text <- gsub("_v04", "_v06", code_text, fixed = TRUE)
code_text <- gsub("FS1V04", "FS1V06", code_text, fixed = TRUE)
code_text <- sub(
  "supersedes_visual_candidate = \"FigureS1 v03\"",
  "supersedes_visual_candidate = \"FigureS1 v05\"",
  code_text, fixed = TRUE
)
code_text <- gsub(
  "build_figureS1.R",
  "export_figureS1.R",
  code_text, fixed = TRUE
)

terminal_exit <- 'q(save = "no", status = 0, runLast = FALSE)'
exit_hits <- gregexpr(terminal_exit, code_text, fixed = TRUE)[[1L]]
if (length(exit_hits) != 1L || exit_hits[[1L]] < 0L) stop("Expected exactly one terminal q() statement")
code_text <- sub(terminal_exit, "", code_text, fixed = TRUE)

grDevices::windowsFonts(Arial = grDevices::windowsFont("Arial"))
metric_device_file <- tempfile(pattern = "sq3_arial_metric_device_export_", fileext = ".png")
grDevices::png(
  filename = metric_device_file,
  width = 180, height = 195, units = "mm", res = 300,
  type = "windows", family = "Arial", bg = "white"
)
options(warn = 1)
eval(parse(text = code_text, keep.source = TRUE), envir = .GlobalEnv)
if (grDevices::dev.cur() > 1L) grDevices::dev.off()

png_path <- file.path(output_dir, "FigureS1_600dpi.png")
pdf_path <- file.path(output_dir, "FigureS1.pdf")
ggplot2::ggsave(
  png_path, figure, width = 180, height = 195, units = "mm", dpi = 600,
  bg = "white", limitsize = FALSE
)
ggplot2::ggsave(
  pdf_path, figure, device = grDevices::cairo_pdf,
  width = 180, height = 195, units = "mm", bg = "white", limitsize = FALSE
)

cat(sprintf('{"status":"PASS","png":"%s","pdf":"%s"}\n', png_path, pdf_path))
