"""Validate packaged executables without opening the editor GUI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    distribution = Path(sys.argv[1]).resolve()
    cli = distribution / "DotEditorCLI" / "DotEditorCLI.exe"
    gui = distribution / "DotEditor" / "DotEditor.exe"
    with tempfile.TemporaryDirectory(prefix="dot-distribution-") as directory:
        root = Path(directory)

        def run(*arguments):
            return subprocess.run([str(cli), *map(str, arguments)], cwd=root,
                                  check=True, capture_output=True, text=True, timeout=60)

        run("new", "--size", 2, "--layered", "--output", "project.json")
        run("edit", "--project", "project.json", "--paint", 0, 0, "#FF0000")
        result = run("inspect", "--project", "project.json", "--sample", 0, 0)
        assert json.loads(result.stdout)["sample"]["rgba"] == [255, 0, 0, 255]
        run("export", "--project", "project.json", "--output", "image.png", "--size", 2)
        from PIL import Image
        with Image.open(root / "image.png") as image:
            assert image.size == (2, 2)
            assert image.getpixel((0, 0)) == (255, 0, 0, 255)
        subprocess.run([str(gui), "--smoke-test"], cwd=root, check=True, timeout=60)
    print("Packaged CLI and GUI headless smoke passed (no GUI window opened).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
