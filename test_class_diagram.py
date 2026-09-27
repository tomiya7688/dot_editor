"""Static documentation checks: no application imports or GUI required."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import generate_class_diagram as diagram


class ClassDiagramTests(unittest.TestCase):
    def test_members_aliases_inheritance_and_duplicate_names(self):
        text = diagram.render_diagram({
            "base": "class Model:\n    pass\n",
            "app": "from base import Model as Parent\nclass Model(Parent):\n"
                   "    def paint(self): pass\n    def _private(self): pass\n"
                   "    @property\n    def size(self): return 1\n",
            "client": "import base as b\nclass Client:\n    def run(self): b.Model()\n",
        })
        self.assertIn('C0["app.Model"]', text)
        self.assertIn('C1["base.Model"]', text)
        self.assertIn("C1 <|-- C0", text)
        self.assertIn("C2 ..> C1 : references", text)
        self.assertIn("+paint()", text)
        self.assertIn("+size\n", text)
        self.assertNotIn("_private", text)

    def test_deterministic_and_never_executes_source(self):
        sources = {"z": "raise RuntimeError('do not execute')\nclass Z: pass",
                   "a": "class A: pass"}
        self.assertEqual(diagram.render_diagram(sources),
                         diagram.render_diagram(dict(reversed(list(sources.items())))))

    def test_ignores_test_files_and_subdirectories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text("class App: pass", encoding="utf-8")
            (root / "test_app.py").write_text("invalid source", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "ignored.py").write_text("invalid", encoding="utf-8")
            self.assertEqual(diagram.read_sources(root), {"app": "class App: pass"})

    def test_check_detects_missing_stale_and_current_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "diagram.md"
            with patch.object(diagram, "OUTPUT", output), patch.object(diagram, "read_sources", return_value={}):
                self.assertEqual(diagram.main(["--check"]), 1)
                self.assertFalse(output.exists())
                self.assertEqual(diagram.main([]), 0)
                self.assertEqual(diagram.main(["--check"]), 0)
                output.write_text("stale", encoding="utf-8")
                self.assertEqual(diagram.main(["--check"]), 1)
                self.assertEqual(output.read_text(encoding="utf-8"), "stale")

    def test_repository_diagram_is_current(self):
        self.assertEqual(diagram.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
