import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_release_index import build


class ReleaseIndexTests(unittest.TestCase):
    def test_rebuild_and_conflicts_preserve_existing_index(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            archive, catalog, index = [folder / n for n in ("demo.zip", "catalog.json", "index.json")]
            release = {"tag": "v1.1.0", "sha256": ""}
            for content in (b"first\r\n", b"second\n"):
                with ZipFile(archive, "w") as z:
                    z.writestr("demo/SKILL.md", content)
                    z.writestr("demo/VERSION", "v1.1.0\n")
                if index.exists():
                    with self.assertRaisesRegex(ValueError, "checksum"):
                        build(catalog, folder, index)
                release["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                catalog.write_text(json.dumps({"demo": release}))
                if index.exists():
                    with self.assertRaisesRegex(ValueError, "already indexed"):
                        build(catalog, folder, index)
                    self.assertEqual(index.read_bytes(), original)
                else:
                    build(catalog, folder, index)
                    original = index.read_bytes()
                    self.assertEqual(json.loads(original)["skills"]["demo"]["v1.1.0"]["files"]["SKILL.md"],
                                     hashlib.sha256(content).hexdigest())
                    build(catalog, folder, index)
                    self.assertEqual(index.read_bytes(), original)
