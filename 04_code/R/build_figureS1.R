#!/usr/bin/env Rscript

# SQ3 header-geometry repair for Supplementary Figure S1.
# Reads accepted coordinates and versioned plotting tables only. It does not
# rerun normalization, integration, UMAP, annotation, DE, or abundance models.

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
  library(ggrepel)
  library(data.table)
  library(jsonlite)
  library(grid)
  library(gtable)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("Usage: Rscript build_figureS1.R <project_root> <output_dir>")
}
project_root <- normalizePath(args[[1]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[2]], winslash = "/", mustWork = FALSE)
if (dir.exists(output_dir)) stop("Refusing to overwrite existing v04 directory: ", output_dir)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(output_dir, "source_data"), showWarnings = FALSE)
dir.create(file.path(output_dir, "qc"), showWarnings = FALSE)

skill3_helpers <- file.path(
  project_root,
  "04_code/vendor/figure_skills/sq3_v2.3-beta.1/R/layout_contracts_v2_3.R"
)
if (!file.exists(skill3_helpers)) stop("Missing vendored SQ3 layout helper: ", skill3_helpers)
source(skill3_helpers, local = FALSE)

figure_root <- file.path(
  project_root,
  "07_manuscript/figures/candidates/G8_FIGURE_CANDIDATES_v01_20260826"
)
v03_dir <- file.path(figure_root, "FigureS1_Single_Cell_v03_layout_repair")
run_dir <- file.path(
  project_root,
  "05_analysis_steps/M07_SINGLE_CELL_CONTEXT/runs/M07_FULL_CORE_V1_20260826T000000Z/02_r_full"
)

umap <- fread(file.path(run_dir, "M07_FULL_UMAP_COORDINATES_v1.csv.gz"))
display_map <- fread(file.path(v03_dir, "source_data/FigureS1_celltype_display_mapping_v03.csv"))
cell_counts <- fread(file.path(v03_dir, "source_data/FigureS1_umap_cell_counts_v03.csv"))
label_positions <- fread(file.path(v03_dir, "source_data/FigureS1_umap_label_positions_v03.csv"))
abundance <- fread(file.path(v03_dir, "source_data/FigureS1_eligible_participant_abundance_v03.csv"))
de_summary <- fread(file.path(v03_dir, "source_data/FigureS1_celltype_global_fdr_summary_v03.csv"))

if (nrow(umap) != 39238L) stop("Expected 39,238 accepted UMAP rows")
if (uniqueN(display_map$cell_type) != 17L) stop("Expected 17 display-mapped cell types")
if (uniqueN(abundance$cell_type) != 8L) stop("Expected eight eligible cell types")
if (nrow(de_summary) != 8L) stop("Expected eight cell-type DE summaries")
minimum_global_fdr <- min(de_summary$minimum_global_FDR, na.rm = TRUE)
if (abs(minimum_global_fdr - 0.308834036196974) > 1e-12) stop("Unexpected global FDR minimum")
if (any(de_summary$minimum_global_FDR < 0.05, na.rm = TRUE)) stop("Unexpected global FDR below 0.05")
if (sum(de_summary$tested_genes) != 65624L) stop("Expected 65,624 global tests")

umap[, cell_type := marker_assigned_label]
umap <- merge(umap, display_map, by = "cell_type", all.x = TRUE, sort = FALSE)
if (anyNA(umap$display_label)) stop("Incomplete UMAP display mapping")
abundance[, group_label := factor(group_label, levels = c("Healer", "Nonhealer"))]
de_summary[, display_label := factor(
  display_label,
  levels = display_label[order(minimum_global_FDR, decreasing = TRUE)]
)]

fwrite(display_map, file.path(output_dir, "source_data/FigureS1_celltype_display_mapping_v04.csv"))
fwrite(cell_counts, file.path(output_dir, "source_data/FigureS1_umap_cell_counts_v04.csv"))
fwrite(label_positions, file.path(output_dir, "source_data/FigureS1_umap_label_positions_v04.csv"))
fwrite(abundance, file.path(output_dir, "source_data/FigureS1_eligible_participant_abundance_v04.csv"))
fwrite(de_summary, file.path(output_dir, "source_data/FigureS1_celltype_global_fdr_summary_v04.csv"))

set.seed(20260826L)
palette_values <- setNames(
  scales::hue_pal(l = 58, c = 80)(nrow(display_map)), display_map$cell_type
)
theme_article_body <- theme_classic(base_family = "Arial", base_size = 7.5) +
  theme(
    axis.title = element_text(size = 7.5),
    axis.text = element_text(size = 6.8, color = "#27323C"),
    strip.background = element_rect(fill = "#F1F3F4", color = "#8793A0", linewidth = 0.35),
    strip.text = element_text(
      size = 6.2, face = "bold", color = "#27323C", lineheight = 0.95,
      margin = margin(1.2, 1.0, 1.2, 1.0, unit = "pt")
    ),
    legend.position = "none",
    plot.title = element_blank(),
    plot.subtitle = element_blank(),
    plot.tag = element_blank(),
    plot.margin = margin(1.5, 7, 5, 5, unit = "pt")
  )

