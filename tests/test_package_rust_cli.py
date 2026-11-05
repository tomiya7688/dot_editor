"""Check archive naming, layout, permissions and determinism without building Rust."""

from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from package_rust_cli import (
    archive_name,
    cargo_version,
    extract_archive,
    make_archive,
    readme_text,
    stage_files,
)


# {
#   責務: [fake_build: 偽の実行ファイルを置いたビルド出力フォルダを作る]
#   処理: [2つの実行ファイル名で小さなファイルを書く]
#   引数: [root: 作業フォルダ, suffix: 実行ファイルの拡張子]
#   戻り値: [ビルド出力フォルダ]
# }
def fake_build(root: Path, suffix: str) -> Path:
    build = root / "build"
    build.mkdir()
    for name in ("pixel-cli", "cli-anything-dot-editor"):
        (build / f"{name}{suffix}").write_bytes(b"binary " + name.encode())
    return build


# {
#   責務: [PackageTests: 配布アーカイブの作り方の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class PackageTests(unittest.TestCase):
    # {
    #   責務: [test_names_and_version: アーカイブ名と案内、版の取得を検証する]
    #   処理: [
    #     1: WindowsはzipとLinux・macOSはtar.gzになることを確認する
    #     2: 案内に版とtargetとコマンド表の場所が載ることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_names_and_version(self):
        self.assertEqual(
            archive_name("1.2.3", "x86_64-pc-windows-msvc", True),
            (
                "hyper-dot-cli-1.2.3-x86_64-pc-windows-msvc",
                "hyper-dot-cli-1.2.3-x86_64-pc-windows-msvc.zip",
            ),
        )
        self.assertTrue(archive_name("1.2.3", "aarch64-apple-darwin", False)[1].endswith(".tar.gz"))
        text = readme_text("1.2.3", "t")
        self.assertIn("1.2.3", text)
        self.assertIn("docs/cli/rust/COMMANDS.md", text)
        self.assertNotIn("\r", text)
        self.assertRegex(cargo_version(), r"^\d+\.\d+\.\d+")

    # {
    #   責務: [test_tar_layout_permissions_and_determinism: tar.gzの中身・実行権限・再現性を検証する]
    #   処理: [
    #     1: 偽のビルドからフォルダを作り、同じ入力で2回アーカイブして内容が一致することを確認する
    #     2: 単一のトップフォルダ、実行ファイルだけ0755、所有者と時刻が固定であることを確認する
    #     3: 展開すると同じファイルが得られることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_tar_layout_permissions_and_determinism(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = fake_build(root, "")
            folder = root / "stage" / "hyper-dot-cli-1.0.0-t"
            stage_files(build, folder, "1.0.0", "t", "")
            first, second = root / "a.tar.gz", root / "b.tar.gz"
            make_archive(folder, first, False)
            make_archive(folder, second, False)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as bundle:
                members = bundle.getmembers()
            self.assertEqual({m.name.split("/")[0] for m in members}, {folder.name})
            modes = {Path(m.name).name: m.mode for m in members}
            self.assertEqual(modes["pixel-cli"], 0o755)
            self.assertEqual(modes["cli-anything-dot-editor"], 0o755)
            self.assertEqual(modes["LICENSE"], 0o644)
            self.assertTrue(all(m.mtime == 0 and m.uid == 0 for m in members))
            extract_archive(first, root / "out")
            self.assertEqual(
                (root / "out" / folder.name / "pixel-cli").read_bytes(), b"binary pixel-cli"
            )
            self.assertTrue(
                (
                    root / "out" / folder.name / "skills" / "cli-anything-dot-editor" / "SKILL.md"
                ).is_file()
            )

    # {
    #   責務: [test_zip_layout_and_missing_binary: zipの中身と、実行ファイル欠落の拒否を検証する]
    #   処理: [
    #     1: .exe付きの偽ビルドでzipを作り、必要なファイルが入ることを確認する
    #     2: 実行ファイルが無い場合は失敗することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_zip_layout_and_missing_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = fake_build(root, ".exe")
            folder = root / "stage" / "hyper-dot-cli-1.0.0-w"
            stage_files(build, folder, "1.0.0", "w", ".exe")
            archive = root / "a.zip"
            make_archive(folder, archive, True)
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
            for expected in (
                "pixel-cli.exe",
                "cli-anything-dot-editor.exe",
                "LICENSE",
                "README-CLI.md",
            ):
                self.assertIn(f"{folder.name}/{expected}", names)
            (build / "pixel-cli.exe").unlink()
            with self.assertRaises(SystemExit):
                stage_files(build, root / "again", "1.0.0", "w", ".exe")


if __name__ == "__main__":
    unittest.main()
