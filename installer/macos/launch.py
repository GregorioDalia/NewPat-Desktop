"""Launch the official macOS installation with bundled dependencies."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys

STATE = Path("/Library/Application Support/NIPAT-Desktop Installer")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
CLI_CODE = ("import sys; sys.path.insert(0, sys.argv.pop(1)); "
            "from nipat.cli import main; raise SystemExit(main())")
RUNTIME_CODE = ("import sys; sys.path.insert(0, sys.argv.pop(1)); "
                "from nipat.macos_runtime import main; raise SystemExit(main())")


def load_manifest(app: Path) -> dict:
    app = app.resolve()
    manifest = json.loads((app / ".distribution/macos-manifest.json").read_text())
    if (manifest.get("schema_version") != 1 or manifest.get("channel") != "desktop"
            or manifest.get("architecture") not in {"arm64", "x86_64"}
            or not re.fullmatch(r"0\.[89]\.\d+", manifest.get("version", ""))
            or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("source_commit", ""))):
        raise ValueError("Manifest macOS non valido; reinstallare NewPat.")
    source_hashes = manifest.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("Inventario sorgenti mancante.")
    for name, expected in source_hashes.items():
        path = Path(name)
        if (path.is_absolute() or path.as_posix() != name or ".." in path.parts
                or "\\" in name or not SHA256.fullmatch(str(expected))):
            raise ValueError("Inventario sorgenti non valido.")
        source = app / path
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(app):
            raise ValueError(f"File installato non valido: {name}")
        with source.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"File installato modificato: {name}; reinstallare NewPat.")
    return manifest


def environment(app: Path, resources: Path, inherited: dict[str, str]) -> dict[str, str]:
    workspace = Path.home() / "Library/Application Support/NIPAT-Desktop"
    clean = {key: value for key, value in inherited.items()
             if not key.startswith(("NIPAT_", "PYTHON", "DOCKER", "COMPOSE", "LIMA_"))}
    clean.update({
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "NIPAT_PROJECT_DIR": str(app), "NIPAT_BACKEND": "lima",
        "NIPAT_WORKSPACE_DIR": str(workspace),
        "NIPAT_DATA_DIR": str(workspace / "data"),
        "NIPAT_RUNS_DIR": str(workspace / "runs"),
        "NIPAT_LIMA_EXECUTABLE": str(resources / "lima/bin/limactl"),
        "LIMA_HOME": str(Path.home() / ".nipat/lima"),
        "NIPAT_LAUNCHER_PID": str(os.getpid()),
    })
    return clean


@contextmanager
def installation_session(state: Path = STATE, *, exclusive: bool = False):
    """A root-owned marker also blocks launches after an interrupted update."""
    import fcntl
    for path in (state, state / "activity.lock"):
        info = path.lstat()
        if path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Coordinamento installazione non valido; reinstallare NewPat.")
    with (state / "activity.lock").open("rb") as stream:
        try:
            fcntl.flock(stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Un'altra sessione NewPat/NIPAT è attiva; chiuderla prima della manutenzione o attendere la fine dell'aggiornamento.") from exc
        if (state / "update-in-progress").exists():
            raise ValueError("Installazione NewPat incompleta; rieseguire il pacchetto .pkg.")
        yield stream


def mount_repair_required(app: Path, resources: Path, workspace: Path) -> bool:
    """Check managed mounts and Rosetta before selecting the installation lease."""
    source = str(app / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from nipat.macos_runtime import LimaRuntime
    from nipat.errors import NipatError
    try:
        runtime = LimaRuntime(app, workspace, resources / "lima/bin/limactl")
        return runtime.requires_mount_repair()
    except NipatError as exc:
        raise ValueError(str(exc)) from exc


def run_foreground(command: list[str], *, env: dict[str, str], cwd: Path | None = None) -> int:
    """Let the foreground client handle Ctrl+C while retaining our install lease."""
    # Terminal sends SIGINT to the entire foreground process group. The CLI can
    # recover to its menu; subprocess.call would kill it when the supervisor
    # receives the same signal. A caught handler resets across exec, so the
    # client still receives SIGINT normally (unlike inheriting SIG_IGN).
    previous = signal.signal(signal.SIGINT, lambda _number, _frame: None)
    try:
        with subprocess.Popen(command, env=env, cwd=cwd) as process:
            return process.wait()
    finally:
        signal.signal(signal.SIGINT, previous)


def gui_startup(app: Path):
    """Use only the packaged native preparation window; no browser or shell."""
    source = str(app / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from nipat.gui import startup
    return startup


def launch(arguments: list[str], app: Path) -> int:
    if sys.platform != "darwin" or os.geteuid() == 0:
        raise ValueError("Avviare NewPat su macOS con il proprio utente, senza sudo.")
    if int(platform.mac_ver()[0].split(".")[0]) < 14:
        raise ValueError("NewPat richiede macOS 14 o successivo.")
    manifest = load_manifest(app)
    if platform.machine() != manifest["architecture"]:
        raise ValueError("Installare il pacchetto NewPat per l'architettura di questo Mac.")
    resources = app.parent
    env = environment(app, resources, dict(os.environ))
    python = resources / "python/bin/python3.12"
    workspace = Path(env["NIPAT_WORKSPACE_DIR"])
    for path in (workspace, workspace / "data", workspace / "runs"):
        path.mkdir(parents=True, exist_ok=True)
    runtime = [str(python), "-I", "-B", "-c", RUNTIME_CODE, str(app / "src")]
    maintenance = len(arguments) >= 2 and arguments[0] == "--runtime" and arguments[1] in {"stop", "remove-runtime"}
    prepare = not arguments or arguments[0] != "--runtime" or arguments[1:2] == ["prepare"]
    relocation = prepare and ("--mount" in arguments or any(value.startswith("--mount=") for value in arguments)
                              or mount_repair_required(app, resources, workspace))
    with installation_session(exclusive=maintenance or relocation) as lease:
        if relocation:
            env["NIPAT_RUNTIME_MAINTENANCE"] = "1"
        if arguments and arguments[0] == "--runtime":
            return run_foreground([*runtime, *arguments[1:]], env=env)
        graphical = not arguments or arguments == ["gui"]
        with (gui_startup(app).preparation_notice(app) if graphical else nullcontext()):
            prepared = run_foreground([*runtime, "prepare"], env=env)
        if prepared:
            if graphical:
                gui_startup(app).show_startup_error(app,
                    "Preparazione dell’ambiente non completata. Consultare il log in " + str(workspace))
            return prepared
        if relocation:
            import fcntl
            # Migration has completed. Normal execution keeps a shared lease,
            # allowing other clients without letting an installer replace us.
            fcntl.flock(lease, fcntl.LOCK_SH)
            env.pop("NIPAT_RUNTIME_MAINTENANCE", None)
        state = json.loads((workspace / ".runtime/macos/runtime.json").read_text())
        identifier = state.get("runtime_image", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", identifier):
            raise ValueError("Identita del runtime preparato non valida.")
        env["NIPAT_RUNTIME_IMAGE"] = identifier
        return run_foreground([str(python), "-I", "-B", "-c", CLI_CODE,
                               str(app / "src"), *(arguments or ["gui"])],
                              env=env, cwd=workspace / "data")


def main(arguments: list[str] | None = None) -> int:
    selected = sys.argv[1:] if arguments is None else arguments
    app = Path(__file__).resolve().parents[2]
    try:
        return launch(selected, app)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"NewPat: {exc}", file=sys.stderr)
        if not selected or selected == ["gui"]:
            try:
                gui_startup(app).show_startup_error(app, str(exc))
            except Exception as notice_error:
                print("NewPat: " + str(notice_error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
