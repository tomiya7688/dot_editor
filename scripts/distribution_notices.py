"""Copy dependency license texts into the Windows distribution."""
from importlib import metadata
from pathlib import Path
import shutil
import sys


# {
#   責務: [main: Python・依存ライブラリ・Tcl/Tkのライセンス告知を配布先へ集める]
#   処理: [
#     1: licensesフォルダーを作りPythonの告知文をコピーする
#     2: PillowとPyInstallerのメタデータからライセンスファイルを収集する
#     3: Tcl/Tkアーカイブ内と個別の告知文書を環境別のフォルダーへコピーする
#     4: 必須依存のライセンスが見つからない場合は理由を付けて停止する
#   ]
#   引数: [なし、コマンドライン第1引数から配布先を取得する]
#   戻り値: [なし、告知文の欠落またはコピー失敗時は例外]
# }
def main():
    destination = Path(sys.argv[1]) / "licenses"
    destination.mkdir(parents=True, exist_ok=True)
    # 実行Pythonに付属する告知文を配布先のlicenses直下へ置く。
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", destination / "Python-LICENSE.txt")
    # 依存ごとにライセンスメタデータを探し、名前別のフォルダーへ分類する。
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
    tcl = Path(sys.base_prefix) / "tcl"
    # Windows版Tcl/Tkのアーカイブ内にある告知文書を収集する。
    for archive in sorted(tcl.glob("lib*.zip")):
        import zipfile
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if "license" in Path(name).name.lower() and not name.endswith("/"):
                    target = destination / "TclTk" / archive.stem / Path(name).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read(name))
    # 展開済みTcl/Tkファイルに付属する告知文書も収集する。
    for license_file in sorted(tcl.rglob("license.terms")):
        target = destination / "TclTk" / license_file.relative_to(tcl)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(license_file, target)


if __name__ == "__main__":
    main()
