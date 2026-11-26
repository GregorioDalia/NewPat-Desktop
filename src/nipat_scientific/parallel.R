# One bounded process budget shared by every scientific R workflow.
# Memory estimates guide scheduling; only the container's RAM limit is a hard limit.

nipat_parallel_positive <- function(text, name, default = NULL, whole = TRUE) {
  if (!nzchar(text)) return(default)
  value <- suppressWarnings(as.numeric(text))
  if (length(value) != 1L || !is.finite(value) || value <= 0 ||
      (whole && value != floor(value))) stop(name, " must be a positive number")
  value
}

nipat_parallel_lines <- function(path) {
  tryCatch(readLines(path, warn = FALSE), error = function(e) character(),
           warning = function(w) character())
}

nipat_parallel_number <- function(path) {
  value <- suppressWarnings(as.numeric(nipat_parallel_lines(path)[1L]))
  if (length(value) && is.finite(value) && value >= 0) value else Inf
}

# Translate the process's hierarchy path through the mount's filesystem root.
# A bind mount can expose only a subtree; stop at its root when checking ancestors.
nipat_parallel_cgroup_paths <- function(mount, root, member) {
  if (!startsWith(member, "/") || any(strsplit(member, "/", fixed = TRUE)[[1L]] == "..")) return(character())
  prefix <- if (root == "/") "/" else paste0(root, "/")
  if (member == root) return(mount)
  if (!startsWith(member, prefix)) return(character())
  relative <- substring(member, nchar(prefix) + 1L)
  path <- mount
  paths <- mount
  for (directory in strsplit(relative, "/", fixed = TRUE)[[1L]]) {
    path <- file.path(path, directory)
    paths <- c(paths, path)
  }
  paths
}

nipat_parallel_cgroups <- function() {
  base <- "/sys/fs/cgroup"
  defaults <- list(unified = base, cpu = file.path(base, "cpu"),
                   memory = file.path(base, "memory"), pids = file.path(base, "pids"))
  members <- list()
  lines <- nipat_parallel_lines("/proc/self/cgroup")
  for (fields in regmatches(lines, regexec("^[0-9]+:([^:]*):(/.*)$", lines))) {
    if (!length(fields)) next
    controllers <- if (nzchar(fields[2L])) strsplit(fields[2L], ",", fixed = TRUE)[[1L]] else "unified"
    for (controller in intersect(controllers, names(defaults))) members[[controller]] <- fields[3L]
  }
  mounts <- grep(" - cgroup2? ", nipat_parallel_lines("/proc/self/mountinfo"), value = TRUE)
  if (!length(mounts)) {
    # Older/restricted procfs installations may expose only the usual controller paths.
    paths <- defaults
    for (controller in names(members)) {
      paths[[controller]] <- unique(c(defaults[[controller]], nipat_parallel_cgroup_paths(
        defaults[[controller]], "/", members[[controller]])))
    }
    return(paths)
  }

  paths <- list()
  mounted <- character()
  for (line in mounts) {
    parts <- strsplit(line, " - ", fixed = TRUE)[[1L]]
    before <- strsplit(parts[1L], " ", fixed = TRUE)[[1L]]
    after <- strsplit(parts[2L], " ", fixed = TRUE)[[1L]]
    if (length(before) < 6L || length(after) < 3L) next
    # mountinfo escapes whitespace and backslashes even for valid cgroup names.
    names_on_disk <- before[4:5]
    names_on_disk <- gsub("\\040", " ", names_on_disk, fixed = TRUE)
    names_on_disk <- gsub("\\011", "\t", names_on_disk, fixed = TRUE)
    names_on_disk <- gsub("\\012", "\n", names_on_disk, fixed = TRUE)
    names_on_disk <- gsub("\\134", "\\", names_on_disk, fixed = TRUE)
    controllers <- if (after[1L] == "cgroup2") "unified" else strsplit(after[3L], ",", fixed = TRUE)[[1L]]
    controllers <- intersect(controllers, names(defaults))
    mounted <- union(mounted, controllers)
    for (controller in intersect(controllers, names(members))) {
      hierarchy <- nipat_parallel_cgroup_paths(names_on_disk[2L], names_on_disk[1L], members[[controller]])
      paths[[controller]] <- unique(c(paths[[controller]], hierarchy))
    }
  }
  if (length(members)) mounted <- intersect(mounted, names(members))
  # If a known controller is visible but its membership cannot be mapped,
  # host capacity alone is insufficient evidence for a parallel pool.
  paths$unresolved <- length(setdiff(mounted, names(paths)[lengths(paths) > 0L])) > 0L
  paths
}

