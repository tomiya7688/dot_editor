"""Non-interactive CLI regressions: run with python test_pixel_cli.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_cli import load_project, save_project
from pixel_layers import LayeredPixelCanvas

ROOT = Path(__file__).resolve().parents[1] / "src"
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)


# {
#   責務: [PixelCliTests: CLI経由の編集・保存・検査・PNG出力と失敗時のファイル保護を検証する]
#   フィールド: [directory: テスト用一時ディレクトリ、root: 一時作業場所、project: 対象JSONパス]
# }
class PixelCliTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テスト用プロジェクトと後片付けを準備する]
    #   処理: [一時ディレクトリを作り、cleanupを登録してJSONプロジェクトのパスを設定する]
    #   引数: [self: 初期化するPixelCliTestsケース]
    #   戻り値: [なし]
    # }
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.project = self.root / "project.json"

    # {
    #   責務: [run_cli: テスト対象CLIを実行し終了値と例外表示を検査する]
    #   処理: [一時ディレクトリを作業場所としてpixel_cli.pyを起動し、期待終了値とTraceback非表示を確認する]
    #   引数: [self: CLIを実行するテストケース、arguments: CLI引数列、code: 期待する終了値]
    #   戻り値: [標準出力・標準エラー・終了値を含むCompletedProcess]
    # }
    def run_cli(self, *arguments: object, code: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "pixel_cli.py"), *(str(a) for a in arguments)],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    # {
    #   責務: [edit: 現在のJSONプロジェクトに対するCLI編集を実行する]
    #   処理: [editと--projectを先頭に付けてrun_cliへ引数と期待終了値を渡す]
    #   引数: [self: 対象プロジェクトを持つテストケース、arguments: edit操作の引数列、code: 期待終了値]
    #   戻り値: [CLIプロセスのCompletedProcess]
    # }
    def edit(self, *arguments: object, code: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_cli("edit", "--project", self.project, *arguments, code=code)

    # {
    #   責務: [report: 現在のプロジェクトをinspectしてJSON結果を返す]
    #   処理: [inspectへプロジェクトパスと追加引数を渡し、標準出力をJSONとして解析する]
    #   引数: [self: inspect対象のプロジェクトを持つテストケース、arguments: inspect引数列]
    #   戻り値: [CLIが出力したJSONオブジェクト]
    # }
    def report(self, *arguments: object) -> dict:
        return json.loads(self.run_cli("inspect", "--project", self.project, *arguments).stdout)

    # {
    #   責務: [new: 4x4の空プロジェクトをフラットまたはレイヤー形式で作る]
    #   処理: [layeredが真なら--layeredを付け、newコマンドでself.projectへ保存する]
    #   引数: [self: 保存先プロジェクトを持つテストケース、layered: レイヤー形式を作るか]
    #   戻り値: [なし]
    # }
    def new(self, layered: bool = False) -> None:
        extra = ["--layered"] if layered else []
        self.run_cli("new", "--size", 4, "--output", self.project, *extra)

    # {
    #   責務: [refined: 親画素と青い子画素を持つ編集済みプロジェクトを用意する]
    #   処理: [指定形式の新規プロジェクトを作り、親を赤く塗って分割後に右上子画素を青く塗る]
    #   引数: [self: 保存先プロジェクトを持つテストケース、layered: レイヤー形式を作るか]
    #   戻り値: [なし]
    # }
    def refined(self, layered: bool = False) -> None:
        self.new(layered)
        self.edit("--paint", 1, 1, "#FF0000")
        self.edit("--split", 1, 1, "--paint-child", 1, 1, 1, 0, "#0000FF")

    # {
    #   責務: [signature: プロジェクトの内容と更新時刻を一組にして取得する]
    #   処理: [JSONファイルのbytesとmtime_nsを読み取る]
    #   引数: [self: 読み取るプロジェクトを持つテストケース]
    #   戻り値: [ファイル内容bytesと最終更新時刻ナノ秒のタプル]
    # }
    def signature(self) -> tuple[bytes, int]:
        return self.project.read_bytes(), self.project.stat().st_mtime_ns

    # {
    #   責務: [test_inspect_new_flat_project: 新規フラットプロジェクトのinspect項目と非変更性を検証する]
    #   処理: [新規作成直後にinspectのschema・形式・解像度・レイヤー・細部情報を調べ、ファイル不変を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、出力またはファイル状態が期待と異なればassertionで失敗する]
    # }
    def test_inspect_new_flat_project(self) -> None:
        self.new()
        before = self.signature()
        report = self.report()
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["project_type"], "flat")
        self.assertEqual(report["resolution"], [4, 4])
        self.assertEqual(report["native_resolution"], [4, 4])
        self.assertIsNone(report["active_layer"])
        self.assertFalse(report["has_detail"])
        self.assertEqual(report["layers"][0]["detail_cells"], [])
        self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_collapse_save_reload_reexpand_and_export: 折りたたみ細部のinspect・保存・再展開・PNG出力を検証する]
    #   処理: [細部を折りたたんで情報保持を確認し、別ファイルへ保存後に再展開してJSONとPNGの画素を比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、保存内容や出力画像が異なればassertionで失敗する]
    # }
    def test_collapse_save_reload_reexpand_and_export(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1)
        before = self.signature()
        report = self.report("--sample", 1, 1, "--child", 1, 0)
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        self.assertEqual(report["layers"][0]["collapsed_detail_cells"], 1)
        self.assertEqual(report["layers"][0]["expanded_cells"], 0)
        self.assertEqual(report["native_resolution"], [4, 4])
        self.assertTrue(report["has_detail"])
        self.assertFalse(report["has_refinements"])
        self.assertEqual(self.signature(), before)
        copied = self.root / "copied.json"
        self.edit("--collapse", 1, 1, "--output", copied)
        self.assertEqual(self.signature(), before)
        self.assertEqual(load_project(copied).to_source(), load_project(self.project).to_source())
        self.run_cli("edit", "--project", copied, "--split", 1, 1)
        image_path = self.root / "image.png"
        self.run_cli("export", "--project", copied, "--output", image_path)
        expected = PixelCanvas(4)
        expected.paint(1, 1, RED)
        expected.split_cell(1, 1)
        expected.paint(1, 1, BLUE, child=(1, 0))
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (8, 8))
            self.assertEqual(image.tobytes(), expected.render().tobytes())
        self.assertEqual(load_project(copied).to_source(), expected.to_source())

    # {
    #   責務: [test_layer_order_can_be_changed_and_exported: CLIのレイヤー順変更が合成結果と選択レイヤーに反映されることを検証する]
    #   処理: [背景と人物を別色で塗り、順序を入れ替えて再読込後のレイヤー順・合成色・active_layerを照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、順序や合成結果が期待と異なればassertionで失敗する]
    # }
    def test_layer_order_can_be_changed_and_exported(self) -> None:
        self.new(layered=True)
        self.edit("--paint", 0, 0, "#FF0000")
        self.edit("--add-layer", "人物", "--paint", 0, 0, "#0000FF")
        before = load_project(self.project)
        self.assertEqual(before.composite().getpixel((0, 0)), BLUE)

        self.edit("--select-layer", "背景", "--move-layer", "up")
        after = load_project(self.project)
        self.assertEqual(list(after.layers), ["人物", "背景"])
        self.assertEqual(after.composite().getpixel((0, 0)), RED)
        self.assertEqual(after.active_layer, "背景")

    # {
    #   責務: [test_layer_rename_persists_and_preserves_visibility_and_order: レイヤー名変更後も可視性・順序・画素を維持することを検証する]
    #   処理: [人物レイヤーを非表示にして改名し、再読込後の名前・選択・可視性・順序・inspect結果を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、改名後の属性が異なればassertionで失敗する]
    # }
    def test_layer_rename_persists_and_preserves_visibility_and_order(self) -> None:
        self.new(layered=True)
        self.edit("--paint", 0, 0, "#FF0000")
        self.edit("--add-layer", "人物", "--paint", 0, 0, "#0000FF")
        self.edit("--layer-visibility", "hide")
        self.edit("--rename-layer", "登場人物")

        renamed = load_project(self.project)
        self.assertEqual(list(renamed.layers), ["背景", "登場人物"])
        self.assertEqual(renamed.active_layer, "登場人物")
        self.assertFalse(renamed.is_layer_visible("登場人物"))
        self.assertEqual(renamed.layers["登場人物"].sample(0, 0), BLUE)
        self.assertEqual(self.report()["layers"][1]["name"], "登場人物")
        self.assertFalse(self.report()["layers"][1]["visible"])

    # {
    #   責務: [test_layer_visibility_persists_and_affects_export: レイヤー可視状態の保存と合成への影響を検証する]
    #   処理: [人物レイヤーの非表示・表示を切り替え、再読込後の可視フラグと合成画素を比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、保存状態または合成結果が異なればassertionで失敗する]
    # }
    def test_layer_visibility_persists_and_affects_export(self) -> None:
        self.new(layered=True)
        self.edit("--paint", 0, 0, "#FF0000")
        self.edit("--add-layer", "人物", "--paint", 0, 0, "#0000FF")
        self.edit("--layer-visibility", "hide")

        hidden = load_project(self.project)
        self.assertFalse(hidden.is_layer_visible("人物"))
        self.assertEqual(hidden.composite().getpixel((0, 0)), RED)
        report = self.report()
        self.assertFalse(report["layers"][1]["visible"])

        self.edit("--layer-visibility", "show")
        restored = load_project(self.project)
        self.assertTrue(restored.is_layer_visible("人物"))
        self.assertEqual(restored.composite().getpixel((0, 0)), BLUE)

    # {
    #   責務: [test_parent_edit_preserves_detail_by_default: CLIの親画素編集で既定の細部保持を検証する]
    #   処理: [折りたたみ状態の親色を変更し、親色と既存の子画素色をinspectおよび再分割後に照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、親子画素のいずれかが異なればassertionで失敗する]
    # }
    def test_parent_edit_preserves_detail_by_default(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1)
        self.edit("--paint", 1, 1, "#00FF00")
        self.assertEqual(self.report("--sample", 1, 1)["sample"]["rgba"], list(GREEN))
        self.assertEqual(self.report("--sample", 1, 1, "--child", 1, 0)["sample"]["rgba"], list(BLUE))
        self.edit("--split", 1, 1)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0)), BLUE)

    # {
    #   責務: [test_parent_edit_discard_replaces_child_initial_color: discard指定の親編集が細部を置き換えることを検証する]
    #   処理: [親を緑でdiscard編集し、細部情報の消失と再分割後の全子画素色を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、破棄後の子画素が緑でなければassertionで失敗する]
    # }
    def test_parent_edit_discard_replaces_child_initial_color(self) -> None:
        self.refined()
        self.edit("--paint", 1, 1, "#00FF00", "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.edit("--split", 1, 1)
        model = load_project(self.project)
        for child in ((0, 0), (1, 0), (0, 1), (1, 1)):
            self.assertEqual(model.sample(1, 1, child), GREEN)

    # {
    #   責務: [test_erase_preserve_and_discard: 親消去でpreserveとdiscardの細部挙動を検証する]
    #   処理: [既存子画素を保つ消去後にdiscard消去を実行し、親の透明化と細部破棄を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、親画素または細部状態が期待と異なればassertionで失敗する]
    # }
    def test_erase_preserve_and_discard(self) -> None:
        self.refined()
        self.edit("--erase", 1, 1)
        model = load_project(self.project)
        self.assertEqual(model.sample(1, 1)[3], 0)
        self.assertEqual(model.sample(1, 1, (1, 0)), BLUE)
        self.edit("--erase", 1, 1, "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1)[3], 0)

    # {
    #   責務: [test_child_erase_is_transparent: 子画素消去が対象子だけを透明にすることを検証する]
    #   処理: [指定子画素をCLIで消去し、対象アルファ値と別子画素の赤色を再読込後に比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、対象外子画素まで変化すればassertionで失敗する]
    # }
    def test_child_erase_is_transparent(self) -> None:
        self.refined()
        self.edit("--erase-child", 1, 1, 1, 0)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0))[3], 0)
        self.assertEqual(load_project(self.project).sample(1, 1, (0, 0)), RED)

    # {
    #   責務: [test_collapse_discard: collapseとdiscardの組み合わせで細部を除去することを検証する]
    #   処理: [細部を破棄して折りたたみ、細部不存在と再分割時の親色継承を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、再分割した子画素が期待色でなければassertionで失敗する]
    # }
    def test_collapse_discard(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1, "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.edit("--split", 1, 1)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0)), RED)

    # {
    #   責務: [test_discard_detail_is_local_to_region_and_layer: 領域指定の細部破棄が対象レイヤー・領域に限られることを検証する]
    #   処理: [背景と人物に細部を作って矩形破棄し、背景状態・領域内外・人物の子画素をバックエンド結果と比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、対象外レイヤーまたはセルが変化すればassertionで失敗する]
    # }
    def test_discard_detail_is_local_to_region_and_layer(self) -> None:
        self.refined(layered=True)
        self.edit("--add-layer", "人物", "--paint", 2, 2, "#00FF00")
        self.edit("--split-region", 0, 0, 3, 3)
        original = load_project(self.project)
        background = original.layers["背景"].to_source()
        self.edit("--discard-detail", 0, 0, 2, 2)
        actual = load_project(self.project)
        self.assertEqual(actual.layers["背景"].to_source(), background)
        for y in range(3):
            for x in range(3):
                self.assertEqual(actual.has_detail_at(x, y), not (x < 2 and y < 2))
        self.assertEqual(actual.sample(2, 2, (1, 0)), GREEN)
        original.discard_detail(0, 0, 2, 2)
        self.assertEqual(actual.to_source(), original.to_source())

    # {
    #   責務: [test_discard_single_cell: 単一セルの細部破棄が保存後も反映されることを検証する]
    #   処理: [対象セルの細部を破棄し、inspectで細部不存在、JSON再読込で親色を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、破棄結果が異なればassertionで失敗する]
    # }
    def test_discard_single_cell(self) -> None:
        self.refined()
        self.edit("--discard-detail", 1, 1)
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1), RED)

    # {
    #   責務: [test_fill_same_color_discard_drops_detail: 同色fillでもdiscardなら細部を破棄することを検証する]
    #   処理: [親と同色で塗りつぶしを実行し、細部消失と保存後の親色を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、同色編集で細部が残ればassertionで失敗する]
    # }
    def test_fill_same_color_discard_drops_detail(self) -> None:
        self.refined()
        self.edit("--fill", 1, 1, "#FF0000", "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1), RED)

    # {
    #   責務: [test_fill_same_color_preserve_is_noop: 同色preserve fillがファイルと細部を変えないことを検証する]
    #   処理: [編集前後のファイル内容・更新時刻を比較し、細部保持も確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、no-opでファイルや細部が変化すればassertionで失敗する]
    # }
    def test_fill_same_color_preserve_is_noop(self) -> None:
        self.refined()
        before = self.signature()
        self.edit("--fill", 1, 1, "#FF0000")
        self.assertEqual(self.signature(), before)
        self.assertTrue(self.report()["has_detail"])

    # {
    #   責務: [test_fill_policy_matches_backend: CLIのfill結果が共有バックエンドの両細部ポリシーと一致することを検証する]
    #   処理: [preserve/discardごとに期待Canvasを直接編集し、CLI保存後のJSON状態と比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、CLIとバックエンドの保存表現が異なればassertionで失敗する]
    # }
    def test_fill_policy_matches_backend(self) -> None:
        for policy in ("preserve", "discard"):
            with self.subTest(policy=policy):
                self.refined(layered=True)
                expected = load_project(self.project)
                expected.fill(1, 1, GREEN, detail_policy=policy)
                self.edit("--fill", 1, 1, "#00FF00", "--detail-policy", policy)
                self.assertEqual(load_project(self.project).to_source(), expected.to_source())

    # {
    #   責務: [test_same_color_fill_discard_undo_and_redo: 同色discard fillの変更件数・局所性・Undo/Redoを検証する]
    #   処理: [異なる細部を持つ隣接セルを用意し、対象セルだけの破棄・履歴復元・再実行no-opを確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、破棄範囲または履歴状態が異なればassertionで失敗する]
    # }
    def test_same_color_fill_discard_undo_and_redo(self) -> None:
        model = PixelCanvas(4)
        model.paint(1, 1, RED)
        model.paint(2, 1, RED)
        for x in (1, 2):
            model.split_cell(x, 1)
            model.paint(x, 1, BLUE, child=(0, 0))
        model.split_cell(0, 0)  # 塗りつぶし領域外に異なる親色の分割セルを置く。
        before = model.to_source()
        self.assertEqual(model.fill(1, 1, RED, detail_policy="discard"), 2)
        after = model.to_source()
        self.assertFalse(model.has_detail_at(1, 1))
        self.assertTrue(model.has_detail_at(0, 0))
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)
        self.assertTrue(model.redo())
        self.assertEqual(model.to_source(), after)
        self.assertEqual(model.fill(1, 1, RED, detail_policy="discard"), 0)

    # {
    #   責務: [test_inspect_sample_layer_does_not_change_active_layer: 指定レイヤーのinspect標本がactive_layerを変更しないことを検証する]
    #   処理: [背景を標本対象に指定してinspectし、active_layer・標本・レイヤー順とファイル不変を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、inspectがプロジェクトを変更すればassertionで失敗する]
    # }
    def test_inspect_sample_layer_does_not_change_active_layer(self) -> None:
        self.refined(layered=True)
        self.edit("--add-layer", "人物")
        before = self.signature()
        report = self.report("--sample", 1, 1, "--child", 1, 0, "--layer", "背景")
        self.assertEqual(report["active_layer"], "人物")
        self.assertEqual(report["sample"]["layer"], "背景")
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        self.assertEqual([entry["name"] for entry in report["layers"]], ["背景", "人物"])
        self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_inspect_invalid_options_do_not_write: 不正なinspect引数がエラーになりプロジェクトを変更しないことを検証する]
    #   処理: [子指定・座標・レイヤーの不正例を実行し、終了値・空stdout・ファイル署名不変を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、出力やファイルが変化すればassertionで失敗する]
    # }
    def test_inspect_invalid_options_do_not_write(self) -> None:
        self.refined(layered=True)
        before = self.signature()
        cases = (
            ("--child", 0, 0), ("--layer", "背景"),
            ("--sample", 0, 0, "--child", 0, 0),
            ("--sample", 1, 1, "--child", 2, 0),
            ("--sample", -1, 0), ("--sample", 4, 0),
            ("--sample", 1, 1, "--layer", "missing"),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli("inspect", "--project", self.project, *arguments, code=2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_flat_project_rejects_named_layer_sample: フラットプロジェクトへのレイヤー指定標本を拒否することを検証する]
    #   処理: [フラット形式を作成し、存在しないレイヤー名を伴うinspectが終了値2になることを確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、CLIが入力を受理すればassertionで失敗する]
    # }
    def test_flat_project_rejects_named_layer_sample(self) -> None:
        self.new()
        self.run_cli("inspect", "--project", self.project, "--sample", 0, 0, "--layer", "背景", code=2)

    # {
    #   責務: [test_invalid_regions_fail_without_partial_save: 不正な破棄領域を拒否し編集前ファイルを保つことを検証する]
    #   処理: [長さ・寸法・境界が不正な領域を順に渡し、エラー終了とファイル署名不変を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、部分保存または成功扱いになればassertionで失敗する]
    # }
    def test_invalid_regions_fail_without_partial_save(self) -> None:
        self.refined()
        before = self.signature()
        for region in ((1,), (1, 1, 2), (1, 1, 1, 1, 1), (1, 1, 0, 1),
                       (1, 1, -1, 1), (3, 3, 2, 2), (-1, 0), (4, 0)):
            with self.subTest(region=region):
                self.edit("--paint", 0, 0, "#00FF00", "--discard-detail", *region, code=2)
                self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_invalid_edits_do_not_save_earlier_operations: 編集列の後続操作が不正なら先行操作も保存しないことを検証する]
    #   処理: [不正な座標・色・細部・領域操作を試し、プロジェクトと既存出力ファイルの両方を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、部分更新または既存出力の上書きがあればassertionで失敗する]
    # }
    def test_invalid_edits_do_not_save_earlier_operations(self) -> None:
        self.refined()
        before = self.signature()
        output = self.root / "output.json"
        output.write_text("do not overwrite", encoding="utf-8")
        cases = (
            ("--paint", 5, 0, "#00FF00"), ("--paint", "oops", 0, "#00FF00"),
            ("--paint-child", 1, 1, 5, 0, "#00FF00"),
            ("--paint-child", 2, 2, 0, 0, "#00FF00"),
            ("--paint", 1, 1, "#GGGGGG"), ("--split-region", 3, 3, 2, 2),
            ("--erase", -1, 0), ("--collapse", 4, 0),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.edit("--split", 0, 0, "--output", output, *arguments, code=2)
                self.assertEqual(self.signature(), before)
                self.assertEqual(output.read_text(encoding="utf-8"), "do not overwrite")

    # {
    #   責務: [test_discard_parent_then_child_edit_fails_transactionally: 同じ編集列で細部破棄後の子編集が失敗した場合に保存しないことを検証する]
    #   処理: [discardする親編集と不正になる子編集を連続指定し、終了値2とファイル署名不変を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、先行する親編集が保存されればassertionで失敗する]
    # }
    def test_discard_parent_then_child_edit_fails_transactionally(self) -> None:
        self.refined()
        before = self.signature()
        self.edit("--paint", 1, 1, "#00FF00", "--detail-policy", "discard",
                  "--paint-child", 1, 1, 0, 0, "#FF0000", code=2)
        self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_no_operation_and_invalid_policy_are_errors: 操作なし・細部ポリシー単独・未知ポリシーをエラーにすることを検証する]
    #   処理: [各CLI引数列を実行し、終了値2で拒否されることを確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、いずれかの不正入力を受理すればassertionで失敗する]
    # }
    def test_no_operation_and_invalid_policy_are_errors(self) -> None:
        self.new()
        self.edit(code=2)
        self.edit("--detail-policy", "preserve", code=2)
        self.edit("--paint", 0, 0, "#00FF00", "--detail-policy", "typo", code=2)

    # {
    #   責務: [test_valid_idempotent_operations_succeed_without_write: 有効な再実行no-opが成功しファイルを書き換えないことを検証する]
    #   処理: [既に成立している分割・塗り・破棄・折りたたみを再要求し、各操作前後のファイル署名を比較する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、no-opが失敗扱いまたは書込扱いになればassertionで失敗する]
    # }
    def test_valid_idempotent_operations_succeed_without_write(self) -> None:
        self.refined()
        for arguments in (("--split", 1, 1), ("--paint", 1, 1, "#FF0000"),
                          ("--discard-detail", 0, 0), ("--collapse", 0, 0)):
            before = self.signature()
            self.edit(*arguments)
            self.assertEqual(self.signature(), before)

    # {
    #   責務: [test_legacy_refinement_without_expanded_field: expandedを持たない旧形式の細分データをCLIで移行することを検証する]
    #   処理: [旧JSONを直接作成し、inspectで展開セル数を確認して折りたたみ後の子画素標本を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、旧形式の解釈や保存結果が異なればassertionで失敗する]
    # }
    def test_legacy_refinement_without_expanded_field(self) -> None:
        self.project.write_text(json.dumps({
            "canvas_size": 2, "pixels": [["#FF0000", None], [None, None]],
            "refined_cells": [{"x": 0, "y": 0, "children": [
                ["#FF0000", "#0000FF"], [None, "#FF0000"],
            ]}],
        }), encoding="utf-8")
        self.assertEqual(self.report()["layers"][0]["expanded_cells"], 1)
        self.edit("--collapse", 0, 0)
        self.assertEqual(self.report("--sample", 0, 0, "--child", 1, 0)["sample"]["rgba"], list(BLUE))

    # {
    #   責務: [test_malformed_projects_and_io_errors_are_reported: 不正JSON・読込不能・保存不能をCLIがエラーとして報告することを検証する]
    #   処理: [複数の不正バイト列と欠落パスでinspect/newを実行し、失敗後も不正ファイルのbytesが保たれることを確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、異常入力が成功扱いまたは変更されればassertionで失敗する]
    # }
    def test_malformed_projects_and_io_errors_are_reported(self) -> None:
        for content in (b'{', b'[]', b'null', b'{}', b'\xff\xfe'):
            with self.subTest(content=content):
                self.project.write_bytes(content)
                self.run_cli("inspect", "--project", self.project, code=2)
                self.assertEqual(self.project.read_bytes(), content)
        self.run_cli("inspect", "--project", self.root / "missing.json", code=2)
        self.run_cli("new", "--output", self.root / "missing" / "file.json", code=2)

    # {
    #   責務: [test_failed_atomic_replace_keeps_original_and_removes_temporary: 原子的置換に失敗しても元JSONを保ち一時ファイルを消すことを検証する]
    #   処理: [os.replaceを例外化して保存し、例外送出・元ファイル署名不変・tmpファイル不在を照合する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、元ファイルまたは一時ファイル状態が異なればassertionで失敗する]
    # }
    def test_failed_atomic_replace_keeps_original_and_removes_temporary(self) -> None:
        self.refined()
        before = self.signature()
        model = load_project(self.project)
        model.paint(0, 0, GREEN)
        with patch("pixel_cli.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                save_project(model, self.project)
        self.assertEqual(self.signature(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    # {
    #   責務: [test_help_for_all_subcommands: 全CLIサブコマンドがhelp要求を受け付けることを検証する]
    #   処理: [new・edit・inspect・exportそれぞれで--helpを実行し正常終了を確認する]
    #   引数: [self: テスト対象のPixelCliTestsケース]
    #   戻り値: [なし、いずれかのhelpが失敗すればassertionで失敗する]
    # }
    def test_help_for_all_subcommands(self) -> None:
        for command in ("new", "edit", "inspect", "export"):
            self.run_cli(command, "--help")


if __name__ == "__main__":
    unittest.main()
