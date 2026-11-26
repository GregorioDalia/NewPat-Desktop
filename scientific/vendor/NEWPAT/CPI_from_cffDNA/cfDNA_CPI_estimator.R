#!/usr/bin/env Rscript
# Prenatal CPI model from NEWPAT 867a446, including maternal/fetal HOM sites and coverage filters.
# Reuse invariant CPI calculations and identical threshold selections; retain every output row.
# NewPat schedules independent pairs, cutoffs or threshold intervals within one
# worker budget and retains the order of the scientific reductions.

suppressPackageStartupMessages({
  library(dplyr)
  library(readxl)
  library(ggplot2)
  library(patchwork)
  library(argparse)
  library(stringr)
  library(tidyr)
})

source(Sys.getenv("NIPAT_PARALLEL_HELPER",
                  unset = "/opt/nipat/lib/nipat_scientific/parallel.R"))
source(Sys.getenv("NIPAT_PLOTS_HELPER", unset = "/opt/nipat/lib/nipat_scientific/plots.R"))

source(Sys.getenv("NIPAT_SETTINGS_HELPER", unset="/opt/nipat/lib/nipat_scientific/settings.R"))
nipat_cfg <- nipat_settings("cpi")

parser <- ArgumentParser()

parser$add_argument("--pileup_dir",    required=TRUE)
parser$add_argument("--out_dir",       required=TRUE)
parser$add_argument("--pairs",         required=TRUE)
parser$add_argument("--mother_prefix", required=TRUE)
parser$add_argument("--father_prefix", required=TRUE)
parser$add_argument("--popfreq",       required=TRUE)

parser$add_argument("--cutoff_map", required=FALSE,
                    help='named marker panels: label=/path/panel.tsv,...')
parser$add_argument("--markers", required=FALSE)
parser$add_argument("--err_const", default=NULL,
                    help="Explicit override for the detected marker type")
parser$add_argument("--err_const_snp", default=NULL)
parser$add_argument("--err_const_dnp", default=NULL)
parser$add_argument("--min_fetal_reads", type="double", default=NULL)
parser$add_argument("--min_fetal_percent", type="double", default=NULL)
parser$add_argument("--include_homozygous_child", choices=c("TRUE", "FALSE"), default=NULL)
parser$add_argument("--min_coverage", type="double", default=NULL)
parser$add_argument("--max_other_fraction", type="double", default=NULL)
args <- parser$parse_args()
args$err_const_snp <- if (is.null(args$err_const_snp)) nipat_cfg$err_const_snp else args$err_const_snp
args$err_const_dnp <- if (is.null(args$err_const_dnp)) nipat_cfg$err_const_dnp else args$err_const_dnp
# Explicit native filter arguments select the requested combination. A run
# without native filter arguments uses the settings supplied by the desktop.
if (!is.null(args$min_fetal_reads) || !is.null(args$min_fetal_percent)) {
  min_fetal_reads <- args$min_fetal_reads
  min_fetal_percent <- args$min_fetal_percent
} else {
  min_fetal_reads <- nipat_cfg$min_fetal_reads
  min_fetal_percent <- nipat_cfg$min_fetal_percent
}
if (is.null(min_fetal_reads) && is.null(min_fetal_percent)) min_fetal_reads <- 2L
if (!is.null(min_fetal_reads)) {
  if (!is.finite(min_fetal_reads) || min_fetal_reads < 1 ||
      min_fetal_reads != floor(min_fetal_reads) || min_fetal_reads > .Machine$integer.max)
    stop("--min_fetal_reads must be a positive integer within the R integer range")
  min_fetal_reads <- as.integer(min_fetal_reads)
}
if (!is.null(min_fetal_percent) && (!is.finite(min_fetal_percent) ||
    min_fetal_percent <= 0 || min_fetal_percent > 100))
  stop("--min_fetal_percent must be a finite number in (0, 100]")
if (!is.null(args$include_homozygous_child))
  nipat_cfg$include_homozygous_child <- args$include_homozygous_child == "TRUE"
if (!is.null(args$min_coverage)) nipat_cfg$min_coverage <- args$min_coverage
if (!is.null(args$max_other_fraction)) nipat_cfg$other_fraction_max <- args$max_other_fraction
min_coverage <- nipat_cfg$min_coverage
if (!is.null(min_coverage) && (!is.finite(min_coverage) || min_coverage < 1 ||
    min_coverage != floor(min_coverage) || min_coverage > .Machine$integer.max))
  stop("--min_coverage must be a positive integer within the R integer range")
if (!is.null(min_coverage)) nipat_cfg$min_coverage <- as.integer(min_coverage)
if (!is.finite(nipat_cfg$other_fraction_max) || nipat_cfg$other_fraction_max < 0 ||
    nipat_cfg$other_fraction_max > 1) stop("--max_other_fraction must be between 0 and 1")
coverage_floor <- if (is.null(min_coverage)) 0 else min_coverage
curve_start <- if (is.null(min_fetal_reads)) 1L else min_fetal_reads
message("Minimum fetal reads: ", if (is.null(min_fetal_reads)) "NULL" else min_fetal_reads)
message("Minimum fetal-read percentage: ",
        if (is.null(min_fetal_percent)) "NULL" else paste0(min_fetal_percent, "%"))
