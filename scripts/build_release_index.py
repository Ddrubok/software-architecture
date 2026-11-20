"""Append verified specialist ZIP inventories to an offline release index.

Run with --catalog PATH --archives DIR --index PATH for each catalog, oldest
first. DIR contains <skill-name>.zip downloaded from the catalog's release.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from zipfile import BadZipFile, ZipFile


def inventory(name, archive_path, release):
    data = archive_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != release["sha256"]:
        raise ValueError(f"{archive_path}: ZIP checksum mismatch")
    files = {}
    with ZipFile(io.BytesIO(data)) as archive:
        version = None
        for member in archive.infolist():
            path = PurePosixPath(member.orig_filename.replace("\\", "/"))
            if (not path.parts or path.parts[0] != name or ".." in path.parts
                    or ":" in member.filename
                    or stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"{archive_path}: unexpected member {member.filename!r}")
            if member.is_dir():
                continue
            relative = path.relative_to(name).as_posix()
            if relative in files or relative == ".":
                raise ValueError(f"{archive_path}: duplicate or invalid path {relative!r}")
            payload = archive.read(member)
            files[relative] = hashlib.sha256(payload).hexdigest()
            if relative == "VERSION":
                version = payload.decode("utf-8").splitlines()
        if "SKILL.md" not in files:
            raise ValueError(f"{archive_path}: missing SKILL.md")
        if "VERSION" in files or release["tag"] != "v1.0.0":
            if version != [release["tag"]]:
                raise ValueError(f"{archive_path}: VERSION differs from {release['tag']}")
    return {"archive_sha256": digest, "files": files}


def build(catalog_path, archives, output):
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    index = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"schema": 1, "skills": {}}
    if index["schema"] != 1:
        raise ValueError(f"{output}: unsupported schema")
    for name, release in catalog.items():
        record = inventory(name, archives / f"{name}.zip", release)
        versions = index["skills"].setdefault(name, {})
        tag = release["tag"]
        if tag in versions and versions[tag] != record:
            raise ValueError(f"{name} {tag}: already indexed from different bytes")
        versions[tag] = record
    encoded = (json.dumps(index, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if output.exists() and output.read_bytes() == encoded:
        return
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as staged:
            temp = Path(staged.name)
            staged.write(encoded)
        os.replace(temp, output)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--archives", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.catalog, args.archives, args.index)
    except (OSError, ValueError, KeyError, BadZipFile) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
