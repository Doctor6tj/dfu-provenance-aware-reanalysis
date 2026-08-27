#!/usr/bin/env Rscript

# Prospective M07 core-foot single-cell workflow. Clustering and annotation are
# outcome-blinded; clinical-group inference uses participant-level raw-count
# pseudobulks only. Positive logFC means higher in DFU nonhealers.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 6L) {
  stop(paste(
    "Usage: Rscript m07_run_full_core_analysis_v1.R",
    "<project_root> <sparse_conversion_dir> <library_manifest>",
    "<annotation_dictionary> <parameters_json> <output_dir>"
  ))
}
project_root <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
conversion_dir <- normalizePath(args[[2L]], winslash = "/", mustWork = TRUE)
manifest_path <- normalizePath(args[[3L]], winslash = "/", mustWork = TRUE)
dictionary_path <- normalizePath(args[[4L]], winslash = "/", mustWork = TRUE)
parameters_path <- normalizePath(args[[5L]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[6L]], winslash = "/", mustWork = FALSE)
if (dir.exists(output_dir) || file.exists(output_dir)) stop("Refusing overwrite: ", output_dir)

required_packages <- c(
  "Matrix", "SingleCellExperiment", "scuttle", "scDblFinder", "Seurat",
  "SeuratObject", "SummarizedExperiment", "BiocParallel", "ggplot2",
  "jsonlite", "edgeR"
)
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, quietly = TRUE, FUN.VALUE = logical(1))
]
if (length(missing_packages)) stop("MISSING_REQUIRED_PACKAGES: ", paste(missing_packages, collapse = ","))

source(file.path(project_root, "04_code/R/m07_pilot_helpers_v1.R"), local = TRUE)
source(file.path(project_root, "04_code/R/m07_full_analysis_helpers_v1.R"), local = TRUE)

write_csv_gz <- function(value, path) {
  connection <- gzfile(path, open = "wt", encoding = "UTF-8")
  on.exit(close(connection), add = TRUE)
  utils::write.csv(value, connection, row.names = FALSE, quote = TRUE, na = "")
}

read_gzip_lines <- function(path) {
  connection <- gzfile(path, open = "rt", encoding = "UTF-8")
  on.exit(close(connection), add = TRUE)
  readLines(connection, warn = FALSE)
}

read_sparse_library <- function(gsm_accession) {
  library_dir <- file.path(conversion_dir, "libraries", gsm_accession)
  required <- file.path(library_dir, c("matrix.mtx.gz", "features.tsv.gz", "barcodes.tsv.gz", "conversion_summary.json"))
  if (!all(file.exists(required))) stop("Incomplete sparse library: ", gsm_accession)
  matrix_connection <- gzfile(file.path(library_dir, "matrix.mtx.gz"), open = "rb")
  on.exit(close(matrix_connection), add = TRUE)
  counts <- methods::as(Matrix::readMM(matrix_connection), "dgCMatrix")
  features <- read_gzip_lines(file.path(library_dir, "features.tsv.gz"))
  barcodes <- read_gzip_lines(file.path(library_dir, "barcodes.tsv.gz"))
  if (nrow(counts) != length(features) || ncol(counts) != length(barcodes)) {
    stop("Sparse dimensions do not match features/barcodes: ", gsm_accession)
  }
  if (anyDuplicated(features) || anyDuplicated(barcodes) || any(!nzchar(features)) || any(!nzchar(barcodes))) {
    stop("Duplicate or blank features/barcodes after conversion: ", gsm_accession)
  }
  rownames(counts) <- features
  colnames(counts) <- paste(gsm_accession, barcodes, sep = "__")
  list(counts = counts, source_barcodes = barcodes)
}

inference_started <- FALSE
inference_completed <- FALSE