if (!dir.exists(args$out_dir)) dir.create(args$out_dir, recursive=TRUE)
plots_dir <- file.path(args$out_dir, "plots")
dir.create(plots_dir, recursive=TRUE, showWarnings=FALSE)
parts <- lapply(strsplit(args$pairs, ",", fixed=TRUE)[[1]], function(z) trimws(strsplit(z, ":", fixed=TRUE)[[1]]))
if (!length(parts) || any(lengths(parts) != 2L) || any(!nzchar(unlist(parts)))) stop("Invalid mother:father pairs")
keys <- vapply(parts, paste, collapse=":", FUN.VALUE="")
if (anyDuplicated(tolower(keys))) stop("Duplicate mother:father pairs")
coppie <- data.frame(mamma=vapply(parts, `[`, "", 1), papa=vapply(parts, `[`, "", 2))
if (any(tolower(paste0(args$mother_prefix, coppie$mamma)) ==
        tolower(paste0(args$father_prefix, coppie$papa))))
  stop("Mother and father must refer to distinct input samples")
if (any(!grepl("^[A-Za-z0-9_.-]+$", unlist(parts)))) stop("Invalid sample identifiers")
if (anyDuplicated(tolower(paste0("Mother", coppie$mamma, "-Father", coppie$papa))))
  stop("Distinct pairs would overwrite the same result")

## Read coordinates from the frequency table and use them in every join.
if (!file.exists(args$popfreq)) stop("popfreq file not found")
population <- nipat_read_marker_table(args$popfreq, header=TRUE, sep="\t",
                         stringsAsFactors=FALSE, check.names=FALSE,
                         quote="", comment.char="", colClasses=c(chr="character"))

marker_type <- function(x, label) {
  has_snp <- "pos" %in% names(x)
  has_dnp <- all(c("pos1", "pos2") %in% names(x))
  if (has_snp == has_dnp) {
    stop(label, ": use either pos for SNPs or pos1 and pos2 for DNPs")
  }
  if (has_snp) "SNP" else "DNP"
}

has_markers <- !is.null(args$markers) && nzchar(trimws(args$markers))
marker_list <- NULL
marker <- marker_type(population, "population frequencies")
if (has_markers) {
  # DNPcall lists have five columns without a header; SNPcall lists have four.
  # A header is also accepted, with lower- or upper-case allele column names.
  marker_list <- nipat_read_marker_table(args$markers, chromosome_column="V1", header=FALSE, sep="", quote="",
                            comment.char="", colClasses="character",
                            stringsAsFactors=FALSE, check.names=FALSE)
  marker_columns <- switch(as.character(ncol(marker_list)),
    "4" = c("chr", "pos", "REF", "ALT"),
    "5" = c("chr", "pos1", "pos2", "REF", "ALT"),
    stop("Marker list must contain four SNP columns or five DNP columns")
  )
  first_row <- unlist(marker_list[1, ], use.names=FALSE)
  if (identical(tolower(first_row), tolower(marker_columns))) {
    marker_list <- marker_list[-1, , drop=FALSE]
  }
  names(marker_list) <- marker_columns
  if (!nrow(marker_list)) stop("Marker list is empty")
  marker <- marker_type(marker_list, "marker list")
  if (marker_type(population, "population frequencies") != marker) {
    stop("Population frequency coordinates do not match the marker list format")
  }
}
message("Panel: ", if (has_markers) args$markers else "all calling-output sites")
site_columns <- if (marker == "SNP") c("chr", "pos") else c("chr", "pos1", "pos2")
message("Marker type: ", marker)

# Select the constant for the detected marker type.
read_error_constant <- function(value, option) {
  if (is.null(value)) return(NULL)
  number <- suppressWarnings(as.numeric(value))
  if (length(number) != 1L || !is.finite(number) || number <= 0 || number > 1) {
    stop(option, " must be a finite number in (0, 1], for example 1e-04")
  }
  number
}

error_constants <- list(
  SNP = read_error_constant(args$err_const_snp, "--err_const_snp"),
  DNP = read_error_constant(args$err_const_dnp, "--err_const_dnp")
)
err_const <- error_constants[[marker]]
if (!is.null(args$err_const)) err_const <- read_error_constant(args$err_const, "--err_const")
nipat_cfg$err_const_snp <- error_constants$SNP
nipat_cfg$err_const_dnp <- error_constants$DNP
nipat_cfg[[paste0("err_const_", tolower(marker))]] <- err_const
nipat_cfg[c("min_fetal_reads", "min_fetal_percent")] <- list(min_fetal_reads, min_fetal_percent)
message("Mismatch constant used for ", marker, ": ", sprintf("%.17g", err_const))

site_key <- function(x) {
  do.call(paste, c(unname(as.list(x[site_columns])), sep="\t"))
}

check_sites <- function(x, required, label) {
  missing <- setdiff(required, names(x))
  if (length(missing)) stop(label, ": missing columns ", paste(missing, collapse=", "))
  if (anyNA(x[site_columns]) || anyDuplicated(site_key(x))) {
    stop(label, ": missing or duplicate coordinates")
  }
  if (any(!nzchar(trimws(as.character(x$chr))))) stop(label, ": empty chromosome")
  for (column in setdiff(site_columns, "chr")) {
    values <- suppressWarnings(as.numeric(x[[column]]))
    if (any(!is.finite(values) | values < 1 | values != floor(values)))
      stop(label, ": coordinates must be positive integers")
  }
}

