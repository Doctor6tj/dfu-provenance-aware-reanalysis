# Skill 3 v2.3-beta.1 — executable layout contracts.
# These helpers turn recurring visual-QC rules into builder assertions and
# machine-readable geometry evidence. They do not replace final-size review.

skill3_pt_to_mm <- function(x) as.numeric(x) * 25.4 / 72

skill3_contract_row <- function(figure_id, panel_id, rule_id, relation,
                                observed = NA, expected = NA,
                                lower = NA, upper = NA, tolerance = NA,
                                allowed_values = NA, unit = "",
                                enforcement = "GEOMETRY_QC",
                                source = "R/layout_contracts_v2_3.R",
                                status = "", notes = "") {
  data.frame(
    figure_id = as.character(figure_id),
    panel_id = as.character(panel_id),
    rule_id = as.character(rule_id),
    relation = as.character(relation),
    observed = as.character(observed),
    expected = as.character(expected),
    lower = as.character(lower),
    upper = as.character(upper),
    tolerance = as.character(tolerance),
    allowed_values = as.character(allowed_values),
    unit = as.character(unit),
    enforcement = as.character(enforcement),
    source = as.character(source),
    status = as.character(status),
    notes = as.character(notes),
    stringsAsFactors = FALSE
  )
}

skill3_write_layout_contract <- function(rows, path) {
  required <- c(
    "figure_id", "panel_id", "rule_id", "relation", "observed", "expected",
    "lower", "upper", "tolerance", "allowed_values", "unit", "enforcement",
    "source", "status", "notes"
  )
  if (!is.data.frame(rows) || !all(required %in% names(rows))) {
    stop("Layout contract rows are missing required columns.")
  }
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(rows[, required], path, row.names = FALSE, na = "")
  invisible(normalizePath(path, winslash = "/", mustWork = TRUE))
}

skill3_panel_header_contract <- function(
    figure_id, panel_id, body_left_mm, title_left_mm,
    tag_baseline_mm, title_baseline_mm,
    tag_right_mm, tag_size_pt = 9, title_size_pt = 8.5,
    subtitle_left_mm = NA_real_, gap_mm = title_left_mm - tag_right_mm,
    anchor_tolerance_mm = 0.5, baseline_tolerance_mm = 0.35) {
  values <- c(
    body_left_mm, title_left_mm, tag_baseline_mm, title_baseline_mm,
    tag_right_mm, tag_size_pt, title_size_pt, gap_mm
  )
  if (any(!is.finite(values))) stop("Panel-header geometry must be finite.")
  if (is.finite(subtitle_left_mm)) {
    subtitle_row <- skill3_contract_row(
      figure_id, panel_id, "HDR_SUBTITLE_BODY_ANCHOR", "EQUAL_NUM",
      subtitle_left_mm, body_left_mm, tolerance = anchor_tolerance_mm, unit = "mm",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    )
  } else {
    subtitle_row <- NULL
  }
  rows <- rbind(
    skill3_contract_row(
      figure_id, panel_id, "HDR_TITLE_BODY_ANCHOR", "EQUAL_NUM",
      title_left_mm, body_left_mm, tolerance = anchor_tolerance_mm, unit = "mm",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    ),
    skill3_contract_row(
      figure_id, panel_id, "HDR_TAG_TITLE_BASELINE", "EQUAL_NUM",
      tag_baseline_mm, title_baseline_mm, tolerance = baseline_tolerance_mm, unit = "mm",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    ),
    skill3_contract_row(
      figure_id, panel_id, "HDR_TAG_TITLE_GAP", "BETWEEN",
      gap_mm, lower = 1.5, upper = 2.5, unit = "mm",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    ),
    skill3_contract_row(
      figure_id, panel_id, "HDR_TAG_TITLE_SIZE_DELTA", "BETWEEN",
      tag_size_pt - title_size_pt, lower = 0.5, upper = 1.0, unit = "pt",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    ),
    subtitle_row
  )
  numeric_status <- c(
    abs(title_left_mm - body_left_mm) <= anchor_tolerance_mm,
    abs(tag_baseline_mm - title_baseline_mm) <= baseline_tolerance_mm,
    gap_mm >= 1.5 && gap_mm <= 2.5,
    (tag_size_pt - title_size_pt) >= 0.5 && (tag_size_pt - title_size_pt) <= 1.0,
    if (is.finite(subtitle_left_mm)) abs(subtitle_left_mm - body_left_mm) <= anchor_tolerance_mm else NULL
  )
  if (!all(numeric_status)) stop("Panel-header hard geometry contract failed for ", figure_id, " ", panel_id)
  rows
}

