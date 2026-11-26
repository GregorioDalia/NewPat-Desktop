#!/usr/bin/env Rscript
# Focused dispatcher check: real forked R workers and pileup reads; synthetic
# scientific calculation. The complete scientific equations are qualified by
# check_blocks.R and the frozen 0.8.5 end-to-end comparisons.
root <- normalizePath(commandArgs(trailingOnly = TRUE)[[1L]], mustWork = TRUE)
source(file.path(root, "src/nipat_scientific/dnp_blocks.R"))

main <- function() {
  path <- tempfile(fileext = ".pileup")
  on.exit(unlink(path))
  writeLines(paste("chr1", 1:8, "A", 1, "A", "I", paste0("read", 1:8), sep = "\t"), path)
  index <- nipat_dnp_index(path)
  labels <- data.frame(df.chr = paste0("chr1:", 1:8), uniq = rep(1:4, each = 2L))
  refs <- data.frame(POS = c("d", "c", "b", "a"))
  plan <- nipat_dnp_plan(index, labels, refs, max_loci = 1L, max_bytes = 1024L)
  stopifnot(length(plan$blocks) == 4L)

  # Exercise the block dispatcher independently of the host's CPU/RAM quota.
  # The shared scheduler's resource caps are tested in its own focused checks.
  # Deliberately deliver callbacks in reverse order, but return values in input
  # order, matching the shared scheduler's completion/result-order contract.
  scheduler <- function(X, FUN, ..., label, workers = NULL, memory_mib = NULL,
                        on_result = NULL) {
    workers <- if (is.null(workers)) 2L else as.integer(workers)
    values <- if (workers > 1L) parallel::mclapply(X, FUN, ..., mc.cores = workers,
                                                 mc.preschedule = FALSE) else lapply(X, FUN, ...)
    failed <- which(vapply(values, inherits, logical(1), "try-error"))
    if (length(failed)) stop("worker failure: ", values[[failed[[1L]]]])
    for (number in rev(seq_along(values))) on_result(number, values[[number]])
    attr(values, "workers") <- workers
    values
  }
  assign("nipat_parallel_lapply", scheduler, envir = .GlobalEnv)
  on.exit(rm("nipat_parallel_lapply", envir = .GlobalEnv), add = TRUE)

  parent_pid <- Sys.getpid()
  own_connection <- function() {
    connections <- showConnections(all = TRUE)
    sum(connections[, "description"] == index$path)
  }
  compute <- function(pileup, block_labels, block_refs) {
    stopifnot(own_connection() == 1L,
              identical(paste0(pileup$V1, ":", pileup$V2), block_labels$df.chr))
    list(final = data.frame(locus = block_refs$POS,
                           reads = paste(pileup$V7, collapse = ",")),
         sort_keys = block_refs$POS, pid = Sys.getpid())
  }
  events <- list()
  progress <- function(completed, total) {
    stopifnot(Sys.getpid() == parent_pid, total == 4L)
    events[[length(events) + 1L]] <<- completed
  }
  stopifnot(own_connection() == 0L)
  serial <- nipat_dnp_process_blocks(index, plan, labels, refs, compute, progress, workers = 1L)
  stopifnot(own_connection() == 0L, identical(unlist(events), 1:4))
  events <- list()
  forked <- nipat_dnp_process_blocks(index, plan, labels, refs, compute, progress, workers = 2L)
  stopifnot(own_connection() == 0L, identical(unlist(events), 1:4),
            identical(nipat_dnp_combine(serial$results), nipat_dnp_combine(forked$results)),
            identical(forked$workers, 2L),
            all(vapply(serial$results, function(value) value$pid == parent_pid, logical(1))),
            all(vapply(forked$results, function(value) value$pid != parent_pid, logical(1))),
            length(unique(vapply(forked$results, function(value) value$pid, integer(1)))) >= 2L,
            identical(vapply(forked$results, function(value) value$final$reads, character(1)),
                      c("read1,read2", "read3,read4", "read5,read6", "read7,read8")))

  # Errors must propagate to the caller and leave no parent file handle or
  # misleading completed-locus events. They cannot become partial results.
  events <- list()
  failed <- tryCatch({
    suppressWarnings(nipat_dnp_process_blocks(index, plan, labels, refs,
      function(...) stop("deliberate scientific failure"), progress, workers = 2L))
    NULL
  }, error = identity)
  stopifnot(inherits(failed, "error"),
            grepl("deliberate scientific failure", conditionMessage(failed)),
            own_connection() == 0L, length(events) == 0L)

  # Integrate with the production scheduler as well. The host may legitimately
  # allow only one worker; when resources permit, this executes real child
  # processes and confirms the global outer/inner budget is never multiplied.
  source(file.path(root, "src/nipat_scientific/parallel.R"), local = .GlobalEnv)
  policy_names <- c("NIPAT_EXECUTION_MODE", "NIPAT_MAX_WORKERS", "NIPAT_PARALLEL_CHILD")
  policy <- Sys.getenv(policy_names, unset = NA_character_)
  on.exit(for (name in names(policy)) {
    if (is.na(policy[[name]])) Sys.unsetenv(name) else do.call(Sys.setenv, setNames(list(policy[[name]]), name))
  }, add = TRUE)
  Sys.setenv(NIPAT_EXECUTION_MODE = "auto", NIPAT_MAX_WORKERS = "2")
  Sys.unsetenv("NIPAT_PARALLEL_CHILD")
  events <- list()
  production <- nipat_dnp_process_blocks(index, plan, labels, refs, compute, progress)
  stopifnot(identical(nipat_dnp_combine(serial$results), nipat_dnp_combine(production$results)),
            identical(unlist(events), 1:4), own_connection() == 0L,
            production$workers %in% 1:2)
  if (production$workers > 1L) {
    stopifnot(all(vapply(production$results, function(value) value$pid != parent_pid, logical(1))),
              length(unique(vapply(production$results, function(value) value$pid, integer(1)))) >= 2L)
  }
  nested <- nipat_parallel_lapply(1:2, function(sample_number) {
    sample_pid <- Sys.getpid()
    inner <- nipat_dnp_process_blocks(index, plan, labels, refs, compute,
      progress = function(...) stopifnot(Sys.getpid() == sample_pid))
    list(workers = inner$workers, pid = sample_pid,
         task_pids = vapply(inner$results, function(value) value$pid, integer(1)),
         scientific = nipat_dnp_combine(inner$results))
  }, label = "dnp-test-samples", workers = 2L)
  for (sample in nested) {
    stopifnot(identical(sample$scientific, nipat_dnp_combine(serial$results)))
    if (attr(nested, "workers") > 1L) {
      stopifnot(sample$workers == 1L, all(sample$task_pids == sample$pid))
    }
  }
  Sys.setenv(NIPAT_EXECUTION_MODE = "serial")
  production_serial <- nipat_dnp_process_blocks(index, plan, labels, refs, compute, workers = 2L)
  stopifnot(production_serial$workers == 1L,
            all(vapply(production_serial$results, function(value) value$pid == parent_pid, logical(1))))
  Sys.setenv(NIPAT_EXECUTION_MODE = "auto")
  production_error <- tryCatch({
    nipat_dnp_process_blocks(index, plan, labels, refs,
      function(...) stop("production worker failure"), workers = 2L)
    NULL
  }, error = identity)
  stopifnot(inherits(production_error, "error"),
            grepl("production worker failure", conditionMessage(production_error)),
            own_connection() == 0L)
  cat("DNP production scheduler integration:", production$workers,
      "block worker(s),", attr(nested, "workers"), "sample worker(s); nested budget and serial override passed.\n")

  # The default changed, while indivisible groups remain safe and the memory
  # scheduling estimate uses their actual size, including compatibility mode.
  old <- Sys.getenv(c("NIPAT_DNP_BLOCK_BYTES", "NIPAT_DNP_BLOCK_LOCI"), unset = NA_character_)
  on.exit(for (name in names(old)) {
    if (is.na(old[[name]])) Sys.unsetenv(name) else do.call(Sys.setenv, setNames(list(old[[name]]), name))
  }, add = TRUE)
  Sys.unsetenv(names(old))
  defaults <- nipat_dnp_plan(index, labels, refs)
  stopifnot(defaults$requested_max_bytes == 32 * 1024^2, defaults$max_bytes > 0,
            defaults$max_bytes <= defaults$requested_max_bytes, defaults$max_loci == 64L)
  oversize <- plan
  oversize$blocks[[1L]]$raw_bytes <- 64 * 1024^2
  stopifnot(nipat_dnp_worker_memory_mib(oversize) == 512 + 48 * 64)
  # Resource-derived partitions must retain numerical values, read identity,
  # and output ordering. Scale index byte metadata to exercise realistic raw
  # targets without storing multi-megabyte read names in this scheduler test.
  # Scientific equations remain covered by the frozen-reference checks.
  resource_previous <- Sys.getenv(c("NIPAT_FIXED_RESOURCE_BUDGET", "NIPAT_MAX_WORKERS"), unset = NA_character_)
  on.exit(for (name in names(resource_previous)) {
    if (is.na(resource_previous[[name]])) Sys.unsetenv(name) else
      do.call(Sys.setenv, setNames(list(resource_previous[[name]]), name))
  }, add = TRUE)
  Sys.setenv(NIPAT_MAX_WORKERS = "4")
  numerical <- function(pileup, block_labels, block_refs) {
    ids <- unique(block_labels$uniq)
    rows <- lapply(ids, function(id) {
      selected <- paste0(pileup$V1, ":", pileup$V2) %in% block_labels$df.chr[block_labels$uniq == id]
      data.frame(total_count = sum(pileup$V4[selected]),
                 ref_count = sum(pileup$V5[selected] == "A"),
                 reads = paste(pileup$V7[selected], collapse = ","), stringsAsFactors = FALSE)
    })
    list(final = cbind(locus = block_refs$POS, do.call(rbind, rows)), sort_keys = block_refs$POS)
  }
  con <- file(index$path, "rb")
  all_rows <- nipat_dnp_read(index, seq_len(index$rows), con)
  close(con)
  expected <- nipat_dnp_combine(list(numerical(all_rows, labels, refs)))
  planning_index <- index
  planning_index$lengths[] <- 1024^2
  resource_env <- function(memory, cpus, rss_kib) {
    env <- new.env(parent = globalenv())
    sys.source(file.path(root, "src/nipat_scientific/parallel.R"), env)
    sys.source(file.path(root, "src/nipat_scientific/dnp_blocks.R"), env)
    env$nipat_parallel_cpu_count <- function() cpus
    env$nipat_parallel_lines <- function(path) {
      if (path == "/proc/self/status") paste("VmRSS:", rss_kib, "kB") else character()
    }
    Sys.setenv(NIPAT_FIXED_RESOURCE_BUDGET = jsonlite::toJSON(list(
      interface = "nipat-fixed-resources-v1", source_version = "resource-profile-fixture",
      memory_capacity_mib = memory, cpu_limit = cpus, worker_ceiling = cpus,
      memory_reserve_fraction = 0.20), auto_unbox = TRUE))
    env
  }
  for (memory in c(2048, 4096, 8192)) {
    env <- resource_env(memory, 4L, 262144)
    derived <- env$nipat_dnp_plan(planning_index, labels, refs)
    stopifnot(derived$requested_max_bytes == 32 * 1024^2,
              derived$max_bytes > 0, derived$max_bytes <= derived$requested_max_bytes,
              length(derived$blocks) == 1L)
    result <- env$nipat_dnp_process_blocks(index, derived, labels, refs, numerical)
    stopifnot(result$workers == 1L,
              identical(env$nipat_dnp_combine(result$results), expected))
    # A whole window over the derived byte target is retained intact, and its
    # actual size reduces the pool budget rather than truncating observations.
    large <- planning_index
    large$lengths[1:2] <- 32 * 1024^2
    indivisible <- env$nipat_dnp_plan(large, labels, refs)
    stopifnot(identical(indivisible$blocks[[1L]]$row_ids, 1:2),
              indivisible$blocks[[1L]]$raw_bytes > indivisible$max_bytes,
              env$nipat_parallel_budget(length(indivisible$blocks),
                memory_mib = env$nipat_dnp_worker_memory_mib(indivisible))$workers == 1L)
  }
  # Replay the deep synthetic workload as byte metadata. These checks verify
  # plans and peak-worker estimates, without imposing wall-clock thresholds.
  count <- 64L
  depth_refs <- data.frame(POS = paste0("L", seq_len(count)))
  depth_labels <- data.frame(df.chr = paste0("chr1:", seq_len(count)), uniq = seq_len(count))
  # Exactly 43,522,784 bytes as in both deep reports.
  depth_index <- list(chromosomes = "chr1", chromosome = rep(1L, count),
    positions = seq_len(count), lengths = c(rep(680040, 8L), rep(680044, 56L)),
    classes = index$classes)
  stopifnot(sum(depth_index$lengths) == 43522784)
  for (profile in list(list(cpus = 4L, capacity = 3905, blocks = 3L),
                       list(cpus = 32L, capacity = 15858, blocks = 2L))) {
    Sys.unsetenv("NIPAT_MAX_WORKERS")
    env <- resource_env(profile$capacity, profile$cpus, 202752)
    deep <- env$nipat_dnp_plan(depth_index, depth_labels, depth_refs)
    sizes <- vapply(deep$blocks, function(block) block$raw_bytes, numeric(1))
    workers <- env$nipat_parallel_budget(length(sizes), env$nipat_dnp_worker_memory_mib(deep))
    stopifnot(length(sizes) == profile$blocks, workers$workers == 2L,
              identical(unlist(lapply(deep$blocks, `[[`, "locus_ids")), seq_len(count)),
              identical(unlist(lapply(deep$blocks, `[[`, "row_ids")), seq_len(count)),
              sum(sizes) == sum(depth_index$lengths), all(sizes <= deep$max_bytes),
              workers$workers * workers$memory_per_worker_mib + workers$coordinator_rss_mib <=
                workers$memory_budget_mib)
    # User-selected small targets and serial operation remain available.
    small <- env$nipat_dnp_plan(depth_index, depth_labels, depth_refs, max_bytes = 1024^2)
    stopifnot(small$requested_max_bytes == 1024^2, small$max_bytes <= 1024^2,
              length(small$blocks) == count)
    Sys.setenv(NIPAT_MAX_WORKERS = "2")
    capped <- env$nipat_dnp_plan(depth_index, depth_labels, depth_refs, max_bytes = 1024^2)
    stopifnot(capped$max_bytes == 1024^2, length(capped$blocks) == count)
    Sys.setenv(NIPAT_EXECUTION_MODE = "serial")
    serial_depth <- env$nipat_dnp_plan(depth_index, depth_labels, depth_refs)
    stopifnot(identical(vapply(serial_depth$blocks, function(b) length(b$locus_ids), integer(1)),
                        c(49L, 15L)), env$nipat_parallel_workers(2) == 1L)
    Sys.setenv(NIPAT_EXECUTION_MODE = "auto")
  }
  # Recreate the measured Windows pileup size with equal synthetic loci to
  # check how block size and worker count adapt to two resource budgets.
  count <- 844L
  total_bytes <- 474497291
  rows <- seq_len(count)
  real_size_index <- list(chromosomes = "chr1", chromosome = rep(1L, count),
    positions = rows, lengths = total_bytes %/% count + (rows <= total_bytes %% count),
    classes = index$classes)
  real_size_labels <- data.frame(df.chr = paste0("chr1:", rows), uniq = rows)
  real_size_refs <- data.frame(POS = as.character(rows))
  Sys.unsetenv("NIPAT_MAX_WORKERS")
  for (profile in list(list(cpu = 4L, ram = 3905, rss = 192, target = 4827818, blocks = 106L, pool = 4L),
                       list(cpu = 32L, ram = 15858, rss = 191, target = 27809109, blocks = 18L, pool = 7L))) {
    env <- resource_env(profile$ram, profile$cpu, profile$rss * 1024)
    sized <- env$nipat_dnp_plan(real_size_index, real_size_labels, real_size_refs)
    peak <- env$nipat_dnp_worker_memory_mib(sized)
    pool <- env$nipat_parallel_budget(length(sized$blocks), peak)
    stopifnot(sized$max_bytes == profile$target, length(sized$blocks) == profile$blocks,
              pool$workers == profile$pool,
              pool$coordinator_rss_mib + pool$workers * peak <= pool$memory_budget_mib,
              identical(unlist(lapply(sized$blocks, `[[`, "locus_ids")), rows))
  }
  # Moving a large run across the translated-worker threshold must not
  # fragment it into a separate read/task per locus to expose extra workers.
  Sys.setenv(NIPAT_DNP_LIMA_ARM64 = "1", NIPAT_DNP_OPTIMIZED_IO = "1")
  capacities <- c(4096L, 4097L, 5120L, 6144L, 7168L, 8192L)
  expected_workers <- c(2L, 2L, 2L, 3L, 3L, 4L)
  blocks <- integer(length(capacities))
  for (i in seq_along(capacities)) {
    env <- resource_env(capacities[[i]], 8L, 192 * 1024)
    plan <- env$nipat_dnp_plan(real_size_index, real_size_labels, real_size_refs)
    peak <- env$nipat_dnp_worker_memory_mib(plan)
    blocks[[i]] <- length(plan$blocks)
    pool <- env$nipat_parallel_budget(blocks[[i]], peak, workers = env$nipat_dnp_r_workers())
    stopifnot(plan$max_bytes >= 16 * 1024^2, pool$workers == expected_workers[[i]],
              pool$coordinator_rss_mib + pool$workers * peak <= pool$memory_budget_mib,
              identical(unlist(lapply(plan$blocks, `[[`, "locus_ids")), rows))
  }
  stopifnot(blocks[[1L]] == 22L, blocks[[2L]] == blocks[[1L]])
  Sys.unsetenv(c("NIPAT_DNP_LIMA_ARM64", "NIPAT_DNP_OPTIMIZED_IO"))
  cat("DNP deep scheduling: VM profiles, both block limits, ordered loci and estimated concurrent memory passed.\n")
  cat("DNP resource profiles: 2/4/8 GiB fixed budgets preserve numeric values, read identity, row order and indivisible windows.\n")
  cat("DNP parallel dispatcher: ordered fork results, isolated connections, parent progress, errors and limits passed.\n")
}
main()
