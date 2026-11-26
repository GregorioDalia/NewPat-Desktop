#!/usr/bin/env Rscript
# Postnatal model from NEWPAT 97c4eb5, with validated settings, cached samples
# and bounded parallelism across independent trios.

suppressPackageStartupMessages({
  library(argparse)
  library(dplyr)
})

source(Sys.getenv("NIPAT_PARALLEL_HELPER", unset="/opt/nipat/lib/nipat_scientific/parallel.R"))
source(Sys.getenv("NIPAT_SETTINGS_HELPER", unset="/opt/nipat/lib/nipat_scientific/settings.R"))
nipat_cfg <- nipat_settings("cpin")

parser <- ArgumentParser(description="Postnatal CPI from SNPcall or DNPcall trio outputs")
parser$add_argument("--pileup_dir", required=TRUE)
parser$add_argument("--out_dir", required=TRUE)
parser$add_argument("--trios", required=TRUE,
                    help="mother:father:child identifiers, separated by commas")
parser$add_argument("--mother_prefix", default="full_output_")
parser$add_argument("--father_prefix", default="full_output_")
parser$add_argument("--child_prefix", default="full_output_")
parser$add_argument("--popfreq", required=TRUE)
parser$add_argument("--markers", required=FALSE)
parser$add_argument("--min_coverage", type="double", default=NULL,
                    help="Minimum total reads at a site in each trio member")
parser$add_argument("--mismatch_probability_snp", default=NULL)
parser$add_argument("--mismatch_probability_dnp", default=NULL)
parser$add_argument("--include_hom_hom", choices=c("TRUE", "FALSE"), default=NULL)
parser$add_argument("--include_hom_het", choices=c("TRUE", "FALSE"), default=NULL)
parser$add_argument("--include_het_hom", choices=c("TRUE", "FALSE"), default=NULL)
parser$add_argument("--include_het_het", choices=c("TRUE", "FALSE"), default=NULL)
args <- parser$parse_args()

combos <- c("hom_hom", "hom_het", "het_hom", "het_het")
selection <- setNames(vapply(combos, function(combo) {
  key <- paste0("include_", combo)
  if (is.null(args[[key]])) nipat_cfg[[key]] else args[[key]] == "TRUE"
}, logical(1)), combos)
if (!any(selection)) stop("At least one genotype combination must be enabled")
message("Selected combinations: ", paste(names(selection)[selection], collapse=", "))

min_coverage <- args$min_coverage
if (is.null(min_coverage)) min_coverage <- nipat_cfg$min_coverage
if (!is.null(min_coverage)) {
  if (!is.finite(min_coverage) || min_coverage < 1 ||
      min_coverage != floor(min_coverage) || min_coverage >= .Machine$integer.max) {
    stop("--min_coverage must be a positive integer below the R integer limit")
  }
  min_coverage <- as.integer(min_coverage)
}
message("Minimum coverage per trio member: ", if (is.null(min_coverage)) "not set" else min_coverage)
if (dir.exists(args$out_dir)) {
  existing <- list.files(args$out_dir, all.files=TRUE, no..=TRUE, full.names=TRUE)
  # The trusted presentation wrapper precreates this empty export directory.
  allowed <- basename(existing) == "presentation" & dir.exists(existing) & !nzchar(Sys.readlink(existing))
  if (length(existing) && (!all(allowed) ||
      any(vapply(existing, function(path) length(list.files(path, all.files=TRUE, no..=TRUE)) > 0L, logical(1))))) {
    stop("Output directory is not empty; choose a new --out_dir")
  }
}
dir.create(args$out_dir, recursive=TRUE, showWarnings=FALSE)

