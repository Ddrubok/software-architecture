"""Check the old and current release ZIPs with the reader in the current base ZIP."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile


def snapshot(folder):
    return {p.relative_to(folder): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


def check_read_only(folder, inspect):
    # The archive lives in a private temporary directory. Deny an actual write
    # and prove the current process cannot create a file before checking status.
    if os.name == "nt":
        line = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"])
        sid = "*" + next(csv.reader([line.decode("ascii", errors="replace")]))[-1]
        subprocess.run(["icacls", folder, "/deny", f"{sid}:(OI)(CI)(WD,AD,WA,WEA)"], check=True, stdout=subprocess.DEVNULL)
    else:
        for path in [folder, *folder.rglob("*")]:
            path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        try:
            with (folder / ".write-probe").open("xb"):
                pass
        except PermissionError:
            pass
        else:
            raise RuntimeError("Account can bypass read-only permissions; retry as an ordinary user.")
        before = snapshot(folder)
        assert inspect()["integrity"] == "verified"
        assert snapshot(folder) == before
    finally:
        if os.name == "nt":
            subprocess.run(["icacls", folder, "/remove:d", sid], check=True, stdout=subprocess.DEVNULL)
        else:
            for path in [folder, *folder.rglob("*")]:
                path.chmod(0o755 if path.is_dir() else 0o644)


def check(baseline, current, root):
    base = "software-architecture"
    unity = "unity-game-architecture"
    with ZipFile(current / f"{base}.zip") as z:
        z.extractall(root / "reader")
    reader = root / "reader" / base
    index = json.loads((reader / "references/release-index.json").read_text(encoding="utf-8"))["skills"]

    def status(name, folder):
        args = [sys.executable, str(reader / "scripts/ensure_specialist.py"), name, "--status", "--json",
                "--entry", str(folder / name / "SKILL.md")]
        return json.loads(subprocess.check_output(args))

    for archives, tag in [(baseline, "v1.0.0"), (current, "v1.1.0")]:
        destination = root / tag / "standalone skills"
        for name, versions in index.items():
            zip_path = archives / f"{name}.zip"
            assert hashlib.sha256(zip_path.read_bytes()).hexdigest() == versions[tag]["archive_sha256"], zip_path
            with ZipFile(zip_path) as z:
                # The legacy Unity ZIP uses DOS separators. Mirror an unzip
                # tool that understands them on both Windows and Linux.
                for member in z.infolist():
                    relative = member.orig_filename.replace("\\", "/")
                    parts = relative.split("/")
                    assert parts[0] == name and all(p not in ("", ".", "..") for p in parts)
                    path = destination.joinpath(*parts)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(z.read(member))
            before = snapshot(destination / name)
            state = status(name, destination)
            assert state["verified_tag"] == tag and state["integrity"] == "verified", state
            assert state["installed_from"] is None and not state["extra_paths"], state
            assert state["catalog_relation"] == ("match" if archives == current else "differs"), state
            assert before == snapshot(destination / name)
        bundled = root / tag / "bundled skills"
        with ZipFile(archives / f"{base}-with-unity.zip") as z:
            z.extractall(bundled)
        assert snapshot(destination / unity) == snapshot(bundled / unity)
        before = snapshot(bundled)
        state = status(unity, bundled)
        assert state["verified_tag"] == tag and not state["extra_paths"], state
        assert snapshot(bundled) == before
        check_read_only(bundled / unity, lambda: status(unity, bundled))
        reference = bundled / unity / "references/pattern-selection.md"
        reference.write_bytes(reference.read_bytes() + b"\nlocal note\n")
        edited = snapshot(bundled)
        state = status(unity, bundled)
        assert state["integrity"] == "unverified" and state["verified_tag"] is None, state
        assert snapshot(bundled) == edited
        print(f"{tag}: checked {len(index)} standalone ZIPs, Unity bundle parity read-only lookup and a preserved manual edit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="architecture acceptance ") as temp:
        check(args.baseline, args.current, Path(temp))