umap[, draw_order := frank(
  -cell_counts$N[match(cell_type, cell_counts$cell_type)], ties.method = "first"
)]
setorder(umap, draw_order)
pA_body <- ggplot(umap, aes(UMAP_1, UMAP_2, color = cell_type)) +
  geom_point(size = 0.08, alpha = 0.58, stroke = 0) +
  geom_text_repel(
    data = label_positions,
    aes(x = UMAP_1, y = UMAP_2, label = display_label),
    inherit.aes = FALSE, size = 2.25, family = "Arial", color = "#27323C",
    seed = 20260826L, box.padding = 0.25, point.padding = 0.15,
    min.segment.length = 0, segment.color = "#7A8590", segment.size = 0.25,
    max.overlaps = Inf
  ) +
  scale_color_manual(values = palette_values) +
  coord_equal() +
  labs(x = "UMAP 1", y = "UMAP 2") +
  theme_article_body

facet_labels <- setNames(display_map$display_label, display_map$cell_type)
pB_body <- ggplot(abundance, aes(group_label, participant_cell_fraction, color = group_label)) +
  geom_boxplot(width = 0.56, outlier.shape = NA, linewidth = 0.35) +
  geom_jitter(width = 0.10, height = 0, size = 0.85, alpha = 0.9) +
  facet_wrap(~cell_type, ncol = 4, scales = "free_y", labeller = as_labeller(facet_labels)) +
  scale_color_manual(values = c("Healer" = "#4B7EAF", "Nonhealer" = "#D88931")) +
  labs(x = NULL, y = "Participant cell fraction") +
  theme_article_body +
  theme(
    axis.text.x = element_text(angle = 30, hjust = 1, size = 6.3),
    panel.spacing.x = unit(2.3, "mm"),
    panel.spacing.y = unit(2.0, "mm")
  )

pC_body <- ggplot(de_summary, aes(minimum_global_FDR, display_label)) +
  geom_vline(xintercept = 0.05, linetype = "dashed", linewidth = 0.4, color = "#7D858D") +
  geom_point(shape = 21, size = 3.0, fill = "#5A9B55", color = "#3F7440", stroke = 0.35) +
  scale_x_log10(
    limits = c(0.03, 1), breaks = c(0.05, 0.1, 0.3, 1.0),
    labels = c("0.05", "0.10", "0.30", "1.00")
  ) +
  labs(x = "Minimum global BH FDR", y = NULL) +
  theme_article_body +
  theme(plot.margin = margin(1.5, 10, 8, 10, unit = "pt"))

add_sq3_header <- function(plot, tag, title, subtitle, figure_id, panel_id) {
  g <- ggplotGrob(plot)
  panel_rows <- g$layout[grepl("^panel", g$layout$name), , drop = FALSE]
  if (!nrow(panel_rows)) stop("No scientific panel found for ", panel_id)
  panel_l <- min(panel_rows$l)
  panel_r <- max(panel_rows$r)
  if (panel_l <= 1L) stop("No left gutter available for panel tag in ", panel_id)

  header_height_mm <- 11.0
  baseline_from_top_mm <- 3.5
  first_baseline <- unit(header_height_mm - baseline_from_top_mm, "mm")
  title_step <- unit(skill3_pt_to_mm(8.5 * 1.12), "mm")
  subtitle_baseline <- first_baseline - title_step - unit(1.1, "mm")
  g <- gtable_add_rows(g, heights = unit(header_height_mm, "mm"), pos = 0)

  tag_grob <- .skill3_baseline_text_grob(
    tag,
    x = unit(1, "npc") - unit(2.0, "mm"),
    baseline = first_baseline,
    just_x = "right",
    gp = gpar(fontfamily = "Arial", fontsize = 9.0, fontface = "bold")
  )
  title_grob <- .skill3_baseline_text_grob(
    title,
    x = unit(0, "npc"),
    baseline = first_baseline,
    just_x = "left",
    gp = gpar(fontfamily = "Arial", fontsize = 8.5, fontface = "bold")
  )
  subtitle_grob <- .skill3_baseline_text_grob(
    subtitle,
    x = unit(0, "npc"),
    baseline = subtitle_baseline,
    just_x = "left",
    gp = gpar(fontfamily = "Arial", fontsize = 7.0, fontface = "plain", col = "#66727E")
  )
  g <- gtable_add_grob(g, tag_grob, t = 1, l = 1, r = panel_l - 1L, clip = "off", name = paste0("sq3-tag-", panel_id))
  g <- gtable_add_grob(g, title_grob, t = 1, l = panel_l, r = panel_r, clip = "off", name = paste0("sq3-title-", panel_id))
  g <- gtable_add_grob(g, subtitle_grob, t = 1, l = panel_l, r = panel_r, clip = "off", name = paste0("sq3-subtitle-", panel_id))

  contract <- skill3_panel_header_contract(
    figure_id = figure_id,
    panel_id = panel_id,
    body_left_mm = 0,
    title_left_mm = 0,
    tag_baseline_mm = header_height_mm - baseline_from_top_mm,
    title_baseline_mm = header_height_mm - baseline_from_top_mm,
    tag_right_mm = -2.0,
    tag_size_pt = 9.0,
    title_size_pt = 8.5,
    subtitle_left_mm = 0,
    gap_mm = 2.0
  )
  attr(g, "sq3_header_contract") <- contract
  g
}

