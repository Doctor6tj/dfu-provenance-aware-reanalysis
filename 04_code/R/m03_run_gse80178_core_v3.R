#!/usr/bin/env Rscript

# M03: reconstruct GSE80178 GPL16686 core transcript-cluster expression from
# a prospectively locked all-12 primary or n=11 GSM2114233-exclusion profile,
# run separate participant-aware contrasts, and emit complete QC/effect
# artifacts. The script refuses overwrite and never modifies source objects or
# installs packages.

options(stringsAsFactors = FALSE, warn = 1)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4L) {
  stop(
    "Usage: m03_run_gse80178_core_v3.R ",
    "<GSE80178_RAW.tar> <sample_manifest.csv> <parameters.json> <new_output_dir>"
  )
}

raw_tar <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
sample_manifest_path <- normalizePath(args[[2L]], winslash = "/", mustWork = TRUE)
parameters_path <- normalizePath(args[[3L]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[4L]], winslash = "/", mustWork = FALSE)

if (file.exists(output_dir) || dir.exists(output_dir)) {
  stop("Refusing overwrite: ", output_dir)
}

required_packages <- c(
  "oligo",
  "pd.hugene.1.0.st.v1",
  "hugene10sttranscriptcluster.db",
  "limma",
  "Biobase",
  "AnnotationDbi",
  "jsonlite",
  "digest"
)
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1L), quietly = TRUE)
]
if (length(missing_packages) > 0L) {
  stop("Missing required packages; installation is forbidden: ", paste(missing_packages, collapse = ", "))
}

sha256_file <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

write_json <- function(object, path) {
  jsonlite::write_json(
    object,
    path = path,
    auto_unbox = TRUE,
    pretty = TRUE,
    null = "null",
    digits = NA
  )
}

write_csv_stable <- function(object, path) {
  utils::write.csv(object, file = path, row.names = FALSE, na = "")
}