if (has_markers) {
  check_sites(marker_list, marker_columns, "marker list")
  for (column in setdiff(site_columns, "chr")) {
    position <- suppressWarnings(as.numeric(marker_list[[column]]))
    if (any(!is.finite(position) | position < 1 | position != floor(position))) {
      stop("Marker list positions must be positive integers")
    }
    marker_list[[column]] <- position
  }
  marker_list$REF <- toupper(marker_list$REF)
  marker_list$ALT <- toupper(marker_list$ALT)
  allele_pattern <- if (marker == "SNP") "^[ACGT]$" else "^[ACGT]{2}$"
  if (anyNA(marker_list[c("REF", "ALT")]) ||
      any(!grepl(allele_pattern, marker_list$REF) |
          !grepl(allele_pattern, marker_list$ALT) |
          marker_list$REF == marker_list$ALT)) {
    stop("Marker list must contain distinct REF and ALT alleles for the selected marker type")
  }
  # Check again after converting positions, so equivalent coordinates cannot repeat.
  check_sites(marker_list, marker_columns, "marker list")
  
}

check_sites(population, c(site_columns, "Ref_f.pop", "Alt_f.pop"),
            "population frequencies")
population$chr <- as.character(population$chr)
if (has_markers) {
  frequency_index <- match(site_key(marker_list), site_key(population))
  if (anyNA(frequency_index)) {
    missing_sites <- site_key(marker_list)[is.na(frequency_index)]
    stop("Missing population frequencies for marker-list sites: ",
         paste(head(missing_sites, 5), collapse=", "))
  }
  population <- population[frequency_index, , drop=FALSE]
  if (all(c("REF", "ALT") %in% names(population))) {
    if (anyNA(population[c("REF", "ALT")]) ||
        any(toupper(population$REF) != marker_list$REF |
            toupper(population$ALT) != marker_list$ALT)) {
      stop("Population frequency alleles differ from the marker list")
    }
  }
}
population$Ref_f.pop <- as.numeric(gsub(",", ".", population$Ref_f.pop))
population$Alt_f.pop <- as.numeric(gsub(",", ".", population$Alt_f.pop))
if (any(!is.finite(population$Ref_f.pop) | !is.finite(population$Alt_f.pop) |
        population$Ref_f.pop <= 0 | population$Ref_f.pop > 1 |
        population$Alt_f.pop <= 0 | population$Alt_f.pop > 1)) {
  stop("Population frequencies must be finite and in (0, 1]")
}

# Keep allele columns outside the join to avoid REF and ALT suffix conflicts.
PopFreqDNPs <- population[, c(site_columns, "Ref_f.pop", "Alt_f.pop"), drop=FALSE]

read_calls <- function(path) {
  x <- nipat_read_marker_table(path, header=TRUE, check.names=FALSE, stringsAsFactors=FALSE,
                  colClasses=c(chr="character", REF="character", ALT="character"))
  if (marker_type(x, path) != marker) stop(path, ": format differs from population frequencies")
  check_sites(x, c(site_columns, "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count"), path)
  x$chr <- as.character(x$chr)
  if (has_markers) {
    # Restrict all downstream calculations to the supplied marker list.
    x <- x[site_key(x) %in% site_key(marker_list), , drop=FALSE]
    j <- match(site_key(x), site_key(marker_list))
    if (anyNA(x[c("REF", "ALT")]) ||
        any(toupper(x$REF) != marker_list$REF[j] |
            toupper(x$ALT) != marker_list$ALT[j])) {
      stop(path, ": alleles differ from the marker list")
    }
  }
  expected_length <- if (marker == "SNP") 1L else 2L
  if (anyNA(x[c("REF", "ALT")]) ||
      any(nchar(x$REF) != expected_length | nchar(x$ALT) != expected_length |
          toupper(x$REF) == toupper(x$ALT))) {
    stop(path, ": invalid REF or ALT alleles")
  }
  # Older DNP frequency tables have no REF or ALT columns.
  if (all(c("REF", "ALT") %in% names(population))) {
    j <- match(site_key(x), site_key(population))
    present <- which(!is.na(j))
    if (anyNA(population[j[present], c("REF", "ALT"), drop=FALSE])) {
      stop("Population frequencies contain missing alleles")
    }
    if (any(toupper(x$REF[present]) != toupper(population$REF[j[present]]) |
            toupper(x$ALT[present]) != toupper(population$ALT[j[present]]))) {
      stop(path, ": alleles differ from population frequencies")
    }
  }
  pattern <- if (marker == "SNP") "^[ACGT]$" else "^[ACGT]{2}$"
  if (any(!grepl(pattern, toupper(x$REF)) | !grepl(pattern, toupper(x$ALT))))
    stop(path, ": alleles must contain only A/C/G/T")
  for (column in c("N_REF", "N_ALT", "N_Other"))
    x[[column]] <- suppressWarnings(as.numeric(x[[column]]))
  counts <- as.matrix(x[c("N_REF", "N_ALT", "N_Other")])
  if (anyNA(counts) || any(!is.finite(counts) | counts < 0 | counts != floor(counts)))
    stop(path, ": counts must be finite nonnegative integers")
  allowed_missing <- is.na(x$total_count) & rowSums(counts) == 0
  total <- suppressWarnings(as.numeric(x$total_count))
  if (any(is.na(total) & !allowed_missing) ||
      any(!is.finite(total[!allowed_missing]) | total[!allowed_missing] < 0 |
          total[!allowed_missing] != floor(total[!allowed_missing])))
    stop(path, ": invalid total_count")
  if (any(total[!allowed_missing] != rowSums(counts)[!allowed_missing]))
    stop(path, ": total_count differs from REF + ALT + Other")
  x$total_count <- total
  x
}

