"""Lima lifecycle boundaries; real VM evidence is a separate macOS job."""

import copy
from contextlib import redirect_stdout
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from newpat.errors import RuntimeExecutionError, ValidationError
from newpat.macos_runtime import (
    CHANNEL, INSTANCE, LIMA_VERSION, LimaRuntime, _write_json, file_sha256,
    loaded_image_id, main, read_manifest,
)
from test_bundled_runner import engine_metadata


SOURCE_ID = "sha256:" + "a" * 64
LOADED_ID = "sha256:" + "b" * 64


@unittest.skipUnless(os.name == "posix", "Lima lifecycle is exercised on Linux/macOS hosts")
class MacRuntimeTests(unittest.TestCase):
    def setUp(self):
        # macOS TMPDIR is a long /var/folders/... path. These fixtures represent
        # a real user home and must leave space for Lima's bounded Unix socket.
        self.temp = tempfile.TemporaryDirectory(prefix="nm-", dir="/tmp" if sys.platform == "darwin" else None)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.project = self.home / "App with spaces" / "app"
        self.project.mkdir(parents=True)
        self.executable = self.home / "lima" / "bin" / "limactl"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_text("fixture")
        self.workspace = self.home / "Library" / "Application Support" / "NewPat-Desktop"
        self.runtime = LimaRuntime(self.project, self.workspace, self.executable, home=self.home)
        self.archive = self.project / ".distribution" / "assets" / "runtime.tar.gz"
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b"verified fixture archive")
        self.manifest = {
            "schema_version": 1, "channel": CHANNEL, "version": "0.9.99", "bundle_identifier": "org.newpat.desktop", "source_commit": "c" * 40,
            "architecture": "x86_64", "scientific_platform": "linux/amd64", "lima_version": LIMA_VERSION, "runtime_image": SOURCE_ID,
            "scientific_asset": {"name": self.archive.name, "sha256": file_sha256(self.archive)},
            "engine_description": engine_metadata(),
        }
        _write_json(self.project / ".distribution" / "macos-manifest.json", self.manifest)
        self.owner = {"channel": CHANNEL, "instance": INSTANCE, "lima_home": str(self.runtime.lima_home),
                      "token": "d" * 32, "mounts": self.runtime.default_mounts()}

    def test_overlong_home_is_still_rejected_before_creating_files(self):
        home = self.home / ("long-name-" * 15)
        workspace = home / "Library/Application Support/NewPat-Desktop"
        with self.assertRaisesRegex(ValidationError, "troppo lungo"):
            LimaRuntime(self.project, workspace, self.executable, home=home)
        self.assertFalse(home.exists())

    def owned_vm(self):
        _write_json(self.runtime.owner_path, self.owner)
        self.runtime.instance_dir.mkdir(parents=True)
        (self.runtime.instance_dir / "lima.yaml").write_text(
            "param:\n  NewPatOwner: " + self.owner["token"] + "\n", encoding="utf-8",
        )

    def ready_state(self):
        state = {**self.runtime._bindings(self.manifest), "phase": "ready", "runtime_image": LOADED_ID}
        _write_json(self.runtime.state_path, state)
        return state

    def test_lifecycle_saved_before_start_rotates_logs_and_reused_across_sessions(self):
        self.owned_vm()
        self.ready_state()
        stderr = self.runtime.instance_dir / "ha.stderr.log"
        stdout = self.runtime.instance_dir / "ha.stdout.log"
        stderr.write_text("\n".join(json.dumps({"time": "2026-01-13T10:00:0" + str(i) + "+01:00",
                                                "msg": message, "error": "/private/sample.bam"})
                                    for i, message in enumerate([
                                        "[VZ] - vm state change: running",
                                        "Received SIGTERM, shutting down the host agent",
                                        "Driver stopped due to error: /private/sample.bam",
                                    ])))
        stdout.write_text(json.dumps({"time": "2026-01-13T09:00:03Z",
                                      "status": {"exiting": True, "errors": ["secret"]}}))
        saved = self.runtime.directory / "lima-lifecycle.json"

        def start(argv, **kwargs):
            self.assertEqual(argv[-3:], ["start", "--tty=false", INSTANCE])
            self.assertTrue(saved.is_file())
            stderr.write_text("")
            stdout.write_text("")

        with (patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=start),
              patch.object(self.runtime, "_verify_application"), patch.object(self.runtime, "_verify_image")):
            self.runtime.ensure()
        other = LimaRuntime(self.project, self.workspace, self.executable, home=self.home)
        events = other.hostagent_lifecycle(since="2026-01-13T09:00:01Z")["events"]
        self.assertEqual([row["event"] for row in events], ["hostagent_sigterm", "driver_stopped", "hostagent_exiting"])
        self.assertEqual(other.hostagent_lifecycle(since="2026-01-13T09:00:04Z")["events"], [])
        self.assertNotIn("private", saved.read_text())
        self.assertNotIn("secret", saved.read_text())
        self.assertEqual(len(json.loads(saved.read_text())["events"]), 4)

    def test_lifecycle_ignores_unowned_links_malformed_and_unsuitable_records(self):
        self.owned_vm()
        stdout = self.runtime.instance_dir / "ha.stdout.log"
        stdout.write_text(json.dumps({"time": "2026-01-01T00:00:00Z", "status": {"exiting": True}}))
        (self.runtime.instance_dir / "ha.stderr.log").symlink_to(stdout)
        # An old or damaged archive cannot inject text from raw host logs.
        (self.runtime.directory / "lima-lifecycle.json").write_text(json.dumps({"events": [
            {"time": "raw text", "source": "ha.stderr.log", "event": "hostagent_sigterm"},
            {"time": "2026-01-01T00:00:01Z", "source": "ha.stderr.log", "event": "/private/file"},
            {"time": "2026-01-01T00:00:02Z", "source": "/private/file", "event": "hostagent_sigint"},
        ]}))
        self.assertEqual(len(self.runtime.hostagent_lifecycle()["events"]), 1)
        self.assertEqual(self.runtime.hostagent_lifecycle(since="invalid")["events"], [])
        stdout.unlink()
        os.mkfifo(stdout)
        self.assertEqual(self.runtime.hostagent_lifecycle()["events"], [])
        stdout.unlink()
        stdout.write_text('{"time":"2026-01-01T00:00:00Z","status":{"exiting":true}}')
        self.runtime.owner_path.unlink()
        self.assertEqual(self.runtime.hostagent_lifecycle()["events"], [])

    def test_lifecycle_reads_bounded_tails_skips_damaged_rows_and_limits_history(self):
        self.owned_vm()
        stdout = self.runtime.instance_dir / "ha.stdout.log"
        def event(i):
            return json.dumps({"time": f"2026-01-01T00:00:{i:02}Z", "status": {"running": True}})
        stdout.write_text(event(0) + "\n" + "x" * 70_000 + "\ninvalid\n" +
                          "\n".join(event(i) for i in range(1, 60)))
        result = self.runtime.hostagent_lifecycle()["events"]
        self.assertEqual(len(result), 48)
        self.assertEqual(result[0]["time"], "2026-01-01T00:00:12.000000+00:00")
        selected = self.runtime.hostagent_lifecycle(since="2026-01-01T00:00:59Z")
        self.assertEqual(len(selected["events"]), 1)

    def instance_info(self):
        return {"name": INSTANCE, "status": "Running", "config": {"mounts": self.owner["mounts"]}}

    def application_digest(self):
        path = self.project / ".distribution/macos-manifest.json"
        return file_sha256(path) + "  " + str(path)

    def test_manifest_rejects_experimental_channel_path_traversal_or_partial_contract(self):
        self.assertEqual(read_manifest(self.project), self.manifest)
        mutations = [
            lambda m: m.update(channel="experimental08"),
            lambda m: m.update(bundle_identifier="org.other.desktop"),
            lambda m: m.update(runtime_image="arbitrary:latest"),
            lambda m: m["scientific_asset"].update(name="../runtime.tar.gz"),
            lambda m: m.update(engine_description={}),
            lambda m: m.update(lima_version="latest"),
            lambda m: m.update(scientific_platform="linux/arm64"),
            lambda m: m.pop("scientific_platform"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = copy.deepcopy(self.manifest)
                mutate(value)
                _write_json(self.project / ".distribution" / "macos-manifest.json", value)
                with self.assertRaises((ValidationError, RuntimeExecutionError)):
                    read_manifest(self.project)

    def test_load_receipt_does_not_guess_from_existing_images_or_tags(self):
        self.assertEqual(loaded_image_id("Loading layer\nLoaded image ID: " + LOADED_ID), LOADED_ID)
        for output in ("", "Loaded image: latest", "Loaded image ID: sha256:123", "Loaded image ID: "
                       + LOADED_ID + "\nLoaded image ID: " + SOURCE_ID,
                       "Loaded image ID: " + LOADED_ID + "\nError unpacking image"):
            with self.subTest(output=output), self.assertRaises(RuntimeExecutionError):
                loaded_image_id(output)

    def test_both_guest_architectures_disable_rosetta(self):
        for arch in ("arm64", "x86_64"):
            manifest = dict(self.manifest, architecture=arch)
            config = self.runtime.template(manifest, self.owner)
            self.assertEqual(config["vmType"], "vz")
            self.assertEqual(config["arch"], "aarch64" if arch == "arm64" else "x86_64")
            self.assertEqual(config["vmOpts"]["vz"]["rosetta"], {"enabled": False, "binfmt": False})
            self.assertEqual(len(config["images"]), 1)
            self.assertRegex(config["images"][0]["digest"], r"^sha256:[a-f0-9]{64}$")
            self.assertIn("24.04", config["images"][0]["location"])
            self.assertNotIn("curl", config["provision"][0]["script"])
            self.assertIn("$PARAM_NewPatOwner", config["provision"][0]["script"])
            self.assertFalse(config["ssh"]["forwardAgent"])

    def test_native_evidence_checks_real_guest_image_and_r_before_recording_samtools(self):
        for hardware, target, machine in (("arm64", "linux/arm64", "aarch64"), ("x86_64", "linux/amd64", "x86_64")):
            with self.subTest(hardware=hardware), patch("platform.machine", return_value=hardware), \
                    patch.object(self.runtime, "_instance_info", return_value=self.instance_info()):
                with patch.object(self.runtime, "_run", side_effect=[machine, target, machine, "1.21"]) as run:
                    evidence = self.runtime.native_evidence(LOADED_ID)
                    self.assertEqual(evidence["r_arch"], machine)
                    self.assertEqual(evidence["samtools_version"], "1.21")
                    self.assertIn("--platform=" + target, run.call_args.args[0])
                with patch.object(self.runtime, "_run", side_effect=[machine, target, "other"]):
                    with self.assertRaisesRegex(RuntimeExecutionError, "architettura di R"):
                        self.runtime.native_evidence(LOADED_ID)

    def test_owned_arm_guest_enforces_native_execution_and_preserves_mounts(self):
        self.manifest.update(architecture="arm64", scientific_platform="linux/arm64", version="0.9.99")
        _write_json(self.project / ".distribution/macos-manifest.json", self.manifest)
        self.owned_vm()
        previous = self.runtime.template(self.manifest, self.owner)
        previous["vmOpts"]["vz"]["rosetta"] = {"enabled": True, "binfmt": True}
        previous.update(cpus=3, memory="4096MiB", disk="65GiB")
        config = self.runtime.instance_dir / "lima.yaml"
        _write_json(config, previous)
        _write_json(self.runtime.state_path, {"version": "0.9.99", "runtime_image": SOURCE_ID, "phase": "ready"})
        disk = self.runtime.instance_dir / "diffdisk"
        disk.write_text("retained guest disk")
        info = {"status": "Running", "active": "old-container", "commands": []}

        def execute(argv, **kwargs):
            info["commands"].append(argv)
            if "list" in argv:
                return json.dumps({"name": INSTANCE, "status": info["status"], "config": json.loads(config.read_bytes())})
            if "ps" in argv:
                return info["active"]
            if "stop" in argv or "start" in argv:
                info["status"] = "Stopped" if "stop" in argv else "Running"
                return ""
            if "edit" in argv:
                self.assertEqual(info["status"], "Stopped")
                expression = argv[argv.index("--set") + 1]
                self.assertNotIn(".mounts", expression)
                self.assertIn(".vmOpts.vz.rosetta.enabled = false", expression)
                self.assertIn(".vmOpts.vz.rosetta.binfmt = false", expression)
                current = json.loads(config.read_bytes())
                current["vmOpts"]["vz"]["rosetta"] = {"enabled": False, "binfmt": False}
                _write_json(config, current)
                return ""
            if "sha256sum" in argv:
                return self.application_digest()
            if "load" in argv:
                return "Loaded image ID: " + LOADED_ID
            if "inspect" in argv:
                return LOADED_ID + " linux arm64"
            if "describe" in argv:
                self.assertIn("--platform=linux/arm64", argv)
                return json.dumps(self.manifest["engine_description"])
            self.fail(argv)
        with patch.dict(os.environ, {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}), \
                patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=execute):
            self.assertTrue(self.runtime.requires_mount_repair())
            with self.assertRaisesRegex(ValidationError, "attivi"):
                self.runtime.prepare()
            self.assertFalse(any("stop" in argv or "edit" in argv for argv in info["commands"]))
            info["active"] = ""
            state = self.runtime.prepare()
            self.assertEqual(state["scientific_platform"], "linux/arm64")
            self.assertFalse(self.runtime.requires_mount_repair())
            self.assertEqual(self.runtime.prepare(), state)
        self.assertEqual(sum("load" in argv for argv in info["commands"]), 1)
        current = json.loads(config.read_bytes())
        for key in ("mounts", "disk", "memory", "cpus", "param"):
            self.assertEqual(current[key], previous[key])
        self.assertEqual(disk.read_text(), "retained guest disk")

    def test_owned_config_accepts_original_json_and_lima_yaml(self):
        self.owned_vm()
        self.assertEqual(self.runtime._assert_owned(), self.owner)
        _write_json(self.runtime.instance_dir / "lima.yaml", self.runtime.template(self.manifest, self.owner))
        self.assertEqual(self.runtime._assert_owned(), self.owner)

    def test_initial_vm_budget_leaves_host_memory_available(self):
        with patch("newpat.resources.host_resources", return_value={"memory_mib": 8192, "cpus": 4}):
            config = self.runtime.template(self.manifest, self.owner)
        self.assertEqual(config["memory"], "4096MiB")
        self.assertEqual(config["cpus"], 3)
        with patch("newpat.resources.host_resources", return_value={"memory_mib": 32768, "cpus": 24}):
            config = self.runtime.template(self.manifest, self.owner)
        self.assertEqual(config["memory"], "8192MiB")
        self.assertEqual(config["cpus"], 4)

    def test_does_not_adopt_an_existing_unowned_vm(self):
        self.runtime.instance_dir.mkdir(parents=True)
        (self.runtime.instance_dir / "keep").write_text("unrelated")
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run") as execute:
            with self.assertRaisesRegex(ValidationError, "non gestita"):
                self.runtime.prepare()
        execute.assert_not_called()
        self.assertFalse(self.runtime.owner_path.exists())
        self.assertEqual((self.runtime.instance_dir / "keep").read_text(), "unrelated")

    def orphaned_vm(self):
        limactl = self.project.parent / "lima/bin/limactl"
        limactl.parent.mkdir(parents=True)
        limactl.write_bytes(b"bundled executable fixture")
        limactl.chmod(0o755)
        runtime = LimaRuntime(self.project, self.workspace, limactl, home=self.home)
        runtime.instance_dir.mkdir(parents=True)
        config = runtime.template(self.manifest, self.owner)
        _write_json(runtime.instance_dir / "lima.yaml", config)
        (runtime.instance_dir / "diffdisk").write_bytes(b"original virtual disk")
        return runtime

    def test_stopped_orphan_is_preserved_and_replacement_is_reused(self):
        runtime = self.orphaned_vm()
        prior = (runtime.instance_dir / "lima.yaml").read_bytes()
        saved_run = self.workspace / "runs" / "previous experiment" / "run.json"
        _write_json(saved_run, {"status": "succeeded", "run_id": "previous"})
        original_run = saved_run.read_bytes()
        other_vm = runtime.lima_home / "unrelated-vm" / "user-disk"
        other_vm.parent.mkdir()
        other_vm.write_bytes(b"foreign disk")
        starts = []
        imports = []
        status = "Stopped"

        def execute(argv, **kwargs):
            nonlocal status
            if "list" in argv:
                return json.dumps({"name": INSTANCE, "dir": str(runtime.instance_dir), "status": status,
                                   "config": json.loads((runtime.instance_dir / "lima.yaml").read_text())})
            if "start" in argv:
                if "--name=" + INSTANCE in argv:
                    self.assertFalse(runtime.instance_dir.exists())
                    runtime.instance_dir.mkdir()
                    (runtime.instance_dir / "lima.yaml").write_bytes(Path(argv[-1]).read_bytes())
                    starts.append(argv)
                status = "Running"
                return ""
            if "load" in argv:
                imports.append(argv)
                return "Loaded image ID: " + LOADED_ID
            if "inspect" in argv:
                return LOADED_ID + " linux amd64"
            if "describe" in argv:
                return json.dumps(self.manifest["engine_description"])
            if "sha256sum" in argv:
                return self.application_digest()
            self.fail(f"Unexpected command during orphan recovery: {argv}")

        lease = {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}
        with (redirect_stdout(io.StringIO()), patch.dict(os.environ, lease),
              patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute)):
            self.assertTrue(runtime.requires_mount_repair())
            state = runtime.prepare()
            self.assertEqual(state["phase"], "ready")
            self.assertEqual(state["runtime_image"], LOADED_ID)
            self.assertNotEqual(runtime._assert_owned()["token"], self.owner["token"])
            self.assertFalse(runtime.requires_mount_repair())
            self.assertEqual(runtime.prepare(), state)
        self.assertEqual((len(starts), len(imports)), (1, 1))
        backups = list(runtime.lima_home.parent.glob("recovered-newpat-*/newpat"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "lima.yaml").read_bytes(), prior)
        self.assertEqual((backups[0] / "diffdisk").read_bytes(), b"original virtual disk")
        self.assertEqual(other_vm.read_bytes(), b"foreign disk")
        self.assertEqual(saved_run.read_bytes(), original_run)

    def test_orphan_recovery_refuses_active_foreign_or_ambiguous_instances(self):
        runtime = self.orphaned_vm()
        yaml = runtime.instance_dir / "lima.yaml"
        original = json.loads(yaml.read_text())
        active = {"name": INSTANCE, "dir": str(runtime.instance_dir), "status": "Stopped"}
        lease = {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}
        cases = [
            ("running", {"status": "Running"}, original),
            ("protected", {"protected": True}, original),
            ("inspection_errors", {"errors": ["inconsistent disk metadata"]}, original),
            ("host_agent_still_present", {"hostAgentPID": 1234}, original),
            ("driver_still_present", {"driverPID": 5678}, original),
            ("wrong_directory", {"dir": str(runtime.lima_home / "foreign")}, original),
            ("wrong_name", {"name": "foreign"}, original),
            ("no_provision", {}, dict(original, provision=[])),
            ("foreign_token", {}, dict(original, param={"NewPatOwner": "unrelated"})),
        ]
        for label, info, config in cases:
            _write_json(yaml, config)
            before = yaml.read_bytes()
            report = json.dumps({**active, **info, "config": config})
            with (self.subTest(case=label), patch.dict(os.environ, lease),
                  patch.object(runtime, "_host_check"), patch.object(runtime, "_run", return_value=report) as run,
                  self.assertRaises((ValidationError, RuntimeExecutionError))):
                runtime.prepare()
            self.assertTrue(all("list" in call.args[0] for call in run.call_args_list))
            self.assertEqual(yaml.read_bytes(), before)
            self.assertEqual((runtime.instance_dir / "diffdisk").read_bytes(), b"original virtual disk")
            self.assertFalse(runtime.owner_path.exists())
            self.assertFalse(list(runtime.lima_home.parent.glob("recovered-newpat-*")))

    def test_orphan_recovery_requires_launcher_maintenance_and_rejects_linked_paths(self):
        runtime = self.orphaned_vm()
        config_file = runtime.instance_dir / "lima.yaml"
        original = config_file.read_bytes()
        linked_file = self.home / "user-file"
        linked_file.write_bytes(original)
        info = json.dumps({"name": INSTANCE, "dir": str(runtime.instance_dir), "status": "Stopped",
                           "config": json.loads(original)})
        lease = {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}
        for label in ("no-exclusive-lease", "wrong-launcher", "linked-config", "dangling-owner"):
            environment = dict(lease)
            if label == "no-exclusive-lease":
                environment["NEWPAT_RUNTIME_MAINTENANCE"] = "0"
            elif label == "wrong-launcher":
                environment["NEWPAT_LAUNCHER_PID"] = str(os.getppid() + 1)
            elif label == "linked-config":
                config_file.unlink()
                config_file.symlink_to(linked_file)
            else:
                runtime.owner_path.parent.mkdir(parents=True, exist_ok=True)
                runtime.owner_path.symlink_to(self.home / "missing-owner")
            with (self.subTest(case=label), patch.dict(os.environ, environment),
                  patch.object(runtime, "_host_check"), patch.object(runtime, "_run", return_value=info) as run,
                  self.assertRaises((ValidationError, RuntimeExecutionError))):
                runtime.prepare()
            self.assertTrue(all("list" in call.args[0] for call in run.call_args_list))
            self.assertFalse(list(runtime.lima_home.parent.glob("recovered-newpat-*")))
            self.assertEqual((runtime.instance_dir / "diffdisk").read_bytes(), b"original virtual disk")
            if label == "linked-config":
                self.assertTrue(config_file.is_symlink())
                config_file.unlink()
                config_file.write_bytes(original)
            if label == "dangling-owner":
                self.assertTrue(runtime.owner_path.is_symlink())
                self.assertFalse((self.home / "missing-owner").exists())
            self.assertEqual(linked_file.read_bytes(), original)

    def test_linked_orphan_instance_never_moves_the_target(self):
        runtime = self.orphaned_vm()
        target = self.home / "other-vm"
        runtime.instance_dir.rename(target)
        runtime.instance_dir.symlink_to(target, target_is_directory=True)
        config = json.loads((target / "lima.yaml").read_text())
        info = json.dumps({"name": INSTANCE, "dir": str(runtime.instance_dir), "status": "Stopped", "config": config})
        lease = {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}
        with (patch.dict(os.environ, lease), patch.object(runtime, "_host_check"),
              patch.object(runtime, "_run", return_value=info) as execute,
              self.assertRaises((ValidationError, RuntimeExecutionError))):
            runtime.prepare()
        self.assertTrue(all("list" in call.args[0] for call in execute.call_args_list))
        self.assertTrue(runtime.instance_dir.is_symlink())
        self.assertEqual((target / "diffdisk").read_bytes(), b"original virtual disk")
        self.assertFalse(list(runtime.lima_home.parent.glob("recovered-newpat-*")))

    def test_remove_rejects_forged_ownership_and_preserves_analyses(self):
        self.owned_vm()
        self.ready_state()
        data = self.workspace / "data" / "keep.bam"
        data.parent.mkdir(parents=True)
        data.write_text("original")
        (self.runtime.instance_dir / "lima.yaml").write_text("param:\n  NewPatOwner: foreign\n")
        with patch.object(self.runtime, "_run") as execute:
            with self.assertRaises(ValidationError):
                self.runtime.remove_runtime()
            execute.assert_not_called()
        (self.runtime.instance_dir / "lima.yaml").write_text("param:\n  NewPatOwner: " + self.owner["token"] + "\n")
        with patch.object(self.runtime, "_run", return_value="") as execute:
            self.runtime.remove_runtime()
            self.assertEqual(execute.call_args.args[0][-3:], ["delete", "--force", INSTANCE])
        self.assertEqual(data.read_text(), "original")
        self.assertFalse(self.runtime.state_path.exists())
        self.assertFalse(self.runtime.owner_path.exists())

    def test_checksum_failure_prevents_any_image_load(self):
        self.owned_vm()
        self.archive.write_bytes(b"tampered archive")
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_instance_info", return_value=self.instance_info()), patch.object(self.runtime, "_verify_application"), patch.object(self.runtime, "_run", return_value="") as execute:
            with self.assertRaisesRegex(ValidationError, "checksum"):
                self.runtime.prepare()
        self.assertFalse(any("load" in call.args[0] for call in execute.call_args_list))
        self.assertEqual(json.loads(self.runtime.state_path.read_text())["phase"], "failed")

    def test_verified_import_accepts_local_id_only_with_exact_contract(self):
        self.owned_vm()
        responses = [json.dumps(self.instance_info()), "started", self.application_digest(), "Loaded image ID: " + LOADED_ID,
                     LOADED_ID + " linux amd64", json.dumps(self.manifest["engine_description"])]
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=responses) as execute:
            state = self.runtime.prepare()
        self.assertEqual(state["runtime_image"], LOADED_ID)
        self.assertEqual(state["source_runtime_image"], SOURCE_ID)
        self.assertEqual(state["phase"], "ready")
        self.assertFalse(any("image" in call.args[0] and "ls" in call.args[0] for call in execute.call_args_list))

    def test_first_prepare_creates_only_owned_instance_and_survives_json_config(self):
        original = self.archive.read_bytes()

        def execute(argv, **kwargs):
            if "start" in argv:
                self.assertIn("--name=newpat", argv)
                self.runtime.instance_dir.mkdir(parents=True)
                (self.runtime.instance_dir / "lima.yaml").write_bytes(Path(argv[-1]).read_bytes())
                return "started"
            if "load" in argv:
                return "Loaded image ID: " + LOADED_ID
            if "inspect" in argv:
                return LOADED_ID + " linux amd64"
            if "describe" in argv:
                return json.dumps(self.manifest["engine_description"])
            if "sha256sum" in argv:
                return self.application_digest()
            self.fail(f"Unexpected runtime command: {argv}")

        with redirect_stdout(io.StringIO()), patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=execute):
            state = self.runtime.prepare()
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(self.runtime._assert_owned()["instance"], INSTANCE)

    def test_first_boot_failure_records_diagnostic_and_can_be_retried(self):
        with redirect_stdout(io.StringIO()), patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=RuntimeExecutionError("download failed")):
            with self.assertRaisesRegex(RuntimeExecutionError, "download failed"):
                self.runtime.prepare()
        state = json.loads(self.runtime.state_path.read_text())
        self.assertEqual(state["phase"], "failed")
        self.assertIn("download failed", state["last_error"])
        self.assertTrue(self.runtime.owner_path.exists())

    def test_same_interface_different_science_is_rejected(self):
        altered = copy.deepcopy(self.manifest["engine_description"])
        altered["workflows"]["cpi"]["sha256"] = "f" * 64
        with patch.object(self.runtime, "_run", side_effect=[LOADED_ID + " linux amd64", json.dumps(altered)]):
            with self.assertRaisesRegex(RuntimeExecutionError, "non corrisponde"):
                self.runtime._verify_image(self.manifest, LOADED_ID)

    def test_repeated_prepare_reuses_verified_vm_without_import(self):
        self.owned_vm()
        state = self.ready_state()
        responses = [json.dumps(self.instance_info()), "started", self.application_digest()]
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run", side_effect=responses) as execute, patch.object(self.runtime, "_verify_image") as verify:
            self.assertEqual(self.runtime.prepare(), state)
        verify.assert_called_once_with(self.manifest, LOADED_ID)
        self.assertEqual(len(execute.call_args_list), 3)
        self.assertEqual(execute.call_args_list[1].args[0][-3:], ["start", "--tty=false", INSTANCE])

    def test_ensure_waits_for_another_experiments_cold_start_then_verifies_image(self):
        self.owned_vm()
        state = self.ready_state()
        with (patch.object(self.runtime, "_host_check"),
              patch("fcntl.flock", side_effect=[BlockingIOError(), None, None]),
              patch("newpat.macos_runtime.time.monotonic", side_effect=[0.0, 20.0]),
              patch("newpat.macos_runtime.time.sleep"),
              patch.object(self.runtime, "_run", side_effect=["started", self.application_digest()]),
              patch.object(self.runtime, "_verify_image") as verify):
            self.assertEqual(self.runtime.ensure(), state)
        verify.assert_called_once_with(self.manifest, LOADED_ID)

    def test_ensure_requires_correct_build_and_never_imports_or_creates(self):
        self.owned_vm()
        state = self.ready_state()
        state["source_commit"] = "e" * 40
        _write_json(self.runtime.state_path, state)
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run") as execute:
            with self.assertRaisesRegex(ValidationError, "altra build"):
                self.runtime.ensure()
        execute.assert_not_called()

    def relocated_runtime(self, *, old_application=False):
        """Model a Desktop installation followed by a different application path."""
        external = tempfile.TemporaryDirectory(prefix="applications-")
        self.addCleanup(external.cleanup)
        new_project = Path(external.name) / "NewPat.app/Contents/Resources/app"
        new_project.mkdir(parents=True)
        _write_json(new_project / ".distribution/macos-manifest.json", self.manifest)
        # The real macOS temp path is not a parent of /Applications. Avoid the
        # Linux test runner's /tmp parent covering every fixture application.
        temporary = self.home / "T"
        temporary.mkdir()
        environment = patch.dict(os.environ, {"TMPDIR": str(temporary),
                                "NEWPAT_RUNTIME_MAINTENANCE": "1",
                                "NEWPAT_LAUNCHER_PID": str(os.getppid())})
        environment.start()
        self.addCleanup(environment.stop)
        self.owner["mounts"] = self.runtime.default_mounts()
        if old_application:
            old = Path(external.name) / "moved" / "NewPat.app/Contents/Resources/app"
            self.owner["mounts"].append({"location": str(old), "mountPoint": str(old), "writable": False})
        custom = {"location": "/Volumes/Scientific Data", "mountPoint": "/Volumes/Scientific Data", "writable": True}
        self.owner["mounts"].append(custom)
        self.owned_vm()
        self.ready_state()
        config = {"param": {"NewPatOwner": self.owner["token"]}, "memory": "6144MiB", "cpus": 3,
                  "mounts": copy.deepcopy(self.owner["mounts"]), "disk": "65GiB"}
        _write_json(self.runtime.instance_dir / "lima.yaml", config)
        runtime = LimaRuntime(new_project, self.workspace, self.executable, home=self.home)
        state = {"status": "Running", "active": "", "fail_edit": False, "fail_probe": False, "commands": []}

        def execute(argv, **kwargs):
            state["commands"].append(argv)
            if "list" in argv:
                current = json.loads((runtime.instance_dir / "lima.yaml").read_text())
                return json.dumps({"name": INSTANCE, "status": state["status"], "config": current})
            if "ps" in argv:
                return state["active"]
            if "stop" in argv:
                state["status"] = "Stopped"
                return ""
            if "edit" in argv:
                self.assertEqual(state["status"], "Stopped")
                current = json.loads((runtime.instance_dir / "lima.yaml").read_text())
                expression = argv[argv.index("--set") + 1]
                clauses = expression.split(" | ")
                for clause in clauses[:-1]:
                    retired = json.loads(clause.removeprefix(".mounts |= map(select(.location != ").removesuffix("))"))
                    current["mounts"] = [item for item in current["mounts"] if item["location"] != retired]
                additions = json.loads(clauses[-1].removeprefix(".mounts += "))
                current["mounts"].extend(additions)
                _write_json(runtime.instance_dir / "lima.yaml", current)
                if state["fail_edit"]:
                    raise RuntimeExecutionError("edit failed after write")
                return ""
            if "start" in argv:
                state["status"] = "Running"
                return ""
            if "sha256sum" in argv:
                if state["fail_probe"]:
                    return "0" * 64 + "  " + argv[-1]
                return file_sha256(Path(argv[-1])) + "  " + argv[-1]
            self.fail(f"Unexpected relocation command: {argv}")
        return runtime, state, execute, config

    def assert_successful_relocation(self, *, old_application=False):
        runtime, state, execute, before = self.relocated_runtime(old_application=old_application)
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute), patch.object(runtime, "_verify_image"):
            self.assertTrue(runtime.requires_mount_repair())
            result = runtime.prepare()
            self.assertFalse(runtime.requires_mount_repair())
        self.assertEqual(result["phase"], "ready")
        after = json.loads((runtime.instance_dir / "lima.yaml").read_text())
        for key in ("memory", "cpus", "disk", "param"):
            self.assertEqual(after[key], before[key])
        retained = [item for item in before["mounts"] if not item["location"].endswith("/moved/NewPat.app/Contents/Resources/app")]
        self.assertEqual(after["mounts"][:-1], retained)
        self.assertEqual(after["mounts"][-1], {"location": str(runtime.project), "mountPoint": str(runtime.project), "writable": False})
        self.assertTrue(list(runtime.directory.glob("mount-backup-*.json")))
        self.assertFalse(any("delete" in call or "load" in call for call in state["commands"]))

    def test_desktop_to_applications_relocation_preserves_vm_and_configuration(self):
        self.assert_successful_relocation()

    def test_relocating_app_bundle_preserves_vm_and_custom_configuration(self):
        self.assert_successful_relocation(old_application=True)

    def test_existing_application_and_custom_readonly_mounts_are_preserved(self):
        runtime, state, execute, before = self.relocated_runtime(old_application=True)
        previous = next(item["location"] for item in before["mounts"] if "/moved/NewPat.app/" in item["location"])
        Path(previous).mkdir(parents=True)
        custom = {"location": str(self.home / "custom-readonly"),
                  "mountPoint": str(self.home / "custom-readonly"), "writable": False}
        before["mounts"].append(custom)
        owner = runtime._owner()
        owner["mounts"].append(custom)
        _write_json(runtime.owner_path, owner)
        _write_json(runtime.instance_dir / "lima.yaml", before)
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute), patch.object(runtime, "_verify_image"):
            runtime.prepare()
        actual = json.loads((runtime.instance_dir / "lima.yaml").read_text())
        self.assertEqual(actual["mounts"][:-1], before["mounts"])

    def test_modified_previous_mount_is_never_retired_as_application_mount(self):
        runtime, state, execute, before = self.relocated_runtime(old_application=True)
        for item in before["mounts"]:
            if "/moved/NewPat.app/" in item["location"]:
                item["writable"] = True
        _write_json(runtime.instance_dir / "lima.yaml", before)
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute):
            with self.assertRaisesRegex(ValidationError, "condivisione personalizzata"):
                runtime.prepare()
        self.assertFalse(any("stop" in call or "edit" in call for call in state["commands"]))

    def test_mount_repair_refuses_running_analysis_before_stop_or_edit(self):
        runtime, state, execute, before = self.relocated_runtime()
        state["active"] = "container-with-active-analysis"
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute):
            with self.assertRaisesRegex(ValidationError, "analisi o container attivi"):
                runtime.prepare()
        self.assertFalse(any("stop" in call or "edit" in call for call in state["commands"]))
        self.assertEqual(json.loads((runtime.instance_dir / "lima.yaml").read_text()), before)

    def test_mount_repair_requires_exclusive_launcher_lease(self):
        runtime, state, execute, before = self.relocated_runtime()
        with patch.dict(os.environ, {"NEWPAT_RUNTIME_MAINTENANCE": "0"}), patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute):
            with self.assertRaisesRegex(ValidationError, "Chiudere tutte le sessioni"):
                runtime.prepare()
        self.assertFalse(any("stop" in call or "edit" in call for call in state["commands"]))

    def test_failed_mount_edit_rolls_back_owner_configuration_and_running_state(self):
        runtime, state, execute, before = self.relocated_runtime()
        owner_before = runtime.owner_path.read_bytes()
        config_before = (runtime.instance_dir / "lima.yaml").read_bytes()
        state["fail_edit"] = True
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute):
            with self.assertRaisesRegex(RuntimeExecutionError, "configurazione precedente ripristinata"):
                runtime.prepare()
        self.assertEqual(runtime.owner_path.read_bytes(), owner_before)
        self.assertEqual((runtime.instance_dir / "lima.yaml").read_bytes(), config_before)
        self.assertEqual(state["status"], "Running")
        self.assertFalse(any("delete" in call for call in state["commands"]))

    def test_failed_guest_probe_restores_old_mounts_after_app_relocation(self):
        runtime, state, execute, before = self.relocated_runtime(old_application=True)
        owner_before = runtime.owner_path.read_bytes()
        config_before = (runtime.instance_dir / "lima.yaml").read_bytes()
        state["fail_probe"] = True
        with patch.object(runtime, "_host_check"), patch.object(runtime, "_run", side_effect=execute):
            with self.assertRaisesRegex(RuntimeExecutionError, "configurazione precedente ripristinata"):
                runtime.prepare()
        self.assertEqual(runtime.owner_path.read_bytes(), owner_before)
        self.assertEqual((runtime.instance_dir / "lima.yaml").read_bytes(), config_before)
        self.assertEqual(state["status"], "Running")

    def test_guest_visibility_failure_prevents_ready_and_image_reimport(self):
        self.owned_vm()
        self.ready_state()
        stale_manifest = "0" * 64 + self.application_digest()[64:]
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "requires_mount_repair", return_value=False), patch.object(self.runtime, "_run", side_effect=["", stale_manifest]) as execute, patch.object(self.runtime, "_verify_image") as image:
            with self.assertRaisesRegex(RuntimeExecutionError, "copia diversa"):
                self.runtime.prepare()
        image.assert_not_called()
        self.assertFalse(any("load" in call.args[0] for call in execute.call_args_list))

    def test_replaced_app_at_same_path_recovers_only_an_idle_guest_under_exclusive_lease(self):
        self.owned_vm()
        self.ready_state()
        manifest_path = self.project / ".distribution/macos-manifest.json"
        missing = (1, "", f"sha256sum: {manifest_path}: No such file or directory")
        mismatch = (0, "0" * 64 + "  " + str(manifest_path), "")
        success = (0, self.application_digest(), "")
        for failure in (missing, mismatch):
            with self.subTest(failure=failure):
                checks = iter([failure, failure, failure, success, success])
                actions = []
                active = "running-experiment"

                def guest(argv, **kwargs):
                    if "sha256sum" in argv:
                        return subprocess.CompletedProcess(argv, *next(checks))
                    if "ps" in argv:
                        return subprocess.CompletedProcess(argv, 0, active, "")
                    action = argv[len(self.runtime.host_prefix())]
                    self.assertIn(action, {"start", "stop"})
                    actions.append(action)
                    return subprocess.CompletedProcess(argv, 0, "", "")

                environment = {"NEWPAT_LAUNCHER_PID": str(os.getppid()), "NEWPAT_RUNTIME_MAINTENANCE": ""}
                with (patch.dict(os.environ, environment), patch.object(LimaRuntime, "from_environment", return_value=self.runtime),
                      patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_verify_image"),
                      patch.object(self.runtime, "_instance_info", return_value=self.instance_info()),
                      patch("newpat.macos_runtime.subprocess.run", side_effect=guest)):
                    self.assertEqual(main(["prepare"]), os.EX_TEMPFAIL)
                    self.assertNotIn("stop", actions)
                    os.environ["NEWPAT_RUNTIME_MAINTENANCE"] = "1"
                    with self.assertRaisesRegex(ValidationError, "container attivi"):
                        self.runtime.prepare()
                    self.assertNotIn("stop", actions)
                    active = ""
                    self.assertEqual(main(["prepare"]), 0)
                    self.assertEqual(actions[-2:], ["stop", "start"])
                    os.environ["NEWPAT_RUNTIME_MAINTENANCE"] = ""
                    self.assertEqual(main(["prepare"]), 0)
                    self.assertEqual(actions.count("stop"), 1)

    def test_guest_manifest_failures_do_not_authorize_unbounded_or_speculative_restarts(self):
        self.owned_vm()
        path = self.project / ".distribution/macos-manifest.json"
        cases = [
            (255, "", "ssh: connection refused", 0),
            (1, "", f"sha256sum: {path}: Permission denied", 0),
            (1, "", "sha256sum: /other: No such file or directory", 0),
            (0, "not a valid digest", "", 0),
            (0, "0" * 64 + "  wrong-path", "", 0),
            (1, "", f"sha256sum: {path}: No such file or directory", 1),
        ]
        for code, stdout, stderr, expected_stops in cases:
            with self.subTest(code=code, stdout=stdout, stderr=stderr):
                def guest(argv, **kwargs):
                    if "sha256sum" in argv:
                        return subprocess.CompletedProcess(argv, code, stdout, stderr)
                    return subprocess.CompletedProcess(argv, 0, "", "")

                with (patch.dict(os.environ, {"NEWPAT_RUNTIME_MAINTENANCE": "1", "NEWPAT_LAUNCHER_PID": str(os.getppid())}),
                      patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_instance_info", return_value=self.instance_info()),
                      patch("newpat.macos_runtime.subprocess.run", side_effect=guest) as runner, self.assertRaises(RuntimeExecutionError)):
                    self.runtime.prepare()
                self.assertEqual(sum("stop" in call.args[0] for call in runner.call_args_list), expected_stops)

    def test_owner_claim_alone_does_not_hide_missing_live_mount(self):
        runtime, state, execute, before = self.relocated_runtime()
        owner = runtime._owner()
        owner["mounts"].append({"location": str(runtime.project), "mountPoint": str(runtime.project), "writable": False})
        _write_json(runtime.owner_path, owner)
        with patch.object(runtime, "_run", side_effect=execute):
            self.assertTrue(runtime.requires_mount_repair())

    def test_concurrent_prepare_is_rejected_without_stealing_lock(self):
        with self.runtime.lock():
            with self.assertRaisesRegex(RuntimeExecutionError, "già in corso"):
                with self.runtime.lock(timeout=0):
                    self.fail("lock was stolen")

    def test_paths_preserve_spaces_and_special_characters_without_shell_commands(self):
        value = self.home / "Case $HOME; $(touch nope), è" / "sample.bam"
        with patch("newpat.macos_runtime.subprocess.run") as run:
            self.assertEqual(self.runtime.host_path(value), str(value))
            command = self.runtime.docker_command(["image", "load", "--input", str(value)])
        run.assert_not_called()
        self.assertEqual(command[-1], str(value))
        self.assertNotIn("sh", command)
        self.assertNotIn("-c", command)
        self.assertIn("LIMA_HOME=" + str(self.home / ".newpat/lima"), command)
        self.assertIn("SSH=/usr/bin/ssh", command)
        self.assertIn("--workdir=/", command)
        from platform import machine
        from newpat.macos_runtime import scientific_platform
        self.assertIn("DOCKER_DEFAULT_PLATFORM=" + scientific_platform(machine()), command)

    def test_paths_outside_mounts_and_escaping_symlinks_are_rejected(self):
        outside = Path("/unshared/newpat/file.bam")
        with self.assertRaisesRegex(ValidationError, "non condivisa"):
            self.runtime.host_path(outside)
        link = self.home / "escape"
        link.symlink_to("/unshared")
        with self.assertRaises(ValidationError):
            self.runtime.host_path(link / "input.bam")
        for raw in ("", "/tmp/path\n", "/tmp/path\x00"):
            with self.assertRaises(ValidationError):
                self.runtime.host_path(raw)

    def test_first_setup_mounts_custom_root_but_never_whole_system(self):
        self.owned_vm()
        with patch.object(self.runtime, "_host_check"), patch.object(self.runtime, "_run") as execute:
            with self.assertRaisesRegex(ValidationError, "radice"):
                self.runtime.prepare([Path("/")])
        execute.assert_not_called()

    def test_host_check_rejects_foreign_lima_version_and_global_overrides(self):
        with patch("newpat.macos_runtime.sys.platform", "darwin"), patch("newpat.macos_runtime.platform.mac_ver", return_value=("14.7", (), "")), patch("newpat.macos_runtime.platform.machine", return_value="x86_64"), patch.object(self.runtime, "_run", return_value="limactl version 99.0.0"):
            with self.assertRaisesRegex(ValidationError, "versione Lima"):
                self.runtime._host_check(self.manifest)
        override = self.runtime.lima_home / "_config" / "override.yaml"
        override.parent.mkdir(parents=True)
        override.write_text("vmType: qemu")
        with patch("newpat.macos_runtime.sys.platform", "darwin"), patch("newpat.macos_runtime.platform.mac_ver", return_value=("14.7", (), "")), patch("newpat.macos_runtime.platform.machine", return_value="x86_64"), patch.object(self.runtime, "_run") as execute:
            with self.assertRaisesRegex(ValidationError, "Override"):
                self.runtime._host_check(self.manifest)
        execute.assert_not_called()

    def test_process_failure_is_logged_and_reported(self):
        failed = subprocess.CompletedProcess([], 7, "", "VZ not available")
        with patch("newpat.macos_runtime.subprocess.run", return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeExecutionError, "VZ not available"):
                self.runtime._run(["limactl", "start", INSTANCE])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertIn("VZ not available", (self.runtime.directory / "setup.log").read_text())

    def test_real_runner_report_preserves_failed_step_evidence(self):
        source = Path(__file__).resolve().parents[1] / "scripts/verify_macos_runtime.py"
        spec = importlib.util.spec_from_file_location("verify_macos_runtime_fixture", source)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        app = self.home / "Fixture.app"
        resources = app / "Contents/Resources"
        (resources / "app/.distribution").mkdir(parents=True)
        (resources / "NewPat.command").write_text("fixture")
        _write_json(resources / "app/.distribution/macos-manifest.json", self.manifest)
        self.ready_state()
        report_path = self.home / "evidence/report.json"
        with patch.object(verifier.sys, "platform", "darwin"), patch.object(verifier.Path, "home", return_value=self.home), patch.object(verifier.platform, "mac_ver", return_value=("14.7", (), "")), patch.object(verifier.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 7)]):
            report = verifier.verify(app, report_path)
        self.assertFalse(report["passed"])
        self.assertEqual(report["checks"][-1]["name"], "doctor")
        self.assertEqual(report["checks"][-1]["exit_code"], 7)
        self.assertEqual(json.loads(report_path.read_text()), report)
        self.assertTrue(self.runtime.state_path.exists())
        logs = report_path.parent / "report-logs"
        (logs / "prepare.log").write_text("first run")
        with (patch.object(verifier.sys, "platform", "darwin"),
              patch.object(verifier.Path, "home", return_value=self.home),
              patch.object(verifier.subprocess, "run") as launch):
            with self.assertRaisesRegex(FileExistsError, "report.json"):
                verifier.verify(app, report_path)
            self.assertEqual(json.loads(report_path.read_text()), report)
            report_path.unlink()
            with self.assertRaisesRegex(FileExistsError, "report-logs"):
                verifier.verify(app, report_path)
            self.assertEqual((logs / "prepare.log").read_text(), "first run")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