# Capacity is captured once per scientific coordinator. The desktop supplies
# the same immutable run-start document to every phase/container subprocess.
# Native invocations use MemTotal and configured cgroup limits, never free RAM.
.nipat_parallel_capacity_cache <- new.env(parent = emptyenv())

nipat_parallel_rss_mib <- function() {
  text <- grep("^VmRSS:", nipat_parallel_lines("/proc/self/status"), value = TRUE)
  if (!length(text)) return(NA_real_)
  value <- suppressWarnings(as.numeric(strsplit(trimws(text[[1L]]), "[[:space:]]+")[[1L]][2L]) / 1024)
  if (length(value) != 1L || !is.finite(value) || value <= 0) NA_real_ else value
}

nipat_parallel_cpu_count <- function() {
  cpu <- tryCatch(length(parallel::mcaffinity()), error = function(e) 0L)
  if (!cpu) cpu <- parallel::detectCores(logical = TRUE)
  if (!length(cpu) || is.na(cpu) || cpu < 1) cpu <- 1L
  cpu
}

nipat_parallel_capacity <- function() {
  if (exists("value", envir = .nipat_parallel_capacity_cache, inherits = FALSE)) {
    return(.nipat_parallel_capacity_cache$value)
  }
  cpu <- min(nipat_parallel_cpu_count(), nipat_parallel_positive(Sys.getenv("NIPAT_CPU_LIMIT"),
                                         "NIPAT_CPU_LIMIT", Inf, whole = FALSE))
  cgroups <- nipat_parallel_cgroups()
  total <- grep("^MemTotal:", nipat_parallel_lines("/proc/meminfo"), value = TRUE)
  memory <- if (length(total)) suppressWarnings(as.numeric(strsplit(trimws(total[[1L]]), "[[:space:]]+")[[1L]][2L]) / 1024) else NA_real_
  process_ceiling <- if (isTRUE(cgroups$unresolved)) 1L else Inf
  for (path in cgroups$unified) {
    text <- nipat_parallel_lines(file.path(path, "cpu.max"))
    if (length(text)) {
      numbers <- suppressWarnings(as.numeric(strsplit(trimws(text[[1L]]), "[[:space:]]+")[[1L]]))
      if (length(numbers) == 2L && all(is.finite(numbers)) && all(numbers > 0)) {
        cpu <- min(cpu, numbers[[1L]] / numbers[[2L]])
      }
    }
    limit <- nipat_parallel_number(file.path(path, "memory.max"))
    if (is.finite(limit)) memory <- min(memory, limit / 1024^2, na.rm = TRUE)
  }
  for (path in cgroups$cpu) {
    quota <- nipat_parallel_number(file.path(path, "cpu.cfs_quota_us"))
    period <- nipat_parallel_number(file.path(path, "cpu.cfs_period_us"))
    if (is.finite(quota) && is.finite(period) && quota > 0 && period > 0) cpu <- min(cpu, quota / period)
  }
  for (path in cgroups$memory) {
    limit <- nipat_parallel_number(file.path(path, "memory.limit_in_bytes"))
    # A v1 sentinel above the signed-address range is not an assigned capacity.
    if (is.finite(limit) && limit < 2^60) memory <- min(memory, limit / 1024^2, na.rm = TRUE)
  }
  for (path in c(cgroups$unified, cgroups$pids)) {
    pids <- nipat_parallel_number(file.path(path, "pids.max"))
    used <- nipat_parallel_number(file.path(path, "pids.current"))
    if (is.finite(pids) && is.finite(used)) process_ceiling <- min(process_ceiling, max(1, pids - used - 4))
  }
  explicit_memory <- nipat_parallel_positive(Sys.getenv("NIPAT_MEMORY_LIMIT_MIB"),
                                              "NIPAT_MEMORY_LIMIT_MIB", Inf)
  if (is.finite(explicit_memory)) memory <- min(memory, explicit_memory, na.rm = TRUE)
  cpu <- max(1L, floor(cpu))
  reserve <- 0.20
  ceiling <- cpu
  source <- "configured-capacity-at-coordinator-start"
  source_version <- NULL
  supplied <- Sys.getenv("NIPAT_FIXED_RESOURCE_BUDGET")
  if (nzchar(supplied)) {
    value <- tryCatch(jsonlite::fromJSON(supplied), error = function(e) NULL)
    if (!is.list(value) || !identical(value$interface, "nipat-fixed-resources-v1") ||
        length(value$worker_ceiling) != 1L || !is.finite(value$worker_ceiling) ||
        value$worker_ceiling < 1 || value$worker_ceiling != floor(value$worker_ceiling) ||
        length(value$memory_reserve_fraction) != 1L || !is.finite(value$memory_reserve_fraction) ||
        value$memory_reserve_fraction < 0 || value$memory_reserve_fraction >= 1) {
      stop("Invalid fixed resource budget")
    }
    ceiling <- min(cpu, value$worker_ceiling)
    if (!is.null(value$cpu_limit)) {
      cpu <- min(cpu, nipat_parallel_positive(as.character(value$cpu_limit), "cpu_limit", whole = FALSE))
      ceiling <- min(ceiling, max(1L, floor(cpu)))
    }
    if (is.null(value$memory_capacity_mib)) {
      memory <- NA_real_
    } else {
      fixed_memory <- nipat_parallel_positive(as.character(value$memory_capacity_mib), "memory_capacity_mib", whole = FALSE)
      memory <- min(memory, fixed_memory, na.rm = TRUE)
    }
    reserve <- value$memory_reserve_fraction
    source <- if (identical(value$basis, "assigned-capacity-at-step-boundary")) value$basis else "assigned-capacity-at-run-start"
    source_version <- value$source_version
  }
  if (!is.finite(memory) || memory <= 0) {
    memory <- NA_real_
    ceiling <- 1L
  }
  ceiling <- max(1L, min(ceiling, process_ceiling))
  result <- list(interface = "nipat-fixed-resources-v1", source = source, source_version = source_version,
    cpu_limit = max(1L, floor(cpu)), memory_capacity_mib = if (is.finite(memory)) memory else NULL,
    memory_budget_mib = if (is.finite(memory)) floor((1 - reserve) * memory) else NULL,
    memory_reserve_fraction = reserve, worker_ceiling = as.integer(ceiling))
  .nipat_parallel_capacity_cache$value <- result
  result
}

