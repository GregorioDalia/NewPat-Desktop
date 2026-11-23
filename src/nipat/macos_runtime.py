"""Owned Lima runtime for the macOS distribution.

The host never needs Docker, Homebrew, or a system Python. Lima is bundled with
the application; Docker runs only in the private VM. Scientific code is loaded
from a checksummed archive and checked against the build's complete descriptor.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import unicodedata
import uuid

from nipat.errors import NipatError, RuntimeExecutionError, ValidationError


CHANNEL = "desktop"
INSTANCE = "nipat"
LIMA_VERSION = "2.2.1"
WORKSPACE_NAME = "NIPAT-Desktop"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LINUX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
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
printf '%s\\n' "$PARAM_NipatOwner" > /etc/nipat-owner
"""


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


def read_manifest(project: Path) -> dict:
    manifest = _read_json(project / ".distribution" / "macos-manifest.json")
    asset = manifest.get("scientific_asset")
    valid = (
        manifest.get("schema_version") == 1
        and manifest.get("channel") == CHANNEL
        and re.fullmatch(r"0\.[89]\.[0-9]+(?:[ab][0-9]+|rc[0-9]+)?", str(manifest.get("version", "")))
        and re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", "")))
        and manifest.get("architecture") in _BASE_IMAGES
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
    from nipat.execution.runner import DockerComposeRunner
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
        self.lima_home = self.home / ".nipat" / "lima"
        if len(os.fsencode(self.lima_home / INSTANCE / "ssh.sock.1234567890123456")) >= 104:
            raise ValidationError("Il percorso della cartella personale è troppo lungo per i socket Lima su macOS.")
        self.directory = self.workspace / ".runtime" / "macos"
        self.state_path = self.directory / "runtime.json"
        self.owner_path = self.directory / "owner.json"
        self.instance_dir = self.lima_home / INSTANCE

    @classmethod
    def from_environment(cls) -> "LimaRuntime":
        required = ("NIPAT_PROJECT_DIR", "NIPAT_WORKSPACE_DIR", "NIPAT_LIMA_EXECUTABLE", "LIMA_HOME")
        if any(not os.environ.get(key) for key in required):
            raise ValidationError("Avviare NewPat dall'applicazione macOS installata: configurazione Lima incompleta.")
        value = cls(Path(os.environ[required[0]]), Path(os.environ[required[1]]), Path(os.environ[required[2]]))
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
            "DOCKER_DEFAULT_PLATFORM": "linux/amd64", "NIPAT_UID": str(os.getuid()),
            "NIPAT_GID": str(os.getgid()),
        }
        for key in ("NIPAT_PROJECT_DIR", "NIPAT_WORKSPACE_DIR", "NIPAT_DATA_DIR", "NIPAT_RUNS_DIR"):
            if environment and key in environment:
                values[key] = self.host_path(environment[key])
        if environment and environment.get("NIPAT_RUNTIME_IMAGE"):
            values["NIPAT_RUNTIME_IMAGE"] = environment["NIPAT_RUNTIME_IMAGE"]
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
                    and path.parts[-4] in {"NIPAT Desktop.app", "NewPat.app"}
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

    def requires_mount_repair(self) -> bool:
        """Read-only preflight used before selecting the launcher's activity lease."""
        if not self.instance_dir.exists():
            return False
        owner = self._assert_owned()
        if self._obsolete_application_mounts(owner):
            return True
        required = [Path(item["location"]) for item in self.default_mounts()]
        if any(not self._covers(owner["mounts"], path) for path in required):
            return True
        actual = self._instance_info()["config"]["mounts"]
        return any(not self._covers(actual, path) for path in required)

    def _verify_application(self) -> None:
        """A healthy image is insufficient: the current app must be visible too."""
        path = self.project / ".distribution" / "macos-manifest.json"
        self.host_path(path)
        try:
            digest = self._run(self.shell_command(["sha256sum", "--", str(path)]), timeout=30)
        except RuntimeExecutionError as exc:
            raise RuntimeExecutionError(
                f"La VM non può leggere l'applicazione in {self.project}. "
                "Chiudere le altre sessioni NewPat/NIPAT e riaprire NewPat da Applicazioni per aggiornare le cartelle condivise."
            ) from exc
        if digest.split(maxsplit=1)[0:1] != [file_sha256(path)]:
            raise RuntimeExecutionError("La VM vede una copia diversa dell'applicazione. Chiudere le altre sessioni e riaprire NewPat da Applicazioni.")

    def _repair_mounts(self, owner: dict, additions: list[dict]) -> dict:
        """Extend only the owned VM, under the launcher's exclusive lease.

        Lima 2.2.1 edit refuses running instances. The --set expression changes
        mounts only; existing resource settings and advanced mount options stay
        intact. No VM, image, data or result directory is removed.
        """
        if (os.environ.get("NIPAT_RUNTIME_MAINTENANCE") != "1"
                or os.environ.get("NIPAT_LAUNCHER_PID") != str(os.getppid())):
            raise ValidationError(
                "Le cartelle dell'applicazione sono cambiate. Chiudere tutte le sessioni NewPat/NIPAT "
                "e riaprire NewPat da Applicazioni per completare il ripristino automatico."
            )
        self._assert_owned()
        info = self._instance_info()
        running = info["status"] == "Running"
        if running and self._run(self.docker_command(["ps", "--quiet"]), timeout=30).strip():
            raise ValidationError("Sono presenti analisi o container attivi. Attendere la conclusione e riaprire NewPat; il runtime non è stato arrestato.")
        config = self.instance_dir / "lima.yaml"
        original_config = config.read_bytes()
        original_owner = self.owner_path.read_bytes()
        config_mode = config.stat().st_mode & 0o777
        owner_mode = self.owner_path.stat().st_mode & 0o777
        actual = info["config"]["mounts"]
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
        print("Aggiornamento delle cartelle condivise per NewPat; dati e risultati vengono conservati.", flush=True)
        try:
            if append or obsolete:
                if running:
                    self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)
                expressions = [".mounts |= map(select(.location != " + json.dumps(path, ensure_ascii=True) + "))"
                               for path in obsolete]
                expressions.append(".mounts += " + json.dumps(append, ensure_ascii=True))
                expression = " | ".join(expressions)
                self._run(self.host_prefix() + ["edit", "--tty=false", "--set", expression, INSTANCE])
                self._assert_owned()
                verified = self._instance_info()
                if any(not self._covers(verified["config"]["mounts"], Path(item["location"])) for item in additions):
                    raise RuntimeExecutionError("Lima non ha applicato le cartelle condivise richieste.")
            _write_json(self.owner_path, updated)
            self._run(self.host_prefix() + ["start", "--tty=false", INSTANCE], timeout=180)
            self._verify_application()
            return updated
        except (NipatError, OSError, ValueError, KeyboardInterrupt) as exc:
            # Do not overwrite a configuration while the guest is using it.
            try:
                if self._instance_info()["status"] == "Running":
                    self._run(self.host_prefix() + ["stop", INSTANCE], timeout=180)
                _write_bytes(config, original_config, mode=config_mode)
                _write_bytes(self.owner_path, original_owner, mode=owner_mode)
                if running:
                    self._run(self.host_prefix() + ["start", "--tty=false", INSTANCE], timeout=180)
            except (NipatError, OSError, ValueError) as restore_error:
                raise RuntimeExecutionError(
                    f"Ripristino delle cartelle non completato. Conservati VM, dati e backup {backup}. "
                    f"Recupero della configurazione da verificare: {restore_error}. Errore iniziale: {exc}"
                ) from exc
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise RuntimeExecutionError(
                f"Aggiornamento delle cartelle non completato; configurazione precedente ripristinata. "
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
            matched = isinstance(parameters, dict) and parameters.get("NipatOwner") == owner["token"]
        except ValueError:
            # Lima can preserve the original JSON or rewrite it as YAML.
            matched = re.search(r"(?m)^\s*NipatOwner:\s*['\"]?" + owner["token"] + r"['\"]?\s*$", contents) is not None
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
            raise RuntimeExecutionError(f"Runtime macOS non disponibile (codice {result.returncode}): {message}")
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
        from nipat.resources import host_resources, suggested_resources
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
            "vmOpts": {"vz": {"rosetta": {"enabled": manifest["architecture"] == "arm64",
                                               "binfmt": manifest["architecture"] == "arm64"}}},
            "provision": [{"mode": "system", "script": _PROVISION}],
            "probes": [{"script": "#!/bin/sh\nset -eu\ntest \"$(cat /etc/nipat-owner)\" = \"$PARAM_NipatOwner\"\nsudo -n docker info >/dev/null\nsudo -n docker compose version\n",
                        "hint": "Consultare /var/log/cloud-init-output.log nella VM NewPat."}],
            "portForwards": [{"guestIP": "0.0.0.0", "guestPortRange": [1, 65535], "proto": "any", "ignore": True}],
            "param": {"NipatOwner": owner["token"]},
        }

    def _bindings(self, manifest: dict) -> dict:
        return {"schema_version": 1, "channel": CHANNEL, "backend": "lima", "instance": INSTANCE,
                "lima_home": str(self.lima_home), "version": manifest["version"],
                "source_commit": manifest["source_commit"], "architecture": manifest["architecture"],
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
        if inspected != f"{image} linux amd64":
            raise RuntimeExecutionError("Identità o architettura dell'immagine scientifica non valida.")
        name = "nipat-verify-" + uuid.uuid4().hex
        try:
            description = json.loads(self._run(self.docker_command([
                "run", "--rm", "--pull=never", "--platform=linux/amd64", "--name", name,
                "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                "--env", "HOME=/tmp", image, "python3", "/opt/nipat/engine/main.py", "describe", "--json",
            ])))
        except (ValueError, RuntimeExecutionError):
            try:
                self._run(self.docker_command(["rm", "--force", name]), timeout=20)
            except RuntimeExecutionError:
                pass
            raise
        if description != manifest["engine_description"]:
            raise RuntimeExecutionError("Il codice scientifico dell'immagine non corrisponde alla build NewPat.")

    def prepare(self, extra_mounts: list[Path] | None = None) -> dict:
        manifest = read_manifest(self.project)
        self._host_check(manifest)
        with self.lock():
            if self.instance_dir.exists() and not self.owner_path.exists():
                raise ValidationError(f"Esiste già una VM {INSTANCE} non gestita da NewPat: nessuna modifica eseguita.")
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
            if self.instance_dir.exists():
                self._assert_owned()
                changed = any(not self._covers(owner["mounts"], Path(item["location"])) for item in additions)
                if changed or self.requires_mount_repair():
                    owner = self._repair_mounts(owner, additions)
                else:
                    self._run(self.host_prefix() + ["start", "--tty=false", INSTANCE], timeout=180)
                # Keep this outside the image-reimport fallback: an inaccessible
                # app cannot be repaired by reloading an otherwise valid image.
                self._verify_application()
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
                if manifest["architecture"] == "arm64":
                    print("Su Apple Silicon Lima prepara anche Rosetta per eseguire il motore scientifico AMD64.", flush=True)
                try:
                    self._run(self.host_prefix() + ["start", "--tty=false", "--name=" + INSTANCE, str(config)], timeout=1800)
                    self._assert_owned()
                    self._verify_application()
                except (NipatError, OSError, ValueError) as exc:
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
            except (NipatError, OSError, ValueError) as exc:
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
            self._run(self.host_prefix() + ["start", "--tty=false", INSTANCE], timeout=180)
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
    except (NipatError, OSError, ValueError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