check_pair <- function(mother, father) {
  j <- match(site_key(mother), site_key(father))
  present <- which(!is.na(j))
  if (any(toupper(mother$REF[present]) != toupper(father$REF[j[present]]) |
          toupper(mother$ALT[present]) != toupper(father$ALT[j[present]]))) {
    stop("Mother and father have different REF or ALT alleles at shared coordinates")
  }
}

# Each named panel needs coordinates compatible with the selected marker type.
if (has_markers && !is.null(args$cutoff_map) && nzchar(args$cutoff_map))
  stop("Choose --markers or --cutoff_map")
if (has_markers) {
  cutoff_df <- data.frame(Cutoff=args$markers, Path=args$markers)
  cutoff_panels <- list(marker_list)
  has_cutoffs <- TRUE
} else if (!is.null(args$cutoff_map) && nzchar(args$cutoff_map)) {
  panels <- lapply(strsplit(args$cutoff_map, ",", fixed=TRUE)[[1]], function(z) {
    kv <- strsplit(z, "=", fixed=TRUE)[[1]]
    if (length(kv) == 1L) list(Cutoff=kv[1], Path=kv[1]) else {
      if (length(kv) != 2L || any(!nzchar(kv))) stop("Invalid cutoff_map entry")
      list(Cutoff=kv[1], Path=kv[2])
    }
  })
  cutoff_df <- do.call(rbind, lapply(panels, as.data.frame))
  if (anyDuplicated(cutoff_df$Cutoff)) stop("Duplicate cutoff label")
  cutoff_panels <- lapply(cutoff_df$Path, function(path) {
    x <- nipat_read_marker_table(path, header=TRUE, sep="\t", check.names=FALSE, stringsAsFactors=FALSE,
                    colClasses=c(chr="character"))
    if (marker_type(x, path) != marker) stop("Marker panel differs from population type")
    check_sites(x, site_columns, path)
    x$chr <- as.character(x$chr)
    for (key in setdiff(site_columns, "chr")) {
      x[[key]] <- suppressWarnings(as.numeric(x[[key]]))
      if (any(!is.finite(x[[key]]) | x[[key]] < 1 | x[[key]] != floor(x[[key]]))) stop("Invalid panel coordinates")
    }
    check_sites(x, site_columns, path)
    if (anyNA(match(site_key(x), site_key(population)))) stop("Missing population frequencies for marker panel")
    x
  })
  has_cutoffs <- TRUE
} else {
  cutoff_df <- data.frame(Cutoff="ALL", Path=NA_character_)
  cutoff_panels <- list(NULL)
  has_cutoffs <- FALSE
}
# Cache raw tables by path so shared parents are read/validated only once.
call_paths <- unique(c(file.path(args$pileup_dir, paste0(args$mother_prefix, coppie$mamma, ".txt")),
                       file.path(args$pileup_dir, paste0(args$father_prefix, coppie$papa, ".txt"))))
calls_cache <- setNames(lapply(call_paths, read_calls), call_paths)
for (x in calls_cache) {
  for (panel in cutoff_panels) {
    if (is.null(panel) || !all(c("REF", "ALT") %in% names(panel))) next
    j <- match(site_key(x), site_key(panel)); present <- which(!is.na(j))
    if (any(toupper(x$REF[present]) != toupper(panel$REF[j[present]]) |
            toupper(x$ALT[present]) != toupper(panel$ALT[j[present]]))) stop("Calling-output alleles differ from panel")
  }
}

nipat_write_settings("cpi", nipat_cfg, args$out_dir)

compute_madre_info <- function(madre_df) {
  info <- madre_df %>%
    dplyr::filter(ratio_Ref_mother >= nipat_cfg$homozygous_ref_min |
                  ratio_Ref_mother <= nipat_cfg$homozygous_alt_max) %>%
    dplyr::mutate(
      fetal_reads = ifelse(ratio_Ref_mother >= nipat_cfg$homozygous_ref_min, Alt_mother, Ref_mother),
      fetal_percent = 100 * fetal_reads / (Ref_mother + Alt_mother)
    )
  if (!is.null(min_fetal_reads)) info <- dplyr::filter(info, fetal_reads >= min_fetal_reads)
  if (!is.null(min_fetal_percent)) info <- dplyr::filter(info, fetal_percent >= min_fetal_percent)
  info
}

