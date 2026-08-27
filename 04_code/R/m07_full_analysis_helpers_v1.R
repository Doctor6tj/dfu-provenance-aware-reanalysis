# Deterministic helpers for prospective M07 participant-level full analysis.

m07_attach_pseudobulk_metadata <- function(pseudobulk, cell_metadata) {
  required <- c("participant_alias", "biological_group", "marker_assigned_label")
  if (!all(required %in% names(cell_metadata))) stop("Cell metadata schema mismatch")
  mapping <- unique(cell_metadata[, required, drop = FALSE])
  participant_groups <- unique(mapping[, c("participant_alias", "biological_group"), drop = FALSE])
  if (anyDuplicated(participant_groups$participant_alias)) stop("Participant maps to multiple biological groups")
  metadata <- pseudobulk$metadata
  metadata <- merge(metadata, participant_groups, by = "participant_alias", all.x = TRUE, sort = FALSE)
  metadata <- metadata[match(colnames(pseudobulk$counts), metadata$pseudobulk_id), , drop = FALSE]
  if (any(is.na(metadata$biological_group))) stop("Pseudobulk group join is incomplete")
  cell_counts <- as.data.frame(
    table(cell_metadata$participant_alias, cell_metadata$marker_assigned_label),
    stringsAsFactors = FALSE
  )
  names(cell_counts) <- c("participant_alias", "cell_type", "retained_cells")
  cell_counts <- cell_counts[cell_counts$retained_cells > 0, , drop = FALSE]
  metadata <- merge(metadata, cell_counts, by = c("participant_alias", "cell_type"), all.x = TRUE, sort = FALSE)
  metadata <- metadata[match(colnames(pseudobulk$counts), metadata$pseudobulk_id), , drop = FALSE]
  metadata$total_raw_counts <- as.numeric(Matrix::colSums(pseudobulk$counts))
  if (!identical(metadata$pseudobulk_id, colnames(pseudobulk$counts))) stop("Pseudobulk metadata order mismatch")
  list(counts = pseudobulk$counts, metadata = metadata)
}

m07_celltype_eligibility <- function(pseudobulk, min_cells = 20L,
                                     min_total_counts = 1000L,
                                     min_participants_per_group = 3L) {
  metadata <- pseudobulk$metadata
  required <- c(
    "pseudobulk_id", "participant_alias", "cell_type", "biological_group",
    "retained_cells", "total_raw_counts"
  )
  if (!all(required %in% names(metadata))) stop("Pseudobulk eligibility schema mismatch")
  allowed_groups <- c("DFU_HEALER", "DFU_NONHEALER")
  if (!all(metadata$biological_group %in% allowed_groups)) stop("Unexpected primary group")
  metadata$eligible_cell_count <- metadata$retained_cells >= min_cells
  metadata$eligible_library_size <- metadata$total_raw_counts >= min_total_counts
  metadata$eligible_pseudobulk <- metadata$eligible_cell_count & metadata$eligible_library_size
  metadata$exclusion_reason <- ifelse(
    metadata$eligible_pseudobulk,
    "ELIGIBLE",
    ifelse(
      !metadata$eligible_cell_count & !metadata$eligible_library_size,
      "BELOW_MIN_CELLS_AND_TOTAL_COUNTS",
      ifelse(!metadata$eligible_cell_count, "BELOW_MIN_CELLS", "BELOW_MIN_TOTAL_COUNTS")
    )
  )

  cell_types <- sort(unique(metadata$cell_type))
  summary_rows <- lapply(cell_types, function(cell_type) {
    rows <- metadata[metadata$cell_type == cell_type, , drop = FALSE]
    healer <- rows$eligible_pseudobulk & rows$biological_group == "DFU_HEALER"
    nonhealer <- rows$eligible_pseudobulk & rows$biological_group == "DFU_NONHEALER"
    n_healer <- length(unique(rows$participant_alias[healer]))
    n_nonhealer <- length(unique(rows$participant_alias[nonhealer]))
    eligible <- n_healer >= min_participants_per_group && n_nonhealer >= min_participants_per_group
    data.frame(
      cell_type = cell_type,
      observed_healer_participants = length(unique(rows$participant_alias[rows$biological_group == "DFU_HEALER"])),
      observed_nonhealer_participants = length(unique(rows$participant_alias[rows$biological_group == "DFU_NONHEALER"])),
      eligible_healer_participants = n_healer,
      eligible_nonhealer_participants = n_nonhealer,
      minimum_participants_per_group = min_participants_per_group,
      model_eligible = eligible,
      model_status = if (eligible) "ELIGIBLE_PARTICIPANT_LEVEL_EDGER_QL" else "NOT_ESTIMABLE_MINIMUM_PARTICIPANTS",
      stringsAsFactors = FALSE
    )
  })
  list(metadata = metadata, cell_types = do.call(rbind, summary_rows))
}

