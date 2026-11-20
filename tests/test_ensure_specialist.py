import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ensure_specialist as installer


class EnsureSpecialistTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.skills = Path(temp.name) / "skills"
        self.name = "flutter-app-architecture"
        self.entry = self.skills / self.name / "SKILL.md"
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            self.add_file(archive, "SKILL.md", "example instructions")
        self.data = data.getvalue()
        self.release = {"tag": "v1.0.0", "sha256": hashlib.sha256(self.data).hexdigest()}
        self.index = Path(temp.name) / "release-index.json"
        self.write_index()
        index_patch = patch.object(installer, "INDEX", self.index, create=True)
        index_patch.start()
        self.addCleanup(index_patch.stop)

    def write_index(self, versions=None):
        versions = versions or {
            self.release["tag"]: {
                "archive_sha256": self.release["sha256"],
                "files": {"SKILL.md": hashlib.sha256(b"example instructions").hexdigest()},
            }
        }
        self.index.write_text(json.dumps({"schema": 1, "skills": {self.name: versions}}), encoding="utf-8")

    def status(self, entry=None, release=None):
        return installer.status(self.name, release or self.release, entry or self.entry)

    def archive(self, files):
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            for path, content in files.items():
                self.add_file(archive, path, content)
        self.data = data.getvalue()
        self.release = {"tag": "v1.0.0", "sha256": hashlib.sha256(self.data).hexdigest()}
        self.write_index({"v1.0.0": {"archive_sha256": self.release["sha256"],
                                     "files": {path: hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()
                                               for path, content in files.items()}}})

    def add_file(self, archive, path, content):
        info = ZipInfo(f"{self.name}/{path}")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, content)

    def cli_fixture(self):
        root = self.index.parent / "cli fixture"
        scripts = root / "scripts"
        refs = root / "references"
        scripts.mkdir(parents=True, exist_ok=True)
        refs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(installer.__file__), scripts / "ensure_specialist.py")
        shutil.copyfile(self.index, refs / "release-index.json")
        (refs / "specialists.json").write_text(json.dumps({self.name: self.release}), encoding="utf-8")
        return scripts / "ensure_specialist.py"

    def cli(self, *args, script=None, download=None):
        script = script or self.cli_fixture()
        command = self.cli_command(script, args, download)
        return subprocess.run(command, cwd=self.index.parent,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                              text=True, capture_output=True, timeout=20)

    def cli_command(self, script, args, download=None):
        if download is None:
            wrapper = script.parent.parent / "run_offline.py"
            wrapper.write_text(
                "import runpy, sys\n"
                "from unittest.mock import patch\n"
                "script, *args = sys.argv[1:]\n"
                "sys.argv = [script, *args]\n"
                "with patch('urllib.request.urlopen', side_effect=AssertionError('unexpected network call')):\n"
                "    runpy.run_path(script, run_name='__main__')\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(wrapper), str(script), self.name, *map(str, args)]
        else:
            asset = script.parent.parent / "asset.zip"
            asset.write_bytes(download)
            wrapper = script.parent.parent / "run_cli.py"
            wrapper.write_text(
                "import io, runpy, sys\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                "script, asset, *args = sys.argv[1:]\n"
                "sys.argv = [script, *args]\n"
                "with patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(Path(asset).read_bytes())):\n"
                "    runpy.run_path(script, run_name='__main__')\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(wrapper), str(script), str(asset), self.name, *map(str, args)]
        return command

    def ensure(self):
        return installer.ensure(self.name, self.release, self.skills)

    def test_fetch_then_reuse_local_copy_offline(self):
        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)) as fetch:
            self.assertEqual(self.ensure(), self.entry)
            self.assertEqual(self.entry.read_text(), "example instructions")
            self.entry.write_text("local edits")
            self.assertEqual(self.ensure(), self.entry)
            self.assertEqual(self.entry.read_text(), "local edits")
            fetch.assert_called_once()

    def test_changed_download_leaves_no_installation(self):
        with patch.object(installer, "urlopen", return_value=io.BytesIO(b"changed asset")):
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                self.ensure()
        self.assertFalse(self.entry.parent.exists())

    def test_incomplete_local_folder_is_preserved(self):
        self.entry.parent.mkdir(parents=True)
        marker = self.entry.parent / "draft.md"
        marker.write_text("local work")
        with patch.object(installer, "urlopen") as fetch:
            with self.assertRaisesRegex(ValueError, "has no SKILL.md"):
                self.ensure()
            fetch.assert_not_called()
        self.assertEqual(marker.read_text(), "local work")

    def test_v01_install_receipt_cli_stdout_and_offline_status(self):
        script = self.cli_fixture()
        installed = self.cli("--dest", self.skills, script=script, download=self.data)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(installed.stdout, f"{self.entry.resolve()}\n")
        receipt = json.loads((self.entry.parent / ".architecture-install.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt, {"schema": 1, "name": self.name,
                                   "tag": self.release["tag"],
                                   "archive_sha256": self.release["sha256"]})
        before = {str(p.relative_to(self.skills)): p.read_bytes() for p in self.skills.rglob("*") if p.is_file()}
        result = self.cli("--status", "--json", "--dest", self.skills, script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["verified_tag"], "v1.0.0")
        self.assertEqual(report["integrity"], "verified")
        self.assertEqual(report["catalog_relation"], "match")
        self.assertEqual(before, {str(p.relative_to(self.skills)): p.read_bytes()
                                  for p in self.skills.rglob("*") if p.is_file()})

    def test_v04_modified_or_missing_reference_preserves_local_files(self):
        self.archive({"SKILL.md": "example instructions", "references/pattern-selection.md": "official"})
        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)):
            self.ensure()
        reference = self.entry.parent / "references" / "pattern-selection.md"
        reference.write_bytes(b"local edit")
        before = reference.read_bytes()
        report = self.status()
        self.assertEqual(report["integrity"], "modified")
        self.assertIn("references/pattern-selection.md", report["changed_paths"])
        with patch.object(installer, "urlopen") as fetch:
            self.ensure()
            fetch.assert_not_called()
        self.assertEqual(reference.read_bytes(), before)
        reference.unlink()
        report = self.status()
        self.assertEqual(report["integrity"], "modified")
        self.assertIn("references/pattern-selection.md", report["missing_paths"])

    def test_v05_verified_old_release_differs_from_catalog_without_download(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"example instructions")
        recommended = {"tag": "v1.1.0", "sha256": "a" * 64}
        with patch.object(installer, "urlopen") as fetch:
            report = self.status(release=recommended)
            fetch.assert_not_called()
        self.assertEqual(report["verified_tag"], "v1.0.0")
        self.assertEqual(report["integrity"], "verified")
        self.assertEqual(report["catalog_relation"], "differs")
        self.assertEqual(self.entry.read_bytes(), b"example instructions")

    def test_v06_declared_and_unknown_local_copy(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"local edit")
        (self.entry.parent / "VERSION").write_text("v9.0.0\n", encoding="utf-8")
        report = self.status()
        self.assertEqual(report["integrity"], "unverified")
        self.assertEqual(report["declared_tag"], "v9.0.0")
        self.assertIsNone(report["verified_tag"])
        self.assertEqual(report["catalog_relation"], "unknown")
        (self.entry.parent / "VERSION").unlink()
        report = self.status()
        self.assertEqual(report["integrity"], "unverified")
        self.assertIsNone(report["declared_tag"])
        self.assertIsNone(report["installed_from"])

    def test_v06_damaged_receipt_is_ignored_after_official_match(self):
        self.entry.parent.mkdir(parents=True)
        (self.entry.parent / ".architecture-install.json").write_text("{bad json", encoding="utf-8")
        self.entry.write_bytes(b"example instructions")
        report = self.status()
        self.assertEqual(report["verified_tag"], "v1.0.0")
        self.assertTrue(report["warnings"])

    def test_v06_ambiguous_identical_releases(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"example instructions")
        versions = json.loads(self.index.read_text(encoding="utf-8"))["skills"][self.name]
        versions["v0.9.0"] = dict(versions["v1.0.0"])
        self.write_index(versions)
        report = self.status()
        self.assertEqual(report["integrity"], "ambiguous")
        self.assertIsNone(report["verified_tag"])
        self.assertEqual(set(report["candidate_tags"]), {"v0.9.0", "v1.0.0"})

    def test_v07_missing_incomplete_extra_file_and_read_only_status(self):
        self.assertEqual(self.status()["integrity"], "missing")
        self.assertFalse(self.skills.exists())
        self.entry.parent.mkdir(parents=True)
        note = self.entry.parent / "note.txt"
        note.write_bytes(b"do not change")
        self.assertEqual(self.status()["integrity"], "incomplete")
        self.entry.write_bytes(b"example instructions")
        before = {p.name: p.read_bytes() for p in self.entry.parent.iterdir()}
        with patch.object(installer, "urlopen") as fetch:
            report = self.status()
            fetch.assert_not_called()
        self.assertEqual(report["integrity"], "verified")
        self.assertEqual(report["extra_paths"], ["note.txt"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.entry.parent.iterdir()})

    def test_v08_bad_index_hash_does_not_publish_folder(self):
        wrong = {"archive_sha256": self.release["sha256"], "files": {"SKILL.md": "0" * 64}}
        self.write_index({"v1.0.0": wrong})
        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)):
            with self.assertRaises(ValueError):
                self.ensure()
        self.assertFalse(self.entry.parent.exists())
        if self.skills.exists():
            self.assertEqual(list(self.skills.iterdir()), [])

    def test_v08_receipt_write_failure_preserves_existing_folder(self):
        write = Path.write_text
        def fail_receipt(path, *args, **kwargs):
            if path.name == ".architecture-install.json":
                raise OSError("receipt write failed")
            return write(path, *args, **kwargs)

        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)):
            with patch.object(Path, "write_text", fail_receipt):
                with self.assertRaisesRegex(OSError, "receipt write failed"):
                    self.ensure()
        self.assertFalse(self.entry.parent.exists())
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"user copy")
        self.assertEqual(self.ensure(), self.entry)
        self.assertEqual(self.entry.read_bytes(), b"user copy")

    def test_v09_two_cli_processes_and_explicit_entry(self):
        script = self.cli_fixture()
        command = self.cli_command(script, ("--dest", self.skills), self.data)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        processes = [subprocess.Popen(command, cwd=self.index.parent, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        results = [process.communicate(timeout=20) for process in processes]
        for process, (stdout, stderr) in zip(processes, results):
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, f"{self.entry.resolve()}\n")
        self.assertEqual(self.status()["integrity"], "verified")
        self.assertEqual(json.loads((self.entry.parent / ".architecture-install.json").read_text())["tag"], "v1.0.0")
        other = self.index.parent / "other skills" / self.name / "SKILL.md"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"different copy")
        result = self.cli("--status", "--json", "--entry", other, script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(Path(report["entry"]).samefile(other))
        self.assertEqual(report["integrity"], "unverified")
        self.assertEqual(self.entry.read_bytes(), b"example instructions")

    def test_cli_invalid_options_and_status_stdout_contract(self):
        script = self.cli_fixture()
        missing = self.cli("--status", "--json", "--dest", self.skills, script=script)
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertEqual(json.loads(missing.stdout)["integrity"], "missing")
        self.assertFalse(self.skills.exists())
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"example instructions")
        valid = self.cli("--status", "--json", "--entry", self.entry, script=script)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(len(valid.stdout.splitlines()), 1)
        self.assertEqual(json.loads(valid.stdout)["schema"], 1)
        for args in (("--json",), ("--entry", self.entry),
                     ("--status", "--entry", self.entry, "--dest", self.skills)):
            result = self.cli(*args, script=script)
            self.assertEqual(result.returncode, 2, (args, result.stderr))
            self.assertEqual(result.stdout, "")
        unknown = subprocess.run([sys.executable, str(script), "unknown", "--status"],
                                 cwd=self.index.parent, capture_output=True, text=True, timeout=20)
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(unknown.stdout, "")

    def test_ambiguous_bytes_with_valid_install_receipt(self):
        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)):
            self.ensure()
        versions = json.loads(self.index.read_bytes())["skills"][self.name]
        versions["v0.9.0"] = versions["v1.0.0"]
        self.write_index(versions)
        report = self.status()
        self.assertEqual(report["installed_from"], "v1.0.0")
        self.assertEqual(report["integrity"], "ambiguous")
        self.assertIsNone(report["verified_tag"])

    def test_version_specific_files_and_stale_receipt(self):
        with patch.object(installer, "urlopen", return_value=io.BytesIO(self.data)):
            self.ensure()
        versions = json.loads(self.index.read_bytes())["skills"][self.name]
        old = versions["v1.0.0"]["files"]
        new_files = dict(old, VERSION=hashlib.sha256(b"v1.1.0").hexdigest())
        versions["v1.1.0"] = {"archive_sha256": "1" * 64, "files": new_files}
        self.write_index(versions)
        (self.entry.parent / "VERSION").write_bytes(b"v1.1.0")
        report = self.status()
        self.assertEqual(report["verified_tag"], "v1.1.0")
        self.assertEqual(report["installed_from"], "v1.0.0")
        self.assertTrue(report["warnings"])

    def test_directory_links_are_not_followed_as_local_extras(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"example instructions")
        external = self.index.parent / "another project"
        external.mkdir()
        (external / "private.txt").write_bytes(b"external")
        link = self.entry.parent / "linked files"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                           capture_output=True, check=True)
        else:
            link.symlink_to(external, target_is_directory=True)
        try:
            self.assertEqual(self.status()["extra_paths"], ["linked files"])
        finally:
            link.rmdir() if os.name == "nt" else link.unlink()

    def test_extra_local_note_named_like_a_new_release_file(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_bytes(b"example instructions")
        versions = json.loads(self.index.read_bytes())["skills"][self.name]
        new_files = dict(versions["v1.0.0"]["files"], **{"README.md": hashlib.sha256(b"official").hexdigest()})
        versions["v1.1.0"] = {"archive_sha256": "a" * 64, "files": new_files}
        self.write_index(versions)
        (self.entry.parent / "README.md").write_bytes(b"personal notes")
        report = self.status()
        self.assertEqual(report["verified_tag"], "v1.0.0")
        self.assertEqual(report["extra_paths"], ["README.md"])

    def test_v02_v03_manual_zip_and_bundle_verify_same_files_without_writes(self):
        bundled = self.index.parent / "bundle with spaces"
        with ZipFile(io.BytesIO(self.data)) as z:
            z.extractall(self.skills)
            z.extractall(bundled)
        base = bundled / "software-architecture"
        base.mkdir()
        (base / "SKILL.md").write_bytes(b"general skill")
        for folder in (self.skills / self.name, bundled / self.name):
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            report = self.status(entry=folder / "SKILL.md")
            self.assertEqual((report["verified_tag"], report["installed_from"], report["extra_paths"]),
                             ("v1.0.0", None, []))
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