## core: compute cpi for one list (or all sites if dnp_list is NULL)
run_CPI_iteration <- function(madre_df, padre_df, dnp_list, cutoff_label, err_const) {
  if (!is.null(dnp_list)) {
    madre <- madre_df %>% dplyr::semi_join(dnp_list, by=site_columns)
    padre <- padre_df %>% dplyr::semi_join(dnp_list, by=site_columns)
  } else {
    madre <- madre_df
    padre <- padre_df
  }

  madre_info <- compute_madre_info(madre)
  madre_hom <- madre[FALSE, , drop=FALSE]
  if (nipat_cfg$include_homozygous_child) {
    madre_hom <- dplyr::filter(madre, (Ref_mother > 0 & Alt_mother == 0) |
                                     (Alt_mother > 0 & Ref_mother == 0))
  }

  # The allele needed from the father is maternal for HOM and non-maternal for HET.
  calculate_PI <- function(mother_sites, child_type) {
    maternal_ref <- mother_sites$ratio_Ref_mother >= nipat_cfg$homozygous_ref_min
    requires_ref <- if (child_type == "HOM") maternal_ref else !maternal_ref
    mother_sites$Paternal_allele <- ifelse(requires_ref, "REF", "ALT")
    mother_sites %>%
      dplyr::inner_join(padre, by=site_columns) %>%
      dplyr::inner_join(PopFreqDNPs, by=site_columns) %>%
      dplyr::mutate(
        Allele_frequency = ifelse(Paternal_allele == "REF", Ref_f.pop, Alt_f.pop),
        Father_genotype = dplyr::case_when(
          ratio_Ref_father >= nipat_cfg$homozygous_ref_min ~ "REF",
          ratio_Ref_father <= nipat_cfg$homozygous_alt_max ~ "ALT",
          between(ratio_Ref_father, nipat_cfg$heterozygous_min, nipat_cfg$heterozygous_max) ~ "HET",
          TRUE ~ NA_character_
        ),
        Mismatch = Father_genotype != "HET" & Father_genotype != Paternal_allele,
        Paternity_Index = dplyr::case_when(
          Father_genotype == Paternal_allele ~ 1 / Allele_frequency,
          Father_genotype == "HET" ~ 0.5 / Allele_frequency,
          Mismatch ~ err_const / Allele_frequency,
          TRUE ~ NA_real_
        )
      )
  }
  valid_PI <- function(sites) dplyr::filter(sites, is.finite(Paternity_Index), Paternity_Index > 0)

  pi_hom <- valid_PI(calculate_PI(madre_hom, "HOM"))
  hom_count <- nrow(pi_hom)
  hom_mismatches <- sum(pi_hom$Mismatch)
  log_hom <- sum(log10(pi_hom$Paternity_Index))
  het_candidates <- calculate_PI(madre_info, "HET")
  candidate_reads <- het_candidates$fetal_reads
  pi_het <- valid_PI(het_candidates)
  rm(het_candidates)
  log_pi <- log10(pi_het$Paternity_Index)
  het_reads <- pi_het$fetal_reads
  het_mismatch <- pi_het$Mismatch
  rm(pi_het)
  max_fetal <- suppressWarnings(max(madre_info$fetal_reads, na.rm=TRUE))

  # An empty threshold sequence still exports column headers and all qualifying HOM sites.
  iterations <- if (is.finite(max_fetal) && max_fetal >= curve_start) {
    seq.int(curve_start, max_fetal)
  } else integer()
  by_interval <- matrix(numeric(), nrow=0L, ncol=5L,
    dimnames=list(NULL, c("mother", "het", "mismatch", "log_het", "candidates")))
  interval_lengths <- integer()
  if (length(iterations)) {
    # Thresholds between two observed read counts select the same sites. Sum in
    # input order once per interval and restore all rows for curves and medians.
    interval_starts <- sort(unique(c(1L, floor(madre_info$fetal_reads) - curve_start + 2L)))
    interval_starts <- interval_starts[interval_starts <= length(iterations)]
    interval_lengths <- diff(c(interval_starts, length(iterations) + 1))
    interval_count <- length(interval_starts)
    compute_interval <- function(index) {
      threshold <- iterations[interval_starts[index]]
      selected <- het_reads >= threshold
      het_count <- sum(selected)
      mismatches <- sum(het_mismatch[selected])
      c(mother=sum(madre_info$fetal_reads >= threshold) + nrow(madre_hom), het=het_count,
        mismatch=mismatches, log_het=sum(log_pi[selected]), candidates=sum(candidate_reads >= threshold))
    }
    interval_workers <- nipat_parallel_workers(interval_count)
    chunk_size <- if (interval_workers == 1L) interval_count else ceiling(interval_count / (4L * interval_workers))
    chunks <- split(seq_along(interval_starts), ceiling(seq_along(interval_starts) / chunk_size))
    values <- nipat_parallel_lapply(chunks, function(indices) {
      do.call(rbind, lapply(indices, compute_interval))
    }, label="cpi-thresholds", workers=interval_workers)
    by_interval <- do.call(rbind, values)
  }
  het_count <- as.integer(by_interval[, "het"])
  mismatches <- as.integer(by_interval[, "mismatch"])
  matches <- het_count - mismatches
  log_total <- by_interval[, "log_het"] + log_hom
  log_total[het_count + hom_count == 0L] <- NA_real_
  expand <- function(x) rep(x, interval_lengths)
  results <- data.frame(
    Iteration=iterations,
    InfSites_mother=expand(as.integer(by_interval[, "mother"])),
    InfSites_father=expand(het_count + hom_count),
    CPI=expand(10^log_total), log_CPI=expand(log_total),
    Mismatch=expand(mismatches + hom_mismatches),
    NotMismatch=expand(matches + hom_count - hom_mismatches),
    N_sites_HET_child=expand(het_count), N_sites_HOM_child=rep(hom_count, length(iterations)),
    Matching_HET_child=expand(matches), Mismatching_HET_child=expand(mismatches),
    Matching_HOM_child=rep(hom_count - hom_mismatches, length(iterations)),
    Mismatching_HOM_child=rep(hom_mismatches, length(iterations)),
    Log10_CPI_HET_child=expand(by_interval[, "log_het"]), Log10_CPI_HOM_child=rep(log_hom, length(iterations)),
    HET_with_frequency=expand(as.integer(by_interval[, "candidates"])), Cutoff=rep(cutoff_label, length(iterations))
  )
  list(results=results, madre_info=madre_info, pi_hom=pi_hom, log_hom=log_hom)
}

