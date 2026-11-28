# Bounded DNP input handling. Scientific transformations remain in DNPcall.R.
# Byte limits describe raw input, not a guarantee about R's resident memory.

newpat_dnp_number <- function(name, default) {
  text <- Sys.getenv(name, unset = as.character(default))
  value <- suppressWarnings(as.numeric(text))
  if (length(value) != 1L || !is.finite(value) || value < 1 || value != floor(value)) {
    stop(name, " must be a positive whole number")
  }
  value
}

newpat_dnp_index <- function(path, empty_samples = NULL) {
  started <- proc.time()[["elapsed"]]
  con <- file(path, open = "rb")
  on.exit(close(con))
  capacity <- 4096L
  offsets <- lengths <- positions <- numeric(capacity)
  chromosome <- integer(capacity)
  reference <- character(capacity)
  dictionary <- character()
  classes <- NULL
  if (!is.null(empty_samples)) {
    classes <- c("character", "integer", "character",
                 rep(c("integer", "character", "character", "character"), empty_samples))
  }
  count <- 0L
  repeated_qname_rows <- 0L
  repeat {
    offset <- seek(con)
    line <- readLines(con, n = 1L, warn = FALSE)
    if (!length(line)) break
    fields <- strsplit(line, "\t", fixed = TRUE)[[1L]]
    if (length(fields) < 7L || (length(fields) - 3L) %% 4L != 0L ||
        (!is.null(classes) && length(fields) != length(classes))) stop("Invalid DNP pileup columns")
    if (is.null(classes)) {
      classes <- c("character", "integer", "character",
                   rep(c("integer", "character", "character", "character"), (length(fields) - 3L) / 4L))
    }
    # Duplicate QNAMEs at one position can make legacy grouping infer a
    # middle pair belonging to another window. Preserve its global behavior;
    # ordinary reuse across different loci does not trigger this condition.
    if (any(vapply(seq.int(7L, length(fields), by = 4L), function(column) {
      anyDuplicated(strsplit(fields[[column]], ",", fixed = TRUE)[[1L]]) > 0L
    }, logical(1)))) repeated_qname_rows <- repeated_qname_rows + 1L
    count <- count + 1L
    if (count > capacity) {
      capacity <- capacity * 2L
      length(offsets) <- length(lengths) <- length(positions) <- capacity
      length(chromosome) <- length(reference) <- capacity
    }
    offsets[[count]] <- offset
    lengths[[count]] <- seek(con) - offset
    code <- match(fields[[1L]], dictionary)
    if (is.na(code)) {
      dictionary <- c(dictionary, fields[[1L]])
      code <- length(dictionary)
    }
    chromosome[[count]] <- code
    positions[[count]] <- as.numeric(fields[[2L]])
    reference[[count]] <- fields[[3L]]
  }
  if (!count && is.null(classes)) stop("DNP pileup contains no rows")
  rows <- seq_len(count)
  positions <- positions[rows]
  if (any(!is.finite(positions) | positions < 1 | positions > .Machine$integer.max |
          positions != floor(positions))) stop("Invalid DNP pileup position")
  list(path = normalizePath(path, mustWork = TRUE), offsets = offsets[rows],
       lengths = lengths[rows], chromosome = chromosome[rows],
       chromosomes = dictionary, positions = as.integer(positions),
       reference = reference[rows], classes = classes,
       rows = count, bytes = sum(lengths[rows]), repeated_qname_rows = repeated_qname_rows,
       elapsed_seconds = unname(proc.time()[["elapsed"]] - started))
}

# Two R workers outperformed four on translated AMD64 in a 3,905 MiB
# guest. Apply that ceiling to similar run allocations, including tighter
# container or cgroup limits. Acquisition has a separate workload model.
newpat_dnp_r_workers <- function() {
  if (!identical(Sys.getenv("NEWPAT_DNP_LIMA_ARM64"), "1") ||
      nzchar(Sys.getenv("NEWPAT_MAX_WORKERS"))) return(NULL)
  capacity <- newpat_parallel_capacity()$memory_capacity_mib
  if (!is.null(capacity) && capacity <= 4096) 2L else NULL
}