.skill3_baseline_text_grob <- function(label, x, baseline, just_x, gp) {
  g <- grid::textGrob(
    label, x = x, y = grid::unit(0, "mm"),
    just = c(just_x, "bottom"), gp = gp
  )
  grid::editGrob(g, y = baseline - grid::grobDescent(g))
}

skill3_make_panel_header_grob <- function(
    tag, title, width_mm, height_mm, body_left_mm,
    baseline_from_top_mm = 4.5, subtitle = NULL,
    family = "Arial", tag_size_pt = 9, title_size_pt = 8.5,
    subtitle_size_pt = 7.2, gap_mm = 2.0,
    title_lineheight = 1.12, subtitle_gap_mm = 1.3,
    figure_id = "FIGURE", panel_id = tag) {
  stopifnot(width_mm > 0, height_mm > 0, body_left_mm >= 0, body_left_mm <= width_mm)
  stopifnot(gap_mm >= 1.5, gap_mm <= 2.5)
  delta <- tag_size_pt - title_size_pt
  if (delta < 0.5 || delta > 1.0) stop("Panel tag/title size delta must be 0.5-1.0 pt.")
  title_lines <- strsplit(as.character(title), "\n", fixed = TRUE)[[1]]
  if (!length(title_lines) || any(!nzchar(title_lines))) stop("Title lines must be non-empty.")

  first_baseline <- grid::unit(height_mm - baseline_from_top_mm, "mm")
  title_x <- grid::unit(body_left_mm, "mm")
  tag_right_x <- grid::unit(body_left_mm - gap_mm, "mm")
  if (body_left_mm - gap_mm < 0) stop("Panel-tag gutter falls outside the supplied header viewport.")

  grobs <- list(
    .skill3_baseline_text_grob(
      tag, tag_right_x, first_baseline, "right",
      grid::gpar(fontfamily = family, fontsize = tag_size_pt, fontface = "bold")
    )
  )
  title_step <- grid::unit(skill3_pt_to_mm(title_size_pt * title_lineheight), "mm")
  for (i in seq_along(title_lines)) {
    grobs[[length(grobs) + 1L]] <- .skill3_baseline_text_grob(
      title_lines[[i]], title_x, first_baseline - (i - 1) * title_step, "left",
      grid::gpar(fontfamily = family, fontsize = title_size_pt, fontface = "bold")
    )
  }
  if (!is.null(subtitle) && nzchar(as.character(subtitle))) {
    subtitle_baseline <- first_baseline - length(title_lines) * title_step - grid::unit(subtitle_gap_mm, "mm")
    grobs[[length(grobs) + 1L]] <- .skill3_baseline_text_grob(
      as.character(subtitle), title_x, subtitle_baseline, "left",
      grid::gpar(fontfamily = family, fontsize = subtitle_size_pt, fontface = "plain")
    )
  }
  out <- grid::gTree(
    children = do.call(grid::gList, grobs),
    vp = grid::viewport(
      x = grid::unit(0, "mm"), y = grid::unit(0, "mm"),
      width = grid::unit(width_mm, "mm"), height = grid::unit(height_mm, "mm"),
      just = c("left", "bottom"), clip = "off"
    )
  )
  attr(out, "layout_contract") <- skill3_panel_header_contract(
    figure_id, panel_id,
    body_left_mm = body_left_mm, title_left_mm = body_left_mm,
    tag_baseline_mm = height_mm - baseline_from_top_mm,
    title_baseline_mm = height_mm - baseline_from_top_mm,
    tag_right_mm = body_left_mm - gap_mm,
    tag_size_pt = tag_size_pt, title_size_pt = title_size_pt,
    subtitle_left_mm = if (is.null(subtitle)) NA_real_ else body_left_mm,
    gap_mm = gap_mm
  )
  out
}