## get logCPI at iteration closest to target (median fetal reads)
closest_logCPI <- function(res_df, target_i) {
  if (nrow(res_df)==0 || is.na(target_i) || !is.finite(target_i)) return(NA_real_)
  idx <- which.min(abs(res_df$Iteration - target_i))
  res_df$log_CPI[idx]
}

plot_CPI <- function(df, cutoff_label, pair_name,
                     cfDNA_percent = NA_real_,
                     cpi_medff = NA_real_, median_reads = NA_real_) {

  if (nrow(df) == 0) {
    return(
      ggplot() +
        theme_void(base_size = 9) +
        annotate("text", x = 0, y = 0, label = "No informative loci available", size = 3) +
        labs(title = paste(pair_name, "-", cutoff_label, "(no data)")) +
        theme(plot.title = element_text(size = 9, hjust = 0))
    )
  }

  max_iter <- max(df$Iteration, na.rm = TRUE)

  ticks <- sort(unique(c(curve_start, pretty(c(curve_start, max_iter), n=8), max_iter)))
  ticks <- ticks[ticks >= curve_start & ticks <= max_iter]
  median_threshold <- if (is.finite(median_reads)) df$Iteration[which.min(abs(df$Iteration - median_reads))] else numeric()

  cfDNA_lbl <- if (is.finite(cfDNA_percent)) {
    sprintf("%.2f", cfDNA_percent)
  } else {
    "NA"
  }

  cpi_lbl <- if (is.finite(cpi_medff)) {
    sprintf("%.3f", cpi_medff)
  } else {
    "NA"
  }

  annot_text <- paste0(
    "atop(",
    "'cfDNA: ", cfDNA_lbl, "%',",
    "log[10](CPI) * ': ' * '", cpi_lbl, "'",
    ")"
  )

  cpi_plot <- ggplot(df, aes(x = Iteration)) +
    annotate("rect", xmin = -Inf, xmax = Inf,
             ymin = -Inf, ymax = nipat_cfg$log_cpi_lower, fill = "red", alpha = 0.05) +
    annotate("rect", xmin = -Inf, xmax = Inf,
             ymin = nipat_cfg$log_cpi_lower, ymax = nipat_cfg$log_cpi_upper, fill = "grey", alpha = 0.05) +
    annotate("rect", xmin = -Inf, xmax = Inf,
             ymin = nipat_cfg$log_cpi_upper, ymax = Inf, fill = "green", alpha = 0.05) +

    geom_vline(xintercept=median_threshold, colour="red", linetype="dashed") +
    geom_line(aes(y = log_CPI), colour = "black") +
    geom_point(aes(y = log_CPI), colour = "black", size = 1.3) +

    annotate(
      "label",
      x = Inf, y = Inf,
      label = annot_text,
      parse = TRUE,
      hjust = 1.05,
      vjust = 1.10,
      size = 3,
      fill = "white",
      colour = "black",
      label.size = 0.2
    ) +

    scale_y_continuous(
      name = expression(log[10](CPI)),
      expand = expansion(mult = c(0.02, 0.14))
    ) +

    scale_x_continuous(
      name = "minimum number of fetal reads considered",
      breaks = ticks,
      limits = c(curve_start, max(curve_start + 1, max_iter)),
      expand = expansion(mult = c(0.02, 0.02))
    ) +

    labs(title = paste(pair_name, "-", cutoff_label)) +

    theme_bw(base_size = 9) +
    theme(
      legend.position = "bottom",
      plot.caption = element_text(size = 7, hjust = 0),
      plot.title = element_text(size = 9, hjust = 0),
      axis.title = element_text(size = 8),
      axis.text.x = element_text(angle = 45, hjust = 1, size = 7),
      panel.border = element_rect(
        colour = "black", fill = NA, linewidth = 0.6
      ),
      plot.margin = margin(8, 12, 8, 8)
    )
  # Counts and log likelihood ratios have different units. Separate aligned
  # panels keep the original values and avoid negative/fractional site axes.
  sites_plot <- ggplot(df, aes(x = Iteration)) +
    geom_line(aes(y = NotMismatch, colour = "Matching sites")) +
    geom_point(aes(y = NotMismatch, colour = "Matching sites"), size = 1) +
    geom_line(aes(y = Mismatch, colour = "Mismatching sites"), linetype = "dashed") +
    geom_point(aes(y = Mismatch, colour = "Mismatching sites"), size = 1) +
    scale_colour_manual(name = NULL, values = c("Matching sites" = "#008A38", "Mismatching sites" = "#C46B00")) +
    scale_y_continuous(name = "Sites contributing a paternity index", limits = c(0, NA), breaks = nipat_integer_breaks) +
    scale_x_continuous(name = "Minimum number of fetal reads considered", breaks = ticks,
      limits = c(curve_start, max(curve_start + 1, max_iter)), expand = expansion(mult = c(0.02, 0.02))) +
    theme_bw(base_size = 9) +
    theme(legend.position = "bottom", axis.text.x = element_text(angle = 45, hjust = 1, size = 7))
  (cpi_plot / sites_plot) + patchwork::plot_layout(heights = c(2, 1))
}