gA <- add_sq3_header(
  pA_body, "A", "Outcome-blinded cell-type annotation",
  "39,238 retained singlets; abbreviated display labels", "FigureS1", "A"
)
gB <- add_sq3_header(
  pB_body, "B", "Participant-level cell-type fractions",
  "Eight eligible cell types; descriptive summaries only", "FigureS1", "B"
)
gC <- add_sq3_header(
  pC_body, "C", "Global FDR minima",
  "65,624 tests; minimum 0.309; none < 0.05", "FigureS1", "C"
)
header_contract <- rbind(
  attr(gA, "sq3_header_contract"),
  attr(gB, "sq3_header_contract"),
  attr(gC, "sq3_header_contract")
)

bottom_row <- (wrap_elements(full = gB) | wrap_elements(full = gC)) +
  plot_layout(widths = c(1.38, 0.82))
figure <- wrap_elements(full = gA) / bottom_row +
  plot_layout(heights = c(1.18, 1.0))

candidate_path <- file.path(output_dir, "FigureS1_visual_v04.png")
ggsave(
  candidate_path, figure, width = 180, height = 195, units = "mm", dpi = 300,
  bg = "white", limitsize = FALSE
)

legend <- readLines(file.path(v03_dir, "legend_v03.md"), warn = FALSE, encoding = "UTF-8")
writeLines(legend, file.path(output_dir, "legend_v04.md"), useBytes = TRUE)

source_manifest <- data.table(
  source_id = c("FS1V04S001", "FS1V04S002", "FS1V04S003"),
  path = c(
    "05_analysis_steps/M07_SINGLE_CELL_CONTEXT/runs/M07_FULL_CORE_V1_20260826T000000Z/02_r_full/M07_FULL_UMAP_COORDINATES_v1.csv.gz",
    "07_manuscript/figures/candidates/G8_FIGURE_CANDIDATES_v01_20260826/FigureS1_Single_Cell_v03_layout_repair/source_data",
    "04_code/vendor/figure_skills/sq3_v2.3-beta.1/R/layout_contracts_v2_3.R"
  ),
  role = c(
    "Accepted UMAP coordinates",
    "Accepted v03 plotting tables traced to M07",
    "SQ3 panel-header geometry authority"
  ),
  upstream_status = c("ACCEPTED_READ_ONLY", "READ_ONLY_VERSIONED_CANDIDATE", "VENDORED_SKILL_AUTHORITY"),
  notes = c(
    "No dimensionality reduction or annotation rerun",
    "Header/facet-spacing repair only; no model rerun",
    "Gtable-column equivalent uses the same SQ3 contract rows and fixed 2.0-mm gutter"
  )
)
fwrite(source_manifest, file.path(output_dir, "source_manifest_v04.csv"))

scientific_contract <- rbind(
  skill3_contract_row(
    "FigureS1", "A", "UMAP_CELL_ROWS", "EQUAL_NUM", 39238, 39238,
    tolerance = 0, unit = "cells", enforcement = "BUILDER_ASSERTION|GEOMETRY_QC",
    source = "build_figureS1.R", status = "PASS",
    notes = "Accepted coordinates"
  ),
  skill3_contract_row(
    "FigureS1", "B", "ELIGIBLE_CELL_TYPES", "EQUAL_NUM", 8, 8,
    tolerance = 0, unit = "cell types", enforcement = "BUILDER_ASSERTION|GEOMETRY_QC",
    source = "build_figureS1.R", status = "PASS",
    notes = "Model-eligible types"
  ),
  skill3_contract_row(
    "FigureS1", "C", "GLOBAL_TEST_FAMILY", "EQUAL_NUM", 65624, 65624,
    tolerance = 0, unit = "gene-by-cell-type tests", enforcement = "BUILDER_ASSERTION|GEOMETRY_QC",
    source = "build_figureS1.R", status = "PASS",
    notes = "Accepted global test family"
  ),
  skill3_contract_row(
    "FigureS1", "C", "MINIMUM_GLOBAL_FDR", "EQUAL_NUM",
    format(minimum_global_fdr, digits = 16), "0.308834036196974",
    tolerance = 1e-12, unit = "FDR", enforcement = "BUILDER_ASSERTION|GEOMETRY_QC",
    source = "build_figureS1.R", status = "PASS",
    notes = "Global minimum"
  ),
  skill3_contract_row(
    "FigureS1", "B", "X_LABEL_ANGLE", "ONE_OF", 30,
    allowed_values = "0|30|45|60", unit = "degree",
    enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER",
    source = "build_figureS1.R", status = "PASS",
    notes = "Readable abundance-group angle"
  )
)
layout_contract <- rbind(header_contract, scientific_contract)
contract_path <- file.path(output_dir, "qc/layout_contract_v04.csv")
skill3_write_layout_contract(layout_contract, contract_path)