nipat_parallel_budget <- function(tasks, memory_mib = NULL, workers = NULL, workload_observed = TRUE) {
  if (!is.logical(workload_observed) || length(workload_observed) != 1L || is.na(workload_observed)) {
    stop("workload_observed must be TRUE or FALSE")
  }
  mode <- Sys.getenv("NIPAT_EXECUTION_MODE", "auto")
  if (!mode %in% c("auto", "serial")) stop("Invalid NIPAT_EXECUTION_MODE")
  maximum <- nipat_parallel_positive(Sys.getenv("NIPAT_MAX_WORKERS"), "NIPAT_MAX_WORKERS", Inf)
  if (!is.null(workers)) maximum <- min(maximum, nipat_parallel_positive(as.character(workers), "workers"))
  if (length(tasks) != 1L || !is.finite(tasks) || tasks < 0 || tasks != floor(tasks)) stop("tasks must be a nonnegative whole number")
  capacity <- nipat_parallel_capacity()
  ceiling <- max(1L, min(capacity$worker_ceiling, maximum))
  rss <- nipat_parallel_rss_mib()
  # The loaded coordinator footprint is a workload observation, not host free
  # memory. Account for the parent once, then allow a proportional copy/heap
  # margin for each child. This is a conservative heuristic, not an RSS limit.
  estimate <- if (workload_observed && is.finite(rss)) 2 * rss else NA_real_
  if (workload_observed && !is.null(memory_mib)) {
    requested_memory <- nipat_parallel_positive(as.character(memory_mib), "memory_mib", whole = FALSE)
    estimate <- max(estimate, requested_memory, na.rm = TRUE)
  }
  memory <- capacity$memory_budget_mib
  remaining <- if (length(memory) && is.finite(memory) && is.finite(rss)) max(0, memory - rss) else NA_real_
  memory_workers <- if (is.finite(remaining) && is.finite(estimate) && estimate > 0) max(1L, floor(remaining / estimate)) else 1L
  nested <- identical(Sys.getenv("NIPAT_PARALLEL_CHILD"), "1")
  reason <- if (mode == "serial") "requested-serial" else if (nested) "shared-budget-child" else if (.Platform$OS.type == "windows") "fork-unavailable" else if (!workload_observed) "workload-not-observed" else if (!is.finite(remaining) || !is.finite(estimate)) "workload-memory-unavailable" else if (estimate > remaining) "workload-exceeds-budget-serial" else if (memory_workers < ceiling) "workload-memory-budget" else "fixed-capacity-task-budget"
  selected <- max(1L, min(max(1L, tasks), ceiling, memory_workers))
  if (mode == "serial" || nested || .Platform$OS.type == "windows") selected <- 1L
  list(mode = mode, max_workers = if (is.finite(maximum)) maximum else NULL,
       workers = as.integer(selected), tasks = tasks, cpu_limit = capacity$cpu_limit,
       resource_policy = capacity$interface, resource_basis = capacity$source,
       resource_source_version = capacity$source_version,
       workload_model = if (!workload_observed) "not-observed" else if (is.null(memory_mib))
         "loaded-coordinator-rss-x2" else "max-loaded-coordinator-rss-x2-and-module-estimate",
       worker_ceiling = as.integer(ceiling), memory_capacity_mib = capacity$memory_capacity_mib,
       memory_budget_mib = capacity$memory_budget_mib,
       memory_reserve_fraction = capacity$memory_reserve_fraction,
       coordinator_rss_mib = if (is.finite(rss)) rss else NULL,
       memory_allocation_per_worker_mib = if (is.finite(remaining)) remaining / ceiling else NULL,
       memory_per_worker_mib = if (is.finite(estimate)) estimate else NULL,
       memory_worker_limit = memory_workers,
       workload_fits_memory_budget = is.finite(remaining) && is.finite(estimate) && estimate <= remaining,
       reason = reason)
}

