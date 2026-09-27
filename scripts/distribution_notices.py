"""Copy dependency license texts into the Windows distribution."""
from importlib import metadata
from pathlib import Path
import shutil
import sys


def main():
    destination = Path(sys.argv[1]) / "licenses"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", destination / "Python-LICENSE.txt")
    for name in ("pillow", "pyinstaller"):
        distribution = metadata.distribution(name)
        found = False
        for entry in distribution.files or ():
            if "licenses" in entry.parts:
                relative = Path(*entry.parts[entry.parts.index("licenses") + 1:])
                target = destination / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(distribution.locate_file(entry), target)
                found = True
        if not found:
            raise RuntimeError(f"Missing license metadata for {name}")
    # Tcl/Tk archives in current Windows Python builds contain their notices.
    tcl = Path(sys.base_prefix) / "tcl"
    for archive in sorted(tcl.glob("lib*.zip")):
        import zipfile
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if "license" in Path(name).name.lower() and not name.endswith("/"):
                    target = destination / "TclTk" / archive.stem / Path(name).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read(name))
    for license_file in sorted(tcl.rglob("license.terms")):
        target = destination / "TclTk" / license_file.relative_to(tcl)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(license_file, target)


if __name__ == "__main__":
    main()