trio_parts <- strsplit(args$trios, ",", fixed=TRUE)[[1]]
trios <- lapply(trio_parts, function(z) trimws(strsplit(z, ":", fixed=TRUE)[[1]]))
if (!length(trios) || any(lengths(trios) != 3L) ||
    any(!nzchar(unlist(trios))) ||
    anyDuplicated(vapply(trios, paste, collapse=":", FUN.VALUE=character(1)))) {
  stop("--trios must be mother:father:child entries separated by commas")
}
if (any(!grepl("^[A-Za-z0-9_.-]+$", unlist(trios)))) {
  stop("Identifiers may contain letters, digits, underscores, dots and hyphens")
}
if (any(unlist(trios) %in% c(".", ".."))) stop("Invalid sample identifier")
trio_names <- vapply(trios, function(ids) paste0("Mother", ids[1], "-Father", ids[2], "-Child", ids[3]), character(1))
if (anyDuplicated(tolower(trio_names))) stop("Trio identifiers produce colliding output names")
# Identifiers are role-local: MotherA, FatherA and ChildA are distinct samples.
# Validate identities after prefixes and filesystem links have been resolved.
prefixes <- c(args$mother_prefix, args$father_prefix, args$child_prefix)
if (any(!grepl("^[A-Za-z0-9_.-]*$", prefixes))) stop("Invalid sample filename prefix")
sample_names <- character()
sample_owners <- character()
for (ids in trios) for (i in seq_along(ids)) {
  name <- paste0(prefixes[i], ids[i], ".txt")
  key <- tolower(name)
  owner <- paste(i, tolower(ids[i]), sep=":")
  if (key %in% names(sample_names) && (sample_names[[key]] != name || sample_owners[[key]] != owner)) {
    stop("Sample prefixes and identifiers produce colliding filenames")
  }
  sample_names[[key]] <- name
  sample_owners[[key]] <- owner
}
resolved_sources <- vapply(sample_names, function(name)
  normalizePath(file.path(args$pileup_dir, name), mustWork=TRUE), character(1))
if (anyDuplicated(resolved_sources)) stop("One input file cannot identify distinct samples")

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

# Apply command-line overrides to the same marker-specific defaults used by the app.
for (key in c("mismatch_probability_snp", "mismatch_probability_dnp")) {
  if (!is.null(args[[key]])) {
    probability <- suppressWarnings(as.numeric(args[[key]]))
    if (!is.finite(probability) || probability <= 0 || probability > 1)
      stop("--", key, " must be a finite number in (0, 1]")
    nipat_cfg[[key]] <- probability
  }
}
mismatch_probability <- nipat_cfg[[paste0("mismatch_probability_", tolower(marker))]]
message("Mismatch probability used for ", marker, ": ", sprintf("%.17g", mismatch_probability))

site_key <- function(x) {
  do.call(paste, c(unname(as.list(x[site_columns])), sep="\t"))
}