m07_run_edger_celltypes <- function(pseudobulk, eligibility,
                                    filter_min_count = 10L,
                                    filter_min_total_count = 15L,
                                    filter_large_n = 10L,
                                    filter_min_prop = 0.7) {
  if (!requireNamespace("edgeR", quietly = TRUE)) stop("MISSING_REQUIRED_PACKAGE: edgeR")
  metadata <- eligibility$metadata
  summary <- eligibility$cell_types
  result_rows <- list()
  model_rows <- list()
  result_index <- 0L
  model_index <- 0L
  for (cell_type in summary$cell_type[summary$model_eligible]) {
    selected <- metadata$cell_type == cell_type & metadata$eligible_pseudobulk
    meta <- metadata[selected, , drop = FALSE]
    counts <- pseudobulk$counts[, meta$pseudobulk_id, drop = FALSE]
    if (anyDuplicated(meta$participant_alias)) stop("Duplicate participant in a cell-type model")
    group <- factor(meta$biological_group, levels = c("DFU_HEALER", "DFU_NONHEALER"))
    if (any(is.na(group))) stop("Unexpected group in edgeR model")
    design <- stats::model.matrix(~0 + group)
    colnames(design) <- levels(group)
    rownames(design) <- meta$participant_alias
    dge <- edgeR::DGEList(counts = counts, group = group)
    keep <- edgeR::filterByExpr(
      dge,
      design = design,
      min.count = filter_min_count,
      min.total.count = filter_min_total_count,
      large.n = filter_large_n,
      min.prop = filter_min_prop
    )
    model_index <- model_index + 1L
    if (!any(keep)) {
      model_rows[[model_index]] <- data.frame(
        cell_type = cell_type,
        healer_participants = sum(group == "DFU_HEALER"),
        nonhealer_participants = sum(group == "DFU_NONHEALER"),
        genes_before_filter = nrow(dge),
        genes_after_filter = 0L,
        model_status = "VALID_NULL_NO_GENES_AFTER_FILTER",
        dispersion_status = "NOT_FIT",
        stringsAsFactors = FALSE
      )
      next
    }
    dge <- dge[keep, , keep.lib.sizes = FALSE]
    dge <- edgeR::calcNormFactors(dge, method = "TMM")
    dge <- edgeR::estimateDisp(dge, design = design, robust = TRUE)
    fit <- edgeR::glmQLFit(dge, design = design, robust = TRUE)
    contrast <- c(DFU_HEALER = -1, DFU_NONHEALER = 1)
    qlf <- edgeR::glmQLFTest(fit, contrast = contrast)
    table <- edgeR::topTags(qlf, n = Inf, sort.by = "none")$table
    table$gene <- rownames(table)
    table$cell_type <- cell_type
    table$contrast <- "DFU_NONHEALER_MINUS_DFU_HEALER"
    table$effect_direction_rule <- "positive_logFC_higher_in_nonhealer"
    table$healer_participants <- sum(group == "DFU_HEALER")
    table$nonhealer_participants <- sum(group == "DFU_NONHEALER")
    table$within_cell_type_FDR <- stats::p.adjust(table$PValue, method = "BH")
    table <- table[, c(
      "cell_type", "gene", "contrast", "effect_direction_rule", "logFC", "logCPM",
      "F", "PValue", "within_cell_type_FDR", "healer_participants", "nonhealer_participants"
    )]
    result_index <- result_index + 1L
    result_rows[[result_index]] <- table
    model_rows[[model_index]] <- data.frame(
      cell_type = cell_type,
      healer_participants = sum(group == "DFU_HEALER"),
      nonhealer_participants = sum(group == "DFU_NONHEALER"),
      genes_before_filter = length(keep),
      genes_after_filter = sum(keep),
      model_status = "FIT_PARTICIPANT_LEVEL_EDGER_QL",
      dispersion_status = "ROBUST_ESTIMATED",
      stringsAsFactors = FALSE
    )
  }
  results <- if (length(result_rows)) do.call(rbind, result_rows) else data.frame(
    cell_type = character(), gene = character(), contrast = character(),
    effect_direction_rule = character(), logFC = numeric(), logCPM = numeric(),
    F = numeric(), PValue = numeric(), within_cell_type_FDR = numeric(),
    healer_participants = integer(), nonhealer_participants = integer(),
    stringsAsFactors = FALSE
  )
  results$global_FDR <- stats::p.adjust(results$PValue, method = "BH")
  results$global_FDR_significant_0_05 <- results$global_FDR < 0.05
  results <- results[order(results$global_FDR, results$PValue, -abs(results$logFC), results$cell_type, results$gene), , drop = FALSE]
  models <- if (length(model_rows)) do.call(rbind, model_rows) else data.frame(
    cell_type = character(), healer_participants = integer(), nonhealer_participants = integer(),
    genes_before_filter = integer(), genes_after_filter = integer(), model_status = character(),
    dispersion_status = character(), stringsAsFactors = FALSE
  )
  list(results = results, models = models)
}

