#!/usr/bin/env Rscript
# Exact current-model comparison: frozen NEWPAT 9c2a8be is the oracle.
# The former 0.8.5 oracle used a different denominator; HEAD already rejected
# this test's NA-count fixture before 0.9.5. Invalid counts are negative cases.
arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 1L) stop("Expected one repository root argument")
repository <- normalizePath(arguments[[1L]], mustWork = TRUE)
relative <- "scientific/vendor/NEWPAT/contamination/detect_contamination.R"
Sys.setenv(NIPAT_PARALLEL_HELPER = file.path(repository, "src/nipat_scientific/parallel.R"),
           NIPAT_SETTINGS_HELPER = file.path(repository, "src/nipat_scientific/settings.R"),
           NIPAT_MAX_WORKERS = "2")
source(Sys.getenv("NIPAT_PARALLEL_HELPER"))
root <- tempfile("nipat-contamination-parallel-")
dir.create(root)

panel <- data.frame(chr = "chr1", pos1 = 10:19, pos2 = 11:20)
panel_path <- file.path(root, "panel.txt")
write.table(panel, panel_path, sep = "\t", row.names = FALSE, quote = FALSE)
template <- transform(panel,
  N_REF = c(90, 1, 50, 0, 99, 9, 10, 100, 4, 0),
  N_ALT = c(10, 9, 50, 0, 1, 1, 90, 0, 96, 2),
  N_Other = c(0, 0, 0, 0, 11, 1, 0, 0, 10, 0),
  extra = c("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"))
large_path <- file.path(root, "large.txt")
write.table(template[rep(seq_len(nrow(template)), length.out = 120003L), ],
            large_path, sep = "\t", row.names = FALSE, quote = FALSE)
duplicate_dir <- file.path(root, "duplicate")
dir.create(duplicate_dir)
for (name in c("first", "last")) dir.create(file.path(duplicate_dir, name))
write.table(template[1:3, ], file.path(duplicate_dir, "first", "same.txt"),
            sep = "\t", row.names = FALSE, quote = FALSE)
write.table(template[6:9, ], file.path(duplicate_dir, "last", "same.txt"),
            sep = "\t", row.names = FALSE, quote = FALSE)