newpat_dnp_target_bytes <- function(requested, tasks = .Machine$integer.max, share_samples = 1L) {
  if (identical(Sys.getenv("NEWPAT_EXECUTION_MODE", "auto"), "serial") ||
      !exists("newpat_parallel_budget", mode = "function")) return(requested)
  # Keep useful work in each fork: an additional parallel lane can justify
  # smaller blocks, but never size every block for the machine's CPU ceiling.
  # Half the requested grain bounds the fragmentation incurred for parallelism.
  budget <- newpat_parallel_budget(tasks, memory_mib = newpat_dnp_estimate_mib(requested / 2),
                                  workers = newpat_dnp_r_workers())
  remaining <- budget$memory_budget_mib - budget$coordinator_rss_mib
  if (!length(remaining) || !is.finite(remaining)) return(requested)
  full_block <- newpat_dnp_estimate_mib(requested)
  workers <- min(budget$workers, max(1, ceiling(remaining / full_block)))
  # The optimized reader can share a block across samples. Size its lanes for
  # useful blocks (at least half the requested grain when it fits). Estimating
  # lanes at one byte could split every locus into a separate read and fork.
  if (remaining < 2 * full_block && !identical(Sys.getenv("NEWPAT_DNP_OPTIMIZED_IO"), "1")) {
    # When memory is tight, smaller blocks can keep more cores busy.
    # Use this division only if the job has enough independent tasks.
    # A short job can still use the coarser plan when it has too few tasks
    # at the requested size to keep the finer-grained pool busy.
    fine <- newpat_parallel_budget(.Machine$integer.max, memory_mib = newpat_dnp_estimate_mib(1),
                                  workers = newpat_dnp_r_workers())
    if (tasks >= fine$workers) {
      workers <- fine$workers
      remaining <- fine$memory_budget_mib - fine$coordinator_rss_mib
      if (!length(remaining) || !is.finite(remaining)) return(requested)
    }
  }
  allocation <- floor(remaining / workers)
  # A single worker can still require smaller blocks to fit the fixed budget.
  # At or below the base footprint, use one indivisible locus group per block.
  # Only reserve additional heap when the budget constrains the target and
  # there are enough sample/block pairs for workers to share projections.
  expansion <- 48
  if (share_samples >= 2L * ceiling(workers / ceiling(tasks / share_samples))) expansion <- 56
  max(1, min(requested, floor((allocation - 512) / expansion * 1024^2)))
}

newpat_dnp_plan <- function(index, labels, ref_alt,
                           max_loci = newpat_dnp_number("NEWPAT_DNP_BLOCK_LOCI", 64),
                           max_bytes = newpat_dnp_number("NEWPAT_DNP_BLOCK_BYTES", 32 * 1024^2)) {
  requested_max_bytes <- max_bytes
  # Approximate the number of tasks before reducing any blocks. Independent
  # samples share the pool. The final partition enforces complete locus groups.
  coarse_blocks <- max(1, ceiling(sum(index$lengths) / max_bytes), ceiling(nrow(ref_alt) / max_loci))
  samples <- max(1, (length(index$classes) - 3L) / 4L)
  keys <- paste(index$chromosomes[index$chromosome], index$positions, sep = ":")
  by_coordinate <- split(seq_along(keys), keys)
  unmatched <- sum(!keys %in% labels$df.chr)
  reasons <- character()
  if (unmatched) reasons <- c(reasons, "legacy-unmatched-coordinate-groups")
  if (!is.null(index$repeated_qname_rows) && index$repeated_qname_rows > 0L) {
    reasons <- c(reasons, "legacy-repeated-qname-within-position")
  }
  share_samples <- if (!length(reasons) && identical(Sys.getenv("NEWPAT_DNP_OPTIMIZED_IO"), "1"))
    samples else 1L
  max_bytes <- newpat_dnp_target_bytes(requested_max_bytes, coarse_blocks * samples, share_samples)
  if (length(reasons)) {
    return(list(blocks = list(list(locus_ids = seq_len(nrow(ref_alt)),
      row_ids = seq_along(keys), raw_bytes = sum(index$lengths))),
      max_loci = max_loci, max_bytes = max_bytes, requested_max_bytes = requested_max_bytes,
      compatibility_reasons = reasons, unmatched_rows = unmatched))
  }
  # Equal effective POS must stay together to preserve all merges.
  effective <- unique(ref_alt$POS)
  group_ids <- match(ref_alt$POS, effective)
  groups <- split(seq_len(nrow(ref_alt)), factor(group_ids, levels = seq_along(effective)))
  # Index panel membership and raw coordinates once. Repeated which()/%in%
  # scans and named-list lookups otherwise make planning quadratic in the
  # number of panel loci, before any scientific computation begins.
  label_groups <- group_ids[match(labels$uniq, seq_len(nrow(ref_alt)))]
  coordinate_indices <- match(labels$df.chr, names(by_coordinate))
  group_coordinates <- split(coordinate_indices,
    factor(label_groups, levels = seq_along(effective)))
  blocks <- list()
  active_ids <- active_rows <- integer()
  append_block <- function() {
    if (length(active_ids)) {
      blocks[[length(blocks) + 1L]] <<- list(
        locus_ids = active_ids, row_ids = sort(active_rows),
        raw_bytes = sum(index$lengths[active_rows])
      )
    }
  }
  for (group_number in seq_along(groups)) {
    ids <- groups[[group_number]]
    coordinates <- unique(group_coordinates[[group_number]])
    rows <- unique(unlist(by_coordinate[coordinates], use.names = FALSE))
    if (is.null(rows)) rows <- integer()
    combined <- union(active_rows, rows)
    if (length(active_ids) && (length(active_ids) + length(ids) > max_loci ||
                              sum(index$lengths[combined]) > max_bytes)) {
      append_block()
      active_ids <- active_rows <- integer()
      combined <- rows
    }
    active_ids <- c(active_ids, ids)
    active_rows <- combined
  }
  append_block()
  list(blocks = blocks, max_loci = max_loci, max_bytes = max_bytes, requested_max_bytes = requested_max_bytes,
       compatibility_reasons = character(), unmatched_rows = 0L)
}