nipat_parallel_workers <- function(tasks, memory_mib = NULL) {
  nipat_parallel_budget(tasks, memory_mib)$workers
}

nipat_parallel_record <- function(event, label, coordinator_pid, budget, task_index = NULL, outcome = NULL) {
  directory <- Sys.getenv("NIPAT_PARALLEL_LOG_DIR")
  if (!nzchar(directory)) return(invisible(NULL))
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  if (!dir.exists(directory)) stop("Cannot create parallel diagnostics directory")
  target <- file.path(directory, paste0("worker-", Sys.getpid(), ".jsonl"))
  link <- Sys.readlink(target)
  if (!is.na(link) && nzchar(link)) stop("Parallel diagnostics cannot use a symbolic link")
  document <- c(list(schema_version = 1L, interface = "nipat-parallel-v1", event = event,
                     label = label, coordinator_pid = coordinator_pid, pid = Sys.getpid(),
                     task_index = task_index, outcome = outcome,
                     observed_at_unix = as.numeric(Sys.time()),
                     elapsed_seconds = unname(proc.time()[["elapsed"]])), budget)
  cat(jsonlite::toJSON(document, auto_unbox = TRUE, null = "null", digits = NA), "\n",
      file = target, append = TRUE, sep = "")
  invisible(NULL)
}

