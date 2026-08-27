#!/usr/bin/env Rscript

# M04: quantify how exact cross-accession sample reuse and biologically merged
# comparators alter apparent reproducibility. The script processes the two
# six-array control containers separately, consumes only locked M03 effects,
# refuses overwrite, installs nothing, and never treats GSE68183 as independent
# biological validation.

options(stringsAsFactors = FALSE, warn = 1)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4L) {
  stop(
    "Usage: m04_run_naive_vs_aware_sensitivity_v1.R ",
    "<GSE68183_RAW.tar> <GSE80178_RAW.tar> <parameters.json> <new_output_dir>"
  )
}

raw_68183 <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
raw_80178 <- normalizePath(args[[2L]], winslash = "/", mustWork = TRUE)
parameters_path <- normalizePath(args[[3L]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[4L]], winslash = "/", mustWork = FALSE)
if (file.exists(output_dir) || dir.exists(output_dir)) stop("Refusing overwrite: ", output_dir)

required_packages <- c("oligo", "pd.hugene.1.0.st.v1", "limma", "Biobase", "jsonlite", "digest")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1L), quietly = TRUE)]
if (length(missing_packages) > 0L) {
  stop("Missing required packages; installation is forbidden: ", paste(missing_packages, collapse = ", "))
}

sha256_file <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)
write_json <- function(object, path) {
  jsonlite::write_json(object, path, auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA)
}
write_csv_stable <- function(object, path) utils::write.csv(object, path, row.names = FALSE, na = "")
write_tsv_gz <- function(object, path) {
  con <- gzfile(path, open = "wt", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  utils::write.table(object, con, sep = "\t", quote = FALSE, row.names = FALSE, col.names = TRUE, na = "")
}
read_tsv_gz <- function(path) {
  con <- gzfile(path, open = "rt", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  utils::read.delim(con, check.names = FALSE, stringsAsFactors = FALSE)
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
}
first_nonempty <- function(values) {
  values <- sort(unique(as.character(values[!is.na(values) & nzchar(values)])))
  if (length(values) == 0L) NA_character_ else values[[1L]]
}

parameters <- jsonlite::read_json(parameters_path, simplifyVector = FALSE)
if (!identical(parameters$module_id, "M04_NAIVE_VS_AWARE_SENSITIVITY")) stop("Unexpected module_id")
for (package in required_packages) {
  observed <- as.character(utils::packageVersion(package))
  expected <- as.character(parameters$software[[package]])
  if (!identical(observed, expected)) stop("Package version mismatch for ", package, ": ", observed, " != ", expected)
}

project_root <- normalizePath(file.path(dirname(parameters_path), "..", ".."), winslash = "/", mustWork = TRUE)
resolve_project_path <- function(relative_path) {
  normalizePath(file.path(project_root, relative_path), winslash = "/", mustWork = TRUE)
}
if (!identical(raw_68183, resolve_project_path(parameters$input_authority$gse68183_raw_tar$path))) {
  stop("GSE68183 argument path does not match parameter authority")
}
if (!identical(raw_80178, resolve_project_path(parameters$input_authority$gse80178_raw_tar$path))) {
  stop("GSE80178 argument path does not match parameter authority")
}

trust_rows <- do.call(rbind, lapply(names(parameters$input_authority), function(input_id) {
  item <- parameters$input_authority[[input_id]]
  path <- resolve_project_path(item$path)
  data.frame(
    input_id = input_id,
    path = path,
    expected_sha256 = as.character(item$sha256),
    observed_sha256 = sha256_file(path),
    stringsAsFactors = FALSE
  )
}))
trust_rows$hash_match <- trust_rows$expected_sha256 == trust_rows$observed_sha256
if (!all(trust_rows$hash_match)) {
  stop("Trust-boundary hash mismatch: ", paste(trust_rows$input_id[!trust_rows$hash_match], collapse = ", "))
}

manifest_columns <- c(
  "dataset_id", "gsm_accession", "cel_member", "group_code", "biological_group",
  "pair_id", "participant_unit_id", "naive_study_label", "independent_study_eligible", "analysis_role"
)
manifest_68183 <- utils::read.csv(
  resolve_project_path(parameters$input_authority$gse68183_manifest$path),
  colClasses = "character", check.names = FALSE
)
manifest_80178 <- utils::read.csv(
  resolve_project_path(parameters$input_authority$gse80178_alias_manifest$path),
  colClasses = "character", check.names = FALSE
)
pair_map <- utils::read.csv(
  resolve_project_path(parameters$input_authority$m01_pair_adjudication$path),
  colClasses = "character", check.names = FALSE
)
axes <- utils::read.csv(
  resolve_project_path(parameters$input_authority$sensitivity_axes$path),
  colClasses = "character", check.names = FALSE
)
if (!identical(names(manifest_68183), manifest_columns) || !identical(names(manifest_80178), manifest_columns)) {
  stop("M04 alias manifest schema mismatch")
}
for (manifest in list(manifest_68183, manifest_80178)) {
  if (nrow(manifest) != 6L || anyDuplicated(manifest$gsm_accession) || anyDuplicated(manifest$cel_member) ||
      anyDuplicated(manifest$pair_id) || anyDuplicated(manifest$participant_unit_id) ||
      !identical(as.integer(table(factor(manifest$group_code, levels = c("DFS", "NFS")))), c(3L, 3L))) {
    stop("M04 alias manifest identity/group-count violation")
  }
}
if (!all(manifest_68183$dataset_id == "GSE68183") || !all(manifest_80178$dataset_id == "GSE80178") ||
    !identical(manifest_68183$pair_id, manifest_80178$pair_id) ||
    !identical(manifest_68183$participant_unit_id, manifest_80178$participant_unit_id) ||
    !identical(manifest_68183$group_code, manifest_80178$group_code) ||
    !all(manifest_68183$independent_study_eligible == "FALSE")) {
  stop("Cross-accession alias authority mismatch")
}
pair_map <- pair_map[match(manifest_68183$pair_id, pair_map$pair_id), , drop = FALSE]
if (anyNA(pair_map$pair_id) || !all(pair_map$exact_raw_object_identity == "TRUE") ||
    !identical(pair_map$gse68183_gsm, manifest_68183$gsm_accession) ||
    !identical(pair_map$gse80178_gsm, manifest_80178$gsm_accession) ||
    !identical(pair_map$analytic_independence_unit, manifest_68183$participant_unit_id)) {
  stop("Locked M01 pair adjudication does not match M04 manifests")
}
if (!setequal(axes$axis_id, c(
  "M04_AXIS_REUSED_CONTROLS", "M04_AXIS_MERGED_COMPARATOR", "M04_AXIS_QC_SAMPLE",
  "M04_AXIS_PARTICIPANT_LIBRARY", "M04_AXIS_LEAVE_ONE_STUDY_OUT"
))) stop("Sensitivity-axis specification mismatch")

m01_lock <- jsonlite::read_json(resolve_project_path(parameters$input_authority$m01_metadata_result_lock$path))
m02_lock <- jsonlite::read_json(resolve_project_path(parameters$input_authority$m02_result_lock$path))
m03_lock_path <- resolve_project_path(parameters$input_authority$m03_accepted_result_lock$path)
m03_lock <- jsonlite::read_json(m03_lock_path)
m03_dod <- jsonlite::read_json(resolve_project_path(parameters$input_authority$m03_final_dod$path))
if (!identical(m01_lock$lock_id, "L5B_M01_DATASET_RELATIONSHIP_v1") ||
    !identical(m02_lock$status, "ACCEPTED_LOCKED") ||
    !identical(m03_lock$status, "ACCEPTED_LOCKED_PASS_WITH_LIMITATION") ||
    !identical(m03_lock$primary_authority, "ALL12_PRIMARY") ||
    as.integer(m03_dod$checks_passed) != 25L) {
  stop("Upstream lock/status authority mismatch")
}

m03_root <- dirname(m03_lock_path)
m03_manifest <- utils::read.csv(
  resolve_project_path(parameters$input_authority$m03_accepted_object_manifest$path),
  colClasses = "character", check.names = FALSE
)
read_m03_tsv <- function(relative_path) {
  row <- m03_manifest[m03_manifest$path == relative_path, , drop = FALSE]
  if (nrow(row) != 1L) stop("M03 accepted manifest row missing: ", relative_path)
  path <- normalizePath(file.path(m03_root, relative_path), winslash = "/", mustWork = TRUE)
  if (!identical(sha256_file(path), row$sha256[[1L]])) stop("M03 accepted object hash mismatch: ", relative_path)
  read_tsv_gz(path)
}

feature_mapping <- read_m03_tsv("primary_all12/M03_feature_annotation_mapping.tsv.gz")
feature_mapping$feature_id <- as.character(feature_mapping$feature_id)
unambiguous <- feature_mapping$annotation_status == "UNAMBIGUOUS_ENTREZ" &
  feature_mapping$entrez_mapping_count == 1L & !is.na(feature_mapping$ENTREZID) & nzchar(feature_mapping$ENTREZID)
gene_to_features <- split(feature_mapping$feature_id[unambiguous], feature_mapping$ENTREZID[unambiguous])
gene_ids <- sort(names(gene_to_features))
gene_annotation <- do.call(rbind, lapply(gene_ids, function(gene_id) {
  rows <- feature_mapping[feature_mapping$ENTREZID == gene_id & unambiguous, , drop = FALSE]
  data.frame(
    ENTREZID = gene_id,
    SYMBOL = first_nonempty(rows$SYMBOL),
    GENENAME = first_nonempty(rows$GENENAME),
    contributing_core_features = nrow(rows),
    stringsAsFactors = FALSE
  )
}))
rownames(gene_annotation) <- gene_annotation$ENTREZID

started_at <- format(Sys.time(), tz = "UTC", usetz = TRUE)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
work_dir <- file.path(output_dir, "_derived_work")
dir.create(work_dir, recursive = FALSE, showWarnings = FALSE)
failure_path <- file.path(output_dir, "M04_execution_failure.json")

fit_effect <- function(matrix, manifest, annotation, id_name) {
  group <- factor(manifest$group_code, levels = c("DFS", "NFS"))
  design <- stats::model.matrix(~ 0 + group)
  colnames(design) <- levels(group)
  rownames(design) <- manifest$gsm_accession
  if (qr(design)$rank != 2L) stop("Control-only design is not rank two")
  contrast <- limma::makeContrasts(DFS_vs_NFS = DFS - NFS, levels = design)
  fit <- limma::lmFit(matrix, design)
  fit <- limma::contrasts.fit(fit, contrast)
  fit <- limma::eBayes(
    fit,
    trend = isTRUE(parameters$reuse_model$empirical_bayes$trend),
    robust = isTRUE(parameters$reuse_model$empirical_bayes$robust),
    winsor.tail.p = as.numeric(unlist(parameters$reuse_model$empirical_bayes$winsor_tail_p))
  )
  result <- limma::topTable(fit, coef = "DFS_vs_NFS", number = Inf, adjust.method = "BH", sort.by = "none")
  result <- data.frame(identifier = rownames(result), result, check.names = FALSE, row.names = NULL)
  names(result)[[1L]] <- id_name
  result$moderated_SE <- ifelse(is.finite(result$t) & result$t != 0, abs(result$logFC / result$t), NA_real_)
  result$BH_FDR_lt_0_05 <- result$adj.P.Val < as.numeric(parameters$reuse_model$fdr_threshold_for_descriptive_counts)
  if (!is.null(annotation)) {
    index <- match(result[[id_name]], rownames(annotation))
    result <- cbind(
      result[, id_name, drop = FALSE],
      annotation[index, , drop = FALSE],
      result[, setdiff(names(result), id_name), drop = FALSE]
    )
  }
  list(result = result, design = design)
}

process_control_profile <- function(raw_tar, manifest, label) {
  profile_dir <- file.path(work_dir, label)
  dir.create(profile_dir, recursive = TRUE, showWarnings = FALSE)
  members <- utils::untar(raw_tar, list = TRUE)
  member_names <- basename(gsub("\\\\", "/", members))
  selected <- members[match(manifest$cel_member, member_names)]
  if (anyNA(selected)) stop("Locked CEL member missing in ", label)
  utils::untar(raw_tar, files = selected, exdir = profile_dir)
  extracted <- list.files(profile_dir, pattern = "\\.CEL\\.gz$", full.names = TRUE, recursive = TRUE, ignore.case = TRUE)
  extracted <- stats::setNames(extracted, basename(extracted))
  cel_dir <- file.path(profile_dir, "cel")
  dir.create(cel_dir, recursive = FALSE, showWarnings = FALSE)
  cel_paths <- character(nrow(manifest))
  for (index in seq_len(nrow(manifest))) {
    source <- extracted[[manifest$cel_member[[index]]]]
    if (is.null(source)) stop("Extracted CEL missing: ", manifest$cel_member[[index]])
    destination <- file.path(cel_dir, sub("\\.gz$", "", basename(source), ignore.case = TRUE))
    decompress_gzip(source, destination)
    cel_paths[[index]] <- destination
  }
  raw_set <- oligo::read.celfiles(
    filenames = cel_paths,
    pkgname = parameters$preprocessing$reader_pkgname,
    verbose = TRUE
  )
  Biobase::sampleNames(raw_set) <- manifest$gsm_accession
  normalized <- oligo::rma(
    raw_set,
    background = isTRUE(parameters$preprocessing$background),
    normalize = isTRUE(parameters$preprocessing$normalize),
    target = parameters$preprocessing$target
  )
  expression <- Biobase::exprs(normalized)
  colnames(expression) <- manifest$gsm_accession
  if (ncol(expression) != 6L || nrow(expression) < 20000L || nrow(expression) > 50000L || any(!is.finite(expression))) {
    stop("Invalid control-only RMA output for ", label)
  }
  if (!all(feature_mapping$feature_id %in% rownames(expression))) stop("M03 feature mapping does not cover control profile")
  gene_expression <- t(vapply(gene_ids, function(gene_id) {
    apply(expression[gene_to_features[[gene_id]], , drop = FALSE], 2L, stats::median)
  }, numeric(ncol(expression))))
  rownames(gene_expression) <- gene_ids
  colnames(gene_expression) <- colnames(expression)
  feature_annotation <- feature_mapping[match(rownames(expression), feature_mapping$feature_id), , drop = FALSE]
  rownames(feature_annotation) <- feature_annotation$feature_id
  feature_annotation$feature_id <- NULL
  gene_annotation_result <- gene_annotation
  gene_annotation_result$ENTREZID <- NULL
  feature_fit <- fit_effect(expression, manifest, feature_annotation, "feature_id")
  gene_fit <- fit_effect(gene_expression, manifest, gene_annotation_result, "ENTREZID")
  write_tsv_gz(feature_fit$result, file.path(output_dir, paste0("M04_", label, "_feature_effects_DFS_vs_NFS.tsv.gz")))
  write_tsv_gz(gene_fit$result, file.path(output_dir, paste0("M04_", label, "_gene_effects_DFS_vs_NFS.tsv.gz")))
  gene_matrix <- data.frame(ENTREZID = rownames(gene_expression), gene_expression, check.names = FALSE)
  write_tsv_gz(gene_matrix, file.path(output_dir, paste0("M04_", label, "_gene_expression_matrix_log2.tsv.gz")))
  write_csv_stable(
    data.frame(gsm_accession = rownames(feature_fit$design), feature_fit$design, check.names = FALSE),
    file.path(output_dir, paste0("M04_", label, "_model_design.csv"))
  )
  list(expression = expression, gene_expression = gene_expression, feature = feature_fit$result, gene = gene_fit$result)
}

comparison_metrics <- function(left, right, id_column, left_label, right_label, analysis_level) {
  merged <- merge(
    left[, c(id_column, "logFC", "t", "adj.P.Val"), drop = FALSE],
    right[, c(id_column, "logFC", "t", "adj.P.Val"), drop = FALSE],
    by = id_column, suffixes = c("_left", "_right"), sort = TRUE
  )
  finite <- is.finite(merged$logFC_left) & is.finite(merged$logFC_right)
  nonzero <- finite & merged$logFC_left != 0 & merged$logFC_right != 0
  rank_ids <- function(data, suffix) {
    t_values <- data[[paste0("t_", suffix)]]
    ids <- as.character(data[[id_column]])
    ids[order(-abs(t_values), ids)][seq_len(min(as.integer(parameters$metrics$top_rank_n), nrow(data)))]
  }
  left_top <- rank_ids(merged, "left")
  right_top <- rank_ids(merged, "right")
  overlap <- intersect(left_top, right_top)
  left_sig <- merged[[id_column]][merged$adj.P.Val_left < as.numeric(parameters$metrics$significance_threshold)]
  right_sig <- merged[[id_column]][merged$adj.P.Val_right < as.numeric(parameters$metrics$significance_threshold)]
  data.frame(
    analysis_level = analysis_level,
    left_specification = left_label,
    right_specification = right_label,
    matched_objects = nrow(merged),
    spearman_logFC = stats::cor(merged$logFC_left[finite], merged$logFC_right[finite], method = "spearman"),
    sign_concordance = mean(sign(merged$logFC_left[nonzero]) == sign(merged$logFC_right[nonzero])),
    maximum_absolute_logFC_difference = max(abs(merged$logFC_left - merged$logFC_right), na.rm = TRUE),
    top_n = length(left_top),
    top_overlap = length(overlap),
    top_jaccard = length(overlap) / length(union(left_top, right_top)),
    left_BH_FDR_lt_0_05 = length(left_sig),
    right_BH_FDR_lt_0_05 = length(right_sig),
    significant_overlap = length(intersect(left_sig, right_sig)),
    stringsAsFactors = FALSE
  )
}

run_module <- function() {
  write_csv_stable(trust_rows, file.path(output_dir, "M04_input_hash_verification.csv"))
  write_csv_stable(pair_map, file.path(output_dir, "M04_alias_pair_identity.csv"))
  profile_68183 <- process_control_profile(raw_68183, manifest_68183, "GSE68183_CONTROL_ONLY")
  profile_80178 <- process_control_profile(raw_80178, manifest_80178, "GSE80178_ALIAS_CONTROL_ONLY")

  pair_order_68183 <- order(manifest_68183$pair_id)
  pair_order_80178 <- order(manifest_80178$pair_id)
  feature_expression_delta <- max(abs(
    profile_68183$expression[, pair_order_68183, drop = FALSE] -
      profile_80178$expression[, pair_order_80178, drop = FALSE]
  ))
  gene_expression_delta <- max(abs(
    profile_68183$gene_expression[, pair_order_68183, drop = FALSE] -
      profile_80178$gene_expression[, pair_order_80178, drop = FALSE]
  ))
  reuse_metrics <- rbind(
    comparison_metrics(profile_68183$feature, profile_80178$feature, "feature_id", "GSE68183_ACCESSION", "GSE80178_ALIAS_CONTROL_SUBSET", "FEATURE"),
    comparison_metrics(profile_68183$gene, profile_80178$gene, "ENTREZID", "GSE68183_ACCESSION", "GSE80178_ALIAS_CONTROL_SUBSET", "GENE")
  )
  reuse_metrics$maximum_absolute_expression_difference <- c(feature_expression_delta, gene_expression_delta)
  reuse_metrics$naive_independent_study_count <- 2L
  reuse_metrics$provenance_aware_independent_study_count <- 1L
  reuse_metrics$naive_accession_rows <- 12L
  reuse_metrics$provenance_aware_unique_objects <- 6L
  reuse_metrics$independent_replication_eligible <- FALSE
  reuse_metrics$evidence_role <- "PSEUDO_REPLICATION_FROM_EXACT_RAW_OBJECT_REUSE"
  write_csv_stable(reuse_metrics, file.path(output_dir, "M04_reuse_axis_summary.csv"))

  comparator_metrics <- list()
  gene_classifications <- list()
  profile_map <- unlist(parameters$comparator_axis$profiles)
  for (profile_name in names(profile_map)) {
    profile_dir <- as.character(profile_map[[profile_name]])
    for (analysis_level in c("FEATURE", "GENE")) {
      prefix <- if (analysis_level == "FEATURE") "M03_feature_effects_" else "M03_gene_effects_"
      id_column <- if (analysis_level == "FEATURE") "feature_id" else "ENTREZID"
      naive <- read_m03_tsv(file.path(profile_dir, paste0(prefix, "DFU_vs_FS_NAIVE.tsv.gz")))
      for (aware_contrast in c("DFU_vs_DFS", "DFU_vs_NFS")) {
        aware <- read_m03_tsv(file.path(profile_dir, paste0(prefix, aware_contrast, ".tsv.gz")))
        row <- comparison_metrics(
          naive, aware, id_column,
          paste0(profile_name, ":DFU_vs_FS_NAIVE"),
          paste0(profile_name, ":", aware_contrast),
          analysis_level
        )
        row$profile <- profile_name
        row$naive_contrast <- "DFU_vs_FS_NAIVE"
        row$aware_contrast <- aware_contrast
        comparator_metrics[[length(comparator_metrics) + 1L]] <- row
      }
      if (analysis_level == "GENE") {
        dfs <- read_m03_tsv(file.path(profile_dir, paste0(prefix, "DFU_vs_DFS.tsv.gz")))
        nfs <- read_m03_tsv(file.path(profile_dir, paste0(prefix, "DFU_vs_NFS.tsv.gz")))
        ids <- Reduce(intersect, list(as.character(naive$ENTREZID), as.character(dfs$ENTREZID), as.character(nfs$ENTREZID)))
        naive <- naive[match(ids, naive$ENTREZID), , drop = FALSE]
        dfs <- dfs[match(ids, dfs$ENTREZID), , drop = FALSE]
        nfs <- nfs[match(ids, nfs$ENTREZID), , drop = FALSE]
        classification <- data.frame(
          profile = profile_name,
          ENTREZID = ids,
          SYMBOL = naive$SYMBOL,
          GENENAME = naive$GENENAME,
          naive_logFC = naive$logFC,
          naive_adj_P_Val = naive$adj.P.Val,
          DFU_vs_DFS_logFC = dfs$logFC,
          DFU_vs_DFS_adj_P_Val = dfs$adj.P.Val,
          DFU_vs_NFS_logFC = nfs$logFC,
          DFU_vs_NFS_adj_P_Val = nfs$adj.P.Val,
          separate_contrasts_same_direction = sign(dfs$logFC) == sign(nfs$logFC),
          naive_BH_FDR_lt_0_05 = naive$adj.P.Val < 0.05,
          both_separate_BH_FDR_lt_0_05 = dfs$adj.P.Val < 0.05 & nfs$adj.P.Val < 0.05,
          naive_only_threshold_finding = naive$adj.P.Val < 0.05 & !(dfs$adj.P.Val < 0.05 & nfs$adj.P.Val < 0.05),
          robust_signal_eligibility = "NOT_ADJUDICATED_IN_M04_M05_AUTHORITY",
          stringsAsFactors = FALSE
        )
        gene_classifications[[profile_name]] <- classification
        write_tsv_gz(classification, file.path(output_dir, paste0("M04_gene_comparator_classification_", profile_name, ".tsv.gz")))
      }
    }
  }
  comparator_metrics <- do.call(rbind, comparator_metrics)
  comparator_metrics <- comparator_metrics[, c(
    "profile", "analysis_level", "naive_contrast", "aware_contrast",
    setdiff(names(comparator_metrics), c("profile", "analysis_level", "naive_contrast", "aware_contrast"))
  )]
  write_csv_stable(comparator_metrics, file.path(output_dir, "M04_comparator_axis_metrics.csv"))

  tolerance <- as.numeric(parameters$metrics$alias_numerical_equivalence_absolute_tolerance)
  alias_equivalent <- feature_expression_delta <= tolerance && gene_expression_delta <= tolerance &&
    all(reuse_metrics$maximum_absolute_logFC_difference <= tolerance)
  primary_classification <- gene_classifications[["ALL12_PRIMARY"]]
  sensitivity_classification <- gene_classifications[["N11_EXCLUDE_GSM2114233_SENSITIVITY"]]
  axis_summary <- data.frame(
    axis_id = axes$axis_id,
    observed_naive = c(
      "2 accession containers and 12 accession rows appear independent",
      paste0(sum(primary_classification$naive_BH_FDR_lt_0_05), " primary-profile gene hits in pooled contrast"),
      paste0(sum(sensitivity_classification$naive_BH_FDR_lt_0_05), " n11 pooled-contrast sensitivity gene hits"),
      "54 GSE165816 libraries could be miscounted as independent",
      "2 accession labels could be miscounted as 2 studies"
    ),
    observed_aware = c(
      paste0("6 exact aliases collapse to 6 unique objects; numerical equivalence=", alias_equivalent),
      paste0(sum(primary_classification$both_separate_BH_FDR_lt_0_05), " genes pass BH FDR in both separate primary comparators"),
      "All12 remains primary; n11 is QC sensitivity only",
      "Deferred to M07 participant-aware analysis; not executed in M04",
      "1 independent core local-DFU study; leave-one-study-out not estimable"
    ),
    interpretation = c(
      "Pseudo-replication cannot support external validation",
      "Pooled-control findings cannot replace separate comparator inference",
      "Sensitivity-only threshold findings are not primary robust findings",
      "No cell/library-level claim is made by M04",
      "Independent cross-study biological replication cannot be concluded from core M04"
    ),
    robust_claim_eligible = c(FALSE, FALSE, FALSE, FALSE, FALSE),
    stringsAsFactors = FALSE
  )
  write_csv_stable(axis_summary, file.path(output_dir, "M04_axis_interpretation_summary.csv"))

  qc <- data.frame(
    check_id = c(
      "INPUT_HASHES", "ALIAS_PAIR_COUNT", "DECOMPRESSED_IDENTITY_AUTHORITY", "CONTROL_GROUP_COUNTS",
      "FEATURE_RANGE", "GENE_RANGE", "ALIAS_NUMERICAL_EQUIVALENCE", "INDEPENDENT_REPLICATION_INELIGIBLE",
      "M03_PRIMARY_AUTHORITY", "M05_SIGNAL_SELECTION_FIREWALL", "GSE199939_EXCLUDED", "GSE165816_DEFERRED"
    ),
    pass = c(
      all(trust_rows$hash_match), nrow(pair_map) == 6L, all(pair_map$exact_raw_object_identity == "TRUE"),
      all(vapply(list(manifest_68183, manifest_80178), function(x) identical(as.integer(table(factor(x$group_code, levels = c("DFS", "NFS")))), c(3L, 3L)), logical(1L))),
      nrow(profile_68183$expression) >= 20000L && nrow(profile_68183$expression) <= 50000L,
      nrow(profile_68183$gene_expression) >= 10000L,
      alias_equivalent, !isTRUE(parameters$reuse_axis$independent_replication_eligible),
      identical(m03_lock$primary_authority, "ALL12_PRIMARY"),
      !isTRUE(parameters$comparator_axis$gene_robustness_selection_performed),
      identical(parameters$prespecified_boundaries$gse199939_role, "EXCLUDED_FROM_CORE"),
      grepl("M07", parameters$prespecified_boundaries$gse165816_role)
    ),
    hard_gate = TRUE,
    stringsAsFactors = FALSE
  )
  write_csv_stable(qc, file.path(output_dir, "M04_engineering_statistical_scientific_qc.csv"))
  if (!all(qc$pass)) stop("One or more M04 hard QC checks failed: ", paste(qc$check_id[!qc$pass], collapse = ", "))

  summary <- list(
    schema_version = "1.0",
    module_id = "M04_NAIVE_VS_AWARE_SENSITIVITY",
    status = "PASS_CANDIDATE_READY_FOR_VALIDATION",
    started_at_utc = started_at,
    completed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
    reuse_axis = list(
      exact_alias_pairs = 6L,
      naive_accession_rows = 12L,
      provenance_aware_unique_objects = 6L,
      naive_independent_study_count = 2L,
      provenance_aware_independent_study_count = 1L,
      feature_expression_max_abs_delta = feature_expression_delta,
      gene_expression_max_abs_delta = gene_expression_delta,
      numerical_equivalence_pass = alias_equivalent,
      independent_replication_eligible = FALSE
    ),
    comparator_axis = list(
      profiles = names(gene_classifications),
      primary_profile = "ALL12_PRIMARY",
      primary_naive_gene_BH_FDR_lt_0_05 = sum(primary_classification$naive_BH_FDR_lt_0_05),
      primary_both_separate_gene_BH_FDR_lt_0_05 = sum(primary_classification$both_separate_BH_FDR_lt_0_05),
      n11_naive_gene_BH_FDR_lt_0_05 = sum(sensitivity_classification$naive_BH_FDR_lt_0_05),
      n11_both_separate_gene_BH_FDR_lt_0_05 = sum(sensitivity_classification$both_separate_BH_FDR_lt_0_05),
      robust_signal_selection_performed = FALSE
    ),
    principal_interpretation = "Naive accession counting creates pseudo-replication from six exact reused controls, and pooled-control effects cannot replace separate DFS and NFS comparisons.",
    cannot_conclude = list(
      "GSE68183 is not independent replication evidence for GSE80178",
      "Pooled DFS/NFS findings are not eligible as primary comparator findings",
      "M04 does not select robust genes; M05 owns that decision",
      "Independent leave-one-study-out replication is not estimable with one core local-DFU study"
    ),
    expression_reused_from_locked_m03_for_comparator_axis = TRUE,
    new_expression_processing_limited_to_two_separate_six_control_alias_profiles = TRUE,
    source_files_modified = FALSE,
    package_installation_performed = FALSE,
    background_execution = FALSE
  )
  write_json(summary, file.path(output_dir, "M04_result_summary.json"))
  writeLines(capture.output(sessionInfo()), file.path(output_dir, "M04_sessionInfo.txt"))
  execution_log <- list(
    module_id = "M04_NAIVE_VS_AWARE_SENSITIVITY",
    status = "COMPLETED",
    started_at_utc = started_at,
    completed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
    output_directory = output_dir,
    foreground_only = TRUE,
    source_modification = FALSE,
    package_installation = FALSE
  )
  write_json(execution_log, file.path(output_dir, "M04_execution_log.json"))
  unlink(work_dir, recursive = TRUE, force = TRUE)

  output_files <- sort(list.files(output_dir, full.names = TRUE, recursive = FALSE))
  output_files <- output_files[file.info(output_files)$isdir %in% FALSE]
  output_files <- output_files[basename(output_files) != "M04_output_manifest.csv"]
  output_manifest <- data.frame(
    path = basename(output_files),
    size_bytes = file.info(output_files)$size,
    sha256 = vapply(output_files, sha256_file, character(1L)),
    stringsAsFactors = FALSE
  )
  write_csv_stable(output_manifest, file.path(output_dir, "M04_output_manifest.csv"))
  cat("M04_EXECUTION_COMPLETED\n")
  cat("STATUS=PASS_CANDIDATE_READY_FOR_VALIDATION\n")
  cat("ALIAS_EQUIVALENCE=", alias_equivalent, "\n", sep = "")
  cat("INDEPENDENT_STUDIES_AWARE=1\n")
  cat("ROBUST_SIGNAL_SELECTION=FALSE\n")
  invisible(summary)
}

result <- tryCatch(
  run_module(),
  error = function(error) {
    failure <- list(
      schema_version = "1.0",
      module_id = "M04_NAIVE_VS_AWARE_SENSITIVITY",
      status = "EXECUTION_FAILED_PRESERVED",
      started_at_utc = started_at,
      failed_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
      message = conditionMessage(error),
      source_files_modified = FALSE,
      output_overwrite = FALSE
    )
    write_json(failure, failure_path)
    stop(error)
  }
)

invisible(result)