newpat_dnp_read_ranges <- function(index, rows, max_bytes = 8 * 1024^2) {
  # Merge only byte-adjacent rows in the REQUESTED order. Sorting or unique()
  # here would change callers that repeat or reverse rows. Keep each temporary
  # read bounded, except for an indivisible line already larger than the target.
  max_bytes <- min(max_bytes, .Machine$integer.max - 1)
  count <- length(rows)
  offsets <- lengths <- numeric(count)
  first <- last <- integer(count)
  ranges <- 0L
  for (number in seq_along(rows)) {
    row <- rows[[number]]
    offset <- index$offsets[[row]]
    size <- index$lengths[[row]]
    if (ranges > 0L && offset == offsets[[ranges]] + lengths[[ranges]] &&
        lengths[[ranges]] + size <= max_bytes) {
      lengths[[ranges]] <- lengths[[ranges]] + size
      last[[ranges]] <- number
    } else {
      ranges <- ranges + 1L
      offsets[[ranges]] <- offset
      lengths[[ranges]] <- size
      first[[ranges]] <- last[[ranges]] <- number
    }
  }
  selected <- seq_len(ranges)
  list(offsets = offsets[selected], lengths = lengths[selected],
       first = first[selected], last = last[selected])
}

# samtools emits unquoted tab-separated ASCII. Base R's general table scanner
# spends substantial time on deep joint pileups even when most columns are
# skipped. Decode ordinary rows one read range at a time and retain only the
# requested columns. NULL hands all other input back to the original scanner.
newpat_dnp_parse_tabs <- function(chunks, row_count, classes, column_names) {
  selected <- which(classes != "NULL")
  if (anyNA(classes) || !length(selected) ||
      !all(classes[selected] %in% c("character", "integer"))) return(NULL)
  values <- lapply(classes[selected], function(kind) {
    if (kind == "integer") integer(row_count) else character(row_count)
  })
  written <- 0L
  for (chunk in chunks) {
    if (!endsWith(chunk, "\n") ||
        grepl("[^\t\n!-~]", chunk, perl = TRUE, useBytes = TRUE)) return(NULL)
    rows <- strsplit(chunk, "\n", fixed = TRUE)[[1L]]
    if (!length(rows) || written + length(rows) > row_count ||
        any(!nzchar(rows) | startsWith(rows, "\t") | endsWith(rows, "\t")) ||
        any(grepl("\t\t", rows, fixed = TRUE))) return(NULL)
    fields <- strsplit(rows, "\t", fixed = TRUE)
    if (any(lengths(fields) != length(classes))) return(NULL)
    target <- written + seq_along(rows)
    for (number in seq_along(selected)) {
      column <- selected[[number]]
      value <- vapply(fields, `[[`, character(1), column, USE.NAMES = FALSE)
      if (classes[[column]] == "integer") {
        if (!all(grepl("^(0|[1-9][0-9]{0,9})$", value))) return(NULL)
        value <- suppressWarnings(as.integer(value))
        if (anyNA(value)) return(NULL)
      }
      values[[number]][target] <- value
    }
    written <- written + length(rows)
  }
  if (written != row_count) return(NULL)
  names(values) <- column_names[selected]
  as.data.frame(values, stringsAsFactors = FALSE)
}