fetal_fraction_rows <- vector("list", nrow(coppie) * nrow(cutoff_df))
all_combined_plots <- list()
## Reuse a parent shared by consecutive pairs, retaining at most the two
## prepared tables already needed by the current pair.
pair_cache <- new.env(parent = emptyenv())
pair_cache$mother_path <- NULL
pair_cache$father_path <- NULL

process_pair <- function(i) {
  mamma_id <- coppie$mamma[i]
  papa_id  <- coppie$papa[i]
  pair_name <- paste0("Mother", mamma_id, "-Father", papa_id, "_", marker, "s")

  mother_path <- file.path(args$pileup_dir, paste0(args$mother_prefix, mamma_id, ".txt"))
  father_path <- file.path(args$pileup_dir, paste0(args$father_prefix, papa_id, ".txt"))

  check_pair(calls_cache[[mother_path]], calls_cache[[father_path]])

  if (!identical(mother_path, pair_cache$mother_path)) {
    madre <- calls_cache[[mother_path]]
    madre$chr <- as.character(madre$chr)
    madre <- madre %>%
      dplyr::transmute(
        dplyr::across(dplyr::all_of(site_columns)), REF, ALT,
        Ref_mother = N_REF,
        Alt_mother = N_ALT,
        Error_mother = N_Other,
        ratio_Ref_mother = N_REF / (N_REF + N_ALT),
        total_count = total_count
      ) %>% dplyr::filter(total_count > 0, total_count >= coverage_floor,
                          Error_mother/total_count <= nipat_cfg$other_fraction_max)
    pair_cache$mother <- madre
    pair_cache$mother_path <- mother_path
  } else {
    madre <- pair_cache$mother
  }

  if (!identical(father_path, pair_cache$father_path)) {
    padre <- calls_cache[[father_path]]
    padre$chr <- as.character(padre$chr)
    padre <- padre %>%
      dplyr::transmute(
        dplyr::across(dplyr::all_of(site_columns)), REF, ALT,
        Ref_father = N_REF,
        Alt_father = N_ALT,
        Error_father = N_Other,
        ratio_Ref_father = N_REF / (N_REF + N_ALT),
        total_count = total_count
      ) %>%
      dplyr::mutate(
        Ref_father = ifelse(ratio_Ref_father < nipat_cfg$homozygous_alt_max, 0, Ref_father),
        Alt_father = ifelse(ratio_Ref_father > nipat_cfg$homozygous_ref_min, 0, Alt_father)
      ) %>% dplyr::filter(total_count > 0, total_count >= coverage_floor,
                          Error_father/total_count <= nipat_cfg$other_fraction_max)
    pair_cache$father <- padre
    pair_cache$father_path <- father_path
  } else {
    padre <- pair_cache$father
  }

  cutoff_results <- nipat_parallel_lapply(seq_len(nrow(cutoff_df)), function(k) {
    cutoff_label <- cutoff_df$Cutoff[k]
    dnp_list <- cutoff_panels[[k]]

    out <- run_CPI_iteration(madre, padre, dnp_list, cutoff_label, err_const)
    res <- out$results

    target_i <- out$madre_info %>%
      dplyr::pull(fetal_reads) %>%
      stats::median(na.rm = TRUE) %>%
      round()

    cpi_at_med <- closest_logCPI(res, target_i)

    median_fetal_fraction <- out$madre_info %>%
      dplyr::mutate(
        fetal_fraction_site = 2 * fetal_reads /
          (Ref_mother + Alt_mother)
      ) %>%
      dplyr::pull(fetal_fraction_site) %>%
      stats::median(na.rm = TRUE)

    cfDNA_percent <- median_fetal_fraction * 100

    # Each maternal row has already passed both active filters and panel selection.
    n_sites_mother <- nrow(out$madre_info)
    shared <- dplyr::inner_join(out$madre_info, padre, by=site_columns)
    n_sites_father <- sum(
      (shared$ratio_Ref_mother >= nipat_cfg$homozygous_ref_min & shared$Alt_father >= 0) |
      (shared$ratio_Ref_mother <= nipat_cfg$homozygous_alt_max & shared$Ref_father >= 0)
    )

    all_cpi_vals <- res$log_CPI[!is.na(res$log_CPI)]

    max_cpi <- ifelse(length(all_cpi_vals)==0, NA, max(all_cpi_vals))
    min_cpi <- ifelse(length(all_cpi_vals)==0, NA, min(all_cpi_vals))
    med_cpi <- ifelse(length(all_cpi_vals)==0, NA, median(all_cpi_vals))
    mean_cpi <- ifelse(length(all_cpi_vals)==0, NA, mean(all_cpi_vals))

    median_index <- if (nrow(res) && is.finite(target_i)) which.min(abs(res$Iteration - target_i)) else NA_integer_
    median_value <- function(column) res[[column]][median_index]

    summary_row <- data.frame(Pair=pair_name)
    if (has_cutoffs) summary_row$Cutoff <- cutoff_label
    summary_row <- cbind(summary_row, data.frame(
      N_sites_mother = n_sites_mother,
      N_sites_father = n_sites_father,
      Median_fetal_fraction_raw = round(median_fetal_fraction,4),
      Median_fetal_fraction_percent = round(cfDNA_percent,2),
      Max_logCPI = round(max_cpi,3),
      Min_logCPI = round(min_cpi,3),
      Median_logCPI = round(med_cpi,3),
      Mean_logCPI = round(mean_cpi,3),
      CPI_medianFF = round(cpi_at_med,3),
      Include_homozygous_child = nipat_cfg$include_homozygous_child,
      Min_coverage = if (is.null(min_coverage)) NA_integer_ else min_coverage,
      Max_other_fraction = nipat_cfg$other_fraction_max,
      N_sites_HET_child = if (n_sites_mother == 0) 0L else median_value("N_sites_HET_child"),
      N_sites_HOM_child = nrow(out$pi_hom),
      Matching_HET_child = if (n_sites_mother == 0) 0L else median_value("Matching_HET_child"),
      Mismatching_HET_child = if (n_sites_mother == 0) 0L else median_value("Mismatching_HET_child"),
      Matching_HOM_child = sum(!out$pi_hom$Mismatch),
      Mismatching_HOM_child = sum(out$pi_hom$Mismatch),
      Log10_CPI_HET_child = round(median_value("Log10_CPI_HET_child"), 3),
      Log10_CPI_HOM_child = round(out$log_hom, 3),
      Error_constant = err_const,
      Min_fetal_reads = if (is.null(min_fetal_reads)) NA_integer_ else min_fetal_reads,
      Min_fetal_percent = if (is.null(min_fetal_percent)) NA_real_ else min_fetal_percent,
      Marker_type = marker
    ))
    list(label = cutoff_label, plot_data = res, summary = summary_row, hom_sites=out$pi_hom,
         cfDNA_percent = cfDNA_percent, cpi_at_med = cpi_at_med, median_reads=target_i)
  }, label = "cpi-cutoffs")
  list(pair_name = pair_name, cutoffs = cutoff_results)
}