skill3_measure_label_width_mm <- function(labels, font_size_pt = 7, family = "Arial") {
  labels <- as.character(labels)
  if (requireNamespace("systemfonts", quietly = TRUE)) {
    # At 72 dpi, systemfonts returns typographic-point widths. Convert to mm.
    return(as.numeric(systemfonts::string_width(
      labels, family = family, size = font_size_pt, res = 72
    )) * 25.4 / 72)
  }
  vapply(labels, function(z) {
    g <- grid::textGrob(z, gp = grid::gpar(fontfamily = "sans", fontsize = font_size_pt))
    grid::convertWidth(grid::grobWidth(g), "mm", valueOnly = TRUE)
  }, numeric(1))
}

skill3_route_discrete_x_labels <- function(
    labels, body_width_mm, font_size_pt = 7, family = "Arial",
    allowed_angles = c(0, 30, 45, 60), fit_fraction = 0.90,
    journal_override_90 = FALSE, overflow_action = c("error", "return")) {
  overflow_action <- match.arg(overflow_action)
  labels <- as.character(labels)
  if (!length(labels) || any(!nzchar(labels))) stop("Discrete x-axis labels must be non-empty.")
  if (anyDuplicated(allowed_angles)) stop("allowed_angles contains duplicates.")
  if (any(!allowed_angles %in% c(0, 30, 45, 60, 90))) stop("Allowed angles are 0, 30, 45, 60, or 90 degrees.")
  if (90 %in% allowed_angles && !isTRUE(journal_override_90)) {
    stop("90-degree x labels are prohibited by default; record a journal/family override first.")
  }
  widths <- skill3_measure_label_width_mm(labels, font_size_pt, family)
  text_height <- skill3_pt_to_mm(font_size_pt * 1.12)
  slot <- body_width_mm / length(labels)
  fits <- vapply(allowed_angles, function(angle) {
    radians <- angle * pi / 180
    max(widths * cos(radians) + text_height * sin(radians)) <= slot * fit_fraction
  }, logical(1))
  chosen <- if (any(fits)) allowed_angles[which(fits)[1]] else max(allowed_angles)
  radians <- chosen * pi / 180
  footprint <- max(widths * cos(radians) + text_height * sin(radians))
  status <- if (any(fits)) "PASS" else "WRAP_OR_WIDEN_REQUIRED"
  if (status != "PASS" && overflow_action == "error") {
    stop(
      "No approved x-label angle fits the final-size slot. Wrap/abbreviate labels, widen the body, ",
      "or move the complete labels to a supplement; do not force vertical text."
    )
  }
  list(
    angle = chosen,
    hjust = if (chosen == 0) 0.5 else 1,
    vjust = if (chosen == 0) 0.5 else 1,
    slot_width_mm = slot,
    estimated_max_footprint_mm = footprint,
    occupancy = footprint / slot,
    status = status,
    contract = skill3_contract_row(
      "FIGURE", "PANEL", "AXIS_X_LABEL_ANGLE", "ONE_OF", chosen,
      allowed_values = paste(allowed_angles, collapse = "|"), unit = "degree",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER",
      notes = paste0("slot_mm=", signif(slot, 5), ";occupancy=", signif(footprint / slot, 5))
    )
  )
}

skill3_apply_x_label_route <- function(plot, labels, body_width_mm,
                                       font_size_pt = 7, family = "Arial", ...) {
  route <- skill3_route_discrete_x_labels(
    labels = labels, body_width_mm = body_width_mm,
    font_size_pt = font_size_pt, family = family, ...
  )
  plot <- plot + ggplot2::theme(
    axis.text.x = ggplot2::element_text(
      angle = route$angle, hjust = route$hjust, vjust = route$vjust,
      size = font_size_pt, family = family
    )
  )
  attr(plot, "skill3_x_label_route") <- route
  plot
}