newpat_dnp_read <- function(index, rows, connection, columns = NULL) {
  classes <- index$classes
  column_names <- paste0("V", seq_along(classes))
  if (!is.null(columns)) {
    if (!length(columns) || anyNA(columns) || any(columns != as.integer(columns)) ||
        any(columns < 1L | columns > length(classes)) || anyDuplicated(columns)) {
      stop("Invalid DNP selected columns")
    }
    # Retain original pileup order and names, rather than renumbering a sample's
    # columns. Types still come from the complete global index, not this block.
    columns <- sort(as.integer(columns))
    classes[-columns] <- "NULL"
  }
  if (!length(rows)) {
    selected <- which(classes != "NULL")
    empty <- lapply(classes[selected], function(kind) switch(kind,
      logical = logical(), integer = integer(), numeric = numeric(),
      complex = complex(), character = character()))
    names(empty) <- column_names[selected]
    return(as.data.frame(empty, stringsAsFactors = FALSE))
  }
  read_row <- function(row) {
    seek(connection, where = index$offsets[[row]], origin = "start")
    readChar(connection, nchars = index$lengths[[row]], useBytes = TRUE)
  }
  offsets <- index$offsets[rows]
  adjacent <- length(rows) > 1L && any(
    head(offsets, -1L) + head(index$lengths[rows], -1L) == tail(offsets, -1L))
  if (!adjacent) {
    # Sparse/reversed requests cannot benefit from merging. Keep their old
    # direct path instead of allocating one range descriptor for every row.
    lines <- vapply(rows, read_row, character(1), USE.NAMES = FALSE)
  } else {
    ranges <- newpat_dnp_read_ranges(index, rows)
    lines <- vapply(seq_along(ranges$offsets), function(number) {
      first <- ranges$first[[number]]
      last <- ranges$last[[number]]
      if (first == last) return(read_row(rows[[first]]))
      seek(connection, where = ranges$offsets[[number]], origin = "start")
      warned <- FALSE
      value <- withCallingHandlers(
        readChar(connection, nchars = ranges$lengths[[number]], useBytes = TRUE),
        warning = function(warning) {
          warned <<- TRUE
          invokeRestart("muffleWarning")
        })
      # readChar can truncate at an embedded NUL. Preserve the former per-row
      # parsing and warnings on unusual bytes or a short read rather than losing
      # every following row in a combined interval. Normal samtools text is LF.
      if (warned || length(value) != 1L ||
          nchar(value, type = "bytes") != ranges$lengths[[number]]) {
        return(paste0(vapply(rows[seq.int(first, last)], read_row, character(1),
                            USE.NAMES = FALSE), collapse = ""))
      }
      value
    }, character(1), USE.NAMES = FALSE)
  }
  # Indivisible compatibility windows may exceed the ordinary 32 MiB grain.
  # Keep their existing parser and memory behavior.
  if (identical(Sys.getenv("NEWPAT_DNP_OPTIMIZED_IO"), "1") &&
      length(index$classes) > 7L && sum(index$lengths[rows]) <= 32 * 1024^2) {
    parsed <- newpat_dnp_parse_tabs(lines, length(rows), classes, column_names)
    if (!is.null(parsed)) return(parsed)
  }
  read.csv(text = paste0(lines, collapse = ""), quote = "", row.names = NULL,
           stringsAsFactors = FALSE, header = FALSE, sep = "\t",
           colClasses = classes, na.strings = NULL)
}