m07_participant_abundance <- function(cell_metadata) {
  required <- c("participant_alias", "biological_group", "marker_assigned_label")
  if (!all(required %in% names(cell_metadata))) stop("Abundance metadata schema mismatch")
  participants <- sort(unique(cell_metadata$participant_alias))
  cell_types <- sort(unique(cell_metadata$marker_assigned_label))
  grid <- expand.grid(
    participant_alias = participants,
    cell_type = cell_types,
    stringsAsFactors = FALSE
  )
  counts <- as.data.frame(table(cell_metadata$participant_alias, cell_metadata$marker_assigned_label), stringsAsFactors = FALSE)
  names(counts) <- c("participant_alias", "cell_type", "retained_cells")
  output <- merge(grid, counts, by = c("participant_alias", "cell_type"), all.x = TRUE, sort = FALSE)
  output$retained_cells[is.na(output$retained_cells)] <- 0L
  participant_groups <- unique(cell_metadata[, c("participant_alias", "biological_group"), drop = FALSE])
  if (anyDuplicated(participant_groups$participant_alias)) stop("Participant group is not unique")
  output <- merge(output, participant_groups, by = "participant_alias", all.x = TRUE, sort = FALSE)
  totals <- aggregate(retained_cells ~ participant_alias, output, sum)
  names(totals)[2L] <- "participant_total_retained_cells"
  output <- merge(output, totals, by = "participant_alias", all.x = TRUE, sort = FALSE)
  output$participant_cell_fraction <- output$retained_cells / output$participant_total_retained_cells
  output <- output[order(output$participant_alias, output$cell_type), , drop = FALSE]

  summarize_group <- function(values) {
    c(
      n = length(values),
      median = stats::median(values),
      q1 = unname(stats::quantile(values, 0.25, type = 7)),
      q3 = unname(stats::quantile(values, 0.75, type = 7)),
      mean = mean(values),
      sd = if (length(values) > 1L) stats::sd(values) else NA_real_
    )
  }
  summary_rows <- list()
  index <- 0L
  for (cell_type in cell_types) {
    rows <- output[output$cell_type == cell_type, , drop = FALSE]
    by_group <- lapply(c("DFU_HEALER", "DFU_NONHEALER"), function(group) {
      summarize_group(rows$participant_cell_fraction[rows$biological_group == group])
    })
    names(by_group) <- c("healer", "nonhealer")
    index <- index + 1L
    summary_rows[[index]] <- data.frame(
      cell_type = cell_type,
      healer_n = by_group$healer[["n"]],
      healer_median = by_group$healer[["median"]],
      healer_q1 = by_group$healer[["q1"]],
      healer_q3 = by_group$healer[["q3"]],
      nonhealer_n = by_group$nonhealer[["n"]],
      nonhealer_median = by_group$nonhealer[["median"]],
      nonhealer_q1 = by_group$nonhealer[["q1"]],
      nonhealer_q3 = by_group$nonhealer[["q3"]],
      median_difference_nonhealer_minus_healer = by_group$nonhealer[["median"]] - by_group$healer[["median"]],
      inferential_test = "NOT_PERFORMED_SMALL_N_EXPLORATORY_DESCRIPTIVE_ONLY",
      stringsAsFactors = FALSE
    )
  }
  list(participant = output, summary = do.call(rbind, summary_rows))
}

m07_he_fibro_participant_scores <- function(pseudobulk, signature_genes,
                                            eligible_cell_types = c("FIBROBLAST", "HEALING_ASSOCIATED_FIBROBLAST_STATE")) {
  signature_genes <- unique(signature_genes[nzchar(signature_genes)])
  genes <- intersect(signature_genes, rownames(pseudobulk$counts))
  if (!length(genes)) stop("No prespecified HE-Fibro signature gene is present")
  selected <- pseudobulk$metadata$cell_type %in% eligible_cell_types
  metadata <- pseudobulk$metadata[selected, , drop = FALSE]
  counts <- pseudobulk$counts[, metadata$pseudobulk_id, drop = FALSE]
  library_sizes <- Matrix::colSums(counts)
  log_cpm <- log2(sweep(as.matrix(counts[genes, , drop = FALSE]) + 0.5, 2L, library_sizes + 1, "/") * 1e6)
  metadata$signature_genes_prespecified <- length(signature_genes)
  metadata$signature_genes_present <- length(genes)
  metadata$he_fibro_signature_mean_log2_cpm <- colMeans(log_cpm)
  metadata$score_role <- "PRESPECIFIED_PARTICIPANT_LEVEL_DESCRIPTIVE_VALIDATION_ONLY"
  metadata$outcome_used_to_define_state <- FALSE
  metadata
}
