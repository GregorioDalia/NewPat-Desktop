#!/usr/bin/env Rscript
# The production dispatcher and scheduler run real forked tasks. Resource
# discovery alone is replaced with a bounded test policy: host quotas are
# separately qualified by parallel/check_budget.R. Scientific equations are
# compared end-to-end with the immutable 0.8.5 reference by the main harness.
root <- normalizePath(commandArgs(trailingOnly = TRUE)[[1L]], mustWork = TRUE)

main <- function() {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(root, "src/newpat_scientific/parallel.R"), environment)
  sys.source(file.path(root, "src/newpat_scientific/dnp_blocks.R"), environment)
  variables <- c("NEWPAT_EXECUTION_MODE", "NEWPAT_PARALLEL_CHILD", "NEWPAT_PARALLEL_LOG_DIR",
                 "NEWPAT_DNP_OPTIMIZED_IO", "NEWPAT_DNP_LIMA_ARM64", "NEWPAT_MAX_WORKERS", "NEWPAT_PERFORMANCE_DIR")
  previous <- Sys.getenv(variables, unset = NA_character_)
  on.exit(for (name in names(previous)) {
    if (is.na(previous[[name]])) Sys.unsetenv(name) else
      do.call(Sys.setenv, setNames(list(previous[[name]]), name))
  }, add = TRUE)
  Sys.unsetenv(variables)
  directory <- tempfile("dnp-sample-blocks-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  parent_pid <- Sys.getpid()
  checks <- 0L
  check <- function(condition) {
    stopifnot(isTRUE(condition))
    checks <<- checks + 1L
  }
  own_connections <- function(path) {
    sum(showConnections(all = TRUE)[, "description"] == path)
  }
  expect_error <- function(expression, pattern) {
    value <- tryCatch({ force(expression); NULL }, error = identity)
    check(inherits(value, "error") && grepl(pattern, conditionMessage(value)))
  }

  # Numeric-looking names retain their exact spelling in every sample column.
  make_lines <- function(samples, loci) {
    vapply(seq_len(2L * loci), function(row) {
      fields <- c("chr1", row, "A")
      for (sample_number in seq_len(samples)) {
        qname <- switch(as.character(sample_number),
          "1" = if (row == 2L * loci) "last-read" else sprintf("%03d", row),
          "2" = as.character(100L + row),
          "3" = if (row %% 2L) "TRUE" else "FALSE",
          "4" = as.character(row + 0.5),
          "5" = if (row == 2L * loci) "NaN" else as.character(row),
          paste0("sample", sample_number, "-read", row))
        fields <- c(fields, 1L, c("A", "C", "G", "T")[(sample_number - 1L) %% 4L + 1L],
                    if (row == 2L * loci) "I" else "5", qname)
      }
      paste(fields, collapse = "\t")
    }, character(1))
  }
  selected_columns <- function(sample_number) {
    c(1:3, seq.int(4L + (sample_number - 1L) * 4L, 7L + (sample_number - 1L) * 4L))
  }
  reader_path <- file.path(directory, "typed.pileup")
  writeLines(make_lines(5L, 4L), reader_path)
  reader_index <- environment$newpat_dnp_index(reader_path)
  reference <- read.csv(reader_path, quote = "", row.names = NULL,
                        stringsAsFactors = FALSE, header = FALSE, sep = "\t", na.strings = NULL,
                        colClasses = c("character", "integer", "character",
                                       rep(c("integer", "character", "character", "character"), 5L)))
  connection <- file(reader_path, "rb")
  for (rows in list(1:8, 8:1, c(2L, 2L, 7L, 1L), 1L, integer())) {
    for (sample_number in 1:5) {
      columns <- selected_columns(sample_number)
      expected <- reference[rows, columns, drop = FALSE]
      rownames(expected) <- NULL
      actual <- environment$newpat_dnp_read(reader_index, rows, connection, columns)
      check(identical(actual, expected))
      # Requested column order does not renumber or reorder pileup columns.
      check(identical(environment$newpat_dnp_read(reader_index, rows, connection,
                                                rev(columns)), expected))
    }
  }
  close(connection)
  check(own_connections(reader_index$path) == 0L)

  production_lapply <- environment$newpat_parallel_lapply
  controlled_workers <- 1L
  environment$newpat_parallel_capacity <- function() list(memory_capacity_mib = 3905)
  memory_budget <- 32768
  environment$newpat_parallel_budget <- function(tasks, memory_mib = NULL, workers = NULL, workload_observed = TRUE) {
    selected <- min(controlled_workers, if (is.null(workers)) Inf else workers, max(1L, tasks))
    mode <- Sys.getenv("NEWPAT_EXECUTION_MODE", "auto")
    if (!workload_observed || mode == "serial" || identical(Sys.getenv("NEWPAT_PARALLEL_CHILD"), "1")) selected <- 1L
    list(mode = mode, max_workers = workers, workers = as.integer(selected), tasks = tasks,
         cpu_limit = controlled_workers, memory_available_mib = memory_budget,
         memory_budget_mib = memory_budget, coordinator_rss_mib = 64,
         memory_per_worker_mib = memory_mib, memory_worker_limit = controlled_workers,
         reason = "controlled-test-budget")
  }

  # With more processes than samples, at least one sample must have concurrent
  # blocks. With more samples than processes, identity must survive queue reuse.
  cases <- list(
    list(samples = 2L, blocks = 4L, workers = 3L),
    list(samples = 2L, blocks = 4L, workers = 4L, small_arm = TRUE, tasks = 4L),
    list(samples = 2L, blocks = 4L, workers = 4L, native_io = TRUE, tasks = 4L),
    list(samples = 9L, blocks = 3L, workers = 2L, small_arm = TRUE, tasks = 9L),
    list(samples = 2L, blocks = 4L, workers = 2L, small_arm = TRUE, low_memory = TRUE),
    list(samples = 2L, blocks = 4L, workers = 2L, small_arm = TRUE, oversize = TRUE),
    list(samples = 3L, blocks = 1L, workers = 2L, small_arm = TRUE, compatibility = TRUE),
    list(samples = 3L, blocks = 4L, workers = 2L, reverse_callbacks = TRUE),
    list(samples = 5L, blocks = 2L, workers = 4L),
    list(samples = 5L, blocks = 1L, workers = 4L, small_arm = TRUE, manual = TRUE),
    list(samples = 3L, blocks = 1L, workers = 4L, compatibility = TRUE),
    list(samples = 3L, blocks = 4L, workers = 1L),
    list(samples = 3L, blocks = 4L, workers = 4L, serial = TRUE)
  )
  for (case_number in seq_along(cases)) {
    case <- cases[[case_number]]
    case_dir <- file.path(directory, as.character(case_number))
    dir.create(case_dir)
    barrier <- file.path(case_dir, "started")
    dir.create(barrier)
    trace <- file.path(case_dir, "events")
    Sys.setenv(NEWPAT_PARALLEL_LOG_DIR = trace,
               NEWPAT_EXECUTION_MODE = if (isTRUE(case$serial)) "serial" else "auto")
    Sys.setenv(NEWPAT_DNP_OPTIMIZED_IO = if (isTRUE(case$small_arm) || isTRUE(case$native_io)) "1" else "0",
               NEWPAT_DNP_LIMA_ARM64 = if (isTRUE(case$small_arm)) "1" else "0")
    memory_budget <- if (isTRUE(case$low_memory)) 768 else 32768
    if (isTRUE(case$manual)) Sys.setenv(NEWPAT_MAX_WORKERS = case$workers) else Sys.unsetenv("NEWPAT_MAX_WORKERS")
    controlled_workers <- case$workers
    expected_workers <- if (isTRUE(case$serial)) 1L else min(case$workers, case$samples * case$blocks)
    if (isTRUE(case$small_arm) && !isTRUE(case$manual)) expected_workers <- 2L
    loci <- if (isTRUE(case$compatibility)) 4L else case$blocks
    path <- file.path(case_dir, "samples.pileup")
    writeLines(make_lines(case$samples, loci), path)
    index <- environment$newpat_dnp_index(path)
    if (isTRUE(case$compatibility)) index$repeated_qname_rows <- 1L
    labels <- data.frame(df.chr = paste0("chr1:", seq_len(2L * loci)),
                         uniq = rep(seq_len(loci), each = 2L))
    refs <- data.frame(POS = paste0("locus-", seq_len(loci)), stringsAsFactors = FALSE)
    plan <- environment$newpat_dnp_plan(index, labels, refs, max_loci = 1L, max_bytes = 1024L)
    if (isTRUE(case$oversize)) plan$max_bytes <- 1L
    check(length(plan$blocks) == case$blocks)
    if (isTRUE(case$compatibility)) {
      check(identical(plan$compatibility_reasons, "legacy-repeated-qname-within-position"))
      check(identical(plan$blocks[[1L]]$row_ids, seq_len(2L * loci)))
    }
    selections <- lapply(seq_len(case$samples), selected_columns)
    computations <- lapply(seq_len(case$samples), function(sample_number) {
      force(sample_number)
      function(pileup, block_labels, block_refs) {
        stopifnot(own_connections(index$path) == 1L,
                  identical(names(pileup), paste0("V", selections[[sample_number]])),
                  identical(paste0(pileup$V1, ":", pileup$V2), block_labels$df.chr))
        # The first wave cannot finish until all permitted workers have really
        # entered computation. This proves overlap without a timing threshold.
        marker <- file.path(barrier, paste(sample_number, block_refs$POS[[1L]], sep = "-"))
        writeLines(as.character(Sys.getpid()), marker)
        deadline <- proc.time()[["elapsed"]] + 5
        while (length(list.files(barrier)) < expected_workers &&
               proc.time()[["elapsed"]] < deadline) Sys.sleep(0.005)
        stopifnot(length(list.files(barrier)) >= expected_workers)
        qnames <- pileup[[paste0("V", 7L + (sample_number - 1L) * 4L)]]
        list(final = data.frame(locus = block_refs$POS, sample = sample_number,
                                reads = paste(qnames, collapse = ","), stringsAsFactors = FALSE),
             sort_keys = block_refs$POS, pid = Sys.getpid())
      }
    })
    progress_events <- vector("list", case$samples)
    progress <- function(sample_number, completed, total) {
      stopifnot(Sys.getpid() == parent_pid, total == loci)
      progress_events[[sample_number]] <<- c(progress_events[[sample_number]], completed)
    }
    environment$newpat_parallel_lapply <- production_lapply
    if (isTRUE(case$reverse_callbacks)) {
      environment$newpat_parallel_lapply <- function(X, FUN, ..., label, workers = NULL,
                                                    memory_mib = NULL, on_result = NULL) {
        values <- production_lapply(X, FUN, ..., label = label, workers = workers,
                                    memory_mib = memory_mib)
        for (number in rev(seq_along(values))) on_result(number, values[[number]])
        values
      }
    }
    check(own_connections(index$path) == 0L)
    actual <- environment$newpat_dnp_process_samples(index, plan, labels, refs, computations,
                                                    progress, columns = selections)
    check(own_connections(index$path) == 0L)
    check(actual$workers == expected_workers)
    expected_tasks <- if (is.null(case$tasks)) case$samples * case$blocks else case$tasks
    check(actual$task_count == expected_tasks)
    check(actual$totals$sample_block_count == case$samples * case$blocks)
    check(actual$totals$block_read_count == expected_tasks)
    check(actual$totals$block_compute_seconds >= 0 && actual$totals$block_read_seconds >= 0)
    check(actual$totals$block_logical_bytes_read == sum(index$lengths) * expected_tasks / case$blocks)
    check(actual$observed_workers == expected_workers)
    if (is.null(case$tasks) || case$samples == 2L) {
      check(actual$observed_samples == min(expected_workers, case$samples))
    }
    check(length(actual$samples) == case$samples)
    for (sample_number in seq_len(case$samples)) {
      sample <- actual$samples[[sample_number]]
      check(length(sample$results) == case$blocks)
      check(identical(unlist(lapply(sample$results, function(value) value$final$locus),
                             use.names = FALSE), refs$POS))
      check(all(vapply(sample$results, function(value) all(value$final$sample == sample_number), logical(1))))
      expected_progress <- cumsum(vapply(plan$blocks, function(block) length(block$locus_ids), integer(1)))
      check(identical(progress_events[[sample_number]], expected_progress))
      check(all(vapply(sample$results, function(value) {
        if (expected_workers == 1L) value$pid == parent_pid else value$pid != parent_pid
      }, logical(1))))
      for (block_number in seq_along(plan$blocks)) {
        connection <- file(index$path, "rb")
        # Independent full-column read and subset establish correct sample
        # values; dispatcher results cannot pass merely by retaining labels.
        full <- environment$newpat_dnp_read(index, plan$blocks[[block_number]]$row_ids, connection)
        close(connection)
        expected_reads <- paste(full[[paste0("V", 7L + (sample_number - 1L) * 4L)]], collapse = ",")
        check(all(sample$results[[block_number]]$final$reads == expected_reads))
      }
    }
    records <- unlist(lapply(list.files(trace, full.names = TRUE), readLines), use.names = FALSE)
    records <- lapply(records, jsonlite::fromJSON)
    plans <- Filter(function(value) value$event == "plan", records)
    check(length(plans) == 1L && plans[[1L]]$label == "dnp-sample-blocks")
    check(plans[[1L]]$workers == expected_workers && plans[[1L]]$tasks == actual$task_count)
    intervals <- Filter(function(value) value$event %in% c("task-start", "task-end"), records)
    check(length(intervals) == 2L * actual$task_count)
    times <- vapply(intervals, function(value) value$observed_at_unix, numeric(1))
    deltas <- vapply(intervals, function(value) if (value$event == "task-start") 1L else -1L, integer(1))
    occupancy <- cumsum(deltas[order(times, deltas)])
    check(min(occupancy) >= 0L && tail(occupancy, 1L) == 0L && max(occupancy) == expected_workers)
    check(all(vapply(intervals, function(value) value$coordinator_pid == parent_pid, logical(1))))
  }

  # A failing sample-block task must fail the whole dispatch, not return a
  # shorter collection or leave an inherited parent file handle behind.
  environment$newpat_parallel_lapply <- production_lapply
  controlled_workers <- 2L
  Sys.setenv(NEWPAT_EXECUTION_MODE = "auto")
  failing <- list(function(...) { Sys.sleep(0.2); list(final = data.frame()) },
                  function(...) stop("scientific failure in sample two"))
  expect_error(environment$newpat_dnp_process_samples(index, plan, labels, refs, failing,
                workers = 2L, columns = selections[1:2]), "scientific failure in sample two")
  Sys.setenv(NEWPAT_DNP_OPTIMIZED_IO = "1")
  expect_error(environment$newpat_dnp_process_samples(index, plan, labels, refs, failing,
                workers = 1L, columns = selections[1:2]), "scientific failure in sample two")
  check(own_connections(index$path) == 0L)
  check(length(parallel::mccollect(wait = FALSE)) == 0L)
  previous_directory <- setwd(directory)
  on.exit(setwd(previous_directory), add = TRUE, after = FALSE)
  dir.create("work")
  path <- file.path("work", "dnp-block-progress.json")
  succeed <- function(pileup, block_labels, block_refs) nrow(pileup)
  callbacks <- rep(list(succeed), 3L)
  run <- function() environment$newpat_dnp_process_samples(index, plan, labels, refs,
    callbacks, workers = 1L, columns = selections)
  run()
  check(!file.exists(path))
  Sys.setenv(NEWPAT_PERFORMANCE_DIR = directory)
  callbacks[[2L]] <- function(pileup, block_labels, block_refs) {
    if (block_refs$POS[[1L]] == refs$POS[[2L]]) stop("interrupted in second group")
    nrow(pileup)
  }
  expect_error(run(), "interrupted in second group")
  snapshot <- jsonlite::fromJSON(path)
  check(snapshot$completed_groups == 1L && snapshot$planned_groups == length(plan$blocks))
  check(snapshot$sample_block_count == 3L && snapshot$block_read_count == 1L)
  check(snapshot$block_logical_bytes_read == plan$blocks[[1L]]$raw_bytes)
  callbacks[[2L]] <- succeed
  all_done <- run()
  snapshot <- jsonlite::fromJSON(path)
  check(snapshot$completed_groups == snapshot$planned_groups)
  check(isTRUE(all.equal(unlist(snapshot[names(all_done$totals)]), unlist(all_done$totals), tolerance = 1e-12)))
  check(identical(list.files("work", all.files = TRUE, no.. = TRUE), basename(path)))
  # A missing diagnostics directory must not affect dispatch or its results.
  unlink("work", recursive = TRUE)
  check(identical(lapply(run()$samples, "[[", "results"), lapply(all_done$samples, "[[", "results")))
  cat("DNP multi-sample dispatcher:", checks,
      "checks passed (2/3/5/9 samples, one global pool, resource caps, actual overlap,",
      "serial execution, ordered identities, compatibility, selective types, progress and errors).\n")
}
main()
