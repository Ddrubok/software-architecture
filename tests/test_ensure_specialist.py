import hashlib
import io
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

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
            archive.writestr(f"{self.name}/SKILL.md", "example instructions")
        self.data = data.getvalue()
        self.release = {"tag": "v1.0.0", "sha256": hashlib.sha256(self.data).hexdigest()}

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
