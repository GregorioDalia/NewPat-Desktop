"""Owned Lima runtime for the macOS distribution.

The host never needs Docker, Homebrew, or a system Python. Lima is bundled with
the application; Docker runs only in the private VM. Scientific code is loaded
from a checksummed archive and checked against the build's complete descriptor.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid

from newpat.environment import setting
from newpat.errors import NewPatError, RuntimeExecutionError, ValidationError


CHANNEL = "desktop"
INSTANCE = "newpat"
LIMA_VERSION = "2.2.1"
WORKSPACE_NAME = "NewPat-Desktop"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LINUX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_HA_MESSAGES = {
    "[VZ] - vm state change: running": "vz_running",
    "[VZ] - vm state change: stopped": "vz_stopped",
    "Received SIGTERM, shutting down the host agent": "hostagent_sigterm",
    "Received SIGINT, shutting down the host agent": "hostagent_sigint",
    "Context closed, stopping vm": "vz_context_closed",
    "an error during shutting down the host agent": "hostagent_shutdown_error",
    "guest agent events closed unexpectedly": "guest_events_closed",
    "connection to the guest agent was closed unexpectedly": "guest_connection_closed",
}
_HA_SOURCES = ("ha.stderr.log", "ha.stdout.log")
_HA_EVENTS = set(_HA_MESSAGES.values()) | {
    "driver_stopped", "hostagent_running", "hostagent_degraded", "hostagent_exiting",
}
_HA_BYTES = 64 * 1024
_HA_EVENT_LIMIT = 48
# Pinned upstream Lima v2.2.1 ubuntu-24.04 template. No mutable fallback URL.
# https://github.com/lima-vm/lima/blob/v2.2.1/templates/_images/ubuntu-24.04.yaml
_BASE_IMAGES = {
    "x86_64": {
        "location": "https://cloud-images.ubuntu.com/releases/noble/release-20260926/ubuntu-24.04-server-cloudimg-amd64.img",
        "arch": "x86_64",
        "digest": "sha256:6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2",
    },
    "arm64": {
        "location": "https://cloud-images.ubuntu.com/releases/noble/release-20260926/ubuntu-24.04-server-cloudimg-arm64.img",
        "arch": "aarch64",
        "digest": "sha256:1d6bffe64b848468ac97f821d369a4846d983de1800ccf6b5ec8853e85cefc55",
    },
}
_PROVISION = """#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends docker.io docker-compose-v2
fi
systemctl enable --now docker
printf '%s\\n' "$PARAM_NewPatOwner" > /etc/newpat-owner
"""


class _StaleApplicationMount(RuntimeExecutionError):
    """The guest cannot see the current host manifest on a configured mount."""


class _ExclusivePreparationRequired(RuntimeExecutionError):
    """The launcher must repeat prepare under an exclusive installation lease."""


def _exclusive_maintenance() -> bool:
    return (os.environ.get("NEWPAT_RUNTIME_MAINTENANCE") == "1"
            and os.environ.get("NEWPAT_LAUNCHER_PID") == str(os.getppid()))


def absolute_path(value: str | Path) -> Path:
    raw = os.fspath(value)
    if not raw or any(unicodedata.category(c) == "Cc" for c in raw):
        raise ValidationError("Percorso macOS vuoto o con caratteri di controllo.")
    return Path(raw).expanduser().resolve()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Configurazione NewPat non leggibile: {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Configurazione NewPat non valida: {path}")
    return value


def _write_bytes(path: Path, value: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(value)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: dict) -> None:
    _write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _lifecycle_bytes(path: Path) -> bytes:
    """Read a bounded tail of a regular, user-owned file without following links."""
    try:
        if path.parent.resolve(strict=True) != path.parent:
            return b""
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                return b""
            stream.seek(max(0, info.st_size - _HA_BYTES))
            return stream.read(_HA_BYTES)
    except (OSError, RuntimeError):
        return b""


def _lifecycle_time(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("missing time zone")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def _hostagent_event(row: dict, source: str) -> str | None:
    # Lima 2.2.1 sends logrus JSON to stderr and hostagent/events.Event to stdout.
    # Error text, addresses, command lines and guest-provided fields stay local.
    if source == "ha.stderr.log":
        message = row.get("msg")
        if isinstance(message, str):
            if message.startswith("Driver stopped due to error: "):
                return "driver_stopped"
            return _HA_MESSAGES.get(message)
    else:
        status = row.get("status")
        if isinstance(status, dict):
            for flag in ("exiting", "degraded", "running"):
                if status.get(flag) is True:
                    return "hostagent_" + flag
    return None


def scientific_platform(architecture: str) -> str:
    try:
        return {"arm64": "linux/arm64", "x86_64": "linux/amd64"}[architecture]
    except KeyError as exc:
        raise ValidationError(f"Architettura macOS non supportata: {architecture}") from exc


def rosetta_enabled(config: dict) -> bool:
    options = (config.get("vmOpts") or {}).get("vz") or {}
    nested = options.get("rosetta") or {}
    return any(options.get(key) for options in (nested, config.get("rosetta", {}))
               if isinstance(options, dict) for key in ("enabled", "binfmt"))


def read_manifest(project: Path) -> dict:
    manifest = _read_json(project / ".distribution" / "macos-manifest.json")
    asset = manifest.get("scientific_asset")
    valid = (
        manifest.get("schema_version") == 1
        and manifest.get("channel") == CHANNEL
        and manifest.get("bundle_identifier") == "org.newpat.desktop"
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(manifest.get("version", "")))
        and re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", "")))
        and manifest.get("architecture") in _BASE_IMAGES
        and manifest.get("scientific_platform") == scientific_platform(manifest["architecture"])
        and manifest.get("lima_version") == LIMA_VERSION
        and _IMAGE.fullmatch(str(manifest.get("runtime_image", "")))
        and isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz", asset["name"])
        and _DIGEST.fullmatch(str(asset.get("sha256", "")))
        and isinstance(manifest.get("engine_description"), dict)
    )
    if not valid:
        raise ValidationError("Manifest macOS non valido; reinstallare il pacchetto completo.")
    # Reuse the same contract validation as normal workflow execution.
    from newpat.experiments.runner import DockerComposeRunner
    DockerComposeRunner._validate_engine_description(manifest["engine_description"])
    return manifest


def loaded_image_id(output: str) -> str:
    """Accept only the receipt for the single tagless, verified build archive."""
    receipts = [line for line in output.splitlines() if line.startswith("Loaded image")]
    if re.search(r"(?m)^Error\b", output) or len(receipts) != 1:
        raise RuntimeExecutionError("Docker non ha restituito una sola immagine verificabile.")
    match = re.fullmatch(r"Loaded image ID: (sha256:[0-9a-f]{64})", receipts[0])
    if match is None:
        raise RuntimeExecutionError("Ricevuta Docker non valida: richiesto un ID immutabile senza tag.")
    return match[1]


class LimaRuntime:
    def __init__(self, project: Path, workspace: Path, executable: Path, *, home: Path | None = None):
        self.project = absolute_path(project)
        self.workspace = absolute_path(workspace)
        self.executable = absolute_path(executable)
        self.home = absolute_path(home or Path.home())
        expected = self.home / "Library" / "Application Support" / WORKSPACE_NAME
        if self.workspace != expected:
            raise ValidationError(f"Il runtime macOS richiede la cartella dedicata {expected}.")
        # macOS Unix sockets have a 104-byte pathname limit. Application Support
        # is deliberately reserved for state/data, not Lima's SSH socket paths.
        self.lima_home = self.home / ".newpat" / "lima"
        if len(os.fsencode(self.lima_home / INSTANCE / "ssh.sock.1234567890123456")) >= 104:
            raise ValidationError("Il percorso della cartella personale è troppo lungo per i socket Lima su macOS.")
        self.directory = self.workspace / ".runtime" / "macos"
        self.state_path = self.directory / "runtime.json"
        self.owner_path = self.directory / "owner.json"
        self.instance_dir = self.lima_home / INSTANCE

    @classmethod
    def from_environment(cls) -> "LimaRuntime":
        project = setting("PROJECT_DIR")
        workspace = setting("WORKSPACE_DIR")
        executable = setting("LIMA_EXECUTABLE")
        if not (project and workspace and executable and os.environ.get("LIMA_HOME")):
            raise ValidationError("Avviare NewPat dall'applicazione macOS installata: configurazione Lima incompleta.")
        value = cls(Path(project), Path(workspace), Path(executable))
        if absolute_path(os.environ["LIMA_HOME"]) != value.lima_home:
            raise ValidationError("LIMA_HOME non appartiene a questa installazione.")
        return value

    def host_prefix(self) -> list[str]:
        # Prevent inherited SSH aliases, Docker contexts and user Lima overrides
        # from redirecting a command to another VM or Docker daemon.
        values = {
            "HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
            "LIMA_HOME": str(self.lima_home), "SSH": "/usr/bin/ssh",
            "TMPDIR": str(absolute_path(os.environ.get("TMPDIR", "/private/tmp"))),
        }
        return ["/usr/bin/env", "-i", *(f"{key}={value}" for key, value in values.items()), str(self.executable)]

    def shell_command(self, argv: list[str]) -> list[str]:
        return self.host_prefix() + ["shell", "--workdir=/", INSTANCE, *argv]

    def docker_command(self, argv: list[str], environment: dict[str, str] | None = None) -> list[str]:
        values = {
            "HOME": "/root", "PATH": _LINUX_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CONFIG": "/root/.docker",
            "DOCKER_DEFAULT_PLATFORM": scientific_platform(platform.machine()), "NEWPAT_UID": str(os.getuid()),
            "NEWPAT_GID": str(os.getgid()),
        }
        for key in ("NEWPAT_PROJECT_DIR", "NEWPAT_WORKSPACE_DIR", "NEWPAT_DATA_DIR", "NEWPAT_RUNS_DIR"):
            if environment and key in environment:
                values[key] = self.host_path(environment[key])
        if environment and environment.get("NEWPAT_RUNTIME_IMAGE"):
            values["NEWPAT_RUNTIME_IMAGE"] = environment["NEWPAT_RUNTIME_IMAGE"]
        return self.shell_command([
            "sudo", "-n", "/usr/bin/env", "-i", *(f"{key}={value}" for key, value in values.items()),
            "docker", "--host", "unix:///var/run/docker.sock", *argv,
        ])

    def default_mounts(self) -> list[dict]:
        candidates = [(self.home, True), (Path("/Volumes"), True), (Path("/private/tmp"), True),
                      (absolute_path(os.environ.get("TMPDIR", "/private/tmp")), True),
                      (self.project, False)]
        mounts = []
        for path, writable in candidates:
            path = path.resolve()
            if any(path.is_relative_to(Path(item["location"])) for item in mounts):
                continue
            mounts.append({"location": str(path), "mountPoint": str(path), "writable": writable})
        return mounts

    def host_path(self, path: Path | str) -> str:
        resolved = absolute_path(path)
        mounts = self.default_mounts()
        if self.owner_path.is_file():
            mounts = self._owner()["mounts"]
        if not any(resolved.is_relative_to(Path(item["location"])) for item in mounts):
            raise ValidationError(
                f"Cartella non condivisa con Lima: {resolved}. Usare la cartella personale, un disco "
                "in /Volumes, oppure aggiungere la cartella con 'macos_runtime prepare --mount PERCORSO'."
            )
        return str(resolved)

    @staticmethod
    def _covers(mounts: list[dict], path: Path) -> bool:
        return any(path.is_relative_to(Path(item["location"])) for item in mounts)

    @staticmethod
    def _obsolete_application_mounts(owner: dict) -> list[str]:
        """Only retire absent, read-only application roots previously owned by us."""
        obsolete = []
        for item in owner["mounts"]:
            path = Path(item["location"])
            if (item["writable"] is False and len(path.parts) >= 4
                    and path.parts[-3:] == ("Contents", "Resources", "app")
                    and path.parts[-4] == "NewPat.app"
                    and not path.exists()):
                obsolete.append(str(path))
        return obsolete

    def _instance_info(self) -> dict:
        raw = self._run(self.host_prefix() + ["list", "--json", INSTANCE], timeout=20)
        try:
            values = [json.loads(line) for line in raw.splitlines() if line.strip()]
            if len(values) != 1 or values[0].get("name") != INSTANCE:
                raise ValueError("instance mismatch")
            info = values[0]
            if info.get("status") not in {"Running", "Stopped"}:
                raise ValueError("instance transitioning")
            mounts = info["config"]["mounts"]
            if not isinstance(mounts, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("location"), str)
                    or not Path(item["location"]).is_absolute()
                    or item.get("mountPoint", item["location"]) != item["location"]
                    for item in mounts):
                raise ValueError("invalid mounts")
            return info
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeExecutionError("Configurazione o stato della VM Lima non verificabile; nessuna modifica eseguita.") from exc

    def hostagent_lifecycle(self, *, since: str | None = None) -> dict:
        """Collect only verifiable event labels and times from the owned instance."""
        result = {"schema_version": 1, "events": []}
        try:
            self._assert_owned()
            earliest = _lifecycle_time(since) if since is not None else ""
            latest = datetime.now(UTC).isoformat(timespec="microseconds")
        except (NewPatError, OSError, ValueError, OverflowError, TypeError, RecursionError):
            return result
        seen = set()

        def add(timestamp, source, event):
            try:
                timestamp = _lifecycle_time(timestamp)
            except (TypeError, ValueError, OverflowError):
                return
            if earliest <= timestamp <= latest:
                seen.add((timestamp, source, event))

        # After a restart Lima replaces both logs. Earlier captures retain the
        # same allowlist, including when read from an older or damaged file.
        saved = _lifecycle_bytes(self.directory / "lima-lifecycle.json")
        if saved:
            try:
                archive = json.loads(saved)
                if isinstance(archive, dict) and isinstance(archive.get("events"), list):
                    for row in archive["events"]:
                        if (isinstance(row, dict) and row.get("source") in _HA_SOURCES
                                and isinstance(row.get("event"), str) and row["event"] in _HA_EVENTS):
                            add(row.get("time"), row["source"], row["event"])
            except (ValueError, RecursionError):
                pass
        for source in _HA_SOURCES:
            for line in _lifecycle_bytes(self.instance_dir / source).splitlines():
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(row, dict) and (event := _hostagent_event(row, source)):
                    add(row.get("time"), source, event)
        result["events"] = [{"time": stamp, "source": source, "event": event}
                            for stamp, source, event in sorted(seen)[-_HA_EVENT_LIMIT:]]
        return result

    def start_existing(self) -> None:
        """Keep hostagent observations before limactl can rotate them (under the operation lock)."""
        lifecycle = self.hostagent_lifecycle()
        if lifecycle["events"]:
            path = self.directory / "lima-lifecycle.json"
            try:
                if path.parent.resolve(strict=True) == path.parent:
                    encoded = (json.dumps(lifecycle, indent=2) + "\n").encode()
                    if _lifecycle_bytes(path) != encoded:
                        _write_bytes(path, encoded)
            except (OSError, RuntimeError):
                pass  # Optional observations must not prevent starting a healthy guest.
        self._run(self.host_prefix() + ["start", "--tty=false", INSTANCE], timeout=180)

    def _missing_instance_owner(self) -> bool:
        """A dangling link is not an absent ownership record or a fresh installation."""
        if (self.instance_dir.resolve() != self.instance_dir or self.directory.resolve() != self.directory
                or self.owner_path.is_symlink()):
            raise ValidationError("Percorso della VM o del registro di proprietà non valido: verificare i collegamenti simbolici.")
        return self.instance_dir.exists() and not self.owner_path.exists()

    def _check_recovery_paths(self) -> None:
        # Before invoking Lima (which also writes setup.log) or opening the runtime lock,
        # ensure that only ordinary files and directories in this account can be touched.
        config = self.instance_dir / "lima.yaml"
        if (self.executable != self.project.parent / "lima/bin/limactl" or not config.is_file()):
            raise ValidationError(f"VM {INSTANCE} non gestita o eseguibile Lima non incluso in NewPat.")
        files = (config, self.directory / "lima.yaml", self.directory / "setup.log",
                 self.directory / "operation.lock", self.state_path)
        paths = set(files)
        for directory in (config.parent, self.directory):
            while directory != self.home:
                paths.add(directory)
                directory = directory.parent
        paths.add(self.home)
        for path in paths:
            try:
                item = path.lstat()
            except FileNotFoundError:
                continue
            if path in files:
                valid_type = stat.S_ISREG(item.st_mode) and item.st_nlink == 1
            else:
                valid_type = stat.S_ISDIR(item.st_mode)
            if item.st_uid != os.getuid() or item.st_mode & 0o022 or not valid_type:
                raise ValidationError(f"Percorso del ripristino Lima non sicuro: {path}")

    def _preserve_stopped_instance(self) -> None:
        if not _exclusive_maintenance():
            raise ValidationError("La VM non gestita richiede il ripristino esclusivo. Chiudere le sessioni e riaprire NewPat.")
        self._check_recovery_paths()
        config = self.instance_dir / "lima.yaml"
        before = config.stat()
        original_instance = self.instance_dir.stat()
        info = self._instance_info()
        actual = info["config"]
        params = actual.get("param")
        provisions = actual.get("provision")
        # The token alone does not establish origin without owner.json. Recognize
        # the provisioning script that created this NewPat instance.
        if (info.get("dir") != str(self.instance_dir) or info.get("status") != "Stopped"
                or info.get("errors") or info.get("protected") or info.get("hostAgentPID") or info.get("driverPID")
                or info.get("additionalDisks") or actual.get("additionalDisks") or actual.get("vmType") != "vz"
                or not isinstance(params, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(params.get("NewPatOwner", "")))
                or not isinstance(provisions, list) or not any(
                    isinstance(step, dict) and step.get("mode") == "system"
                    and isinstance(step.get("script"), str) and step["script"].rstrip("\n") == _PROVISION.rstrip("\n")
                    for step in provisions)):
            raise ValidationError(f"VM {INSTANCE} senza owner.json: stato o configurazione NewPat non verificabili. "
                                  "Per il recupero occorre una VM NewPat arrestata e non protetta.")
        self._check_recovery_paths()
        after = config.stat()
        if (not self._missing_instance_owner() or not os.path.samestat(original_instance, self.instance_dir.stat())
                or not os.path.samestat(before, after)
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValidationError("La configurazione Lima è cambiata durante il ripristino. Riaprire NewPat.")
        # A single rename preserves all guest disk data. No copy/delete fallback on EXDEV.
        backup = Path(tempfile.mkdtemp(prefix="recovered-newpat-", dir=self.lima_home.parent))
        saved = backup / INSTANCE
        try:
            self.instance_dir.rename(saved)
        except OSError:
            backup.rmdir()
            raise
        message = f"VM precedente conservata in {saved}. NewPat prepara una nuova VM dedicata."
        print(message, flush=True)
        with (self.directory / "setup.log").open("a", encoding="utf-8") as log:
            log.write(message + "\n")

    def requires_mount_repair(self) -> bool:
        """Read-only preflight used before selecting the launcher's activity lease."""
        if self._missing_instance_owner():
            return True
        if not self.instance_dir.exists():
            return False
        owner = self._assert_owned()
        if self._obsolete_application_mounts(owner):
            return True
        required = [Path(item["location"]) for item in self.default_mounts()]
        if any(not self._covers(owner["mounts"], path) for path in required):
            return True
        config = self._instance_info()["config"]
        return rosetta_enabled(config) or any(not self._covers(config["mounts"], path) for path in required)

    def _verify_application(self) -> None:
        """A healthy image is insufficient: the current app must be visible too."""
        path = self.project / ".distribution" / "macos-manifest.json"
        self.host_path(path)
        expected = file_sha256(path)
        try:
            digest = self._run(self.shell_command(["env", "LC_ALL=C", "sha256sum", "--", str(path)]), timeout=30)
        except RuntimeExecutionError as exc:
            command = exc.__cause__
            if isinstance(command, subprocess.CalledProcessError) and command.returncode == 1:
                missing = {f"sha256sum: {name}: No such file or directory" for name in (str(path), f"'{path}'")}
                if any(line in missing for line in (command.stderr or "").splitlines()):
                    raise _StaleApplicationMount(f"La VM non trova il manifesto dell'applicazione: {path}") from exc
            raise RuntimeExecutionError(
                f"La VM non può leggere l'applicazione in {self.project}. {exc}"
            ) from exc
        value, _, name = digest.partition("  ")
        if not _DIGEST.fullmatch(value) or name != str(path):
            raise RuntimeExecutionError("La VM non ha restituito un checksum del manifesto valido.")
        if value != expected:
            raise _StaleApplicationMount("La VM vede una copia diversa dell'applicazione.")

    def _require_idle_guest(self) -> None:
        if self._run(self.docker_command(["ps", "--quiet"]), timeout=30).strip():
            raise ValidationError("Sono presenti analisi o container attivi. Attendere la conclusione e riaprire NewPat; il runtime non è stato arrestato.")

    def _verify_existing_mount(self) -> None:
        try:
            self._verify_application()
        except _StaleApplicationMount as exc:
            if not _exclusive_maintenance():
                raise _ExclusivePreparationRequired(
                    f"{exc} Chiudere le altre sessioni NewPat e riaprire l'applicazione."
                ) from exc
            self._assert_owned()
            if self._instance_info()["status"] != "Running":
                raise
            self._require_idle_guest()
            print("Aggiornamento della condivisione dell'applicazione: riavvio della VM NewPat.", flush=True)
            self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)
            self.start_existing()
            self._verify_application()

    def _repair_mounts(self, owner: dict, additions: list[dict]) -> dict:
        """Update the owned VM under the launcher's exclusive lease.

        Lima 2.2.1 edit refuses running instances. The edit preserves resource settings, disks and existing mount options. No VM, image, data or result directory is removed.
        """
        if not _exclusive_maintenance():
            raise ValidationError(
                "La configurazione della VM richiede un aggiornamento. Chiudere tutte le sessioni NewPat "
                "e riaprire NewPat da Applicazioni per completare il ripristino automatico."
            )
        self._assert_owned()
        info = self._instance_info()
        running = info["status"] == "Running"
        if running:
            self._require_idle_guest()
        config = self.instance_dir / "lima.yaml"
        original_config = config.read_bytes()
        original_owner = self.owner_path.read_bytes()
        config_mode = config.stat().st_mode & 0o777
        owner_mode = self.owner_path.stat().st_mode & 0o777
        actual = info["config"]["mounts"]
        disable_rosetta = rosetta_enabled(info["config"])
        obsolete = self._obsolete_application_mounts(owner)
        if any(item["location"] in obsolete and item.get("writable") is not False for item in actual):
            raise ValidationError("Una vecchia cartella dell'applicazione ha una condivisione personalizzata: nessuna modifica eseguita.")
        updated = dict(owner, mounts=[dict(item) for item in owner["mounts"] if item["location"] not in obsolete])
        append = [item for item in additions if not self._covers(actual, Path(item["location"]))]
        for item in additions:
            if not self._covers(updated["mounts"], Path(item["location"])):
                updated["mounts"].append(item)
        backup = self.directory / ("mount-backup-" + uuid.uuid4().hex + ".json")
        _write_json(backup, {"schema_version": 1, "project": str(self.project),
                            "config_path": str(config), "owner_path": str(self.owner_path),
                            "config_mode": config_mode, "owner_mode": owner_mode,
                            "config_base64": base64.b64encode(original_config).decode("ascii"),
                            "owner_base64": base64.b64encode(original_owner).decode("ascii")})
        print("Aggiornamento della configurazione Lima. I dati e i risultati vengono conservati.", flush=True)
        try:
            if append or obsolete or disable_rosetta:
                if running:
                    self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)
                expressions = [".mounts |= map(select(.location != " + json.dumps(path, ensure_ascii=True) + "))"
                               for path in obsolete]
                if append or obsolete:
                    expressions.append(".mounts += " + json.dumps(append, ensure_ascii=True))
                if disable_rosetta:
                    expressions.extend(["del(.rosetta)", ".vmOpts.vz.rosetta.enabled = false",
                                        ".vmOpts.vz.rosetta.binfmt = false"])
                expression = " | ".join(expressions)
                self._run(self.host_prefix() + ["edit", "--tty=false", "--set", expression, INSTANCE])
                self._assert_owned()
                verified = self._instance_info()
                if rosetta_enabled(verified["config"]):
                    raise RuntimeExecutionError("Lima non ha disattivato Rosetta per il motore nativo.")
                if any(not self._covers(verified["config"]["mounts"], Path(item["location"])) for item in additions):
                    raise RuntimeExecutionError("Lima non ha applicato le cartelle condivise richieste.")
            _write_json(self.owner_path, updated)
            self.start_existing()
            self._verify_application()
            return updated
        except (NewPatError, OSError, ValueError, KeyboardInterrupt) as exc:
            # Do not overwrite a configuration while the guest is using it.
            try:
                if self._instance_info()["status"] == "Running":
                    self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)
                _write_bytes(config, original_config, mode=config_mode)
                _write_bytes(self.owner_path, original_owner, mode=owner_mode)
                if running:
                    self.start_existing()
            except (NewPatError, OSError, ValueError) as restore_error:
                raise RuntimeExecutionError(
                    f"Ripristino della configurazione Lima non completato. Conservati VM, dati e backup {backup}. "
                    f"Recupero della configurazione da verificare: {restore_error}. Errore iniziale: {exc}"
                ) from exc
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise RuntimeExecutionError(
                f"Aggiornamento di Lima non completato, configurazione precedente ripristinata. "
                f"Dati e risultati conservati. Backup: {backup}. {exc}"
            ) from exc

    def _owner(self) -> dict:
        owner = _read_json(self.owner_path)
        if (owner.get("channel") != CHANNEL or owner.get("instance") != INSTANCE
                or owner.get("lima_home") != str(self.lima_home)
                or not re.fullmatch(r"[0-9a-f]{32}", str(owner.get("token", "")))
                or not isinstance(owner.get("mounts"), list)):
            raise ValidationError("Identità del runtime Lima non valida; nessuna VM è stata modificata.")
        for item in owner["mounts"]:
            if (not isinstance(item, dict) or not isinstance(item.get("location"), str)
                    or not Path(item["location"]).is_absolute() or item.get("mountPoint") != item["location"]
                    or type(item.get("writable")) is not bool):
                raise ValidationError("Elenco delle cartelle Lima non valido.")
        return owner

    def _assert_owned(self) -> dict:
        owner = self._owner()
        config = self.instance_dir / "lima.yaml"
        if self.instance_dir.is_symlink() or config.is_symlink() or not config.is_file():
            raise ValidationError("La VM Lima dedicata non è presente o non appartiene a NewPat.")
        contents = config.read_text(encoding="utf-8")
        try:
            parsed = json.loads(contents)
            parameters = parsed.get("param") if isinstance(parsed, dict) else None
            matched = isinstance(parameters, dict) and parameters.get("NewPatOwner") == owner["token"]
        except ValueError:
            # Lima can preserve the original JSON or rewrite it as YAML.
            matched = re.search(r"(?m)^\s*NewPatOwner:\s*['\"]?" + owner["token"] + r"['\"]?\s*$", contents) is not None
        if not matched:
            raise ValidationError("La VM Lima esistente non appartiene a questa installazione; operazione interrotta.")
        return owner

    @contextmanager
    def lock(self, timeout: float = 15):
        import fcntl
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "operation.lock").open("a", encoding="utf-8") as stream:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeExecutionError("Un'altra operazione sul runtime NewPat è già in corso.")
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _run(self, argv: list[str], *, timeout: int = 180) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    check=False, stdin=subprocess.DEVNULL, timeout=timeout, cwd=str(self.home))
        except (OSError, subprocess.TimeoutExpired) as exc:
            with (self.directory / "setup.log").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"argv": argv, "error": str(exc)}, ensure_ascii=False) + "\n")
            raise RuntimeExecutionError(f"Il comando Lima non è stato completato: {exc}") from exc
        with (self.directory / "setup.log").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"argv": argv, "returncode": result.returncode}, ensure_ascii=False) + "\n")
            log.write(result.stdout + result.stderr + "\n")
        if result.returncode:
            message = (result.stderr or result.stdout).strip()[-2000:]
            failure = subprocess.CalledProcessError(result.returncode, argv, output=result.stdout, stderr=result.stderr)
            raise RuntimeExecutionError(f"Runtime macOS non disponibile (codice {result.returncode}): {message}") from failure
        return result.stdout.strip()

    def _host_check(self, manifest: dict) -> None:
        release = platform.mac_ver()[0]
        if sys.platform != "darwin" or not release or int(release.split(".")[0]) < 14:
            raise ValidationError("Il pacchetto richiede macOS 14 o successivo.")
        if platform.machine() != manifest["architecture"]:
            raise ValidationError("Usare il pacchetto NewPat della propria architettura (Intel o Apple Silicon).")
        if not self.executable.is_file():
            raise ValidationError("Lima incluso nel pacchetto non trovato. Reinstallare NewPat.")
        if self.lima_home.exists() and self.lima_home.is_symlink():
            raise ValidationError("La cartella Lima dedicata non può essere un collegamento simbolico.")
        if any((self.lima_home / "_config" / name).exists() for name in ("default.yaml", "override.yaml", "base.yaml")):
            raise ValidationError("Override Lima esterni non ammessi nel runtime dedicato NewPat.")
        version = self._run(self.host_prefix() + ["--version"], timeout=15)
        if not re.fullmatch(r"limactl version " + re.escape(LIMA_VERSION), version):
            raise ValidationError("La versione Lima non corrisponde a quella del pacchetto NewPat.")

    def template(self, manifest: dict, owner: dict) -> dict:
        from newpat.resources import host_resources, suggested_resources
        suggested = suggested_resources(host_resources())
        memory_mib = suggested["memory_mib"] or 4096
        return {
            "minimumLimaVersion": LIMA_VERSION, "vmType": "vz",
            "arch": _BASE_IMAGES[manifest["architecture"]]["arch"],
            "images": [_BASE_IMAGES[manifest["architecture"]]],
            "cpus": suggested["cpus"] or min(4, os.cpu_count() or 2),
            "memory": f"{memory_mib}MiB", "disk": "40GiB",
            "mountType": "virtiofs", "mounts": owner["mounts"],
            "containerd": {"system": False, "user": False},
            "ssh": {"loadDotSSHPubKeys": False, "forwardAgent": False, "forwardX11": False},
            "vmOpts": {"vz": {"rosetta": {"enabled": False, "binfmt": False}}},
            "provision": [{"mode": "system", "script": _PROVISION}],
            "probes": [{"script": "#!/bin/sh\nset -eu\ntest \"$(cat /etc/newpat-owner)\" = \"$PARAM_NewPatOwner\"\nsudo -n docker info >/dev/null\nsudo -n docker compose version\n",
                        "hint": "Consultare /var/log/cloud-init-output.log nella VM NewPat."}],
            "portForwards": [{"guestIP": "0.0.0.0", "guestPortRange": [1, 65535], "proto": "any", "ignore": True}],
            "param": {"NewPatOwner": owner["token"]},
        }

    def _bindings(self, manifest: dict) -> dict:
        return {"schema_version": 1, "channel": CHANNEL, "backend": "lima", "instance": INSTANCE,
                "lima_home": str(self.lima_home), "version": manifest["version"],
                "source_commit": manifest["source_commit"], "architecture": manifest["architecture"],
                "scientific_platform": manifest["scientific_platform"],
                "source_runtime_image": manifest["runtime_image"],
                "runtime_archive_sha256": manifest["scientific_asset"]["sha256"]}

    def _state(self, manifest: dict) -> dict:
        state = _read_json(self.state_path)
        if (any(state.get(key) != value for key, value in self._bindings(manifest).items())
                or state.get("phase") != "ready" or not _IMAGE.fullmatch(str(state.get("runtime_image", "")))):
            raise ValidationError("Preparazione macOS incompleta o di un'altra build. Avviare di nuovo l'applicazione.")
        return state

    def _verify_image(self, manifest: dict, image: str) -> None:
        inspected = self._run(self.docker_command([
            "image", "inspect", "--format", "{{.Id}} {{.Os}} {{.Architecture}}", image,
        ]))
        if inspected != image + " " + manifest["scientific_platform"].replace("/", " "):
            raise RuntimeExecutionError("Identità o architettura dell'immagine scientifica non valida.")
        name = "newpat-verify-" + uuid.uuid4().hex
        try:
            description = json.loads(self._run(self.docker_command([
                "run", "--rm", "--pull=never", "--platform=" + manifest["scientific_platform"], "--name", name,
                "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                "--env", "HOME=/tmp", image, "python3", "/opt/newpat/engine/main.py", "describe", "--json",
            ])))
        except (ValueError, RuntimeExecutionError):
            try:
                self._run(self.docker_command(["rm", "--force", name]), timeout=20)
            except RuntimeExecutionError:
                pass
            raise
        if description != manifest["engine_description"]:
            raise RuntimeExecutionError("Il codice scientifico dell'immagine non corrisponde alla build NewPat.")

    def native_evidence(self, image: str) -> dict:
        """Inspect the running guest and execute the bundled tools for physical acceptance."""
        target = scientific_platform(platform.machine())
        expected_machine = "aarch64" if target == "linux/arm64" else "x86_64"
        guest = self._run(self.shell_command(["uname", "-m"]), timeout=30)
        detected = self._run(self.docker_command(["image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image]))
        if rosetta_enabled(self._instance_info()["config"]) or detected != target or guest != expected_machine:
            raise RuntimeExecutionError("La VM o l’immagine non corrisponde alla piattaforma nativa del Mac.")
        command = ["run", "--rm", "--pull=never", "--network=none", "--platform=" + target, "--entrypoint"]
        r_arch = self._run(self.docker_command([*command, "Rscript", image, "-e", "cat(R.version$arch)"]))
        if r_arch != expected_machine:
            raise RuntimeExecutionError("L’architettura di R non corrisponde a quella del Mac.")
        samtools = self._run(self.docker_command([*command, "samtools", image, "--version-only"]))
        return {"scientific_platform": detected, "guest_machine": guest, "r_arch": r_arch,
                "samtools_version": samtools, "rosetta_enabled": False}

    def prepare(self, extra_mounts: list[Path] | None = None) -> dict:
        manifest = read_manifest(self.project)
        if self._missing_instance_owner():
            self._check_recovery_paths()
        self._host_check(manifest)
        with self.lock():
            missing_owner = self._missing_instance_owner()
            owner = self._owner() if self.owner_path.exists() else {
                "channel": CHANNEL, "instance": INSTANCE, "lima_home": str(self.lima_home),
                "token": uuid.uuid4().hex, "mounts": self.default_mounts(),
            }
            additions = self.default_mounts()
            for value in extra_mounts or []:
                path = absolute_path(value)
                if not path.is_dir() or path == Path("/"):
                    raise ValidationError("Condividere una cartella esistente specifica, non la radice del sistema.")
                if not self._covers(additions, path):
                    additions.append({"location": str(path), "mountPoint": str(path), "writable": True})
            if missing_owner:
                self._preserve_stopped_instance()
            if self.instance_dir.exists():
                self._assert_owned()
                changed = any(not self._covers(owner["mounts"], Path(item["location"])) for item in additions)
                if changed or self.requires_mount_repair():
                    owner = self._repair_mounts(owner, additions)
                else:
                    self.start_existing()
                    self._verify_existing_mount()
                try:
                    state = self._state(manifest)
                    self._verify_image(manifest, state["runtime_image"])
                    return state
                except (ValidationError, RuntimeExecutionError):
                    pass  # A verified archive below repairs an interrupted import.
            else:
                for item in additions:
                    if not self._covers(owner["mounts"], Path(item["location"])):
                        owner["mounts"].append(item)
                _write_json(self.owner_path, owner)
                self.lima_home.mkdir(parents=True, exist_ok=True)
                config = self.directory / "lima.yaml"
                _write_json(config, self.template(manifest, owner))  # JSON is a YAML subset.
                state = {**self._bindings(manifest), "phase": "preparing_vm", "last_error": None}
                _write_json(self.state_path, state)
                print("Prima preparazione NewPat: download di Linux e configurazione di Docker nella VM dedicata. Può richiedere diversi minuti.", flush=True)
                try:
                    self._run(self.host_prefix() + ["start", "--tty=false", "--name=" + INSTANCE, str(config)], timeout=1800)
                    self._assert_owned()
                    self._verify_application()
                except (NewPatError, OSError, ValueError) as exc:
                    state.update(phase="failed", last_error=str(exc))
                    _write_json(self.state_path, state)
                    raise
            state = {**self._bindings(manifest), "phase": "loading_image"}
            _write_json(self.state_path, state)
            try:
                asset = manifest["scientific_asset"]
                archive = self.project / ".distribution" / "assets" / asset["name"]
                if not archive.is_file() or file_sha256(archive) != asset["sha256"]:
                    raise ValidationError("Archivio scientifico mancante o checksum non valido. Reinstallare il pacchetto completo.")
                print("Caricamento e verifica del motore scientifico incluso nel pacchetto...", flush=True)
                image = loaded_image_id(self._run(self.docker_command([
                    "image", "load", "--input", self.host_path(archive),
                ]), timeout=3600))
                self._verify_image(manifest, image)
                state.update(phase="ready", runtime_image=image, last_error=None)
                _write_json(self.state_path, state)
                return state
            except (NewPatError, OSError, ValueError) as exc:
                state.update(phase="failed", last_error=str(exc))
                _write_json(self.state_path, state)
                raise

    def ensure(self) -> dict:
        manifest = read_manifest(self.project)
        self._host_check(manifest)
        # Another experiment may be starting the same guest. Wait for its boot
        # window before running this experiment's own ownership/image checks.
        with self.lock(timeout=180):
            self._assert_owned()
            state = self._state(manifest)
            if manifest["architecture"] == "arm64" and rosetta_enabled(self._instance_info()["config"]):
                raise ValidationError("Riaprire NewPat per aggiornare la VM al motore ARM64 nativo.")
            self.start_existing()
            self._verify_application()
            self._verify_image(manifest, state["runtime_image"])
            return state

    def stop(self) -> None:
        with self.lock():
            self._assert_owned()
            self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)

    def remove_runtime(self) -> None:
        """Explicit maintenance action: remove only our owned VM, never analyses."""
        with self.lock():
            self._assert_owned()
            self._run(self.host_prefix() + ["delete", "--force", INSTANCE], timeout=180)
            self.state_path.unlink(missing_ok=True)
            self.owner_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preparazione e manutenzione del runtime macOS NewPat.")
    parser.add_argument("action", choices=("prepare", "ensure", "status", "stop", "remove-runtime"))
    parser.add_argument("--mount", type=Path, action="append", default=[], help="Cartella aggiuntiva da condividere con il runtime.")
    options = parser.parse_args(argv)
    try:
        runtime = LimaRuntime.from_environment()
        if options.mount and options.action != "prepare":
            raise ValidationError("--mount è disponibile solo con prepare.")
        if options.action == "prepare":
            result = runtime.prepare(options.mount)
        elif options.action == "ensure":
            result = runtime.ensure()
        elif options.action == "status":
            runtime._assert_owned()
            result = runtime._state(read_manifest(runtime.project))
            if runtime.requires_mount_repair():
                result = {**result, "phase": "repair_required",
                          "last_error": "Le cartelle condivise non comprendono l'applicazione attuale. Chiudere le altre sessioni e riaprire NewPat da Applicazioni."}
        elif options.action == "stop":
            runtime.stop()
            result = {"instance": INSTANCE, "phase": "stopped"}
        else:
            runtime.remove_runtime()
            result = {"instance": INSTANCE, "phase": "removed", "analyses_preserved": True}
        if options.action == "status":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif options.action in ("prepare", "ensure"):
            print("Runtime scientifico NewPat disponibile.")
        elif options.action == "stop":
            print("Runtime NewPat arrestato.")
        else:
            print("Runtime NewPat rimosso. Dati e risultati sono stati conservati.")
        return 0
    except _ExclusivePreparationRequired as exc:
        if os.environ.get("NEWPAT_LAUNCHER_PID") == str(os.getppid()):
            return os.EX_TEMPFAIL
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1
    except (NewPatError, OSError, ValueError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
