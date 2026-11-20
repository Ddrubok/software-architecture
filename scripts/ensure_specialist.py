"""Find or install one architecture skill from this release's GitHub catalog."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


CATALOG = Path(__file__).resolve().parents[1] / "references" / "specialists.json"


def installed_entry(folder):
    entry = folder / "SKILL.md"
    if entry.is_file():
        return entry
    if os.path.lexists(folder):
        raise ValueError(f"{folder} exists but has no SKILL.md. Choose a valid skills directory or repair that installation.")
    return None


def ensure(name, release, destination):
    folder = destination / name
    existing = installed_entry(folder)
    if existing:
        return existing

    url = f"https://github.com/Ddrubok/{name}/releases/download/{release['tag']}/{name}.zip"
    request = Request(url, headers={"User-Agent": "software-architecture-skill"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != release["sha256"]:
        raise ValueError(f"Checksum mismatch for {name} at {release['tag']}.")

    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".architecture-", dir=destination) as tmp:
        with ZipFile(io.BytesIO(data)) as archive:
            # Only archives with the catalog digest reach extraction.
            archive.extractall(tmp)
        staged = Path(tmp) / name
        if not (staged / "SKILL.md").is_file():
            raise ValueError(f"Archive has no {name}/SKILL.md.")
        existing = installed_entry(folder)
        if existing:
            return existing
        try:
            staged.rename(folder)
        except OSError:
            existing = installed_entry(folder)
            if existing:
                return existing
            raise
    return folder / "SKILL.md"


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    default_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=sorted(catalog))
    parser.add_argument("--dest", type=Path, default=default_home / "skills",
                        help="Use this skills directory instead of the personal Codex skills directory.")
    args = parser.parse_args()
    try:
        print(ensure(args.name, catalog[args.name], args.dest.expanduser().resolve()))
    except (OSError, ValueError, BadZipFile, URLError) as error:
        parser.exit(1, f"{args.name}: {error}\n")


if __name__ == "__main__":
    main()