# Scheduling estimate, not an allocation limit: expanded observations, joins
# and R's own heap are larger than the raw pileup. Account for indivisible
# oversize/compatibility blocks instead of assuming the configured target held.
newpat_dnp_estimate_mib <- function(raw_bytes) ceiling(512 + 48 * raw_bytes / 1024^2)

newpat_dnp_worker_memory_mib <- function(plan) {
  largest <- max(c(0, vapply(plan$blocks, function(block) block$raw_bytes, numeric(1))))
  newpat_dnp_estimate_mib(largest)
}

# Each task holds at most one parsed block. Keep the input descriptor local
# to the worker and release each sample's scientific workspace before the next.
newpat_dnp_run_sample_group <- function(index, block, labels, ref_alt, computations,
                                       columns, sample_numbers, block_number) {
  started_at <- as.numeric(Sys.time())
  read_start <- proc.time()[["elapsed"]]
  connection <- file(index$path, open = "rb")
  on.exit(close(connection))
  selected <- if (length(sample_numbers) == 1L) columns[[sample_numbers]] else
    sort(unique(unlist(columns[sample_numbers])))
  pileup <- newpat_dnp_read(index, block$row_ids, connection, selected)
  read_seconds <- proc.time()[["elapsed"]] - read_start
  block_labels <- labels[labels$uniq %in% block$locus_ids, , drop = FALSE]
  block_refs <- ref_alt[block$locus_ids, , drop = FALSE]
  lapply(seq_along(sample_numbers), function(i) {
    number <- sample_numbers[[i]]
    first <- i == 1L
    sample_start <- if (first) started_at else as.numeric(Sys.time())
    sample_elapsed <- if (first) read_start else proc.time()[["elapsed"]]
    sample <- if (length(sample_numbers) == 1L) pileup else
      pileup[, paste0("V", sort(columns[[number]])), drop = FALSE]
    compute_start <- proc.time()[["elapsed"]]
    result <- computations[[number]](sample, block_labels, block_refs)
    compute_seconds <- proc.time()[["elapsed"]] - compute_start
    rm(sample)
    if (i == length(sample_numbers)) pileup <<- NULL
    # Count the shared read once, on the first sample in the scheduled group.
    metric <- list(loci = length(block$locus_ids), raw_rows = length(block$row_ids),
                   raw_bytes = block$raw_bytes, read_count = as.integer(first),
                   read_seconds = if (first) read_seconds else 0,
                   compute_seconds = compute_seconds,
                   elapsed_seconds = proc.time()[["elapsed"]] - sample_elapsed)
    gc(verbose = FALSE)
    list(result = result, metric = metric, started_at = sample_start,
         finished_at = as.numeric(Sys.time()), sample_number = number, block_number = block_number)
  })
}

newpat_dnp_run_block <- function(index, block, labels, ref_alt, compute, columns = NULL) {
  newpat_dnp_run_sample_group(index, block, labels, ref_alt, list(compute),
                            if (is.null(columns)) NULL else list(columns), 1L, 1L)[[1L]]
}

newpat_dnp_process_blocks <- function(index, plan, labels, ref_alt, compute,
                                     progress = function(...) invisible(NULL),
                                     workers = newpat_dnp_r_workers()) {
  started <- proc.time()[["elapsed"]]
  run_block <- function(number) {
    newpat_dnp_run_block(index, plan$blocks[[number]], labels, ref_alt, compute)
  }
  # Scientific values and metrics retain the plan's order regardless of which
  # worker completed first. Only this coordinating process publishes progress.
  completed <- 0L
  values <- newpat_parallel_lapply(seq_along(plan$blocks), run_block,
    label = "dnp-blocks", workers = workers,
    memory_mib = newpat_dnp_worker_memory_mib(plan),
    on_result = function(number, value) {
      completed <<- completed + value$metric$loci
      progress(completed, nrow(ref_alt))
    })
  list(results = lapply(values, function(value) value$result),
       metrics = lapply(values, function(value) value$metric),
       workers = attr(values, "workers"),
       elapsed_seconds = unname(proc.time()[["elapsed"]] - started))
}