skill3_validate_heatmap_columns <- function(
    column_ids, display_labels = column_ids, breaks = column_ids,
    matrix_columns = NULL, figure_id = "FIGURE", panel_id = "PANEL") {
  column_ids <- as.character(column_ids)
  display_labels <- as.character(display_labels)
  breaks <- as.character(breaks)
  n <- length(column_ids)
  if (!n) stop("Heatmap must have at least one column.")
  if (length(display_labels) != n || length(breaks) != n) {
    stop("Heatmap column IDs, labels, and breaks must have identical lengths.")
  }
  if (any(!nzchar(column_ids)) || any(!nzchar(display_labels))) stop("Heatmap column IDs/labels may not be blank.")
  if (anyDuplicated(column_ids)) stop("Heatmap column IDs must be unique.")
  if (!identical(breaks, column_ids)) stop("Heatmap breaks must be the locked column IDs in locked order.")
  if (!is.null(matrix_columns) && !identical(as.character(matrix_columns), column_ids)) {
    stop("Heatmap matrix columns differ from the locked display order.")
  }
  centers <- (seq_len(n) - 0.5) / n
  mapping <- data.frame(
    figure_id = figure_id,
    panel_id = panel_id,
    column_index = seq_len(n),
    column_id = column_ids,
    display_label = display_labels,
    axis_break = breaks,
    expected_center_npc = centers,
    observed_center_npc = centers,
    center_error = 0,
    stringsAsFactors = FALSE
  )
  attr(mapping, "layout_contract") <- do.call(rbind, lapply(seq_len(n), function(i) {
    skill3_contract_row(
      figure_id, panel_id, paste0("HEATMAP_COLUMN_CENTER_", i), "EQUAL_NUM",
      mapping$observed_center_npc[i], mapping$expected_center_npc[i],
      tolerance = 1e-9, unit = "npc",
      enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER",
      notes = paste(mapping$column_id[i], "->", mapping$display_label[i])
    )
  }))
  mapping
}

skill3_directional_label_position <- function(
    x, y, direction = c("RIGHT", "LEFT", "ABOVE", "BELOW"),
    x_gap = 0, y_gap = 0, figure_id = "FIGURE", panel_id = "PANEL") {
  direction <- match.arg(direction)
  stopifnot(length(x) == 1, length(y) == 1, is.finite(x), is.finite(y))
  if (direction %in% c("RIGHT", "LEFT") && (!is.finite(x_gap) || x_gap <= 0)) {
    stop("RIGHT/LEFT label placement requires a positive x_gap.")
  }
  if (direction %in% c("ABOVE", "BELOW") && (!is.finite(y_gap) || y_gap <= 0)) {
    stop("ABOVE/BELOW label placement requires a positive y_gap.")
  }
  label_x <- switch(direction, RIGHT = x + x_gap, LEFT = x - x_gap, ABOVE = x, BELOW = x)
  label_y <- switch(direction, RIGHT = y, LEFT = y, ABOVE = y + y_gap, BELOW = y - y_gap)
  relation_x <- switch(direction, RIGHT = "GT", LEFT = "LT", ABOVE = "EQUAL_NUM", BELOW = "EQUAL_NUM")
  relation_y <- switch(direction, RIGHT = "EQUAL_NUM", LEFT = "EQUAL_NUM", ABOVE = "GT", BELOW = "LT")
  list(
    x = label_x, y = label_y,
    hjust = switch(direction, RIGHT = 0, LEFT = 1, ABOVE = 0.5, BELOW = 0.5),
    vjust = switch(direction, RIGHT = 0.5, LEFT = 0.5, ABOVE = 0, BELOW = 1),
    contract = rbind(
      skill3_contract_row(
        figure_id, panel_id, paste0("ANNOTATION_", direction, "_X"), relation_x,
        label_x, x, tolerance = 1e-12, unit = "data",
        enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
      ),
      skill3_contract_row(
        figure_id, panel_id, paste0("ANNOTATION_", direction, "_Y"), relation_y,
        label_y, y, tolerance = 1e-12, unit = "data",
        enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
      )
    )
  )
}
