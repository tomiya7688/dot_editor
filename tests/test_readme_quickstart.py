"""Execute the README quickstart against the installed CLI and GUI smoke entrypoint."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


# {
#   責務: [ReadmeQuickstartTests: READMEの起動・編集・出力手順を実際のパッケージと照合する]
#   フィールド: [ROOT: リポジトリ直下のパス, README: 動作例を記載した文書]
# }
class ReadmeQuickstartTests(unittest.TestCase):
    # {
    #   責務: [test_quickstart_cli_commands_run_in_order: READMEのCLI初回操作例が新規作業場所で完走することを検証する]
    #   処理: [
    #     1: 最短の動作確認からBashのCLIコマンド列を抽出する
    #     2: 同じPythonで対話入力なしに新規作成・編集・inspect・exportを順番に実行する
    #     3: 保存JSONのバージョン・子セル色とPNGの寸法・色を確認する
    #   ]
    #   引数: [self: テストを実行するインスタンス]
    #   戻り値: [なし、READMEの例が失敗した場合はテストを失敗させる]
    # }
    def test_quickstart_cli_commands_run_in_order(self):
        content = README.read_text(encoding="utf-8")
        heading = "## 最短の動作確認（CLI）"
        self.assertIn(heading, content)
        section = content.split(heading, 1)[1].split("\n## ", 1)[0]
        match = re.search(r"```bash\n(.*?)\n```", section, re.DOTALL)
        self.assertIsNotNone(match)
        commands = [line.strip() for line in match.group(1).splitlines() if line.strip()]
        self.assertEqual(len(commands), 6)

        with tempfile.TemporaryDirectory() as workdir:
            root = Path(workdir)
            inspected = None
            for command in commands:
                parts = shlex.split(command)
                self.assertEqual(parts[:3], ["python", "-m", "pixel_cli"])
                result = subprocess.run(
                    [sys.executable, *parts[1:]],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, command + "\n" + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                if parts[3] == "inspect":
                    inspected = json.loads(result.stdout)

            self.assertIsNotNone(inspected)
            self.assertEqual(inspected["sample"]["rgba"], [0, 0, 255, 255])
            project = json.loads((root / "quickstart.json").read_text(encoding="utf-8"))
            self.assertEqual(project["version"], 2)
            self.assertEqual(project["resolution"], [16, 16])
            self.assertEqual(len(project["layers"]), 1)
            with Image.open(root / "quickstart.png") as image:
                self.assertEqual(image.size, (256, 256))
                self.assertEqual(image.getpixel((16, 16)), (255, 0, 0, 255))
                self.assertEqual(image.getpixel((24, 16)), (0, 0, 255, 255))
                self.assertEqual(image.getpixel((0, 0))[3], 0)

    # {
    #   責務: [test_documented_gui_smoke_is_headless: READMEのGUI非表示スモーク用コマンドを検証する]
    #   処理: [
    #     1: READMEに非表示スモーク用オプションが書かれていることを確認する
    #     2: 独立プロセスでコマンドを実行し、ウィンドウを開かず正常終了することを確認する
    #   ]
    #   引数: [self: テストを実行するインスタンス]
    #   戻り値: [なし、GUIスモークコマンドの失敗を検知する]
    # }
    def test_documented_gui_smoke_is_headless(self):
        self.assertIn(
            "python -m dot_editor --smoke-test",
            README.read_text(encoding="utf-8"),
        )
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [sys.executable, "-m", "dot_editor", "--smoke-test"],
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # {
    #   責務: [test_local_links_and_build_commands_match_repository: READMEのリンクと検証コマンドの参照先を検査する]
    #   処理: [
    #     1: README内のリポジトリ相対リンクがすべて存在することを検証する
    #     2: Python・Rustの標準検証コマンドがREADMEとGitHub Actionsで一致することを確認する
    #     3: Windows配布手順が環境準備を前提に記載されていることを確認する
    #   ]
    #   引数: [self: テストを実行するインスタンス]
    #   戻り値: [なし、切れたリンクや手順の差異があればAssertionErrorを発生させる]
    # }
    def test_local_links_and_build_commands_match_repository(self):
        content = README.read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "#")):
                continue
            path = target.split("#", 1)[0]
            self.assertTrue((ROOT / path).is_file(), f"README link is missing: {path}")

        commands = (
            "python scripts/evaluate.py",
            "python -m unittest discover -s tests",
            "cargo fmt --manifest-path rust/Cargo.toml -- --check",
            "cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets --all-features -- -D warnings",
            "cargo test --manifest-path rust/Cargo.toml --workspace",
            "cargo build --manifest-path rust/Cargo.toml --workspace",
            "python scripts/test_rust_json_compat.py",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, content)
                self.assertIn(command, workflow)

        self.assertIn("scripts/setup_environment.ps1", content)
        self.assertIn("scripts/build_windows.ps1", content)
        self.assertIn("requirements-build.txt", content)
        self.assertNotIn("pixel_art.png", content)


if __name__ == "__main__":
    unittest.main()