# One process pool spans every sample and block. A sample does not reserve one
# worker and serialize all of its blocks: available workers take the next task,
# including when the sample count is smaller or larger than the shared budget.
newpat_dnp_process_samples <- function(index, plan, labels, ref_alt, computations,
                                      progress = function(...) invisible(NULL),
                                      workers = newpat_dnp_r_workers(), columns = NULL) {
  started <- proc.time()[["elapsed"]]
  sample_count <- length(computations)
  block_count <- length(plan$blocks)
  if (!sample_count || !block_count ||
      !all(vapply(computations, is.function, logical(1)))) {
    stop("DNP processing requires samples, blocks and compute functions")
  }
  if (!is.null(columns) && length(columns) != sample_count) {
    stop("DNP column selections must match the sample count")
  }
  sample_block_count <- sample_count * block_count
  group_sizes <- rep(1L, block_count)
  memory_mib <- newpat_dnp_worker_memory_mib(plan)
  if (sample_count > 1L && !length(plan$compatibility_reasons) &&
      identical(Sys.getenv("NEWPAT_DNP_OPTIMIZED_IO"), "1") && !is.null(columns) &&
      all(vapply(columns, function(ids) is.numeric(ids) && length(ids) > 0L &&
          all(is.finite(ids)) && all(ids == trunc(ids) & ids >= 1L & ids <= length(index$classes)) &&
          !anyDuplicated(ids), logical(1)))) {
    budget <- newpat_parallel_budget(sample_block_count, memory_mib, workers)
    remaining <- budget$memory_budget_mib - budget$coordinator_rss_mib
    if (length(remaining) == 1L && is.finite(remaining)) {
      # Leave enough independently schedulable work for all admitted workers.
      # Four samples per task also bounds buffered results and progress latency.
      groups_needed <- ceiling(budget$workers / block_count)
      max_samples <- max(1L, min(4L, floor(sample_count / groups_needed)))
      for (i in seq_along(plan$blocks)) {
        block <- plan$blocks[[i]]
        if (max_samples < 2L || block$raw_bytes > plan$max_bytes) next
        # Budget both copies of long strings and per-cell/per-column overhead
        # for the retained projection, conservatively using all input columns.
        columns_total <- length(index$classes)
        extra_bytes <- 4 * block$raw_bytes + columns_total * (128 + 96 * length(block$row_ids))
        estimate <- newpat_dnp_estimate_mib(block$raw_bytes) + ceiling(extra_bytes / 1024^2)
        if (estimate <= remaining / budget$workers) {
          group_sizes[[i]] <- as.integer(max_samples)
          memory_mib <- max(memory_mib, estimate)
        }
      }
    }
  }
  shared <- any(group_sizes > 1L)
  task_count <- sample_block_count
  if (shared) {
    groups_per_block <- ceiling(sample_count / group_sizes)
    group_offsets <- c(0, cumsum(groups_per_block))
    block_numbers <- rep.int(seq_len(block_count), groups_per_block)
    task_count <- length(block_numbers)
  }
  completed <- integer(sample_count)
  run_task <- function(number) {
    if (shared) {
      block_number <- block_numbers[[number]]
      size <- group_sizes[[block_number]]
      first <- (number - group_offsets[[block_number]] - 1L) * size + 1L
      samples <- seq.int(first, min(first + size - 1L, sample_count))
      # Start adjacent shared blocks with different samples so that multiple
      # samples can still advance together on a two-worker guest.
      if (size > 1L) samples <- as.integer((samples + block_number - 2L) %% sample_count + 1L)
    } else {
      block_number <- as.integer((number - 1L) %/% sample_count + 1L)
      samples <- as.integer((number - 1L) %% sample_count + 1L)
    }
    newpat_dnp_run_sample_group(index, plan$blocks[[block_number]], labels, ref_alt,
                              computations, columns, samples, block_number)
  }
  totals <- c(block_read_seconds = 0, block_compute_seconds = 0, block_read_count = 0,
              block_logical_bytes_read = 0, sample_block_count = 0)
  completed_groups <- 0L
  record_progress <- nzchar(Sys.getenv("NEWPAT_PERFORMANCE_DIR"))
  last_snapshot <- -Inf
  snapshot <- function() {
    now <- proc.time()[["elapsed"]]
    if (completed_groups > 1L && completed_groups < task_count && now - last_snapshot < 5) return()
    record_progress <<- newpat_dnp_write_block_progress(completed_groups, task_count, totals)
    last_snapshot <<- now
  }
  if (record_progress) snapshot()
  groups <- newpat_parallel_lapply(seq_len(task_count), run_task,
    label = "dnp-sample-blocks", workers = workers, memory_mib = memory_mib,
    on_result = function(number, group) {
      for (value in group) {
        sample_number <- value$sample_number
        metric <- value$metric
        completed[[sample_number]] <<- completed[[sample_number]] + metric$loci
        totals <<- totals + c(metric$read_seconds, metric$compute_seconds, metric$read_count,
                              metric$raw_bytes * metric$read_count, 1)
        progress(sample_number, completed[[sample_number]], nrow(ref_alt))
      }
      completed_groups <<- completed_groups + 1L
      if (record_progress) snapshot()
    })
  pool_workers <- attr(groups, "workers")
  values <- unlist(groups, recursive = FALSE, use.names = FALSE)
  # Count observed concurrency separately from the resource-policy upper bound.
  # End events precede start events at equal timestamps; empty intervals do not
  # imply overlap. These timestamps describe successful tasks, not predictions.
  starts <- vapply(values, function(value) value$started_at, numeric(1))
  ends <- vapply(values, function(value) value$finished_at, numeric(1))
  sample_numbers <- vapply(values, function(value) value$sample_number, integer(1))
  active <- peaks <- integer(sample_count)
  observed_workers <- observed_samples <- 0L
  times <- c(starts, ends)
  deltas <- c(rep(1L, sample_block_count), rep(-1L, sample_block_count))
  samples <- rep(sample_numbers, 2L)
  nonempty <- rep(ends > starts, 2L)
  events <- which(nonempty)
  events <- events[order(times[events], deltas[events])]
  for (event in events) {
    sample_number <- samples[[event]]
    active[[sample_number]] <- active[[sample_number]] + deltas[[event]]
    peaks[[sample_number]] <- max(peaks[[sample_number]], active[[sample_number]])
    observed_workers <- max(observed_workers, sum(active))
    observed_samples <- max(observed_samples, sum(active > 0L))
  }
  grouped <- lapply(seq_len(sample_count), function(sample_number) {
    selected <- values[sample_numbers == sample_number]
    selected <- selected[order(vapply(selected, function(value) value$block_number, integer(1)))]
    list(results = lapply(selected, function(value) value$result),
         metrics = lapply(selected, function(value) value$metric),
         workers = as.integer(min(block_count, pool_workers)),
         observed_workers = as.integer(peaks[[sample_number]]),
         elapsed_seconds = max(vapply(selected, function(value) value$finished_at, numeric(1))) -
                           min(vapply(selected, function(value) value$started_at, numeric(1))))
  })
  list(samples = grouped, workers = pool_workers, task_count = task_count,
       totals = as.list(totals), memory_mib = memory_mib,
       observed_workers = as.integer(observed_workers), observed_samples = as.integer(observed_samples),
       elapsed_seconds = unname(proc.time()[["elapsed"]] - started))
}

