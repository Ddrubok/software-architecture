"""Inspect or install an architecture skill from the release catalog."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


CATALOG = Path(__file__).resolve().parents[1] / "references" / "specialists.json"
INDEX = CATALOG.with_name("release-index.json")
RECEIPT = ".architecture-install.json"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _relative(value):
    return (isinstance(value, str) and "\\" not in value and ":" not in value
            and all(part not in ("", ".", "..") for part in value.split("/")))


def _records(name, warnings):
    try:
        root = json.loads(INDEX.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append("Release index is unavailable.")
        return {}
    except (ValueError, UnicodeError):
        warnings.append("Release index is malformed.")
        return {}
    if not isinstance(root, dict) or root.get("schema") != 1 or not isinstance(root.get("skills"), dict):
        warnings.append("Release index has an unsupported schema.")
        return {}
    versions = root["skills"].get(name, {})
    if not isinstance(versions, dict):
        warnings.append("Release index entry is malformed.")
        return {}
    valid = {}
    for tag, record in versions.items():
        if (not isinstance(tag, str) or not isinstance(record, dict)
                or not _sha(record.get("archive_sha256")) or not isinstance(record.get("files"), dict)
                or "SKILL.md" not in record["files"] or not record["files"]
                or any(not _relative(path) or not _sha(digest)
                       for path, digest in record["files"].items())):
            warnings.append(f"Ignored malformed release record for {tag}.")
            continue
        valid[tag] = record
    return valid


def _receipt(folder, name, records, warnings):
    path = folder / RECEIPT
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (ValueError, UnicodeError):
        warnings.append("Ignored malformed installation record.")
        return None
    if not isinstance(value, dict) or value.get("schema") != 1 or value.get("name") != name:
        warnings.append("Ignored installation record with invalid schema or name.")
        return None
    tag = value.get("tag")
    record = records.get(tag) if isinstance(tag, str) else None
    if record is None or value.get("archive_sha256") != record["archive_sha256"]:
        warnings.append("Ignored stale installation record.")
        return None
    return tag


def _declared(folder, warnings):
    path = folder / "VERSION"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except UnicodeError:
        warnings.append("Ignored malformed VERSION.")
        return None
    if not value or "\n" in value or "\r" in value:
        warnings.append("Ignored malformed VERSION.")
        return None
    return value


def _tree(folder):
    """List local entries. Inspect links as leaves, including Windows junctions."""
    found = {}

    def visit(parent):
        with os.scandir(parent) as children:
            for child in children:
                path = Path(child.path)
                info = child.stat(follow_symlinks=False)
                linked = stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                if child.name in (".git", "__pycache__") and (linked or stat.S_ISDIR(info.st_mode)):
                    continue
                if stat.S_ISDIR(info.st_mode) and not linked:
                    visit(path)
                else:
                    found[path.relative_to(folder).as_posix()] = bool(not linked and stat.S_ISREG(info.st_mode))

    visit(folder)
    return found


def status(name, release, entry):
    """Inspect exactly this entry, without network access or writes."""
    entry = Path(entry).absolute()
    folder = entry.parent
    warnings = []
    result = {
        "schema": 1, "name": name, "entry": str(entry),
        "catalog_tag": release.get("tag"), "verified_tag": None,
        "installed_from": None, "declared_tag": None,
        "integrity": "missing", "catalog_relation": "unknown",
        "candidate_tags": [], "changed_paths": [], "missing_paths": [],
        "extra_paths": [], "warnings": warnings,
    }
    try:
        mode = folder.stat().st_mode  # The caller may select a linked skill root.
    except FileNotFoundError:
        return result
    if not stat.S_ISDIR(mode):
        result["integrity"] = "incomplete"
        return result
    try:
        entry_info = entry.lstat()
    except FileNotFoundError:
        result["integrity"] = "incomplete"
        return result
    if stat.S_ISDIR(entry_info.st_mode):
        result["integrity"] = "incomplete"
        return result

    local = _tree(folder)
    records = _records(name, warnings)
    receipt = _receipt(folder, name, records, warnings) if local.get(RECEIPT) else None
    declared = _declared(folder, warnings) if local.get("VERSION") else None
    if local.get(RECEIPT) is False:
        warnings.append("Ignored non-regular installation record.")
    result["installed_from"] = receipt
    result["declared_tag"] = declared
    known = {path for record in records.values() for path in record["files"]}
    present = known.intersection(local)
    hashes = {path: _digest((folder / path).read_bytes()) for path in present if local[path]}
    # A local note may share a filename with a later release. Only matching
    # bytes count as evidence for that release's additional packaged files.
    evidence = {p for record in records.values() for p, h in record["files"].items()
                if hashes.get(p) == h}
    matches = sorted(tag for tag, record in records.items()
                     if evidence <= record["files"].keys()
                     and all(hashes.get(p) == h for p, h in record["files"].items())
                     and ("VERSION" in record["files"] or not declared or declared == tag))
    # A receipt identifies the download. It cannot distinguish identical release bytes.
    if len(matches) == 1:
        tag = matches[0]
        result["verified_tag"] = tag
        result["integrity"] = "verified"
        result["extra_paths"] = sorted(local.keys() - records[tag]["files"].keys() - {RECEIPT})
        if receipt and receipt != tag:
            warnings.append("Installation record does not match current files.")
    elif matches:
        result["integrity"] = "ambiguous"
        result["candidate_tags"] = sorted(matches)
    elif receipt:
        files = records[receipt]["files"]
        result["changed_paths"] = sorted(p for p in files if p in local and hashes.get(p) != files[p])
        result["missing_paths"] = sorted(files.keys() - local.keys())
        result["integrity"] = "modified" if result["changed_paths"] or result["missing_paths"] else "unverified"
        result["extra_paths"] = sorted(local.keys() - files.keys() - {RECEIPT})
    else:
        result["integrity"] = "unverified"
    if result["verified_tag"] is not None:
        result["catalog_relation"] = "match" if result["verified_tag"] == release.get("tag") else "differs"
    return result


def installed_entry(folder):
    entry = folder / "SKILL.md"
    if entry.is_file():
        return entry
    if os.path.lexists(folder):
        raise ValueError(f"{folder} exists but has no SKILL.md. Choose a valid skills directory or repair that installation.")
    return None


def _extract_verified(data, name, staged, files):
    seen = set()
    with ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            path = info.orig_filename.replace("\\", "/")
            if not _relative(path.rstrip("/")) or not path.startswith(name + "/"):
                raise ValueError(f"Unsafe archive path: {path}")
            relative = path[len(name) + 1:].rstrip("/")
            if not relative:
                continue
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsafe archive member: {path}")
            if info.is_dir():
                continue
            if relative in seen or relative not in files:
                raise ValueError(f"Unexpected or duplicate archive file: {path}")
            seen.add(relative)
            payload = archive.read(info)
            if _digest(payload) != files[relative]:
                raise ValueError(f"Release index mismatch for {path}.")
            target = staged.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    if seen != set(files):
        raise ValueError(f"Release index mismatch: missing archive files for {name}.")


def ensure(name, release, destination):
    """Return an existing entry or publish a validated release without replacement."""
    destination = Path(destination)
    folder = destination / name
    existing = installed_entry(folder)
    if existing:
        return existing
    record = _records(name, []).get(release["tag"])
    if record is None or record["archive_sha256"] != release["sha256"]:
        raise ValueError(f"Missing or mismatched release index for {name} at {release['tag']}.")
    url = f"https://github.com/Ddrubok/{name}/releases/download/{release['tag']}/{name}.zip"
    request = Request(url, headers={"User-Agent": "software-architecture-skill"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    if _digest(data) != release["sha256"]:
        raise ValueError(f"Checksum mismatch for {name} at {release['tag']}.")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".architecture-", dir=destination) as tmp:
        staged = Path(tmp) / name
        staged.mkdir()
        _extract_verified(data, name, staged, record["files"])
        (staged / RECEIPT).write_text(json.dumps({
            "schema": 1, "name": name, "tag": release["tag"],
            "archive_sha256": release["sha256"],
        }, indent=2) + "\n", encoding="utf-8")
        existing = installed_entry(folder)
        if existing:
            return existing
        try:
            staged.rename(folder)
        except OSError:
            # Concurrent installs publish a nonempty directory in one rename.
            existing = installed_entry(folder)
            if existing:
                return existing
            raise

    return folder / "SKILL.md"


def _summary(result):
    parts = [result["name"], result["integrity"]]
    for key, label in [("verified_tag", "release"), ("installed_from", "installed from"),
                       ("declared_tag", "declares")]:
        if result[key]:
            parts.append(f"{label} {result[key]}")
    if result["catalog_relation"] == "differs":
        parts.append(f"catalog recommends {result['catalog_tag']}")
    for key, label in [("candidate_tags", "candidates"), ("changed_paths", "changed"),
                       ("missing_paths", "missing"), ("extra_paths", "local additions")]:
        if result[key]:
            parts.append(f"{label}: " + ", ".join(result[key]))
    return " · ".join(parts + result["warnings"])


def main(argv=None):
    default_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parser = argparse.ArgumentParser(description=__doc__)
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot read catalog: {error}\n")
    parser.add_argument("name", choices=sorted(catalog))
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--entry", type=Path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.entry and (not args.status or args.dest is not None):
        parser.error("--entry requires --status and cannot be combined with --dest")
    if args.entry and args.entry.name != "SKILL.md":
        parser.error("--entry must point to SKILL.md")
    if args.json and not args.status:
        parser.error("--json requires --status")
    destination = (args.dest or default_home / "skills").expanduser().resolve()
    entry = args.entry.expanduser().absolute() if args.entry else destination / args.name / "SKILL.md"
    try:
        if args.status:
            result = status(args.name, catalog[args.name], entry)
            print(json.dumps(result, ensure_ascii=True) if args.json else _summary(result))
        else:
            print(ensure(args.name, catalog[args.name], destination))
    except (OSError, ValueError, BadZipFile, URLError) as error:
        parser.exit(1, f"{args.name}: {error}\n")


if __name__ == "__main__":
    main()
