"""Stable, standard-library-only downloader for the Windows setup (contract 1).

This program is embedded in the small setup with official CPython. It never
executes downloaded files. The setup supplies an explicit immutable target for
updates; only a new/manual installation resolves the current stable release.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import urllib.parse
import urllib.request
import zipfile

BOOTSTRAP_VERSION = "1.0.0"
REPOSITORY = "https://github.com/GregorioDalia/nipat-desktop"
FEED_NAME = "update-manifest-windows-bootstrap.json"
PLATFORM = "windows-bootstrap-x86_64"
MAX_DOWNLOAD = 2**31 - 1
MAX_EXPANDED = 3 * 1024**3
MAX_MANIFEST = 1024**2
MAX_MEMBERS = 10000
SHA256 = re.compile(r"[a-f0-9]{64}")
COMMIT = re.compile(r"[a-f0-9]{40}")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Chiave JSON duplicata")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def _sha(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _target(version, source, sha256, size):
    if (not isinstance(version, str) or not VERSION.fullmatch(version)
            or tuple(map(int, version.split("."))) < (0, 8, 99)
            or not isinstance(source, str) or not COMMIT.fullmatch(source)
            or not isinstance(sha256, str) or not SHA256.fullmatch(sha256)
            or type(size) is not int or not 0 < size <= MAX_DOWNLOAD):
        raise ValueError("Identita del pacchetto NIPAT non valida o non compatibile")
    return {"version": version, "source_commit": source, "sha256": sha256, "size": size}


def validate_feed(value):
    fields = {"schema_version", "product", "version", "release_tag", "channel", "source_commit",
              "minimum_updater_version", "assets", "release_notes_url"}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["product"] != "nipat-desktop" or value["channel"] != "stable"
            or type(value["minimum_updater_version"]) is not int
            or value["minimum_updater_version"] != 1
            or not isinstance(value["assets"], list) or len(value["assets"]) != 1):
        raise ValueError("Manifest di distribuzione non supportato da questo setup")
    asset = value["assets"][0]
    if not isinstance(asset, dict) or set(asset) != {"platform", "name", "size", "sha256", "url"}:
        raise ValueError("Descrizione del pacchetto non valida")
    target = _target(value["version"], value["source_commit"], asset["sha256"], asset["size"])
    tag = "v" + target["version"]
    name = "NIPAT-" + target["version"] + "-Windows-payload.zip"
    url = REPOSITORY + "/releases/download/" + tag + "/" + name
    if (asset["platform"] != PLATFORM or asset["name"] != name or asset["url"] != url
            or value["release_tag"] != tag
            or value["release_notes_url"] != REPOSITORY + "/releases/tag/" + tag):
        raise ValueError("Il pacchetto non appartiene alla release ufficiale richiesta")
    return dict(target, url=url)


def _approved_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
            and parsed.hostname in {"github.com", "release-assets.githubusercontent.com",
                                    "objects.githubusercontent.com", "github-releases.githubusercontent.com"})


class _GitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not _approved_url(newurl):
            raise ValueError("Reindirizzamento download non consentito")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _open(url):
    if not _approved_url(url):
        raise ValueError("Indirizzo download non consentito")
    request = urllib.request.Request(url, headers={"User-Agent": "NIPAT-Setup/" + BOOTSTRAP_VERSION})
    return urllib.request.build_opener(_GitHubRedirects()).open(request, timeout=60)


def current_target():
    with _open(REPOSITORY + "/releases/latest/download/" + FEED_NAME) as response:
        data = response.read(MAX_MANIFEST + 1)
    if len(data) > MAX_MANIFEST:
        raise ValueError("Manifest di distribuzione troppo grande")
    return validate_feed(_json(data))


def download(target, destination):
    digest = hashlib.sha256()
    count = 0
    previous_progress = -1
    try:
        with _open(target["url"]) as source, Path(destination).open("xb") as output:
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                if count > target["size"]:
                    raise ValueError("Dimensione del download diversa dal manifest")
                digest.update(chunk)
                output.write(chunk)
                progress = count * 100 // target["size"]
                if progress // 5 != previous_progress // 5:
                    print(f"Scaricamento NIPAT {target['version']}: {progress}%", flush=True)
                    previous_progress = progress
        if count != target["size"] or digest.hexdigest() != target["sha256"]:
            raise ValueError("Download incompleto o SHA-256 diverso dalla release")
    except BaseException:
        Path(destination).unlink(missing_ok=True)
        raise


def _safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or "\\" in name
            or any(p in {".", ".."} or p.endswith((".", " "))
                   or re.search(r'[\x00-\x1f<>:"|?*]', p)
                   or re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p)
                   for p in path.parts)):
        raise ValueError("Percorso non valido nel pacchetto")
    return path


def _plain_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Il percorso attraversa un collegamento")
    return path


@contextlib.contextmanager
def _locked_reader(path):
    """Deny Windows writers/deletion until hashing and extraction have finished."""
    if os.name != "nt":
        with Path(path).open("rb") as stream:
            yield stream
        return
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "Pacchetto aperto in scrittura o non accessibile")
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        yield stream


def extract_payload(package, destination, target, *, check_only=False):
    """Verify the entire archive before extraction, then hash each written file."""
    package = _plain_path(package)
    destination = _plain_path(destination)
    if destination.exists() and not check_only:
        raise ValueError("La cartella temporanea del pacchetto esiste gia")
    if not package.is_file() or package.stat().st_size != target["size"]:
        raise ValueError("Dimensione del pacchetto diversa dalla release")
    with _locked_reader(package) as source:
        if _sha(source) != target["sha256"]:
            raise ValueError("SHA-256 del pacchetto diverso dalla release")
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if (not infos or len(infos) > MAX_MEMBERS
                    or sum(info.file_size for info in infos) > MAX_EXPANDED):
                raise ValueError("Dimensioni del pacchetto non valide")
            seen = set()
            for info in infos:
                _safe_name(info.filename)
                if (info.is_dir() or info.flag_bits & 1
                        or stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFREG}
                        or info.filename.casefold() in seen or info.file_size > MAX_DOWNLOAD):
                    raise ValueError("Pacchetto con membri duplicati o non regolari")
                seen.add(info.filename.casefold())
            def read_metadata(name):
                if archive.getinfo(name).file_size > MAX_MANIFEST:
                    raise ValueError("Metadati del pacchetto troppo grandi")
                return archive.read(name)
            manifest = _json(read_metadata("app/.distribution/installer-manifest.json"))
            inventory_bytes = read_metadata("app/.distribution/application-files.json")
            inventory = _json(inventory_bytes)
            if (manifest.get("version") != target["version"]
                    or manifest.get("source_commit") != target["source_commit"]
                    or manifest.get("installation_profile", {}).get("channel") != "desktop"
                    or inventory.get("schema_version") != 1
                    or inventory.get("installation_channel") != "desktop"
                    or inventory.get("source_commit") != target["source_commit"]):
                raise ValueError("Versione o provenienza del contenuto diversa dalla release")
            expected = {}
            for item in inventory["files"]:
                name = "app/" + str(_safe_name(item["path"]))
                if name in expected or not SHA256.fullmatch(item["sha256"]):
                    raise ValueError("Inventario del pacchetto non valido")
                expected[name] = item["sha256"]
            expected["app/.distribution/application-files.json"] = hashlib.sha256(inventory_bytes).hexdigest()
            if set(manifest.get("assets", {})) != {"rootfs", "scientific_image"}:
                raise ValueError("Archivi del runtime non validi")
            for asset in manifest["assets"].values():
                name = "assets/" + str(_safe_name(asset["file"]))
                if name in expected or not SHA256.fullmatch(asset["sha256"]):
                    raise ValueError("Inventario del runtime non valido")
                expected[name] = asset["sha256"]
            if {info.filename for info in infos} != set(expected):
                raise ValueError("Il contenuto del pacchetto non corrisponde all'inventario")
            # Keep archive descriptors in one process and reject changed content on write.
            for info in infos:
                with archive.open(info) as content:
                    if _sha(content) != expected[info.filename]:
                        raise ValueError("Contenuto del pacchetto non integro: " + info.filename)
            if check_only:
                expected_extracted = dict(expected)
                for asset in manifest["assets"].values():
                    expected_extracted["runtime-cache/" + asset["sha256"] + "-" + asset["file"]] = asset["sha256"]
                actual = set()
                for path in destination.rglob("*"):
                    _plain_path(path)
                    if path.is_file():
                        name = path.relative_to(destination).as_posix()
                        actual.add(name)
                        with _locked_reader(path) as content:
                            if name not in expected_extracted or _sha(content) != expected_extracted[name]:
                                raise ValueError("Contenuto estratto modificato: " + name)
                if actual != set(expected_extracted):
                    raise ValueError("Contenuto estratto incompleto")
                return manifest
            destination.mkdir()
            try:
                for info in infos:
                    output_path = destination.joinpath(*PurePosixPath(info.filename).parts)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(info) as content, output_path.open("xb") as output:
                        for chunk in iter(lambda: content.read(1024 * 1024), b""):
                            output.write(chunk)
                            digest.update(chunk)
                    if digest.hexdigest() != expected[info.filename]:
                        raise ValueError("Pacchetto modificato durante l'estrazione")
            except BaseException:
                shutil.rmtree(destination)
                raise
    # Inno copies both archives to their final resume-cache names before running
    # the WSL bootstrap. A reboot must not depend on this temporary directory.
    cache = destination / "runtime-cache"
    cache.mkdir()
    for asset in manifest["assets"].values():
        original = destination / "assets" / asset["file"]
        retained = cache / (asset["sha256"] + "-" + asset["file"])
        try:
            os.link(original, retained)
        except OSError:
            shutil.copyfile(original, retained)
    return manifest


def check_installed(project, version, source):
    """Never overwrite a newer app or reuse a release number for other bytes."""
    manifest_path = _plain_path(Path(project) / ".distribution/installer-manifest.json")
    if not manifest_path.exists():
        return
    installed = _json(manifest_path.read_bytes())
    old_version = installed.get("version", "")
    if not VERSION.fullmatch(old_version):
        raise ValueError("Versione installata non riconosciuta; nessun file viene sostituito")
    if tuple(map(int, old_version.split("."))) > tuple(map(int, version.split("."))):
        raise ValueError("E gia installata una versione NIPAT piu recente")
    if old_version == version and installed.get("source_commit") != source:
        raise ValueError("La stessa versione NIPAT identifica sorgenti differenti")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--check-installed", type=Path)
    parser.add_argument("--check-extracted", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--source")
    parser.add_argument("--sha256")
    parser.add_argument("--size", type=int)
    parser.add_argument("--error-file", type=Path, required=True)
    parser.add_argument("--report-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.check_installed is not None:
            if (not args.version or not VERSION.fullmatch(args.version)
                    or not args.source or not COMMIT.fullmatch(args.source)):
                raise ValueError("Identita richiesta non valida")
            check_installed(args.check_installed, args.version, args.source)
            return 0
        if args.check_extracted is not None:
            target = _target(args.version, args.source, args.sha256, args.size)
            if args.package is None:
                raise ValueError("Pacchetto originale non disponibile")
            extract_payload(args.package, args.check_extracted, target, check_only=True)
            return 0
        if args.destination is None or args.report_file is None:
            raise ValueError("Destinazione o rapporto del setup mancanti")
        explicit = [args.version, args.source, args.sha256, args.size]
        if any(value is not None for value in explicit) or args.package is not None:
            if args.package is None or any(value is None for value in explicit):
                raise ValueError("Aggiornamento senza versione esatta: riaprire manualmente il setup")
            target = _target(*explicit)
            package = args.package
        else:
            print("Ricerca dell'ultima versione stabile di NIPAT...", flush=True)
            target = current_target()
            package = args.destination.parent / "nipat-payload-download.zip"
            download(target, package)
        print("Verifica completa del pacchetto NIPAT " + target["version"] + "...", flush=True)
        extract_payload(package, args.destination, target)
        args.report_file.write_text("[NIPAT]\nversion=" + target["version"] + "\nsource_commit="
                                    + target["source_commit"] + "\nsha256=" + target["sha256"]
                                    + "\nsize=" + str(target["size"]) + "\n", encoding="utf-16")
        print("Pacchetto verificato. Avvio dell'installazione guidata.", flush=True)
        return 0
    except Exception as error:
        message = "Preparazione del setup non completata: " + str(error)
        args.error_file.write_text(message + "\n", encoding="utf-8-sig")
        print(message, file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