write_tsv_gz <- function(object, path) {
  con <- gzfile(path, open = "wt", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  utils::write.table(
    object,
    file = con,
    sep = "\t",
    quote = FALSE,
    row.names = FALSE,
    col.names = TRUE,
    na = ""
  )
}

decompress_gzip <- function(source, destination) {
  input <- gzfile(source, open = "rb")
  output <- file(destination, open = "wb")
  on.exit(close(input), add = TRUE)
  on.exit(close(output), add = TRUE)
  repeat {
    block <- readBin(input, what = "raw", n = 1024L * 1024L)
    if (length(block) == 0L) break
    writeBin(block, output)
  }
  invisible(destination)
}

first_nonempty <- function(values) {
  values <- sort(unique(as.character(values[!is.na(values) & nzchar(values)])))
  if (length(values) == 0L) NA_character_ else values[[1L]]
}

parameters <- jsonlite::read_json(parameters_path, simplifyVector = TRUE)
if (!identical(parameters$module_id, "M03_WITHIN_STUDY_EFFECTS")) {
  stop("Unexpected parameter module_id")
}
if (!identical(parameters$dataset$accession, "GSE80178")) {
  stop("Unexpected dataset accession")
}
if (!identical(parameters$dataset$platform, "GPL16686")) {
  stop("Unexpected platform; expected GPL16686")
}
if (!parameters$dataset$analysis_profile %in% c(
  "ALL12_PRIMARY",
  "N11_EXCLUDE_GSM2114233_SENSITIVITY"
)) {
  stop("Unexpected M03 v3 analysis profile")
}
if (!identical(parameters$author_decision$lock_id, "L3B_M03_QC_ROUTE_AUTHOR_DECISION_v1")) {
  stop("Missing or unexpected author QC-route lock")
}

for (package in required_packages) {
  expected <- as.character(parameters$software[[package]])
  observed <- as.character(utils::packageVersion(package))
  if (!identical(observed, expected)) {
    stop("Package version mismatch for ", package, ": expected ", expected, ", observed ", observed)
  }
}

project_root <- normalizePath(
  file.path(dirname(parameters_path), "..", ".."),
  winslash = "/",
  mustWork = TRUE
)
resolve_project_path <- function(relative_path) {
  normalizePath(file.path(project_root, relative_path), winslash = "/", mustWork = TRUE)
}

trust_inputs <- data.frame(
  input_id = c(
    "raw_tar",
    "analysis_sample_manifest",
    "primary_sample_manifest",
    "m02_accession_manifest",
    "m02_result_lock",
    "r_environment_manifest",
    "local_method_api_snapshot",
    "author_qc_route_decision"
  ),
  path = c(
    raw_tar,
    sample_manifest_path,
    resolve_project_path(parameters$input_authority$primary_sample_manifest$path),
    resolve_project_path(parameters$input_authority$m02_accession_manifest$path),
    resolve_project_path(parameters$input_authority$m02_result_lock$path),
    resolve_project_path(parameters$input_authority$r_environment_manifest$path),
    resolve_project_path(parameters$input_authority$local_method_api_snapshot$path),
    resolve_project_path(parameters$input_authority$author_qc_route_decision$path)
  ),
  expected_sha256 = c(
    parameters$input_authority$raw_tar$sha256,
    parameters$input_authority$sample_manifest$sha256,
    parameters$input_authority$primary_sample_manifest$sha256,
    parameters$input_authority$m02_accession_manifest$sha256,
    parameters$input_authority$m02_result_lock$sha256,
    parameters$input_authority$r_environment_manifest$sha256,
    parameters$input_authority$local_method_api_snapshot$sha256,
    parameters$input_authority$author_qc_route_decision$sha256
  )
)
trust_inputs$observed_sha256 <- vapply(trust_inputs$path, sha256_file, character(1L))
trust_inputs$hash_match <- trust_inputs$expected_sha256 == trust_inputs$observed_sha256
if (!all(trust_inputs$hash_match)) {
  bad <- trust_inputs$input_id[!trust_inputs$hash_match]
  stop("Trust-boundary hash mismatch: ", paste(bad, collapse = ", "))
}

sample_manifest <- utils::read.csv(
  sample_manifest_path,
  colClasses = "character",
  check.names = FALSE
)
primary_manifest <- utils::read.csv(
  resolve_project_path(parameters$input_authority$primary_sample_manifest$path),
  colClasses = "character",
  check.names = FALSE
)
required_sample_columns <- c(
  "dataset_id", "gsm_accession", "cel_member", "group_code",
  "biological_group", "participant_unit_id", "primary_eligible", "analysis_role"
)
if (!identical(names(sample_manifest), required_sample_columns) ||
    !identical(names(primary_manifest), required_sample_columns)) {
  stop("Sample manifest schema mismatch")
}
expected_sample_count <- as.integer(parameters$dataset$expected_samples)
expected_primary_count <- as.integer(parameters$dataset$primary_sample_universe_expected)
expected_analysis_role <- as.character(parameters$dataset$analysis_role)
expected_group_counts <- as.integer(unlist(parameters$dataset$expected_group_counts))
names(expected_group_counts) <- names(unlist(parameters$dataset$expected_group_counts))
excluded_gsm_accessions <- as.character(unlist(parameters$dataset$excluded_gsm_accessions))
excluded_gsm_accessions <- excluded_gsm_accessions[nzchar(excluded_gsm_accessions)]

if (nrow(primary_manifest) != expected_primary_count ||
    anyDuplicated(primary_manifest$gsm_accession) ||
    anyDuplicated(primary_manifest$cel_member) ||
    anyDuplicated(primary_manifest$participant_unit_id) ||
    !all(primary_manifest$dataset_id == "GSE80178") ||
    !all(primary_manifest$primary_eligible == "TRUE") ||
    !all(primary_manifest$analysis_role == "CORE_PRIMARY")) {
  stop("Primary sample-universe manifest identity/count/role violation")
}
if (nrow(sample_manifest) != expected_sample_count || anyDuplicated(sample_manifest$gsm_accession) ||
    anyDuplicated(sample_manifest$cel_member) || anyDuplicated(sample_manifest$participant_unit_id)) {
  stop("Sample manifest identity/count violation")
}
if (!all(sample_manifest$dataset_id == "GSE80178") ||
    !all(sample_manifest$primary_eligible == "TRUE") ||
    !all(sample_manifest$analysis_role == expected_analysis_role)) {
  stop("Sample manifest role violation")
}
if (!all(sample_manifest$gsm_accession %in% primary_manifest$gsm_accession) ||
    !all(sample_manifest$cel_member %in% primary_manifest$cel_member) ||
    !identical(
      sample_manifest$gsm_accession,
      primary_manifest$gsm_accession[!primary_manifest$gsm_accession %in% excluded_gsm_accessions]
    ) ||
    !setequal(setdiff(primary_manifest$gsm_accession, sample_manifest$gsm_accession), excluded_gsm_accessions)) {
  stop("Analysis manifest is not the exact prospectively declared subset of the primary universe")
}
observed_group_counts <- table(factor(sample_manifest$group_code, levels = names(expected_group_counts)))
if (!identical(as.integer(observed_group_counts), as.integer(expected_group_counts))) {
  stop(
    "Group counts mismatch; expected ",
    paste(paste(names(expected_group_counts), expected_group_counts, sep = "="), collapse = ",")
  )
}

started_at <- format(Sys.time(), tz = "UTC", usetz = TRUE)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
work_dir <- file.path(output_dir, "_derived_work")
dir.create(work_dir, recursive = FALSE, showWarnings = FALSE)

failure_path <- file.path(output_dir, "M03_execution_failure.json")

run_module <- function() {
  write_csv_stable(trust_inputs, file.path(output_dir, "M03_input_hash_verification.csv"))
  write_csv_stable(sample_manifest, file.path(output_dir, "M03_sample_manifest_used.csv"))

  tar_members <- utils::untar(raw_tar, list = TRUE)
  tar_member_basenames <- basename(gsub("\\\\", "/", tar_members))
  cel_tar_members <- tar_members[grepl("\\.CEL\\.gz$", tar_members, ignore.case = TRUE)]
  cel_tar_basenames <- basename(gsub("\\\\", "/", cel_tar_members))
  if (length(cel_tar_members) != expected_primary_count ||
      !setequal(cel_tar_basenames, primary_manifest$cel_member)) {
    stop("RAW.tar CEL member set does not exactly match the locked all-12 primary universe")
  }
  selected_tar_members <- tar_members[match(sample_manifest$cel_member, tar_member_basenames)]
  if (anyNA(selected_tar_members)) {
    stop("Failed to resolve one or more locked CEL members inside RAW.tar")
  }
  utils::untar(raw_tar, files = selected_tar_members, exdir = work_dir)

  extracted_gz <- list.files(
    work_dir,
    pattern = "\\.CEL\\.gz$",
    full.names = TRUE,
    recursive = TRUE,
    ignore.case = TRUE
  )
  extracted_by_name <- stats::setNames(extracted_gz, basename(extracted_gz))
  if (!all(sample_manifest$cel_member %in% names(extracted_by_name))) {
    stop("Expected CEL.gz extraction incomplete")
  }
  cel_dir <- file.path(work_dir, "cel_uncompressed")
  dir.create(cel_dir, recursive = FALSE, showWarnings = FALSE)
  cel_paths <- character(nrow(sample_manifest))
  for (index in seq_len(nrow(sample_manifest))) {
    source <- extracted_by_name[[sample_manifest$cel_member[[index]]]]
    destination <- file.path(cel_dir, sub("\\.gz$", "", basename(source), ignore.case = TRUE))
    decompress_gzip(source, destination)
    cel_paths[[index]] <- destination
  }

  raw_feature_set <- oligo::read.celfiles(
    filenames = cel_paths,
    pkgname = parameters$preprocessing$reader_pkgname,
    verbose = TRUE
  )
  Biobase::sampleNames(raw_feature_set) <- sample_manifest$gsm_accession
  normalized_eset <- oligo::rma(
    raw_feature_set,
    background = isTRUE(parameters$preprocessing$background),
    normalize = isTRUE(parameters$preprocessing$normalize),
    target = parameters$preprocessing$target
  )
  expression <- Biobase::exprs(normalized_eset)
  colnames(expression) <- sample_manifest$gsm_accession

  if (ncol(expression) != expected_sample_count || !identical(colnames(expression), sample_manifest$gsm_accession)) {
    stop("Normalized expression sample identity/order mismatch")
  }
  if (nrow(expression) < parameters$quality_control$hard_checks$minimum_core_feature_count ||
      nrow(expression) > parameters$quality_control$hard_checks$maximum_core_feature_count) {
    stop("Normalized core feature count outside locked bounds")
  }
  if (any(!is.finite(expression))) {
    stop("Normalized expression contains non-finite values")
  }

  group <- factor(sample_manifest$group_code, levels = c("DFU", "DFS", "NFS"))
  design <- stats::model.matrix(~ 0 + group)
  colnames(design) <- levels(group)
  rownames(design) <- sample_manifest$gsm_accession
  if (qr(design)$rank != 3L) {
    stop("Design matrix is not full rank")
  }
  contrast_matrix <- limma::makeContrasts(
    DFU_vs_DFS = DFU - DFS,
    DFU_vs_NFS = DFU - NFS,
    DFU_vs_FS_NAIVE = DFU - (DFS + NFS) / 2,
    DFS_vs_NFS = DFS - NFS,
    levels = design
  )
  write_csv_stable(
    data.frame(gsm_accession = rownames(design), design, check.names = FALSE),
    file.path(output_dir, "M03_model_design.csv")
  )
  write_csv_stable(
    data.frame(coefficient = rownames(contrast_matrix), contrast_matrix, check.names = FALSE),
    file.path(output_dir, "M03_contrast_matrix.csv")
  )

  annotation_db <- get(
    "hugene10sttranscriptcluster.db",
    envir = asNamespace("hugene10sttranscriptcluster.db")
  )
  feature_ids <- rownames(expression)
  annotation_long <- AnnotationDbi::select(
    annotation_db,
    keys = feature_ids,
    columns = c("SYMBOL", "ENTREZID", "GENENAME"),
    keytype = "PROBEID"
  )
  annotation_long$PROBEID <- as.character(annotation_long$PROBEID)
  annotation_split <- split(annotation_long, annotation_long$PROBEID)
  feature_mapping <- do.call(
    rbind,
    lapply(feature_ids, function(feature_id) {
      block <- annotation_split[[feature_id]]
      if (is.null(block)) {
        return(data.frame(
          feature_id = feature_id,
          ENTREZID = NA_character_,
          SYMBOL = NA_character_,
          GENENAME = NA_character_,
          entrez_mapping_count = 0L,
          annotation_status = "NO_ENTREZ_MAPPING"
        ))
      }
      entrez <- sort(unique(as.character(block$ENTREZID[!is.na(block$ENTREZID) & nzchar(block$ENTREZID)])))
      status <- if (length(entrez) == 1L) {
        "UNAMBIGUOUS_ENTREZ"
      } else if (length(entrez) == 0L) {
        "NO_ENTREZ_MAPPING"
      } else {
        "AMBIGUOUS_MULTIPLE_ENTREZ"
      }
      chosen <- if (length(entrez) == 1L) entrez[[1L]] else NA_character_
      chosen_rows <- if (is.na(chosen)) block else block[block$ENTREZID == chosen, , drop = FALSE]
      data.frame(
        feature_id = feature_id,
        ENTREZID = chosen,
        SYMBOL = first_nonempty(chosen_rows$SYMBOL),
        GENENAME = first_nonempty(chosen_rows$GENENAME),
        entrez_mapping_count = length(entrez),
        annotation_status = status
      )
    })
  )
  rownames(feature_mapping) <- NULL
  write_tsv_gz(feature_mapping, file.path(output_dir, "M03_feature_annotation_mapping.tsv.gz"))

  unambiguous <- feature_mapping$annotation_status == "UNAMBIGUOUS_ENTREZ"
  mapping_fraction <- mean(unambiguous)
  gene_to_features <- split(
    feature_mapping$feature_id[unambiguous],
    feature_mapping$ENTREZID[unambiguous]
  )
  gene_ids <- sort(names(gene_to_features))
  gene_expression <- t(vapply(
    gene_ids,
    function(gene_id) {
      apply(expression[gene_to_features[[gene_id]], , drop = FALSE], 2L, stats::median)
    },
    numeric(ncol(expression))
  ))
  rownames(gene_expression) <- gene_ids
  colnames(gene_expression) <- colnames(expression)
  gene_annotation <- do.call(
    rbind,
    lapply(gene_ids, function(gene_id) {
      rows <- feature_mapping[feature_mapping$ENTREZID == gene_id & unambiguous, , drop = FALSE]
      data.frame(
        ENTREZID = gene_id,
        SYMBOL = first_nonempty(rows$SYMBOL),
        GENENAME = first_nonempty(rows$GENENAME),
        contributing_core_features = nrow(rows)
      )
    })
  )
  rownames(gene_annotation) <- gene_annotation$ENTREZID

  fit_effect_tables <- function(matrix, id_name, annotation = NULL, prefix) {
    fit <- limma::lmFit(matrix, design)
    fit <- limma::contrasts.fit(fit, contrast_matrix)
    fit <- limma::eBayes(
      fit,
      trend = isTRUE(parameters$model$empirical_bayes$trend),
      robust = isTRUE(parameters$model$empirical_bayes$robust),
      winsor.tail.p = as.numeric(parameters$model$empirical_bayes$winsor_tail_p)
    )
    counts <- list()
    for (contrast_id in colnames(contrast_matrix)) {
      table <- limma::topTable(
        fit,
        coef = contrast_id,
        number = Inf,
        adjust.method = "BH",
        sort.by = "none"
      )
      table <- data.frame(
        identifier = rownames(table),
        table,
        check.names = FALSE,
        row.names = NULL
      )
      names(table)[[1L]] <- id_name
      table$moderated_SE <- ifelse(
        is.finite(table$t) & table$t != 0,
        abs(table$logFC / table$t),
        NA_real_
      )
      table$BH_FDR_lt_0_05 <- table$adj.P.Val < parameters$multiplicity$fdr_threshold_for_descriptive_counts
      if (!is.null(annotation)) {
        match_index <- match(table[[id_name]], rownames(annotation))
        table <- cbind(
          table[, id_name, drop = FALSE],
          annotation[match_index, , drop = FALSE],
          table[, setdiff(names(table), id_name), drop = FALSE]
        )
      }
      output_path <- file.path(output_dir, paste0(prefix, contrast_id, ".tsv.gz"))
      write_tsv_gz(table, output_path)
      counts[[contrast_id]] <- list(
        tested = nrow(table),
        bh_fdr_lt_0_05 = sum(table$BH_FDR_lt_0_05, na.rm = TRUE),
        positive_logFC_bh_fdr_lt_0_05 = sum(table$BH_FDR_lt_0_05 & table$logFC > 0, na.rm = TRUE),
        negative_logFC_bh_fdr_lt_0_05 = sum(table$BH_FDR_lt_0_05 & table$logFC < 0, na.rm = TRUE)
      )
    }
    list(fit = fit, counts = counts)
  }

  feature_annotation_for_results <- feature_mapping
  rownames(feature_annotation_for_results) <- feature_annotation_for_results$feature_id
  feature_annotation_for_results$feature_id <- NULL
  feature_results <- fit_effect_tables(
    expression,
    "feature_id",
    feature_annotation_for_results,
    "M03_feature_effects_"
  )
  gene_annotation_for_results <- gene_annotation
  gene_annotation_for_results$ENTREZID <- NULL
  gene_results <- fit_effect_tables(
    gene_expression,
    "ENTREZID",
    gene_annotation_for_results,
    "M03_gene_effects_"
  )

  saveRDS(normalized_eset, file.path(output_dir, "M03_normalized_core_expression_eset.rds"), compress = "xz")
  gene_matrix_output <- data.frame(ENTREZID = rownames(gene_expression), gene_expression, check.names = FALSE)
  write_tsv_gz(gene_matrix_output, file.path(output_dir, "M03_gene_expression_matrix_log2.tsv.gz"))

  feature_variances <- apply(expression, 1L, stats::var)
  pca_feature_count <- min(as.integer(parameters$quality_control$pca_features), nrow(expression))
  pca_features <- names(sort(feature_variances, decreasing = TRUE))[seq_len(pca_feature_count)]
  pca <- stats::prcomp(t(expression[pca_features, , drop = FALSE]), center = TRUE, scale. = FALSE)
  pca_variance <- (pca$sdev ^ 2) / sum(pca$sdev ^ 2)
  pca_coordinates <- data.frame(
    gsm_accession = rownames(pca$x),
    group_code = sample_manifest$group_code[match(rownames(pca$x), sample_manifest$gsm_accession)],
    PC1 = pca$x[, 1L],
    PC2 = pca$x[, 2L],
    PC1_variance_fraction = pca_variance[[1L]],
    PC2_variance_fraction = pca_variance[[2L]]
  )
  write_csv_stable(pca_coordinates, file.path(output_dir, "M03_pca_coordinates.csv"))

  sample_correlation <- stats::cor(expression, method = "pearson")
  correlation_output <- data.frame(gsm_accession = rownames(sample_correlation), sample_correlation, check.names = FALSE)
  write_csv_stable(correlation_output, file.path(output_dir, "M03_sample_correlation.csv"))
  off_diagonal <- sample_correlation[row(sample_correlation) != col(sample_correlation)]

  feature_medians <- apply(expression, 1L, stats::median)
  rle <- sweep(expression, 1L, feature_medians, FUN = "-")
  sample_qc <- data.frame(
    gsm_accession = colnames(expression),
    group_code = sample_manifest$group_code,
    normalized_median = apply(expression, 2L, stats::median),
    normalized_IQR = apply(expression, 2L, stats::IQR),
    RLE_median = apply(rle, 2L, stats::median),
    RLE_IQR = apply(rle, 2L, stats::IQR),
    mean_pairwise_correlation = (colSums(sample_correlation) - 1) / (ncol(sample_correlation) - 1)
  )
  write_csv_stable(sample_qc, file.path(output_dir, "M03_sample_qc_metrics.csv"))

  review_thresholds <- parameters$quality_control$review_flags
  review_flags <- data.frame(
    flag_id = c("LOW_PAIRWISE_CORRELATION", "RLE_MEDIAN_SHIFT", "RLE_IQR_WIDE", "LOW_ENTREZ_MAPPING"),
    observed = c(
      min(off_diagonal),
      max(abs(sample_qc$RLE_median)),
      max(sample_qc$RLE_IQR),
      mapping_fraction
    ),
    comparator = c(">=", "<=", "<=", ">="),
    threshold = c(
      review_thresholds$minimum_offdiagonal_pearson_correlation,
      review_thresholds$maximum_absolute_sample_RLE_median,
      review_thresholds$maximum_sample_RLE_IQR,
      review_thresholds$minimum_unambiguous_entrez_mapping_fraction
    )
  )
  review_flags$flagged <- c(
    review_flags$observed[[1L]] < review_flags$threshold[[1L]],
    review_flags$observed[[2L]] > review_flags$threshold[[2L]],
    review_flags$observed[[3L]] > review_flags$threshold[[3L]],
    review_flags$observed[[4L]] < review_flags$threshold[[4L]]
  )
  flag_actions <- unlist(parameters$quality_control$review_flag_actions)
  if (!all(review_flags$flag_id %in% names(flag_actions))) {
    stop("Missing one or more declared QC review-flag actions")
  }
  review_flags$evidence_role <- unname(as.character(flag_actions[review_flags$flag_id]))
  review_flags$blocks_promotion <- FALSE
  review_flags$requires_limitation <- review_flags$flagged &
    review_flags$evidence_role == "SAMPLE_QC_LIMITATION_IF_FLAGGED"
  write_csv_stable(review_flags, file.path(output_dir, "M03_qc_review_flags.csv"))
  promotion_status <- if (any(review_flags$requires_limitation)) {
    "PASS_WITH_PRESPECIFIED_QC_LIMITATION"
  } else {
    "PASS_STRUCTURAL_AND_SAMPLE_QC"
  }

  group_colors <- c(DFU = "#C23B22", DFS = "#2A6FBB", NFS = "#2E8B57")
  grDevices::png(file.path(output_dir, "M03_normalized_expression_boxplot.png"), width = 1800, height = 1200, res = 150)
  graphics::boxplot(
    as.data.frame(expression), las = 2, col = group_colors[sample_manifest$group_code],
    ylab = "RMA normalized log2 expression",
    main = paste("GSE80178 normalized core expression:", parameters$dataset$analysis_profile)
  )
  graphics::legend("topright", legend = names(group_colors), fill = group_colors, bty = "n")
  grDevices::dev.off()

  grDevices::png(file.path(output_dir, "M03_RLE_boxplot.png"), width = 1800, height = 1200, res = 150)
  graphics::boxplot(
    as.data.frame(rle), las = 2, col = group_colors[sample_manifest$group_code],
    ylab = "Relative log expression",
    main = paste("GSE80178 RLE after RMA:", parameters$dataset$analysis_profile),
    outline = FALSE
  )
  graphics::abline(h = 0, lty = 2, col = "grey40")
  grDevices::dev.off()

  grDevices::png(file.path(output_dir, "M03_PCA.png"), width = 1600, height = 1200, res = 150)
  graphics::plot(
    pca_coordinates$PC1, pca_coordinates$PC2,
    col = group_colors[pca_coordinates$group_code], pch = 19, cex = 1.3,
    xlab = sprintf("PC1 (%.1f%%)", 100 * pca_variance[[1L]]),
    ylab = sprintf("PC2 (%.1f%%)", 100 * pca_variance[[2L]]),
    main = paste("GSE80178 PCA:", parameters$dataset$analysis_profile)
  )
  graphics::text(
    pca_coordinates$PC1, pca_coordinates$PC2,
    labels = pca_coordinates$gsm_accession, pos = 3, cex = 0.7
  )
  graphics::legend("topright", legend = names(group_colors), col = group_colors, pch = 19, bty = "n")
  grDevices::dev.off()

  grDevices::png(file.path(output_dir, "M03_sample_correlation_heatmap.png"), width = 1500, height = 1400, res = 150)
  stats::heatmap(
    sample_correlation,
    Rowv = NA,
    Colv = NA,
    scale = "none",
    margins = c(10, 10),
    col = grDevices::colorRampPalette(c("#2166AC", "white", "#B2182B"))(100),
    main = paste("GSE80178 Pearson correlation:", parameters$dataset$analysis_profile)
  )
  grDevices::dev.off()

  session_lines <- capture.output(utils::sessionInfo())
  writeLines(session_lines, file.path(output_dir, "M03_sessionInfo.txt"), useBytes = TRUE)

  summary <- list(
    schema_version = "1.0",
    module_id = "M03_WITHIN_STUDY_EFFECTS",
    dataset_id = "GSE80178",
    platform_id = "GPL16686",
    analysis_profile = parameters$dataset$analysis_profile,
    analysis_role = expected_analysis_role,
    author_qc_route_lock_id = parameters$author_decision$lock_id,
    started_at_utc = started_at,
    completed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
    sample_count = ncol(expression),
    primary_sample_universe_count = nrow(primary_manifest),
    excluded_gsm_accessions = as.list(excluded_gsm_accessions),
    group_counts = as.list(stats::setNames(as.integer(observed_group_counts), names(expected_group_counts))),
    core_feature_count = nrow(expression),
    unambiguous_entrez_feature_fraction = mapping_fraction,
    gene_count = nrow(gene_expression),
    contrasts = list(
      DFU_vs_DFS = "PRIMARY",
      DFU_vs_NFS = "PRIMARY",
      DFU_vs_FS_NAIVE = "PRESPECIFIED_NAIVE_COMPARATOR_SENSITIVITY",
      DFS_vs_NFS = "CONTEXT_DIAGNOSTIC"
    ),
    feature_level_counts = feature_results$counts,
    gene_level_counts = gene_results$counts,
    review_flags = split(review_flags, seq_len(nrow(review_flags))),
    promotion_status = promotion_status,
    automatic_sample_exclusion_performed = FALSE,
    authorized_manifest_exclusion_performed = length(excluded_gsm_accessions) > 0L,
    package_installation_performed = FALSE,
    source_files_modified = FALSE,
    randomness = "NONE"
  )
  write_json(summary, file.path(output_dir, "M03_result_summary.json"))

  work_abs <- normalizePath(work_dir, winslash = "/", mustWork = TRUE)
  output_abs <- normalizePath(output_dir, winslash = "/", mustWork = TRUE)
  if (!identical(dirname(work_abs), output_abs) || basename(work_abs) != "_derived_work") {
    stop("Derived-work cleanup boundary validation failed")
  }
  unlink(work_abs, recursive = TRUE, force = TRUE)
  if (dir.exists(work_abs)) {
    stop("Derived-work cleanup incomplete")
  }

  execution_log <- list(
    schema_version = "1.0",
    module_id = "M03_WITHIN_STUDY_EFFECTS",
    status = "EXECUTION_COMPLETED",
    analysis_profile = parameters$dataset$analysis_profile,
    author_qc_route_lock_id = parameters$author_decision$lock_id,
    promotion_status = promotion_status,
    started_at_utc = started_at,
    completed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
    command_args = list(
      raw_tar = raw_tar,
      sample_manifest = sample_manifest_path,
      parameters = parameters_path,
      output_dir = output_dir
    ),
    parameters_sha256 = sha256_file(parameters_path),
    input_hashes_verified = nrow(trust_inputs),
    excluded_gsm_accessions = as.list(excluded_gsm_accessions),
    background_execution = FALSE,
    package_installation_performed = FALSE,
    source_files_modified = FALSE
  )
  write_json(execution_log, file.path(output_dir, "M03_execution_log.json"))

  deliverables <- list.files(output_dir, full.names = TRUE, recursive = FALSE)
  deliverables <- deliverables[file.info(deliverables)$isdir %in% FALSE]
  output_manifest <- data.frame(
    file = basename(deliverables),
    bytes = as.numeric(file.info(deliverables)$size),
    sha256 = vapply(deliverables, sha256_file, character(1L))
  )
  output_manifest <- output_manifest[order(output_manifest$file), , drop = FALSE]
  write_csv_stable(output_manifest, file.path(output_dir, "M03_output_manifest.csv"))

  cat("M03_EXECUTION_COMPLETED\n")
  cat("PROMOTION_STATUS=", promotion_status, "\n", sep = "")
  cat("SAMPLES=", ncol(expression), "\n", sep = "")
  cat("CORE_FEATURES=", nrow(expression), "\n", sep = "")
  cat("GENES=", nrow(gene_expression), "\n", sep = "")
  invisible(summary)
}

result <- tryCatch(
  run_module(),
  error = function(error) {
    failure <- list(
      schema_version = "1.0",
      module_id = "M03_WITHIN_STUDY_EFFECTS",
      status = "EXECUTION_FAILED_PRESERVED",
      started_at_utc = started_at,
      failed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
      error_class = class(error),
      error_message = conditionMessage(error),
      output_dir = output_dir,
      source_files_modified = FALSE
    )
    write_json(failure, failure_path)
    message("M03_EXECUTION_FAILED: ", conditionMessage(error))
    NULL
  }
)

if (is.null(result)) {
  quit(save = "no", status = 1L, runLast = FALSE)
}