nipat_parallel_lapply <- function(X, FUN, ..., label = "scientific", workers = NULL,
                                  memory_mib = NULL, on_result = NULL, workload_observed = TRUE) {
  budget <- nipat_parallel_budget(length(X), memory_mib, workers, workload_observed)
  coordinator <- Sys.getpid()
  nipat_parallel_record("plan", label, coordinator, budget)
  result <- vector("list", length(X))
  names(result) <- names(X)
  arguments <- list(...)
  execute <- function(index) {
    nipat_parallel_record("task-start", label, coordinator, budget, index)
    value <- tryCatch(list(ok = TRUE, value = do.call(FUN, c(list(X[[index]]), arguments))),
                      error = function(error) list(ok = FALSE, message = conditionMessage(error)))
    nipat_parallel_record("task-end", label, coordinator, budget, index,
                          if (isTRUE(value$ok)) "succeeded" else "failed")
    value
  }
  accept <- function(index, value) {
    if (!is.list(value) || !isTRUE(value$ok)) {
      detail <- if (is.list(value) && !is.null(value$message)) value$message else "worker exited without a result"
      stop(label, " task ", index, " failed: ", detail, call. = FALSE)
    }
    result[index] <<- list(value$value)
    if (!is.null(on_result)) on_result(index, value$value)
  }
  if (budget$workers == 1L || !length(X)) {
    for (index in seq_along(X)) accept(index, execute(index))
  } else {
    active <- list()
    indices <- list()
    cleanup <- function() {
      if (!length(active)) return(invisible(NULL))
      for (job in active) try(tools::pskill(job$pid, tools::SIGTERM), silent = TRUE)
      deadline <- proc.time()[["elapsed"]] + 2
      while (length(active) && proc.time()[["elapsed"]] < deadline) {
        finished <- suppressWarnings(parallel::mccollect(active, wait = FALSE, timeout = 0.05))
        for (pid in names(finished)) active[[pid]] <<- NULL
      }
      for (job in active) try(tools::pskill(job$pid, tools::SIGKILL), silent = TRUE)
      if (length(active)) suppressWarnings(parallel::mccollect(active, wait = TRUE))
      invisible(NULL)
    }
    on.exit(cleanup(), add = TRUE)
    next_index <- 1L
    while (next_index <= length(X) || length(active)) {
      while (next_index <= length(X) && length(active) < budget$workers) {
        index <- next_index
        job <- parallel::mcparallel({
          Sys.setenv(NIPAT_PARALLEL_CHILD = "1")
          execute(index)
        }, mc.set.seed = FALSE, silent = FALSE)
        pid <- as.character(job$pid)
        active[[pid]] <- job
        indices[[pid]] <- index
        next_index <- next_index + 1L
      }
      finished <- suppressWarnings(parallel::mccollect(active, wait = FALSE, timeout = 0.05))
      # Remove every collected job before callbacks/errors: collected PIDs may be reused.
      for (pid in names(finished)) active[[pid]] <- NULL
      for (pid in names(finished)) {
        accept(indices[[pid]], finished[[pid]])
        indices[[pid]] <- NULL
      }
    }
  }
  attr(result, "workers") <- budget$workers
  result
}
