# Deterministic helper functions for the M07 technical pilot.

m07_mad_flags <- function(values, lower = TRUE, upper = TRUE, nmads = 3,
                          mad_scale_constant = 1.4826) {
  if (any(!is.finite(values))) stop("Non-finite QC metric")
  center <- stats::median(values)
  spread <- stats::mad(values, center = center, constant = mad_scale_constant)
  low <- rep(FALSE, length(values))
  high <- rep(FALSE, length(values))
  if (spread > 0) {
    if (lower) low <- values < (center - nmads * spread)
    if (upper) high <- values > (center + nmads * spread)
  }
  list(low = low, high = high, median = center, mad_raw = spread, nmads = nmads)
}

m07_qc_flags <- function(total_counts, detected_features, mitochondrial_percent,
                         hard_min_features = 200, hard_max_mito_percent = 50,
                         nmads = 3, mad_scale_constant = 1.4826) {
  if (!(length(total_counts) == length(detected_features) &&
        length(total_counts) == length(mitochondrial_percent))) {
    stop("QC metric lengths differ")
  }
  counts_flags <- m07_mad_flags(log10(total_counts + 1), lower = TRUE, upper = TRUE, nmads = nmads, mad_scale_constant = mad_scale_constant)
  feature_flags <- m07_mad_flags(log10(detected_features + 1), lower = TRUE, upper = TRUE, nmads = nmads, mad_scale_constant = mad_scale_constant)
  mito_flags <- m07_mad_flags(mitochondrial_percent, lower = FALSE, upper = TRUE, nmads = nmads, mad_scale_constant = mad_scale_constant)
  hard_low_features <- detected_features < hard_min_features
  hard_high_mito <- mitochondrial_percent > hard_max_mito_percent
  adaptive_outlier <- counts_flags$low | counts_flags$high |
    feature_flags$low | feature_flags$high | mito_flags$high
  keep <- !(hard_low_features | hard_high_mito | adaptive_outlier)
  data.frame(
    hard_low_features = hard_low_features,
    hard_high_mito = hard_high_mito,
    adaptive_low_counts = counts_flags$low,
    adaptive_high_counts = counts_flags$high,
    adaptive_low_features = feature_flags$low,
    adaptive_high_features = feature_flags$high,
    adaptive_high_mito = mito_flags$high,
    qc_keep_before_doublet = keep,
    stringsAsFactors = FALSE
  )
}

m07_union_align <- function(matrices) {
  if (!length(matrices)) stop("No matrices supplied")
  if (any(vapply(matrices, is.null, logical(1)))) stop("NULL matrix supplied")
  union_features <- sort(unique(unlist(lapply(matrices, rownames), use.names = FALSE)))
  if (any(!nzchar(union_features))) stop("Blank feature identifier")
  aligned <- lapply(matrices, function(matrix) {
    matrix <- methods::as(matrix, "dgCMatrix")
    coordinates <- Matrix::summary(matrix)
    feature_map <- match(rownames(matrix), union_features)
    output <- Matrix::sparseMatrix(
      i = feature_map[coordinates$i],
      j = coordinates$j,
      x = coordinates$x,
      dims = c(length(union_features), ncol(matrix)),
      dimnames = list(union_features, colnames(matrix)),
      giveCsparse = TRUE
    )
    methods::as(output, "dgCMatrix")
  })
  list(features = union_features, matrix = do.call(cbind, aligned))
}