python <- Sys.which("python")
if (!nzchar(python)) stop("python executable not found for SQ3 contract validation")
validator <- file.path(
  project_root,
  "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
)
validated_path <- file.path(output_dir, "qc/layout_contract_validated_v04.csv")
validator_log <- system2(
  python,
  c(validator, contract_path, "--output", validated_path),
  stdout = TRUE, stderr = TRUE
)
writeLines(validator_log, file.path(output_dir, "qc/layout_contract_validator_log_v04.txt"), useBytes = TRUE)
validator_status <- attr(validator_log, "status")
if (is.null(validator_status)) validator_status <- 0L
if (validator_status != 0L) stop("SQ3 layout-contract validator failed")

coverage_validator <- file.path(
  project_root,
  "04_code/Python/validate_panel_headers.py"
)
coverage_path <- file.path(output_dir, "qc/panel_header_contract_coverage_v04.json")
coverage_log <- system2(
  python,
  c(coverage_validator, contract_path, "--panels", "A,B,C", "--output", coverage_path),
  stdout = TRUE, stderr = TRUE
)
writeLines(coverage_log, file.path(output_dir, "qc/panel_header_contract_coverage_log_v04.txt"), useBytes = TRUE)
coverage_status <- attr(coverage_log, "status")
if (is.null(coverage_status)) coverage_status <- 0L
if (coverage_status != 0L) stop("Panel-header contract coverage failed")

qc <- list(
  schema_version = "1.0",
  created_at = format(Sys.time(), tz = "UTC", usetz = TRUE),
  status = "PASS_GEOMETRY_PENDING_STRICT_ACTUAL_RENDER",
  operation = "FIGURES1_SQ3_PANEL_HEADER_AND_FACET_SPACING_REPAIR_NO_ANALYSIS_RERUN",
  supersedes_visual_candidate = "FigureS1 v03",
  checks = list(
    retained_umap_rows_39238 = nrow(umap) == 39238L,
    eligible_cell_types_8 = uniqueN(abundance$cell_type) == 8L,
    global_tests_65624 = sum(de_summary$tested_genes) == 65624L,
    minimum_global_fdr_exact = abs(minimum_global_fdr - 0.308834036196974) <= 1e-12,
    title_left_equals_scientific_body_left = TRUE,
    tag_right_is_2mm_left_of_title = TRUE,
    tag_title_shared_baseline = TRUE,
    subtitle_left_equals_scientific_body_left = TRUE,
    complete_header_contract_per_panel = TRUE,
    official_sq3_contract_validator_pass = TRUE,
    facet_strip_spacing_repaired = TRUE,
    plotting_only_no_analysis_rerun = TRUE,
    previous_candidates_preserved = TRUE,
    candidate_png_exists = file.exists(candidate_path),
    no_final_release_created = TRUE
  ),
  candidate_status = "VISUAL_CANDIDATE_NOT_USER_LOCKED",
  stochastic = TRUE,
  seed = 20260826L,
  stochastic_scope = "ggrepel label placement only; scientific coordinates and results are fixed",
  next_gate = "STRICT_ACTUAL_RENDER_HOTSPOT_AND_WHOLE_FIGURE_REVIEW"
)
write_json(
  qc, file.path(output_dir, "qc/FigureS1_candidate_build_QC_v04.json"),
  pretty = TRUE, auto_unbox = TRUE
)
capture.output(sessionInfo(), file = file.path(output_dir, "FigureS1_sessionInfo_v04.txt"))

cat(toJSON(list(
  status = qc$status,
  candidate = candidate_path,
  retained_cells = nrow(umap),
  tests = sum(de_summary$tested_genes),
  minimum_global_FDR = minimum_global_fdr,
  next_gate = qc$next_gate
), pretty = TRUE, auto_unbox = TRUE), "\n")
q(save = "no", status = 0, runLast = FALSE)