run_full <- function() {
  parameters <- jsonlite::read_json(parameters_path, simplifyVector = TRUE)
  if (!identical(parameters$execution_mode, "FULL_CORE_PARTICIPANT_LEVEL")) stop("Wrong execution mode")
  if (!identical(parameters$condition_inference_allowed, TRUE)) stop("Full contract does not allow participant-level inference")
  if (!identical(parameters$execution_control$analysis_execution_authorized, FALSE)) {
    stop("Parameters must remain false; exact execution authority is a separate SQ9 record")
  }
  if (!identical(parameters$execution_control$background_allowed, FALSE)) stop("Background execution is forbidden")
  conversion_summary <- jsonlite::read_json(
    file.path(conversion_dir, "M07_FULL_SPARSE_CONVERSION_SUMMARY_v1.json"),
    simplifyVector = TRUE
  )
  if (!identical(conversion_summary$status, "PASS_FULL_CORE_SPARSE_CONVERSION")) stop("Sparse conversion is not a full-core PASS")

  manifest <- utils::read.csv(manifest_path, stringsAsFactors = FALSE, check.names = FALSE)
  dictionary <- utils::read.csv(dictionary_path, stringsAsFactors = FALSE, check.names = FALSE)
  signature <- utils::read.csv(file.path(project_root, parameters$inputs$he_fibro_signature), stringsAsFactors = FALSE, check.names = FALSE)
  manifest <- manifest[order(manifest$analysis_order), , drop = FALSE]
  if (nrow(manifest) != parameters$core$expected_library_count) stop("Core library count mismatch")
  if (length(unique(manifest$participant_alias)) != parameters$core$expected_participant_count) stop("Core participant count mismatch")
  if (sum(manifest$expected_cells_pre_qc) != parameters$core$expected_cells_pre_qc) stop("Core pre-QC cell mismatch")
  if (!all(manifest$analysis_role == "CORE_FOOT_SUPPORTING_EXPLORATORY")) stop("Unexpected manifest analysis role")
  if (!identical(sort(unique(manifest$biological_group)), sort(c("DFU_HEALER", "DFU_NONHEALER")))) stop("Primary groups mismatch")

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  started_at <- Sys.time()
  all_metadata <- list()
  retained_matrices <- list()
  flow_rows <- list()

  for (library_index in seq_len(nrow(manifest))) {
    manifest_row <- manifest[library_index, , drop = FALSE]
    gsm <- manifest_row$gsm_accession
    library_data <- read_sparse_library(gsm)
    counts <- library_data$counts
    if (ncol(counts) != manifest_row$expected_cells_pre_qc) stop("Manifest cell mismatch: ", gsm)
    sce <- SingleCellExperiment::SingleCellExperiment(list(counts = counts))
    mitochondrial <- grepl(parameters$qc$mitochondrial_gene_regex, rownames(sce))
    metrics <- scuttle::perCellQCMetrics(sce, subsets = list(Mito = mitochondrial))
    required_metrics <- c("sum", "detected", "subsets_Mito_percent")
    if (!all(required_metrics %in% colnames(metrics))) stop("Unexpected scuttle QC schema")
    flags <- m07_qc_flags(
      total_counts = metrics$sum,
      detected_features = metrics$detected,
      mitochondrial_percent = metrics$subsets_Mito_percent,
      hard_min_features = parameters$qc$hard_min_detected_features,
      hard_max_mito_percent = parameters$qc$hard_max_mitochondrial_percent,
      nmads = parameters$qc$robust_nmads,
      mad_scale_constant = parameters$qc$mad_scale_constant
    )
    metadata <- data.frame(
      cell_id = colnames(counts),
      source_barcode = library_data$source_barcodes,
      gsm_accession = gsm,
      source_sample_alias = manifest_row$source_sample_alias,
      participant_alias = manifest_row$participant_alias,
      biological_group = manifest_row$biological_group,
      tissue_compartment = manifest_row$tissue_compartment,
      total_counts = metrics$sum,
      detected_features = metrics$detected,
      mitochondrial_percent = metrics$subsets_Mito_percent,
      flags,
      doublet_class = NA_character_,
      doublet_score = NA_real_,
      final_keep = FALSE,
      stringsAsFactors = FALSE,
      check.names = FALSE
    )
    rownames(metadata) <- metadata$cell_id
    qc_indices <- which(metadata$qc_keep_before_doublet)
    if (length(qc_indices) < parameters$doublet$minimum_cells_for_scDblFinder) {
      stop("Too few QC-passing cells for scDblFinder: ", gsm)
    }
    qc_sce <- sce[, qc_indices, drop = FALSE]
    set.seed(parameters$seeds$doublet_base + library_index - 1L)
    qc_sce <- scDblFinder::scDblFinder(
      qc_sce,
      clusters = NULL,
      samples = NULL,
      clustCor = NULL,
      artificialDoublets = NULL,
      knownDoublets = NULL,
      knownUse = "discard",
      dbr = NULL,
      dbr.sd = NULL,
      dbr.per1k = parameters$doublet$dbr_per_1k,
      nfeatures = parameters$doublet$nfeatures,
      dims = parameters$doublet$dims,
      k = NULL,
      removeUnidentifiable = TRUE,
      includePCs = parameters$doublet$include_pcs,
      propRandom = 0,
      propMarkers = 0,
      aggregateFeatures = FALSE,
      returnType = "sce",
      score = "xgb",
      processing = "default",
      metric = "logloss",
      nrounds = 0.25,
      max_depth = 4,
      iter = 3,
      trainingFeatures = NULL,
      unident.th = NULL,
      multiSampleMode = "split",
      threshold = TRUE,
      verbose = FALSE,
      BPPARAM = BiocParallel::SerialParam(progressbar = FALSE)
    )
    if (!all(c("scDblFinder.class", "scDblFinder.score") %in% colnames(SummarizedExperiment::colData(qc_sce)))) {
      stop("scDblFinder output schema mismatch: ", gsm)
    }
    metadata[colnames(qc_sce), "doublet_class"] <- as.character(qc_sce$scDblFinder.class)
    metadata[colnames(qc_sce), "doublet_score"] <- as.numeric(qc_sce$scDblFinder.score)
    metadata$final_keep <- metadata$qc_keep_before_doublet & metadata$doublet_class == "singlet"
    keep_cells <- metadata$cell_id[metadata$final_keep]
    if (!length(keep_cells)) stop("No retained cells: ", gsm)
    retained_matrices[[gsm]] <- counts[, keep_cells, drop = FALSE]
    all_metadata[[gsm]] <- metadata
    flow_rows[[gsm]] <- data.frame(
      gsm_accession = gsm,
      participant_alias = manifest_row$participant_alias,
      biological_group = manifest_row$biological_group,
      input_cells = nrow(metadata),
      hard_low_features = sum(metadata$hard_low_features),
      hard_high_mito = sum(metadata$hard_high_mito),
      adaptive_outlier_any = sum(
        metadata$adaptive_low_counts | metadata$adaptive_high_counts |
          metadata$adaptive_low_features | metadata$adaptive_high_features |
          metadata$adaptive_high_mito
      ),
      qc_pass_before_doublet = sum(metadata$qc_keep_before_doublet),
      doublets = sum(metadata$doublet_class == "doublet", na.rm = TRUE),
      retained_singlets = sum(metadata$final_keep),
      retention_fraction = mean(metadata$final_keep),
      stringsAsFactors = FALSE
    )
  }

  metadata_all <- do.call(rbind, all_metadata)
  rownames(metadata_all) <- metadata_all$cell_id
  if (anyDuplicated(metadata_all$cell_id)) stop("Global cell IDs are not unique")
  union <- m07_union_align(retained_matrices)
  counts <- union$matrix
  retained_metadata <- metadata_all[colnames(counts), , drop = FALSE]
  if (!identical(colnames(counts), retained_metadata$cell_id)) stop("Count/metadata order mismatch")

  # Do not place the outcome in the Seurat object until clustering and annotation finish.
  blinded_metadata <- retained_metadata[, setdiff(names(retained_metadata), "biological_group"), drop = FALSE]
  object <- Seurat::CreateSeuratObject(
    counts = counts,
    assay = "RNA",
    project = "M07_FULL_CORE_OUTCOME_BLINDED",
    min.cells = 0,
    min.features = 0,
    meta.data = blinded_metadata
  )
  object <- Seurat::NormalizeData(
    object, normalization.method = "LogNormalize",
    scale.factor = parameters$normalization$scale_factor, margin = 1, verbose = FALSE
  )
  object <- Seurat::FindVariableFeatures(
    object, selection.method = parameters$clustering$variable_feature_method,
    nfeatures = parameters$clustering$variable_features, verbose = FALSE
  )
  variable_features <- Seurat::VariableFeatures(object)
  if (length(variable_features) < 3L) stop("Too few variable features")
  object <- Seurat::ScaleData(object, features = variable_features, vars.to.regress = NULL, verbose = FALSE)
  npcs <- min(parameters$clustering$npcs, length(variable_features) - 1L, ncol(object) - 1L)
  if (npcs < 2L) stop("Too few PCs available")
  set.seed(parameters$seeds$pca)
  object <- Seurat::RunPCA(
    object, assay = "RNA", features = variable_features, npcs = npcs,
    rev.pca = FALSE, weight.by.var = TRUE, verbose = FALSE,
    ndims.print = 1:5, nfeatures.print = 10, reduction.name = "pca",
    reduction.key = "PC_", seed.use = parameters$seeds$pca, approx = TRUE
  )
  neighbor_dims <- seq_len(min(parameters$clustering$neighbor_pcs, npcs))
  object <- Seurat::FindNeighbors(
    object, reduction = "pca", dims = neighbor_dims,
    k.param = parameters$clustering$k_neighbors, compute.SNN = TRUE,
    prune.SNN = parameters$clustering$prune_snn, nn.method = "rann",
    nn.eps = 0, verbose = FALSE, graph.name = c("RNA_nn", "RNA_snn"),
    l2.norm = FALSE, cache.index = FALSE
  )
  set.seed(parameters$seeds$clustering)
  object <- Seurat::FindClusters(
    object, graph.name = "RNA_snn", cluster.name = "seurat_clusters",
    modularity.fxn = 1, initial.membership = NULL, node.sizes = NULL,
    resolution = parameters$clustering$resolution, algorithm = parameters$clustering$clustering_algorithm,
    n.start = parameters$clustering$n_start, n.iter = parameters$clustering$n_iter,
    random.seed = parameters$seeds$clustering, group.singletons = TRUE,
    temp.file.location = NULL, edge.file.name = NULL, verbose = FALSE
  )
  set.seed(parameters$seeds$umap)
  object <- Seurat::RunUMAP(
    object, reduction = "pca", dims = neighbor_dims,
    reduction.name = "umap", reduction.key = "UMAP_", assay = "RNA",
    seed.use = parameters$seeds$umap, n.neighbors = parameters$clustering$umap_neighbors,
    n.components = 2L, metric = parameters$clustering$umap_metric,
    n.epochs = NULL, learning.rate = 1, min.dist = parameters$clustering$umap_min_dist,
    spread = 1, set.op.mix.ratio = 1, local.connectivity = 1,
    repulsion.strength = 1, negative.sample.rate = 5, a = NULL, b = NULL,
    uwot.sgd = FALSE, umap.method = "uwot", return.model = FALSE,
    densmap = FALSE, dens.lambda = 2, dens.frac = 0.3, dens.var.shift = 0.1,
    verbose = FALSE
  )

  log_expression <- SeuratObject::LayerData(object, assay = "RNA", layer = "data")
  clusters <- as.character(object$seurat_clusters)
  annotation <- m07_cluster_marker_scores(
    log_expression = log_expression,
    clusters = clusters,
    dictionary = dictionary,
    min_markers = parameters$annotation$minimum_markers_available,
    min_margin = parameters$annotation$minimum_score_margin
  )
  assignment_map <- setNames(annotation$assignments$assigned_label, annotation$assignments$cluster)
  display_map <- setNames(annotation$assignments$assigned_display_label, annotation$assignments$cluster)
  object$marker_assigned_label <- unname(assignment_map[clusters])
  object$marker_assigned_display_label <- unname(display_map[clusters])
  if (any(is.na(object$marker_assigned_label))) stop("Missing annotation assignment")
  object$biological_group <- retained_metadata[rownames(object[[]]), "biological_group"]
  if (any(is.na(object$biological_group))) stop("Post-annotation outcome join failed")

  final_metadata <- object[[]]
  final_metadata$cell_id <- rownames(final_metadata)
  final_metadata$seurat_cluster <- as.character(final_metadata$seurat_clusters)
  final_metadata <- final_metadata[, c(
    "cell_id", "source_barcode", "gsm_accession", "source_sample_alias",
    "participant_alias", "biological_group", "tissue_compartment", "total_counts",
    "detected_features", "mitochondrial_percent", "doublet_class", "doublet_score",
    "seurat_cluster", "marker_assigned_label", "marker_assigned_display_label"
  )]

  raw_pseudobulk <- m07_pseudobulk_counts(
    counts = counts,
    participant = final_metadata$participant_alias,
    cell_type = final_metadata$marker_assigned_label
  )
  pseudobulk <- m07_attach_pseudobulk_metadata(raw_pseudobulk, final_metadata)
  if (sum(pseudobulk$counts) != sum(counts)) stop("Pseudobulk raw-count conservation failed")
  eligibility <- m07_celltype_eligibility(
    pseudobulk,
    min_cells = parameters$inference$min_cells_per_participant_cell_type,
    min_total_counts = parameters$inference$min_total_counts_per_participant_cell_type,
    min_participants_per_group = parameters$inference$min_eligible_participants_per_group
  )
  inference_started <<- TRUE
  de <- m07_run_edger_celltypes(
    pseudobulk,
    eligibility,
    filter_min_count = parameters$inference$filter_by_expr$min_count,
    filter_min_total_count = parameters$inference$filter_by_expr$min_total_count,
    filter_large_n = parameters$inference$filter_by_expr$large_n,
    filter_min_prop = parameters$inference$filter_by_expr$min_prop
  )
  inference_completed <<- TRUE
  abundance <- m07_participant_abundance(final_metadata)
  he_scores <- m07_he_fibro_participant_scores(pseudobulk, signature$gene)

  marker_coverage <- aggregate(
    gene ~ canonical_label + canonical_display_label + classification_level,
    data = dictionary,
    FUN = function(value) length(intersect(unique(value), rownames(counts)))
  )
  names(marker_coverage)[names(marker_coverage) == "gene"] <- "markers_present"
  marker_total <- aggregate(gene ~ canonical_label, data = dictionary, FUN = function(value) length(unique(value)))
  names(marker_total)[2L] <- "markers_total"
  marker_coverage <- merge(marker_coverage, marker_total, by = "canonical_label", all.x = TRUE)
  marker_coverage$coverage_fraction <- marker_coverage$markers_present / marker_coverage$markers_total

  signature_genes_present <- intersect(unique(signature$gene), rownames(log_expression))
  cluster_signature <- data.frame(cluster = sort(unique(clusters)), stringsAsFactors = FALSE)
  cluster_signature$signature_genes_prespecified <- length(unique(signature$gene))
  cluster_signature$signature_genes_present <- length(signature_genes_present)
  cluster_signature$mean_signature_log_expression <- vapply(
    cluster_signature$cluster,
    function(cluster) mean(Matrix::rowMeans(log_expression[signature_genes_present, clusters == cluster, drop = FALSE])),
    numeric(1)
  )
  cluster_signature$assigned_label <- assignment_map[cluster_signature$cluster]
  cluster_signature$outcome_used_to_define_state <- FALSE

  umap <- as.data.frame(SeuratObject::Embeddings(object, reduction = "umap"))
  umap$cell_id <- rownames(umap)
  umap$seurat_cluster <- object$seurat_clusters
  umap$marker_assigned_label <- object$marker_assigned_label
  umap$gsm_accession <- object$gsm_accession
  umap$participant_alias <- object$participant_alias
  umap$biological_group <- object$biological_group

  utils::write.csv(do.call(rbind, flow_rows), file.path(output_dir, "M07_FULL_LIBRARY_QC_FLOW_v1.csv"), row.names = FALSE, quote = TRUE)
  write_csv_gz(metadata_all, file.path(output_dir, "M07_FULL_ALL_CELL_QC_METADATA_v1.csv.gz"))
  write_csv_gz(final_metadata, file.path(output_dir, "M07_FULL_RETAINED_CELL_METADATA_v1.csv.gz"))
  utils::write.csv(marker_coverage, file.path(output_dir, "M07_FULL_MARKER_COVERAGE_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(annotation$scores, file.path(output_dir, "M07_FULL_CLUSTER_ANNOTATION_SCORES_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(annotation$assignments, file.path(output_dir, "M07_FULL_CLUSTER_LABELS_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(cluster_signature, file.path(output_dir, "M07_FULL_HE_FIBRO_CLUSTER_SIGNATURE_VALIDATION_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(eligibility$metadata, file.path(output_dir, "M07_FULL_PSEUDOBULK_ELIGIBILITY_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(eligibility$cell_types, file.path(output_dir, "M07_FULL_CELLTYPE_MODEL_ELIGIBILITY_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(de$models, file.path(output_dir, "M07_FULL_EDGER_MODEL_STATUS_v1.csv"), row.names = FALSE, quote = TRUE)
  write_csv_gz(de$results, file.path(output_dir, "M07_FULL_PARTICIPANT_PSEUDOBULK_DE_v1.csv.gz"))
  utils::write.csv(abundance$participant, file.path(output_dir, "M07_FULL_PARTICIPANT_CELLTYPE_ABUNDANCE_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(abundance$summary, file.path(output_dir, "M07_FULL_CELLTYPE_ABUNDANCE_SUMMARY_v1.csv"), row.names = FALSE, quote = TRUE)
  utils::write.csv(he_scores, file.path(output_dir, "M07_FULL_HE_FIBRO_PARTICIPANT_SCORES_v1.csv"), row.names = FALSE, quote = TRUE)
  write_csv_gz(umap, file.path(output_dir, "M07_FULL_UMAP_COORDINATES_v1.csv.gz"))
  saveRDS(pseudobulk, file.path(output_dir, "M07_FULL_PSEUDOBULK_COUNTS_v1.rds"), compress = "gzip")
  saveRDS(object, file.path(output_dir, "M07_FULL_SEURAT_OBJECT_v1.rds"), compress = "gzip")

  qc_plot <- ggplot2::ggplot(metadata_all, ggplot2::aes(x = detected_features, y = total_counts, color = final_keep)) +
    ggplot2::geom_point(alpha = 0.2, size = 0.25) + ggplot2::scale_x_log10() + ggplot2::scale_y_log10() +
    ggplot2::facet_wrap(~gsm_accession, scales = "free") +
    ggplot2::labs(title = "M07 full core: per-library QC", color = "Retained") + ggplot2::theme_bw(base_size = 8)
  ggplot2::ggsave(file.path(output_dir, "M07_FULL_QC_DISTRIBUTIONS_v1.pdf"), qc_plot, width = 12, height = 10, units = "in")
  cluster_plot <- Seurat::DimPlot(object, reduction = "umap", group.by = "marker_assigned_display_label", label = TRUE, repel = TRUE) +
    ggplot2::ggtitle("M07 core foot skin: outcome-blinded annotation")
  ggplot2::ggsave(file.path(output_dir, "M07_FULL_UMAP_CELL_TYPES_v1.pdf"), cluster_plot, width = 11, height = 8, units = "in")
  abundance_plot <- ggplot2::ggplot(abundance$participant, ggplot2::aes(x = biological_group, y = participant_cell_fraction, color = biological_group)) +
    ggplot2::geom_boxplot(outlier.shape = NA, width = 0.55) + ggplot2::geom_jitter(width = 0.12, height = 0, size = 1.2) +
    ggplot2::facet_wrap(~cell_type, scales = "free_y") + ggplot2::labs(x = NULL, y = "Participant cell fraction", title = "Participant-level cell-type composition (exploratory)") +
    ggplot2::theme_bw(base_size = 8) + ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 35, hjust = 1), legend.position = "none")
  ggplot2::ggsave(file.path(output_dir, "M07_FULL_PARTICIPANT_CELLTYPE_ABUNDANCE_v1.pdf"), abundance_plot, width = 12, height = 10, units = "in")
  if (nrow(de$results)) {
    de_plot_data <- de$results
    de_plot_data$minus_log10_global_fdr <- -log10(pmax(de_plot_data$global_FDR, .Machine$double.xmin))
    de_plot <- ggplot2::ggplot(de_plot_data, ggplot2::aes(x = logFC, y = minus_log10_global_fdr, color = global_FDR_significant_0_05)) +
      ggplot2::geom_point(alpha = 0.45, size = 0.55) + ggplot2::facet_wrap(~cell_type, scales = "free") +
      ggplot2::labs(x = "log2 fold change: nonhealer minus healer", y = "-log10 global BH FDR", color = "Global FDR < 0.05", title = "Participant-level pseudobulk differential expression") +
      ggplot2::theme_bw(base_size = 8)
  } else {
    de_plot <- ggplot2::ggplot() + ggplot2::annotate("text", x = 0, y = 0, label = "Valid null: no eligible gene-by-cell-type tests") + ggplot2::theme_void()
  }
  ggplot2::ggsave(file.path(output_dir, "M07_FULL_PSEUDOBULK_DE_OVERVIEW_v1.pdf"), de_plot, width = 12, height = 9, units = "in")

  writeLines(capture.output(sessionInfo()), file.path(output_dir, "M07_FULL_SESSIONINFO_v1.txt"), useBytes = TRUE)
  garbage <- gc()
  elapsed <- as.numeric(difftime(Sys.time(), started_at, units = "secs"))
  summary <- list(
    schema_version = "1.0",
    module_id = "M07_SINGLE_CELL_CONTEXT",
    completed_at = format(Sys.time(), tz = "UTC", usetz = TRUE),
    status = "PASS_FULL_CORE_PARTICIPANT_LEVEL_ANALYSIS_CANDIDATE",
    analysis_role = "SUPPORTING_EXPLORATORY_VALUE_ADD",
    mode = "FULL_CORE_PARTICIPANT_LEVEL",
    input_libraries = nrow(manifest),
    input_participants = length(unique(manifest$participant_alias)),
    healer_participants = length(unique(manifest$participant_alias[manifest$biological_group == "DFU_HEALER"])),
    nonhealer_participants = length(unique(manifest$participant_alias[manifest$biological_group == "DFU_NONHEALER"])),
    input_cells = nrow(metadata_all),
    retained_singlets = ncol(counts),
    retained_fraction = ncol(counts) / nrow(metadata_all),
    union_features = nrow(counts),
    clusters = length(unique(clusters)),
    assigned_clusters = sum(annotation$assignments$assigned_label != "UNRESOLVED"),
    unresolved_clusters = sum(annotation$assignments$assigned_label == "UNRESOLVED"),
    pseudobulk_columns = ncol(pseudobulk$counts),
    raw_count_conservation = paste0(sum(pseudobulk$counts), "/", sum(counts)),
    eligible_cell_types = sum(eligibility$cell_types$model_eligible),
    tested_gene_celltype_pairs = nrow(de$results),
    globally_significant_gene_celltype_pairs = sum(de$results$global_FDR_significant_0_05),
    participant_level_de_performed = TRUE,
    cell_level_group_test_performed = FALSE,
    library_level_group_test_performed = FALSE,
    abundance_inference_performed = FALSE,
    clinical_group_used_for_clustering_or_annotation = FALSE,
    contrast = "DFU_NONHEALER_MINUS_DFU_HEALER",
    positive_logfc_rule = "higher_in_nonhealer",
    source_data_modified = FALSE,
    gse199939_used_in_core = FALSE,
    elapsed_seconds = elapsed,
    gc_max_used_cells = max(garbage[, "max used"]),
    next_gate = "FULL_CORE_POST_RUN_VALIDATION"
  )
  jsonlite::write_json(summary, file.path(output_dir, "M07_FULL_ANALYSIS_SUMMARY_v1.json"), auto_unbox = TRUE, pretty = TRUE)
  cat(sprintf("M07_FULL_STATUS=%s\n", summary$status))
  cat(sprintf("INPUT_CELLS=%d\n", summary$input_cells))
  cat(sprintf("RETAINED_SINGLETS=%d\n", summary$retained_singlets))
  cat(sprintf("ELIGIBLE_CELL_TYPES=%d\n", summary$eligible_cell_types))
  cat(sprintf("GLOBAL_FDR_SIGNIFICANT=%d\n", summary$globally_significant_gene_celltype_pairs))
  invisible(summary)
}

status <- tryCatch(
  {
    run_full()
    0L
  },
  error = function(error) {
    if (dir.exists(output_dir)) {
      failure_path <- file.path(output_dir, "M07_FULL_ANALYSIS_FAILURE_v1.json")
      if (!file.exists(failure_path)) {
        jsonlite::write_json(
          list(
            schema_version = "1.0",
            module_id = "M07_SINGLE_CELL_CONTEXT",
            failed_at = format(Sys.time(), tz = "UTC", usetz = TRUE),
            status = "FAILED_PRESERVED_NO_OVERWRITE",
            message = conditionMessage(error),
            partial_output_preserved = TRUE,
            participant_level_inference_started = inference_started,
            participant_level_inference_completed = inference_completed,
            cell_level_group_test_performed = FALSE
          ),
          failure_path,
          auto_unbox = TRUE,
          pretty = TRUE
        )
      }
    }
    message("M07_FULL_ANALYSIS_FAILURE: ", conditionMessage(error))
    1L
  }
)
quit(status = status, save = "no")