m07_cluster_marker_scores <- function(log_expression, clusters, dictionary,
                                      min_markers = 3, min_margin = 0.25) {
  if (ncol(log_expression) != length(clusters)) stop("Cluster vector length mismatch")
  required <- c("canonical_label", "canonical_display_label", "classification_level", "gene")
  if (!all(required %in% names(dictionary))) stop("Annotation dictionary schema mismatch")
  cluster_levels <- sort(unique(as.character(clusters)))
  marker_genes <- intersect(unique(dictionary$gene), rownames(log_expression))
  if (!length(marker_genes)) stop("No annotation marker is present")
  average <- vapply(
    cluster_levels,
    function(cluster_id) Matrix::rowMeans(log_expression[marker_genes, as.character(clusters) == cluster_id, drop = FALSE]),
    numeric(length(marker_genes))
  )
  if (is.null(dim(average))) average <- matrix(average, ncol = 1L)
  rownames(average) <- marker_genes
  colnames(average) <- cluster_levels
  gene_center <- Matrix::rowMeans(average)
  gene_sd <- apply(average, 1L, stats::sd)
  gene_sd[!is.finite(gene_sd) | gene_sd == 0] <- 1
  z <- sweep(sweep(average, 1L, gene_center, "-"), 1L, gene_sd, "/")

  labels <- sort(unique(dictionary$canonical_label))
  score_rows <- list()
  score_index <- 0L
  for (label in labels) {
    label_rows <- dictionary[dictionary$canonical_label == label, , drop = FALSE]
    genes <- intersect(unique(label_rows$gene), rownames(z))
    label_scores <- if (length(genes)) colMeans(z[genes, , drop = FALSE]) else rep(NA_real_, length(cluster_levels))
    for (cluster_index in seq_along(cluster_levels)) {
      score_index <- score_index + 1L
      score_rows[[score_index]] <- data.frame(
        cluster = cluster_levels[[cluster_index]],
        canonical_label = label,
        canonical_display_label = label_rows$canonical_display_label[[1L]],
        classification_level = label_rows$classification_level[[1L]],
        markers_available = length(genes),
        score = label_scores[[cluster_index]],
        stringsAsFactors = FALSE
      )
    }
  }
  scores <- do.call(rbind, score_rows)
  assignments <- lapply(cluster_levels, function(cluster_id) {
    rows <- scores[scores$cluster == cluster_id & scores$markers_available >= min_markers & is.finite(scores$score), , drop = FALSE]
    rows <- rows[order(-rows$score, rows$canonical_label), , drop = FALSE]
    if (!nrow(rows)) {
      return(data.frame(cluster = cluster_id, assigned_label = "UNRESOLVED", assigned_display_label = "Unresolved",
                        classification_level = "UNRESOLVED", top_score = NA_real_, second_score = NA_real_,
                        score_margin = NA_real_, markers_available = 0L, assignment_status = "UNRESOLVED_NO_ELIGIBLE_MARKER_SET",
                        stringsAsFactors = FALSE))
    }
    second <- if (nrow(rows) >= 2L) rows$score[[2L]] else NA_real_
    margin <- if (is.finite(second)) rows$score[[1L]] - second else Inf
    accepted <- is.finite(margin) && margin >= min_margin
    data.frame(
      cluster = cluster_id,
      assigned_label = if (accepted) rows$canonical_label[[1L]] else "UNRESOLVED",
      assigned_display_label = if (accepted) rows$canonical_display_label[[1L]] else "Unresolved",
      classification_level = if (accepted) rows$classification_level[[1L]] else "UNRESOLVED",
      top_score = rows$score[[1L]], second_score = second, score_margin = margin,
      markers_available = rows$markers_available[[1L]],
      assignment_status = if (accepted) "ASSIGNED_BY_BLINDED_MARKER_SCORE" else "UNRESOLVED_LOW_MARGIN",
      stringsAsFactors = FALSE
    )
  })
  list(scores = scores, assignments = do.call(rbind, assignments), marker_genes_present = marker_genes)
}

m07_pseudobulk_counts <- function(counts, participant, cell_type) {
  if (ncol(counts) != length(participant) || length(participant) != length(cell_type)) {
    stop("Pseudobulk metadata length mismatch")
  }
  keys <- paste(participant, cell_type, sep = "__")
  levels <- sort(unique(keys))
  incidence <- Matrix::sparseMatrix(
    i = seq_along(keys),
    j = match(keys, levels),
    x = 1,
    dims = c(length(keys), length(levels)),
    dimnames = list(colnames(counts), levels),
    giveCsparse = TRUE
  )
  aggregated <- counts %*% incidence
  parts <- strsplit(levels, "__", fixed = TRUE)
  metadata <- data.frame(
    pseudobulk_id = levels,
    participant_alias = vapply(parts, `[[`, character(1), 1L),
    cell_type = vapply(parts, function(value) paste(value[-1L], collapse = "__"), character(1)),
    stringsAsFactors = FALSE
  )
  list(counts = methods::as(aggregated, "dgCMatrix"), metadata = metadata)
}