pair_results <- nipat_parallel_lapply(seq_len(nrow(coppie)), process_pair,
                                    label = "cpi-pairs")
for (i in seq_along(pair_results)) {
  pair_result <- pair_results[[i]]
  pair_name <- pair_result$pair_name
  per_cutoff_plots <- list()
  for (k in seq_along(pair_result$cutoffs)) {
    cutoff_result <- pair_result$cutoffs[[k]]
    if (!cutoff_result$summary$N_sites_mother) {
      warning(pair_name, " (", cutoff_result$label, "): No maternal informative sites satisfy ",
              "the selected fetal-read filters. Fetal fraction and CPI cannot be calculated.",
              call.=FALSE, immediate.=TRUE)
    }
    per_cutoff_plots[[cutoff_result$label]] <- plot_CPI(
      cutoff_result$plot_data, cutoff_result$label, pair_name,
      cfDNA_percent = cutoff_result$cfDNA_percent,
      cpi_medff = cutoff_result$cpi_at_med, median_reads=cutoff_result$median_reads)
    curve_dir <- file.path(args$out_dir, "curves")
    dir.create(curve_dir, showWarnings=FALSE)
    write.table(cutoff_result$plot_data,
      file.path(curve_dir, paste0(pair_name, "_panel_", k, ".tsv")),
      sep="\t", quote=FALSE, row.names=FALSE, na="NA")
    prefix <- if (nrow(cutoff_df) == 1L) pair_name else paste0(pair_name, "_panel_", k)
    write.csv(cutoff_result$plot_data[, !names(cutoff_result$plot_data) %in% c("Cutoff", "HET_with_frequency"), drop=FALSE],
      file.path(args$out_dir, paste0(prefix, "_CPI_iterations.csv")), row.names=FALSE)
    write.table(cutoff_result$hom_sites, file.path(args$out_dir, paste0(prefix, "_HOM_child_sites.txt")),
      sep="\t", quote=FALSE, row.names=FALSE, na="NA")
    summary_index <- (i - 1L) * nrow(cutoff_df) + k
    fetal_fraction_rows[[summary_index]] <- cutoff_result$summary
  }

  if (length(per_cutoff_plots)>0) {
    combined <- nipat_cpi_pages(per_cutoff_plots[names(per_cutoff_plots)])
    ggsave(file.path(plots_dir, paste0(pair_name,"_CPIplot.pdf")),
           plot=combined, width=12, height=10)
    all_combined_plots <- c(all_combined_plots, unname(per_cutoff_plots))
  }

}

if (length(all_combined_plots)>0) {
  final_plot <- nipat_cpi_pages(all_combined_plots)
  ggsave(file.path(plots_dir, "All_CPIplots.pdf"),
         plot=final_plot, width=12, height=10)
}

fetal_fraction_summary <- do.call(rbind, fetal_fraction_rows)
write.csv(
  fetal_fraction_summary,
  file.path(args$out_dir, "Summary_FetalFraction_CPI.csv"),
  row.names = FALSE
)

message("done: all summaries and plots saved.")