# The coordinator publishes aggregate counters beside this step's block report.
# Replace the snapshot atomically, so an interruption leaves a complete record.
newpat_dnp_write_block_progress <- function(completed, planned, totals) {
  tryCatch({
    path <- file.path("work", "dnp-block-progress.json")
    temporary <- tempfile(".dnp-block-progress-", tmpdir = dirname(path))
    on.exit(unlink(temporary))
    jsonlite::write_json(c(list(schema_version = 1L, completed_groups = completed,
                                planned_groups = planned), as.list(totals)),
                         temporary, auto_unbox = TRUE, digits = NA)
    isTRUE(suppressWarnings(file.rename(temporary, path)))
  }, error = function(error) FALSE, warning = function(warning) FALSE)
}

newpat_dnp_combine <- function(values) {
  final <- do.call(rbind, lapply(values, function(value) value$final))
  # Numeric final coordinates can use scientific notation. Retain the exact
  # original DNPs strings used by the legacy merge instead of recreating keys.
  keys <- unlist(lapply(values, function(value) value$sort_keys), use.names = FALSE)
  stopifnot(length(keys) == nrow(final))
  final <- final[order(keys), , drop = FALSE]
  rownames(final) <- NULL
  final
}

newpat_dnp_write_metrics <- function(path, value) {
  # Metrics do not participate in the calculation, and an unwritable diagnostic
  # destination must not discard otherwise valid scientific output.
  tryCatch({
    dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
    jsonlite::write_json(value, path, auto_unbox = TRUE, pretty = TRUE,
                         digits = NA, null = "null")
  }, error = function(error) warning("DNP execution metrics unavailable: ", conditionMessage(error)))
}