run_case <- function(name, input, source_root, mode) {
  output <- file.path(root, name)
  log_dir <- paste0(output, "-workers")
  Sys.setenv(NIPAT_EXECUTION_MODE = mode, NIPAT_PARALLEL_LOG_DIR = log_dir)
  values <- new.env(parent = globalenv())
  values$commandArgs <- function(trailingOnly = FALSE) c(panel_path, input, output)
  source_path <- if (source_root == "reference")
    file.path(repository, "tests/reference_r/NEWPAT_20261113/contamination/detect_contamination.R") else
    file.path(source_root, relative)
  sys.source(source_path, envir = values)
  list(output = output, summary = values$contamination_summary, logs = log_dir)
}
bytes <- function(path) readBin(path, "raw", n = file.info(path)$size)
compare <- function(expected, actual) {
  stopifnot(identical(expected$summary, actual$summary))
  files <- list.files(expected$output)
  stopifnot(identical(files, setdiff(list.files(actual$output), "scientific-settings.json")))
  for (name in files) {
    if (!identical(bytes(file.path(expected$output, name)),
                   bytes(file.path(actual$output, name)))) stop("Output differs: ", name)
  }
}
for (case_name in "large") {
  input <- if (case_name == "large") large_path else duplicate_dir
  baseline <- run_case(paste0(case_name, "-reference"), input,
                       "reference", "serial")
  serial <- run_case(paste0(case_name, "-serial"), input, repository, "serial")
  first <- run_case(paste0(case_name, "-parallel1"), input, repository, "auto")
  second <- run_case(paste0(case_name, "-parallel2"), input, repository, "auto")
  for (candidate in list(serial, first, second)) compare(baseline, candidate)
  plans <- unlist(lapply(list.files(first$logs, full.names = TRUE), readLines),
                  use.names = FALSE)
  plans <- lapply(plans, jsonlite::fromJSON)
  plans <- Filter(function(value) identical(value$event, "plan"), plans)
  samples <- Filter(function(value) identical(value$label, "contamination-samples"), plans)
  stopifnot(length(samples) == 1L, samples[[1L]]$workers == 1L,
            samples[[1L]]$reason == "workload-not-observed")
  rows <- Filter(function(value) identical(value$label, "contamination-rows"), plans)
  stopifnot(length(rows) == 1L, rows[[1L]]$tasks > 1L, rows[[1L]]$workers == 2L)
  events <- unlist(lapply(list.files(first$logs, full.names = TRUE), readLines), use.names = FALSE)
  events <- lapply(events, jsonlite::fromJSON)
  child_events <- Filter(function(value) identical(value$event, "task-start") &&
    identical(value$label, "contamination-rows") && value$pid != value$coordinator_pid, events)
  stopifnot(length(unique(vapply(child_events, function(value) value$pid, numeric(1)))) == 2L)
  cat("Observed contamination: serial unobserved outer, two real loaded-row child processes.\n")
  cat("PASS contamination:", case_name,
      "legacy/serial/parallel/repeat exact tables and unrounded summary\n")
}
for (mode in c("serial", "auto")) {
  duplicate_error <- tryCatch({
    run_case(paste0("duplicate-", mode), duplicate_dir, repository, mode)
    NULL
  }, error = identity)
  stopifnot(inherits(duplicate_error, "error"),
            grepl("Duplicate sample output names", conditionMessage(duplicate_error)))
  invalid <- template
  invalid$N_REF[[10L]] <- NA_real_
  invalid_path <- file.path(root, "invalid.txt")
  write.table(invalid, invalid_path, sep = "\t", row.names = FALSE, quote = FALSE)
  invalid_error <- tryCatch({
    run_case(paste0("invalid-", mode), invalid_path, repository, mode)
    NULL
  }, error = identity)
  stopifnot(inherits(invalid_error, "error"),
            grepl("finite nonnegative integers", conditionMessage(invalid_error)))
}
cat("PASS contamination: duplicate aliases and missing counts rejected in serial and auto.\n")
batch <- file.path(root, "batch")
dir.create(batch)
for (name in c("Alpha", "Beta", "Gamma")) {
  write.table(template[seq_len(match(name, c("Alpha", "Beta", "Gamma")) + 3L), ],
              file.path(batch, paste0(name, ".txt")), sep = "\t", row.names = FALSE, quote = FALSE)
}
batch_plan <- function(result) {
  lines <- unlist(lapply(list.files(result$logs, full.names = TRUE), readLines), use.names = FALSE)
  events <- lapply(lines, jsonlite::fromJSON)
  plans <- Filter(function(x) x$event == "plan" && x$label == "contamination-samples", events)
  starts <- Filter(function(x) x$event == "task-start" && x$label == "contamination-samples", events)
  stopifnot(length(plans) == 1L, length(starts) == 3L)
  list(plan = plans[[1L]], pids = unique(vapply(starts, function(x) as.integer(x$pid), integer(1))))
}
expected <- run_case("batch-reference", batch, "reference", "serial")
actual <- run_case("batch-parallel", batch, repository, "auto")
compare(expected, actual)
evidence <- batch_plan(actual)
stopifnot(evidence$plan$workers == 2L, length(evidence$pids) >= 2L,
          !evidence$plan$coordinator_pid %in% evidence$pids,
          evidence$plan$workload_model == "max-loaded-coordinator-rss-x2-and-module-estimate",
          evidence$plan$memory_per_worker_mib > 2 * evidence$plan$coordinator_rss_mib - 1)
old_memory <- Sys.getenv("NIPAT_MEMORY_LIMIT_MIB", unset = NA_character_)
Sys.setenv(NIPAT_MEMORY_LIMIT_MIB = "1")
limited <- run_case("batch-limited", batch, repository, "auto")
if (is.na(old_memory)) Sys.unsetenv("NIPAT_MEMORY_LIMIT_MIB") else Sys.setenv(NIPAT_MEMORY_LIMIT_MIB = old_memory)
compare(expected, limited)
evidence <- batch_plan(limited)
stopifnot(evidence$plan$workers == 1L, evidence$plan$reason == "workload-exceeds-budget-serial",
          identical(evidence$pids, as.integer(evidence$plan$coordinator_pid)))
# A compressed table can be read by R, but its on-disk size cannot predict
# the in-memory table. Preserve the sequential fallback and its exact outputs.
compressed <- file.path(batch, "Gamma.txt")
lines <- readLines(compressed)
connection <- gzfile(compressed, "wt")
writeLines(lines, connection)
close(connection)
unknown <- run_case("batch-compressed", batch, repository, "auto")
compare(expected, unknown)
evidence <- batch_plan(unknown)
stopifnot(evidence$plan$workers == 1L, evidence$plan$reason == "workload-not-observed")
cat("PASS contamination: measured multi-table workers, tight RAM and compressed input fallback.\n")
unlink(root, recursive = TRUE)
