#!/usr/bin/env Rscript
# Resource-policy checks use explicit read-only /proc and cgroup fixtures.
# Scheduler checks below use the production helper, real resource discovery,
# real forked R processes, and actual child cleanup.
root <- normalizePath(commandArgs(trailingOnly = TRUE)[[1L]], mustWork = TRUE)
helper <- file.path(root, "src/newpat_scientific/parallel.R")

main <- function() {
  variables <- c("NEWPAT_EXECUTION_MODE", "NEWPAT_MAX_WORKERS", "NEWPAT_CPU_LIMIT",
                 "NEWPAT_MEMORY_LIMIT_MIB", "NEWPAT_DNP_BLOCK_BYTES", "NEWPAT_DNP_LIMA_ARM64",
                 "NEWPAT_PARALLEL_CHILD", "NEWPAT_PARALLEL_LOG_DIR", "NEWPAT_FIXED_RESOURCE_BUDGET")
  previous <- Sys.getenv(variables, unset = NA_character_)
  on.exit(for (name in names(previous)) {
    if (is.na(previous[[name]])) Sys.unsetenv(name) else
      do.call(Sys.setenv, setNames(list(previous[[name]]), name))
  }, add = TRUE)
  Sys.unsetenv(variables)
  checked <- 0L
  check <- function(condition) {
    stopifnot(isTRUE(condition))
    checked <<- checked + 1L
  }
  fresh <- function(files = NULL) {
    environment <- new.env(parent = globalenv())
    sys.source(helper, environment)
    if (!is.null(files)) environment$newpat_parallel_cpu_count <- function() 64L
    if (!is.null(files)) environment$newpat_parallel_lines <- function(path) {
      value <- files[[path]]
      if (is.null(value) && path == "/proc/self/status") value <- "VmRSS: 102400 kB"
      if (is.null(value)) character() else as.character(value)
    }
    environment
  }
  expect_error <- function(expression, pattern) {
    error <- tryCatch({ force(expression); NULL }, error = identity)
    check(inherits(error, "error") && grepl(pattern, conditionMessage(error)))
  }
  MiB <- 1024^2

  # V2 quotas constrain affinity. Capacity is independent of current use;
  # reserve a proportional margin and account for the coordinator once.
  v2 <- fresh(list(
    "/proc/self/cgroup" = "0::/",
    "/proc/meminfo" = "MemTotal: 33554432 kB",
    "/sys/fs/cgroup/cpu.max" = "250000 100000",
    "/sys/fs/cgroup/memory.max" = 10 * 1024 * MiB,
    "/sys/fs/cgroup/memory.current" = 2 * 1024 * MiB))
  budget <- v2$newpat_parallel_budget(20)
  check(budget$cpu_limit <= 2L)
  check(budget$memory_capacity_mib == 10240)
  check(budget$memory_worker_limit == 40L)
  check(budget$workers <= 2L)
  check(v2$newpat_parallel_budget(1)$workers == 1L)
  unobserved <- v2$newpat_parallel_budget(20, workload_observed = FALSE)
  check(unobserved$workers == 1L)
  check(unobserved$reason == "workload-not-observed")
  check(is.null(unobserved$memory_per_worker_mib))
  # A DNP-specific block preference must not change the generic SNP/CPI/
  # contamination budget; DNP supplies its actual block estimate explicitly.
  Sys.setenv(NEWPAT_DNP_BLOCK_BYTES = as.character(128 * MiB))
  check(v2$newpat_parallel_budget(20)$memory_per_worker_mib == 200)
  check(v2$newpat_parallel_budget(20, memory_mib = 6144)$memory_per_worker_mib == 6144)
  Sys.unsetenv("NEWPAT_DNP_BLOCK_BYTES")
  Sys.setenv(NEWPAT_MAX_WORKERS = "1")
  check(v2$newpat_parallel_budget(20)$workers == 1L)
  Sys.unsetenv("NEWPAT_MAX_WORKERS")
  Sys.setenv(NEWPAT_EXECUTION_MODE = "serial")
  check(v2$newpat_parallel_budget(20)$reason == "requested-serial")
  check(v2$newpat_parallel_budget(20)$workers == 1L)
  Sys.setenv(NEWPAT_EXECUTION_MODE = "auto", NEWPAT_PARALLEL_CHILD = "1")
  check(v2$newpat_parallel_budget(20)$reason == "shared-budget-child")
  check(v2$newpat_parallel_budget(20)$workers == 1L)
  Sys.unsetenv("NEWPAT_PARALLEL_CHILD")

  # Configured limits bound capacity; current use in ancestor cgroups must
  # not make the same configured run choose different parallelism.
  nested <- fresh(list(
    "/proc/self/cgroup" = "0::/parent/child",
    "/proc/meminfo" = "MemTotal: 33554432 kB",
    "/sys/fs/cgroup/memory.max" = 32 * 1024 * MiB,
    "/sys/fs/cgroup/memory.current" = 16 * 1024 * MiB,
    "/sys/fs/cgroup/parent/child/memory.max" = 8 * 1024 * MiB,
    "/sys/fs/cgroup/parent/child/memory.current" = 512 * MiB))
  Sys.setenv(NEWPAT_MEMORY_LIMIT_MIB = "8192")
  check(nested$newpat_parallel_budget(20)$memory_capacity_mib == 8192)
  check(nested$newpat_parallel_budget(20)$memory_worker_limit == 32L)
  Sys.unsetenv("NEWPAT_MEMORY_LIMIT_MIB")

  v1 <- fresh(list(
    "/proc/meminfo" = "MemTotal: 33554432 kB",
    "/sys/fs/cgroup/cpu/cpu.cfs_quota_us" = "150000",
    "/sys/fs/cgroup/cpu/cpu.cfs_period_us" = "100000",
    "/sys/fs/cgroup/memory/memory.limit_in_bytes" = 6 * 1024 * MiB,
    "/sys/fs/cgroup/memory/memory.usage_in_bytes" = 1024 * MiB))
  check(v1$newpat_parallel_budget(20)$cpu_limit == 1L)
  check(v1$newpat_parallel_budget(20)$memory_capacity_mib == 6144)
  check(v1$newpat_parallel_budget(20)$memory_worker_limit == 24L)
  # Host cgroup namespace, combined v1 cpu/cpuacct controller, subtree
  # memory mount. A quota, memory limit and PID headroom each bind independently.
  v1_mounts <- fresh(list(
    "/proc/self/cgroup" = c("3:cpu,cpuacct:/docker/run", "2:memory:/docker/run",
                            "1:pids:/docker/run"),
    "/proc/self/mountinfo" = c(
      "30 20 0:8 / /sys/fs/cgroup/cpu,cpuacct rw - cgroup cgroup rw,cpu,cpuacct",
      "31 20 0:9 /docker /sys/fs/cgroup/memory rw - cgroup cgroup rw,memory",
      "32 20 0:10 / /sys/fs/cgroup/pids rw - cgroup cgroup rw,pids"),
    "/proc/meminfo" = "MemTotal: 16777216 kB",
    "/sys/fs/cgroup/cpu,cpuacct/docker/cpu.cfs_quota_us" = "200000",
    "/sys/fs/cgroup/cpu,cpuacct/docker/cpu.cfs_period_us" = "100000",
    "/sys/fs/cgroup/cpu,cpuacct/docker/run/cpu.cfs_quota_us" = "-1",
    "/sys/fs/cgroup/memory/memory.limit_in_bytes" = "9223372036854771712",
    "/sys/fs/cgroup/memory/run/memory.limit_in_bytes" = 1024 * MiB,
    "/sys/fs/cgroup/pids/docker/pids.max" = "34",
    "/sys/fs/cgroup/pids/docker/pids.current" = "29"))
  budget <- v1_mounts$newpat_parallel_budget(16)
  check(budget$cpu_limit == 2L)
  check(budget$memory_capacity_mib == 1024)
  check(budget$workers == 1L)

  # The v2 mount starts below the physical hierarchy root. An unrelated mount
  # with a similar path prefix must never impose its limits on this process.
  v2_mounts <- fresh(list(
    "/proc/self/cgroup" = "0::/work area/job/run",
    "/proc/self/mountinfo" = c(
      "31 20 0:9 /work\\040area /cgroup\\040view rw - cgroup2 cgroup rw",
      "32 20 0:9 /work /other rw - cgroup2 cgroup rw"),
    "/proc/meminfo" = "MemTotal: 16777216 kB",
    "/cgroup view/cpu.max" = "max 100000",
    "/cgroup view/job/cpu.max" = "200000 100000",
    "/cgroup view/job/memory.max" = 2048 * MiB,
    "/cgroup view/job/run/memory.max" = 1024 * MiB,
    "/other/cpu.max" = "100000 100000",
    "/other/memory.max" = 128 * MiB))
  budget <- v2_mounts$newpat_parallel_budget(16)
  check(budget$cpu_limit == 2L)
  check(budget$memory_capacity_mib == 1024)
  check(budget$workers == 2L)
  # A namespace can have its leaf mounted as the visible root. A different
  # subtree (or a namespace-relative '..' path) cannot explain process limits.
  private <- fresh(list(
    "/proc/self/cgroup" = "0::/docker/ours",
    "/proc/self/mountinfo" = "30 20 0:8 /docker/ours /sys/fs/cgroup rw - cgroup2 cgroup rw",
    "/proc/meminfo" = "MemTotal: 16777216 kB",
    "/sys/fs/cgroup/memory.max" = 2048 * MiB))
  check(private$newpat_parallel_capacity()$memory_capacity_mib == 2048)
  for (member in c("/../outside", "/docker/theirs")) {
    unmapped <- fresh(list(
      "/proc/self/cgroup" = paste0("0::", member),
      "/proc/self/mountinfo" = "30 20 0:8 /docker/ours /sys/fs/cgroup rw - cgroup2 cgroup rw",
      "/proc/meminfo" = "MemTotal: 16777216 kB"))
    check(unmapped$newpat_parallel_budget(16)$workers == 1L)
  }
  unknown <- fresh(list())
  check(unknown$newpat_parallel_budget(20)$workers == 1L)
  check(unknown$newpat_parallel_budget(20)$reason == "workload-memory-unavailable")
  Sys.setenv(NEWPAT_MAX_WORKERS = "0")
  expect_error(v2$newpat_parallel_budget(20), "NEWPAT_MAX_WORKERS")
  Sys.setenv(NEWPAT_MAX_WORKERS = "1.5")
  expect_error(v2$newpat_parallel_budget(20), "NEWPAT_MAX_WORKERS")
  Sys.unsetenv("NEWPAT_MAX_WORKERS")
  expect_error(v2$newpat_parallel_budget(-1), "tasks")
  expect_error(v2$newpat_parallel_budget(2, memory_mib = 0), "memory_mib")

  # A run carries one immutable assigned-capacity document across its phases.
  # Free memory/current cgroup use must neither reduce nor increase that plan.
  fixed_document <- list(schema_version = 1L, interface = "newpat-fixed-resources-v1",
    worker_ceiling = 4L, cpu_limit = 4L, memory_capacity_mib = 4096,
    memory_reserve_fraction = 0.20)
  Sys.setenv(NEWPAT_FIXED_RESOURCE_BUDGET = jsonlite::toJSON(fixed_document, auto_unbox = TRUE))
  fixed <- fresh(list(
    "/proc/meminfo" = c("MemTotal: 16777216 kB", "MemAvailable: 16384 kB"),
    "/proc/self/status" = "VmRSS: 262144 kB",
    "/sys/fs/cgroup/cpu.max" = "400000 100000",
    "/sys/fs/cgroup/memory.max" = 8192 * MiB,
    "/sys/fs/cgroup/memory.current" = 8000 * MiB))
  before <- fixed$newpat_parallel_budget(20, memory_mib = 1024)
  check(before$resource_basis == "assigned-capacity-at-run-start")
  revised_document <- fixed_document
  revised_document$basis <- "assigned-capacity-at-step-boundary"
  Sys.setenv(NEWPAT_FIXED_RESOURCE_BUDGET = jsonlite::toJSON(revised_document, auto_unbox = TRUE))
  next_phase <- fresh(list("/proc/meminfo" = "MemTotal: 16777216 kB"))
  check(next_phase$newpat_parallel_budget(20)$resource_basis == revised_document$basis)
  Sys.setenv(NEWPAT_FIXED_RESOURCE_BUDGET = jsonlite::toJSON(fixed_document, auto_unbox = TRUE))
  check(before$memory_capacity_mib == 4096)
  check(before$worker_ceiling == 4L)
  check(before$workers == 2L)
  check(before$memory_per_worker_mib == 1024)
  fixed$newpat_parallel_lines <- function(path) {
    if (path == "/proc/self/status") "VmRSS: 262144 kB" else character()
  }
  check(identical(before, fixed$newpat_parallel_budget(20, memory_mib = 1024)))
  sys.source(file.path(root, "src/newpat_scientific/dnp_blocks.R"), fixed)
  target <- fixed$newpat_dnp_target_bytes(32 * MiB)
  check(target > 0 && target < 32 * MiB)
  check(fixed$newpat_dnp_target_bytes(1 * MiB) == 1 * MiB)
  tight <- new.env(parent = fixed)
  sys.source(file.path(root, "src/newpat_scientific/dnp_blocks.R"), tight)
  tight$newpat_parallel_budget <- function(...) list(memory_budget_mib = remaining + 100,
    coordinator_rss_mib = 100, workers = 1L)
  # A budget at the base footprint must not jump back to a full 32 MiB block.
  for (remaining in c(400, 511, 512, 513, 514)) {
    expected <- max(1, floor((remaining - 512) / 48 * MiB))
    check(tight$newpat_dnp_target_bytes(32 * MiB) == expected)
  }
  Sys.setenv(NEWPAT_DNP_LIMA_ARM64 = "1")
  for (capacity in c(1952, 3905, 4096, 4097, 8192)) {
    tight$newpat_parallel_capacity <- function() list(memory_capacity_mib = capacity)
    check(identical(tight$newpat_dnp_r_workers(), if (capacity <= 4096) 2L else NULL))
  }
  tight$newpat_parallel_capacity <- function() list(memory_capacity_mib = NULL)
  check(is.null(tight$newpat_dnp_r_workers()))
  check(fixed$newpat_dnp_r_workers() == 2L)
  check(fixed$newpat_dnp_target_bytes(32 * MiB) > target)
  check(fixed$newpat_parallel_budget(8, memory_mib = 512, workers = fixed$newpat_dnp_r_workers())$workers == 2L)
  check(fixed$newpat_parallel_budget(8, memory_mib = 512)$workers == 4L)
  Sys.setenv(NEWPAT_MAX_WORKERS = "3")
  check(is.null(fixed$newpat_dnp_r_workers()))
  check(fixed$newpat_parallel_budget(8, memory_mib = 512, workers = fixed$newpat_dnp_r_workers())$workers == 3L)
  Sys.unsetenv(c("NEWPAT_DNP_LIMA_ARM64", "NEWPAT_MAX_WORKERS"))
  Sys.setenv(NEWPAT_EXECUTION_MODE = "serial")
  check(fixed$newpat_dnp_target_bytes(32 * MiB) == 32 * MiB)
  Sys.unsetenv("NEWPAT_EXECUTION_MODE")
  fixed$newpat_parallel_lines <- function(path) character()
  check(fixed$newpat_parallel_budget(20)$workers == 1L)
  check(fixed$newpat_parallel_budget(20)$reason == "workload-memory-unavailable")
  Sys.unsetenv("NEWPAT_FIXED_RESOURCE_BUDGET")

  # Production scheduler: real resource discovery, without a synthetic budget.
  real <- fresh()
  Sys.setenv(NEWPAT_MAX_WORKERS = "2")
  if (real$newpat_parallel_workers(4) < 2L) {
    stop("Parallel scheduler qualification requires two effective workers; CPU/RAM budget is insufficient")
  }
  directory <- tempfile("parallel-budget-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  Sys.setenv(NEWPAT_PARALLEL_LOG_DIR = file.path(directory, "events"))
  coordinator <- Sys.getpid()
  callback_order <- integer()
  release_first <- file.path(directory, "release-first-task")
  callback <- function(index, value) {
    check(Sys.getpid() == coordinator)
    callback_order <<- c(callback_order, index)
    if (index == 2L) writeLines("release", release_first)
  }
  values <- real$newpat_parallel_lapply(setNames(1:4, letters[1:4]), function(index) {
    if (index == 1L) {
      deadline <- proc.time()[["elapsed"]] + 3
      while (!file.exists(release_first) && proc.time()[["elapsed"]] < deadline) Sys.sleep(0.01)
      stopifnot(file.exists(release_first))
    }
    list(index = index, pid = Sys.getpid())
  }, on_result = callback, label = "budget-order")
  check(identical(names(values), letters[1:4]))
  check(identical(unname(vapply(values, function(value) value$index, integer(1))), 1:4))
  check(callback_order[[1L]] != 1L)
  check(all(vapply(values, function(value) value$pid != coordinator, logical(1))))
  check(attr(values, "workers") == 2L)
  nulls <- real$newpat_parallel_lapply(1:3, function(index) NULL)
  check(length(nulls) == 3L && all(vapply(nulls, is.null, logical(1))))
  nested_values <- real$newpat_parallel_lapply(1:2, function(index) {
    own_pid <- Sys.getpid()
    inner <- real$newpat_parallel_lapply(1:3, function(j) Sys.getpid())
    list(own_pid = own_pid, inner = inner)
  })
  check(all(vapply(nested_values, function(value) {
    attr(value$inner, "workers") == 1L && all(unlist(value$inner) == value$own_pid)
  }, logical(1))))
  Sys.setenv(NEWPAT_EXECUTION_MODE = "serial")
  serial <- real$newpat_parallel_lapply(1:3, function(index) Sys.getpid())
  check(all(unlist(serial) == coordinator) && attr(serial, "workers") == 1L)
  Sys.setenv(NEWPAT_EXECUTION_MODE = "auto")

  # The first worker stays busy while the second raises. Error propagation must
  # terminate and collect the outstanding worker instead of abandoning it.
  marker <- file.path(directory, "busy-pid.txt")
  before <- proc.time()[["elapsed"]]
  expect_error(real$newpat_parallel_lapply(1:2, function(index) {
    if (index == 1L) {
      writeLines(as.character(Sys.getpid()), marker)
      Sys.sleep(10)
      return(TRUE)
    }
    deadline <- proc.time()[["elapsed"]] + 3
    while (!file.exists(marker) && proc.time()[["elapsed"]] < deadline) Sys.sleep(0.01)
    stop("deliberate worker failure")
  }), "deliberate worker failure")
  check(proc.time()[["elapsed"]] - before < 5)
  busy_pid <- as.integer(readLines(marker))
  check(!tools::pskill(busy_pid, signal = 0L))
  check(length(parallel::mccollect(wait = FALSE)) == 0L)

  events <- unlist(lapply(list.files(file.path(directory, "events"), full.names = TRUE),
                          readLines), use.names = FALSE)
  events <- lapply(events, jsonlite::fromJSON)
  check(any(vapply(events, function(event) event$event == "task-start" &&
                   event$pid != event$coordinator_pid, logical(1))))
  check(all(vapply(events, function(event) is.finite(event$observed_at_unix), logical(1))))
  cat("Parallel budget and scheduler:", checked,
      "checks passed (resource fixtures and real ordered forks, callbacks, nested budget, errors, cleanup).\n")
}
main()