# Single-BAM runs with bounded depth measured up to 283 MiB RSS per samtools
# on GRCh37 (largest target ~238 MiB as sequence). The container budget is
# fixed at run start, independent of free RAM.
newpat_dnp_acquisition_budget <- function(chromosomes, samples, settings, reference) {
  chromosomes <- unique(chromosomes)
  plan <- newpat_parallel_budget(length(chromosomes), workload_observed = FALSE)
  if (!identical(plan$reason, "workload-not-observed") || samples < 1L ||
      length(chromosomes) < 2L ||
      !settings$baq || settings$redo_baq || settings$mapping_quality_adjustment > 0L ||
      settings$count_overlaps || settings$include_orphans || settings$min_base_quality < 13L ||
      bitwAnd(settings$excluded_flags, 1796L) != 1796L ||
      is.null(plan$memory_budget_mib) || is.null(plan$coordinator_rss_mib)) return(plan)

  # Estimate the largest reference sequence fetched by a chromosome task.
  # The acquisition helper performs the authoritative FASTA/BAM validation.
  lengths <- tryCatch({
    fai <- scan(paste0(reference, ".fai"), what = list("", 0, NULL, NULL, NULL),
                sep = "\t", quote = "", flush = TRUE, quiet = TRUE)
    fai[[2L]][match(chromosomes, fai[[1L]])]
  }, error = function(e) NA_real_)
  if (any(!is.finite(lengths)) || any(lengths <= 0)) return(plan)

  # Allow for non-reference RSS and double the estimate for depth/allocator variability.
  measured_rss_mib <- 288
  per_input <- 2 * max(measured_rss_mib, ceiling(max(lengths) / 1024^2) + 48)
  # Each chromosome worker reads every BAM. Charge the full reference and
  # allocator allowance again for each input even though the reference is shared.
  estimate <- samples * per_input
  remaining <- max(0, plan$memory_budget_mib - plan$coordinator_rss_mib)
  if (samples == 1L) {
    available <- remaining / 4
    # Admit at most one extra pair using the padded reference-specific cost.
    # Other backends retain their qualified GRCh37-sized envelope.
    pair <- 2 * estimate
    qualified <- identical(Sys.getenv("NEWPAT_DNP_OPTIMIZED_IO"), "1") || estimate == 2 * measured_rss_mib
    if (qualified && plan$worker_ceiling >= 2L && pair <= 0.4 * remaining) {
      available <- max(available, pair)
    }
    plan$workload_model <- "single-bam-bounded-depth-reference-and-rss"
  } else {
    # Acquisition finishes before the R block workers start. Keep half of the
    # remaining work budget available for I/O buffers and unmodelled costs.
    available <- remaining / 2
    plan$workload_model <- "joint-bam-bounded-depth-reference-and-rss"
  }
  # Higher scientific limits may use this pool only after the acquisition
  # helper checks that every input fits the measured depth envelope.
  if (settings$max_depth == 0L || settings$max_depth > 8000L) plan$verify_depth_limit <- 8000L
  plan$input_bams <- samples
  plan$memory_per_worker_mib <- estimate
  plan$acquisition_pool_budget_mib <- available
  plan$memory_worker_limit <- max(1L, floor(available / estimate))
  plan$workload_fits_memory_budget <- estimate <= available
  # Five concurrent chromosome tasks were qualified on the real BAM.
  plan$workers <- as.integer(min(5L, length(chromosomes), plan$worker_ceiling, plan$memory_worker_limit))
  plan$reason <- if (plan$memory_worker_limit < min(5L, length(chromosomes), plan$worker_ceiling))
    "acquisition-memory-budget" else "acquisition-capacity-task-budget"
  plan
}