check_sites <- function(x, required, label) {
  missing <- setdiff(required, names(x))
  if (length(missing)) stop(label, ": missing columns ", paste(missing, collapse=", "))
  if (anyNA(x[site_columns]) || anyDuplicated(site_key(x))) {
    stop(label, ": missing or duplicate coordinates")
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
population_for_join <- population[, c(site_columns, "Ref_f.pop", "Alt_f.pop"), drop=FALSE]

calling_cache <- new.env(parent=emptyenv())
read_calls <- function(path) {
  path <- normalizePath(path, mustWork=TRUE)
  if (exists(path, envir=calling_cache, inherits=FALSE)) return(get(path, envir=calling_cache))
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
  assign(path, x, envir=calling_cache)
  x
}

# Genotype intervals follow the cfDNA script. Intermediate ratios are unassigned.
classify_genotype <- function(ratio) {
  gt <- rep(NA_character_, length(ratio))
  gt[is.finite(ratio) & ratio >= nipat_cfg$homozygous_ref_min] <- "0/0"
  gt[is.finite(ratio) & ratio <= nipat_cfg$homozygous_alt_max] <- "1/1"
  gt[is.finite(ratio) & ratio >= nipat_cfg$heterozygous_min & ratio <= nipat_cfg$heterozygous_max] <- "0/1"
  gt
}

# Apply the same Other/total filter separately to every sample.
passes_quality <- function(ref, alt, other, total) {
  ratio <- other / total
  valid <- total > 0 & (ref + alt) > 0 & is.finite(ratio) & ratio <= nipat_cfg$other_fraction_max
  if (!is.null(min_coverage)) valid <- valid & total >= min_coverage
  valid
}

classify_combination <- function(m, child) {
  case_when(
    is.na(m) | is.na(child) ~ NA_character_,
    m == "0/1" & child == "0/1" ~ "het_het",
    m == "0/1" & child %in% c("0/0", "1/1") ~ "het_hom",
    m %in% c("0/0", "1/1") & child == "0/1" ~ "hom_het",
    m == child & m %in% c("0/0", "1/1") ~ "hom_hom",
    TRUE ~ NA_character_
  )
}

required_allele <- function(m, child) {
  case_when(
    m == "0/0" & child == "0/1" ~ "ALT",
    m == "1/1" & child == "0/1" ~ "REF",
    m %in% c("0/0", "0/1") & child == "0/0" ~ "REF",
    m %in% c("1/1", "0/1") & child == "1/1" ~ "ALT",
    TRUE ~ NA_character_
  )
}

prepared_cache <- new.env(parent=emptyenv())
prepare_sample <- function(id, prefix, role) {
  cache_key <- paste(role, prefix, id, sep="\t")
  if (exists(cache_key, envir=prepared_cache, inherits=FALSE)) return(get(cache_key, envir=prepared_cache))
  path <- file.path(args$pileup_dir, paste0(prefix, id, ".txt"))
  x <- read_calls(path)
  pattern <- if (marker == "SNP") "^[ACGT]$" else "^[ACGT]{2}$"
  if (any(!grepl(pattern, toupper(x$REF)) | !grepl(pattern, toupper(x$ALT)))) {
    stop(path, ": alleles must contain only A, C, G and T")
  }
  count_columns <- c("N_REF", "N_ALT", "N_Other", "total_count")
  for (column in count_columns) {
    # read.table infers logical storage for header-only or entirely NA columns.
    # Preserve missing values for the validation below, including the supported
    # all-zero DNP sample with total_count=NA at every locus. Boolean counts
    # remain invalid rather than silently becoming zero or one.
    if (is.logical(x[[column]]) && all(is.na(x[[column]]))) {
      x[[column]] <- as.numeric(x[[column]])
    }
    if (!is.numeric(x[[column]])) stop(path, ": read counts must be numeric")
  }
  # DNPcall can report NA total_count at sites with no reads.
  # Correct this representation in memory and retain an internal flag.
  x$Missing_total_at_zero_coverage <- is.na(x$total_count) &
    !is.na(x$N_REF) & !is.na(x$N_ALT) & !is.na(x$N_Other) &
    x$N_REF == 0 & x$N_ALT == 0 & x$N_Other == 0
  if (any(x$Missing_total_at_zero_coverage)) {
    message(path, ": ", sum(x$Missing_total_at_zero_coverage),
            " zero-coverage site(s) with missing total_count; treated as zero coverage")
    x$total_count[x$Missing_total_at_zero_coverage] <- 0
  }
  counts <- as.matrix(x[count_columns])
  if (anyNA(counts) || any(!is.finite(counts) | counts < 0 | counts != floor(counts))) {
    stop(path, ": counts must be nonnegative finite integers")
  }
  if (any(x$total_count != x$N_REF + x$N_ALT + x$N_Other)) {
    stop(path, ": total_count differs from REF + ALT + Other")
  }
  x$ratio <- x$N_REF / (x$N_REF + x$N_ALT)
  x$GT <- classify_genotype(x$ratio)
  x$Other_ratio <- x$N_Other / x$total_count
  x$Quality_pass <- passes_quality(x$N_REF, x$N_ALT, x$N_Other, x$total_count)
  x$GT[!x$Quality_pass] <- NA_character_
  x$Present <- rep(TRUE, nrow(x))
  x <- x[c(site_columns, "REF", "ALT", count_columns, "ratio", "GT",
           "Other_ratio", "Quality_pass", "Present", "Missing_total_at_zero_coverage")]
  names(x)[!names(x) %in% site_columns] <- paste0(
    names(x)[!names(x) %in% site_columns], "_", role)
  assign(cache_key, x, envir=prepared_cache)
  x
}

# PI when the mother and child identify an obligatory paternal allele.
site_pi <- function(required, father_gt, ref_frequency, alt_frequency, epsilon) {
  frequency <- ifelse(required == "REF", ref_frequency, alt_frequency)
  transmission <- ifelse(father_gt == "0/1", 0.5,
    ifelse((required == "REF" & father_gt == "0/0") |
           (required == "ALT" & father_gt == "1/1"), 1, 0))
  mismatch <- transmission == 0
  weight <- ifelse(mismatch, epsilon, transmission)
  pi <- weight / frequency
  log_pi <- log10(pi)
  # Preserve ordinary division/log rounding. A positive representable frequency
  # can make PI overflow even though its logarithm is finite and usable.
  overflow <- is.infinite(pi) & is.finite(frequency) & frequency > 0
  log_pi[overflow] <- log10(weight[overflow]) - log10(frequency[overflow])
  list(PI=pi, Log10_PI=log_pi, Mismatch=mismatch,
       Frequency=frequency, Transmission=transmission)
}

# Preflight all unique samples before starting any child. Fork workers share these caches.
for (ids in trios) {
  invisible(prepare_sample(ids[1], args$mother_prefix, "mother"))
  invisible(prepare_sample(ids[2], args$father_prefix, "father"))
  invisible(prepare_sample(ids[3], args$child_prefix, "child"))
}
nipat_cfg["min_coverage"] <- list(min_coverage)
for (combo in combos) nipat_cfg[[paste0("include_", combo)]] <- selection[[combo]]
nipat_write_settings("cpin", nipat_cfg, args$out_dir)

process_trio <- function(ids) {
  trio_name <- paste0("Mother", ids[1], "-Father", ids[2], "-Child", ids[3],
                      "_", marker, "s")
  message("Processing ", trio_name)
  mother <- prepare_sample(ids[1], args$mother_prefix, "mother")
  father <- prepare_sample(ids[2], args$father_prefix, "father")
  child <- prepare_sample(ids[3], args$child_prefix, "child")
  x <- full_join(full_join(mother, father, by=site_columns), child, by=site_columns)
  if (has_markers) {
    x <- full_join(marker_list[site_columns], x, by=site_columns)
  }

  # Check all shared allele definitions, including sites without frequencies.
  for (pair in list(c("mother", "father"), c("mother", "child"), c("father", "child"))) {
    for (allele in c("REF", "ALT")) {
      a <- x[[paste0(allele, "_", pair[1])]]
      b <- x[[paste0(allele, "_", pair[2])]]
      if (any(!is.na(a) & !is.na(b) & toupper(a) != toupper(b))) {
        stop(trio_name, ": inconsistent allele definitions between samples")
      }
    }
  }
  x <- left_join(x, population_for_join, by=site_columns)
  x$REF <- coalesce(x$REF_mother, x$REF_father, x$REF_child)
  x$ALT <- coalesce(x$ALT_mother, x$ALT_father, x$ALT_child)
  if (has_markers) {
    panel_index <- match(site_key(x), site_key(marker_list))
    x$REF <- coalesce(x$REF, marker_list$REF[panel_index])
    x$ALT <- coalesce(x$ALT, marker_list$ALT[panel_index])
  }
  m <- x$GT_mother
  cgt <- x$GT_child
  x$Mother_child_incompatible <- !is.na(m) & !is.na(cgt) &
    ((m == "0/0" & cgt == "1/1") | (m == "1/1" & cgt == "0/0"))
  x$Genotype_combination <- classify_combination(m, cgt)
  x$Required_paternal_allele <- required_allele(m, cgt)
  x$Combination_selected <- x$Genotype_combination %in% names(selection)[selection]
  x$Status <- case_when(
    is.na(x$Present_mother) | is.na(x$Present_father) | is.na(x$Present_child) ~ "missing_call",
    !x$Quality_pass_mother | !x$Quality_pass_father | !x$Quality_pass_child ~ "quality_filter",
    is.na(m) ~ "mother_unassigned",
    is.na(cgt) ~ "child_unassigned",
    is.na(x$GT_father) ~ "father_unassigned",
    x$Mother_child_incompatible ~ "mother_child_incompatible",
    !x$Combination_selected ~ "combination_not_selected",
    is.na(x$Ref_f.pop) | is.na(x$Alt_f.pop) ~ "missing_population_frequency",
    TRUE ~ "eligible")

  eligible <- x$Status == "eligible"
  obligatory <- eligible & !is.na(x$Required_paternal_allele)
  no_obligatory <- eligible & x$Genotype_combination %in% "het_het"
  stopifnot(all(!eligible | obligatory | no_obligatory))

  x$Paternity_Index <- rep(NA_real_, nrow(x))
  site_log_pi <- rep(NA_real_, nrow(x))
  x$Mismatch <- rep(NA, nrow(x))
  x$Paternal_transmission <- rep(NA_real_, nrow(x))
  x$Paternity_status <- rep(NA_character_, nrow(x))
  if (any(obligatory)) {
    pi <- site_pi(x$Required_paternal_allele[obligatory], x$GT_father[obligatory],
                  x$Ref_f.pop[obligatory], x$Alt_f.pop[obligatory], mismatch_probability)
    x$Paternity_Index[obligatory] <- pi$PI
    site_log_pi[obligatory] <- pi$Log10_PI
    x$Mismatch[obligatory] <- pi$Mismatch
    x$Paternal_transmission[obligatory] <- pi$Transmission
    x$Paternity_status[obligatory] <- ifelse(pi$Mismatch, "mismatch", "match")
  }
  if (any(no_obligatory)) {
    frequency_sum <- x$Ref_f.pop[no_obligatory] + x$Alt_f.pop[no_obligatory]
    pi <- 1 / frequency_sum
    x$Paternity_Index[no_obligatory] <- pi
    site_log_pi[no_obligatory] <- ifelse(is.finite(pi), log10(pi), -log10(frequency_sum))
    x$Paternity_status[no_obligatory] <- "no_obligatory_allele"
  }
  write.table(x, file.path(args$out_dir, paste0(trio_name, "_sites.txt")),
              sep="\t", quote=FALSE, row.names=FALSE, na="NA")

  # Keep the logarithm even when the accumulated product overflows or underflows.
  log_cpi <- if (any(eligible)) sum(site_log_pi[eligible]) else NA_real_
  combinations_used <- x$Genotype_combination[eligible]
  data.frame(
    Trio=trio_name, Marker_type=marker, N_sites=sum(eligible),
    N_hom_hom=sum(combinations_used == "hom_hom"), N_hom_het=sum(combinations_used == "hom_het"),
    N_het_hom=sum(combinations_used == "het_hom"), N_het_het=sum(combinations_used == "het_het"),
    Matching_sites=sum(x$Mismatch %in% FALSE), Mismatching_sites=sum(x$Mismatch %in% TRUE),
    No_obligatory_allele_sites=sum(no_obligatory),
    Maternal_incompatible_sites=sum(x$Status == "mother_child_incompatible"),
    Log10_CPI=log_cpi, CPI=10^log_cpi, Mismatch_probability=mismatch_probability,
    Min_coverage=if (is.null(min_coverage)) NA_integer_ else min_coverage,
    Include_hom_hom=selection[["hom_hom"]], Include_hom_het=selection[["hom_het"]],
    Include_het_hom=selection[["het_hom"]], Include_het_het=selection[["het_het"]])
}

summary <- bind_rows(nipat_parallel_lapply(trios, process_trio, label="cpin-trios"))
write.table(summary, file.path(args$out_dir, "Summary_Postnatal_CPI.txt"),
            sep="\t", quote=FALSE, row.names=FALSE, na="NA")
for (trio in summary$Trio[summary$N_sites == 0L]) {
  warning(trio, ": no eligible sites after applying trio quality, genotype, frequency and selection criteria. CPI cannot be calculated.",
          call.=FALSE)
}
message("Done: trio CPI summary and site-level results saved.")
