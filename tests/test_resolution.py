"""解像度変更・保存形式・CLI・GUIの非破壊性を検証する回帰テスト。"""
from __future__ import annotations

import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_cli import load_project, save_project
from pixel_layers import LayeredPixelCanvas
from resolution_field import ResolutionField, cell_box

ROOT = Path(__file__).resolve().parents[1] / "src"


# {
#   責務: [ResolutionTests: 解像度変更・細部保持・保存互換・CLI・GUIの回帰動作を検証する]
#   フィールド: [なし、各テストと補助関数がCanvas・一時ファイル・GUIモックを個別に作る]
# }
class ResolutionTests(unittest.TestCase):
    # {
    #   責務: [patterned: 比較用のRGBAパターン画像をPixelCanvasへ読み込む]
    #   処理: [指定寸法に座標依存の色とアルファ値を持つ画像を生成し、Canvasへ取り込む]
    #   引数: [self: テストケース、width: 画像幅、height: 画像高さ。省略時はwidthと同じ]
    #   戻り値: [画像を読み込んだPixelCanvasと元のPillow Image]
    # }
    def patterned(self, width=16, height=None):
        height = width if height is None else height
        image = Image.new("RGBA", (width, height))
        image.putdata([(70 + x % 40, 90 + y % 40, 110 + (x + y) % 40, 150 + (x * y) % 70)
                       for y in range(height) for x in range(width)])
        model = PixelCanvas(width, height)
        model.import_image(image)
        return model, image

    # {
    #   責務: [cli: テスト用CLIコマンドを実行し終了値を検査する]
    #   処理: [pixel_cli.pyをUTF-8・色なし・30秒制限で実行し、期待終了値とTraceback非表示を確認する]
    #   引数: [self: CLIを実行するテストケース、arguments: CLI引数列、code: 期待終了値]
    #   戻り値: [標準出力・標準エラー・終了値を含むCompletedProcess]
    # }
    def cli(self, *arguments, code=0):
        result = subprocess.run([sys.executable, str(ROOT / "pixel_cli.py"), *map(str, arguments)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding="utf-8", timeout=30,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    # {
    #   責務: [fake_editor: GUIを起動せずポインター・解像度テスト用PixelEditorを作る]
    #   処理: [未初期化EditorへCanvasバックエンドと座標・履歴・描画更新モックを設定する]
    #   引数: [self: テストケース、backend: 接続するLayeredPixelCanvas。省略時は16x16を作る]
    #   戻り値: [テスト用PixelEditorインスタンス]
    # }
    def fake_editor(self, backend=None):
        from dot_editor import PixelEditor
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = LayeredPixelCanvas(16) if backend is None else backend
        editor.num_pixels_x, editor.num_pixels_y = editor.backend.resolution
        editor.canvas_width, editor.canvas_height = 640, 480
        editor.zoom_factor = 1.0
        editor.canvas = Mock()
        editor.canvas.canvasx.side_effect = lambda x: x
        editor.canvas.canvasy.side_effect = lambda y: y
        editor.history, editor.future = [], []
        editor.selected_cell = None
        editor.tool = "brush"
        editor.current_color = (255, 128, 64)
        editor.create_grid = lambda: None
        editor.update_canvas = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.update_canvas_size()
        return editor

    # {
    #   責務: [test_arbitrary_resolution_roundtrip: 正方形・長方形・細長い解像度を往復して原画を保つことを検証する]
    #   処理: [複数の解像度へ順に変更し、最終画像のバイト列と保存表現を変更前と比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、原画または保存情報が変化すればassertionで失敗する]
    # }
    def test_arbitrary_resolution_roundtrip(self):
        model, image = self.patterned()
        before = model.to_source()
        for shape in ((7, 7), (23, 17), (1, 31), (31, 1), (16, 16)):
            model.set_resolution(*shape)
        self.assertEqual(model.image.tobytes(), image.tobytes())
        self.assertEqual(model.to_source(), before)

    # {
    #   責務: [test_rectangular_roundtrip: 長方形Canvasの解像度往復で保存表現を保つことを検証する]
    #   処理: [23x17画像を複数の長方形グリッドへ変更して元解像度へ戻し、JSON相当の状態を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、往復後の保存表現が変化すればassertionで失敗する]
    # }
    def test_rectangular_roundtrip(self):
        model, _ = self.patterned(23, 17)
        before = model.to_source()
        for shape in ((7, 5), (41, 13), (23, 17)):
            model.set_resolution(*shape)
        self.assertEqual(model.to_source(), before)

    # {
    #   責務: [test_downscale_without_data_loss: 1x1表示で標本化されない原画画素を保持することを検証する]
    #   処理: [元画素を1x1へ縮小して細部保持を確認し、16x16へ戻して元色を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、未標本画素や保持フィールドが失われればassertionで失敗する]
    # }
    def test_downscale_without_data_loss(self):
        model = PixelCanvas(16)
        model.paint(0, 0, (255, 0, 0, 255))  # 1x1表示では標本化されない画素に赤色を置く。
        field = model.to_source()["retained_field"]
        model.set_resolution(1)
        self.assertEqual(model.sample(0, 0), (0, 0, 0, 0))
        self.assertTrue(model.has_detail)
        self.assertEqual(model.to_source()["retained_field"], field)
        model.set_resolution(16)
        self.assertEqual(model.sample(0, 0), (255, 0, 0, 255))

    # {
    #   責務: [test_fine_edits_on_unaligned_grid_survive_roundtrip: 23x17の非整列グリッドで行った編集を解像度往復後も保つことを検証する]
    #   処理: [右下セルをdiscard編集し、別解像度を経由して戻した後の保存表現と画素色を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、非整列位置の編集が失われればassertionで失敗する]
    # }
    def test_fine_edits_on_unaligned_grid_survive_roundtrip(self):
        model, _ = self.patterned()
        model.set_resolution(23, 17)
        self.assertTrue(model.paint(22, 16, (23, 45, 67, 255), detail_policy="discard"))
        before = model.to_source()
        model.set_resolution(7)
        model.set_resolution(16)
        model.set_resolution(23, 17)
        self.assertEqual(model.to_source(), before)
        self.assertEqual(model.sample(22, 16), (23, 45, 67, 255))

    # {
    #   責務: [test_coarse_edit_preserves_detail: 粗いグリッドの親画素編集で対象内だけ色差分を加え細部を保つことを検証する]
    #   処理: [7x7上の1セルを編集後に16x16へ戻し、有理座標で対象内外を分類して全画素を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、対象外画素または保持細部が変化すればassertionで失敗する]
    # }
    def test_coarse_edit_preserves_detail(self):
        model, original = self.patterned()
        model.set_resolution(7)
        base = model.sample(2, 3)
        replacement = (120, 130, 140, 200)
        delta = tuple(n - o for n, o in zip(replacement, base))
        self.assertTrue(model.paint(2, 3, replacement))
        self.assertEqual(model.sample(2, 3), replacement)
        self.assertTrue(model.has_detail_at(2, 3))
        model.set_resolution(16)
        for y in range(16):
            for x in range(16):
                inside = 2 <= Fraction(2*x+1, 32)*7 < 3 and 3 <= Fraction(2*y+1, 32)*7 < 4
                expected = original.getpixel((x, y))
                if inside:
                    expected = tuple(c+d for c, d in zip(expected, delta))
                self.assertEqual(model.sample(x, y), expected, (x, y))

    # {
    #   責務: [test_coarse_edit_retains_unclipped_samples: 保存再読込と連続編集後も未クリップの元画素値を保持することを検証する]
    #   処理: [粗い解像度で色差分を加えJSON往復した後に再編集し、元解像度上の複数標本値を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、差分の累積や未クリップ値が誤ればassertionで失敗する]
    # }
    def test_coarse_edit_retains_unclipped_samples(self):
        image = Image.new("RGBA", (16, 16))
        image.putdata([(240+x, 80+y, 100, 255) for y in range(16) for x in range(16)])
        model = PixelCanvas(16)
        model.import_image(image)
        model.set_resolution(7)
        anchor = model.sample(1, 1)
        model.paint(1, 1, (255, 100, 120, 255))
        model = PixelCanvas.from_source(model.to_source())
        model.paint(1, 1, (200, 100, 120, 255))
        self.assertEqual(model.sample(1, 1), (200, 100, 120, 255))
        model.set_resolution(16)
        for x in (2, 3, 4):
            self.assertEqual(model.sample(x, 3)[0], image.getpixel((x, 3))[0]+200-anchor[0])

    # {
    #   責務: [test_coarse_edit_discards_detail: discard編集の範囲だけを粗い色へ置き換えることを検証する]
    #   処理: [7x7上の1セルをdiscard編集し16x16へ戻し、有理座標の対象内外で期待画素を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、編集範囲や対象外原画が期待と異なればassertionで失敗する]
    # }
    def test_coarse_edit_discards_detail(self):
        model, original = self.patterned()
        model.set_resolution(7)
        replacement = (23, 45, 67, 255)
        model.paint(1, 1, replacement, detail_policy="discard")
        self.assertFalse(model.has_detail_at(1, 1))
        model.set_resolution(16)
        for y in range(16):
            for x in range(16):
                inside = 1 <= Fraction(2*x+1, 32)*7 < 2 and 1 <= Fraction(2*y+1, 32)*7 < 2
                self.assertEqual(model.sample(x, y), replacement if inside else original.getpixel((x, y)))

    # {
    #   責務: [test_discard_detail_is_local: 矩形細部破棄が対象範囲だけに作用することを検証する]
    #   処理: [高解像度の前後画像を作り、2x1セル範囲内は粗い画像、範囲外は編集前画像と比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、対象範囲外に差があればassertionで失敗する]
    # }
    def test_discard_detail_is_local(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        reference = model.render_resolution(79, 53)
        coarse = model.image
        self.assertEqual(model.discard_detail(1, 2, 2, 1), 2)
        result = model.render_resolution(79, 53)
        for y in range(53):
            for x in range(79):
                gx, gy = Fraction(2*x+1, 2*79)*7, Fraction(2*y+1, 2*53)*7
                expected = coarse.getpixel((int(gx), int(gy))) if 1 <= gx < 3 and 2 <= gy < 3 else reference.getpixel((x, y))
                self.assertEqual(result.getpixel((x, y)), expected)

    # {
    #   責務: [test_undo_restores_discarded_detail: 細部破棄をUndo/Redoで復元し再破棄がno-opになることを検証する]
    #   処理: [破棄前後の保存状態を記録しUndo/Redo結果と2回目の破棄件数を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、履歴または再実行結果が期待と異なればassertionで失敗する]
    # }
    def test_undo_restores_discarded_detail(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        before = model.to_source()
        model.discard_detail(1, 1, 2, 2)
        after = model.to_source()
        self.assertNotEqual(before, after)
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)
        self.assertTrue(model.redo())
        self.assertEqual(model.to_source(), after)
        self.assertEqual(model.discard_detail(1, 1, 2, 2), 0)

    # {
    #   責務: [test_global_discard_is_explicit_and_undoable: 解像度変更時に明示したglobal discardと二段階Undoを検証する]
    #   処理: [細部付きCanvasをdiscard縮小して情報消失を確認し、二度Undoして元状態へ戻す]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、discard範囲またはUndo結果が異なればassertionで失敗する]
    # }
    def test_global_discard_is_explicit_and_undoable(self):
        model, image = self.patterned()
        before = model.to_source()
        model.set_resolution(7, detail_policy="discard")
        self.assertFalse(model.has_detail)
        self.assertEqual(model.retained_resolution, (7, 7))
        model.set_resolution(16)
        self.assertNotEqual(model.image.tobytes(), image.tobytes())
        self.assertTrue(model.undo())
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)

    # {
    #   責務: [test_split_collapse_global_roundtrip: 展開・折りたたみ双方で子画素を異なる解像度往復後も保つことを検証する]
    #   処理: [expanded状態ごとに親子を編集し、グリッド変更とJSON往復後の保存状態・半透明子色を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、分割状態または子画素色が変化すればassertionで失敗する]
    # }
    def test_split_collapse_global_roundtrip(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                model = PixelCanvas(4)
                model.paint(1, 1, (255, 0, 0, 255))
                model.split_cell(1, 1)
                model.paint(1, 1, (0, 0, 255, 128), child=(1, 0))
                model.paint(1, 1, (0, 255, 0, 255))
                if not expanded:
                    model.collapse_cell(1, 1)
                before = model.to_source()
                model.set_resolution(7, 3)
                model.set_resolution(23, 17)
                model = PixelCanvas.from_source(model.to_source())
                model.set_resolution(4)
                self.assertEqual(model.to_source(), before)
                self.assertEqual(model.sample(1, 1, (1, 0)), (0, 0, 255, 128))

    # {
    #   責務: [test_split_at_another_grid_restores_its_own_metadata: 別グリッド上の分割編集を元グリッドで正確に復元することを検証する]
    #   処理: [7x7上で分割・子画素編集後に23x17を経由し、7x7へ戻した保存表現を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、グリッド固有メタデータが変化すればassertionで失敗する]
    # }
    def test_split_at_another_grid_restores_its_own_metadata(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        model.split_cell(3, 2)
        model.paint(3, 2, (12, 34, 56, 255), child=(1, 0), detail_policy="discard")
        before = model.to_source()
        model.set_resolution(23, 17)
        model.set_resolution(7)
        self.assertEqual(model.to_source(), before)

    # {
    #   責務: [test_save_load_preserves_resolution_history: 解像度変更履歴を保存・再読込後に原画へ戻せることを検証する]
    #   処理: [7x7・23x17へ変更したCanvasを保存・再読込し、16x16へ戻した画像を元画像と比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、保存後の原画が一致しなければassertionで失敗する]
    # }
    def test_save_load_preserves_resolution_history(self):
        model, image = self.patterned()
        model.set_resolution(7)
        model.set_resolution(23, 17)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"p.json"
            save_project(model, p)
            restored = load_project(p)
            restored.set_resolution(16)
            self.assertEqual(restored.image.tobytes(), image.tobytes())

    # {
    #   責務: [test_layer_resolution_change_is_atomic_and_undoable: レイヤー一括解像度変更の原子性・履歴・active layerを検証する]
    #   処理: [背景と人物を編集して解像度を変更し、全レイヤー寸法・選択状態・Undo/Redo・元解像度を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、一部レイヤーや履歴だけが変化すればassertionで失敗する]
    # }
    def test_layer_resolution_change_is_atomic_and_undoable(self):
        layers = LayeredPixelCanvas(16)
        layers.paint(1, 1, (12, 34, 56, 255))
        layers.add_layer("人物")
        layers.paint(14, 13, (23, 45, 67, 128))
        before = layers.to_source()
        layers.set_resolution(23, 17)
        self.assertEqual({c.resolution for c in layers.layers.values()}, {(23, 17)})
        self.assertEqual(layers.active_layer, "人物")
        self.assertTrue(layers.undo())
        self.assertEqual(layers.to_source(), before)
        self.assertTrue(layers.redo())
        self.assertEqual(layers.resolution, (23, 17))
        layers.set_resolution(16)
        self.assertEqual(layers.to_source(), before)

    # {
    #   責務: [test_failed_layer_resize_keeps_all_layers_and_history: レイヤー変更途中の例外で全レイヤーと履歴を保つことを検証する]
    #   処理: [2回目のCanvas解像度変更を例外化し、失敗後の保存状態と履歴件数を変更前と比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、部分的なレイヤー更新や履歴変更があればassertionで失敗する]
    # }
    def test_failed_layer_resize_keeps_all_layers_and_history(self):
        layers = LayeredPixelCanvas(16)
        layers.add_layer("人物")
        before = layers.to_source()
        history = len(layers._history)
        original = PixelCanvas.set_resolution
        calls = 0
        # {
        #   責務: [fail_second: 2回目のPixelCanvas解像度変更だけを予算超過例外にする]
        #   処理: [呼出回数を数え、2回目はValueErrorを送出し、それ以外は元の処理へ委譲する]
        #   引数: [canvas: 解像度変更対象、args: 位置引数列、kwargs: キーワード引数辞書]
        #   戻り値: [元処理が返す結果、または2回目の呼出時のValueError]
        # }
        def fail_second(canvas, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated allocation limit")
            return original(canvas, *args, **kwargs)
        with patch.object(PixelCanvas, "set_resolution", fail_second):
            with self.assertRaises(ValueError):
                layers.set_resolution(7, detail_policy="discard")
        self.assertEqual(layers.to_source(), before)
        self.assertEqual(len(layers._history), history)

    # {
    #   責務: [test_discard_is_local_to_active_layer: 細部破棄がアクティブレイヤー内だけに作用することを検証する]
    #   処理: [背景と人物へ画像を読み込んで解像度を変更し、人物側を破棄した後の背景保存状態を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、非アクティブレイヤーが変化すればassertionで失敗する]
    # }
    def test_discard_is_local_to_active_layer(self):
        layers = LayeredPixelCanvas(16)
        layers.layers["背景"] = self.patterned()[0]
        layers.add_layer("人物")
        layers.active.import_image(self.patterned()[1])
        layers.set_resolution(7)
        background = layers.layers["背景"].to_source()
        layers.discard_detail(1, 1)
        self.assertEqual(layers.layers["背景"].to_source(), background)

    # {
    #   責務: [test_invalid_resolution_leaves_history_and_future_unchanged: 不正解像度を拒否し画像・Undo・Redo履歴を保つことを検証する]
    #   処理: [型・寸法・安全上限が不正な入力を試し、状態と履歴を照合して同解像度指定のno-opも確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、拒否時にCanvasまたは履歴が変化すればassertionで失敗する]
    # }
    def test_invalid_resolution_leaves_history_and_future_unchanged(self):
        model, _ = self.patterned()
        model.paint(0, 0, (11, 22, 33, 255))
        model.undo()
        before = model.to_source()
        history, future = len(model._history), len(model._future)
        for dims in ((0, 1), (-1, 1), (True, 2), (3.0, 2), (4097, 1), (4096, 4096)):
            with self.subTest(dims=dims), self.assertRaises(ValueError):
                model.set_resolution(*dims)
        self.assertEqual(model.to_source(), before)
        self.assertEqual((len(model._history), len(model._future)), (history, future))
        self.assertFalse(model.set_resolution(16))
        self.assertEqual(len(model._future), future)

    # {
    #   責務: [test_safe_dimension_limit_is_not_a_preset_limit: 安全上限内の任意解像度をプリセット外でも受理することを検証する]
    #   処理: [正方形・長方形・極端な縦横比を含む寸法をCanvasへ渡し、解像度が一致することを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、許可寸法が拒否または変換されればassertionで失敗する]
    # }
    def test_safe_dimension_limit_is_not_a_preset_limit(self):
        for dims in ((1, 1), (3, 5), (7, 7), (23, 17), (4096, 1), (1, 4096)):
            with self.subTest(dims=dims):
                self.assertEqual(PixelCanvas(*dims).resolution, dims)

    # {
    #   責務: [test_rgba_roundtrip_including_hidden_transparent_rgb: 透明画素内RGBと部分アルファを含むRGBAデータの往復保持を検証する]
    #   処理: [異なるアルファ値で画素を編集し縮小・復元後の保存表現を元データと比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、透明画素RGBやアルファ値が失われればassertionで失敗する]
    # }
    def test_rgba_roundtrip_including_hidden_transparent_rgb(self):
        model = PixelCanvas(3, 2)
        for x, c in enumerate(((1, 2, 3, 0), (4, 5, 6, 128), (7, 8, 9, 255))):
            model.paint(x, 1, c)
        restored = PixelCanvas.from_source(model.to_source())
        restored.set_resolution(1)
        restored.set_resolution(3, 2)
        self.assertEqual(restored.to_source(), model.to_source())

    # {
    #   責務: [test_legacy_project_migrates_and_retains_children: 旧形式プロジェクトの移行後も折りたたみ子画素を保持することを検証する]
    #   処理: [旧JSONを読み込み解像度変更・新形式JSON往復を行い、折りたたみ状態と青い子画素を確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、旧形式の子画素または展開状態が失われればassertionで失敗する]
    # }
    def test_legacy_project_migrates_and_retains_children(self):
        old = {"canvas_size": 2, "pixels": [["#FF0000", None], [None, None]],
               "refined_cells": [{"x": 0, "y": 0, "expanded": False,
                                  "children": [["#FF0000", "#0000FF"], [None, "#FF0000"]]}]}
        model = PixelCanvas.from_source(old)
        model.set_resolution(7, 3)
        model = PixelCanvas.from_source(model.to_source())
        model.set_resolution(2)
        self.assertFalse(model.is_split(0, 0))
        self.assertEqual(model.sample(0, 0, (1, 0)), (0, 0, 255, 255))

    # {
    #   責務: [test_invalid_v2_is_rejected: version 2形式の不正バージョン・寸法・画素・保持タイルを拒否することを検証する]
    #   処理: [正常な保存表現の複製へ各不正値を設定し、すべてPixelCanvas読込時にValueErrorとなることを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、不正データのいずれかを受理すればassertionで失敗する]
    # }
    def test_invalid_v2_is_rejected(self):
        model, _ = self.patterned()
        source = model.to_source()
        variants = []
        value = copy.deepcopy(source); value["version"] = 99; variants.append(value)
        value = copy.deepcopy(source); value["resolution"] = [True, 16]; variants.append(value)
        value = copy.deepcopy(source); value["pixels"][0][0] = None; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"][0]["offset"][0] = 1_000_001; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"][0]["clip"][0] = [0, 0]; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"].append(value["retained_field"][0]); variants.append(value)
        for value in variants:
            with self.subTest(value=value.get("version")), self.assertRaises(ValueError):
                PixelCanvas.from_source(value)

    # {
    #   責務: [test_overlapping_patches_with_equal_total_area_rejected: 総面積が一致しても重なる保持パッチを拒否することを検証する]
    #   処理: [保持タイルのclipとextentを重複形状に複製し、ResolutionField読込がValueErrorとなることを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、重複タイルを受理すればassertionで失敗する]
    # }
    def test_overlapping_patches_with_equal_total_area_rejected(self):
        model = PixelCanvas(2)
        model.paint(0, 0, (1, 2, 3, 255))
        source = model.to_source()
        tile = copy.deepcopy(source["retained_field"][0])
        tile["clip"] = [[0, 1], [0, 1], [1, 1], [1, 2]]
        tile["extent"] = copy.deepcopy(tile["clip"])
        with self.assertRaises(ValueError):
            ResolutionField.from_source([tile, tile])

    # {
    #   責務: [test_cli_complete_non_interactive_scenario: CLIでの作成・編集・解像度変更・局所破棄・PNG出力を通しで検証する]
    #   処理: [レイヤー付き作品を一時作成して複数操作を行い、JSON標本・元解像度状態・指定サイズPNGを照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、CLIの編集結果または出力画像が期待と異なればassertionで失敗する]
    # }
    def test_cli_complete_non_interactive_scenario(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.png"
            self.cli("new", "--size", 16, "--layered", "--output", path)
            for x, y, color in ((2, 2, "#FF0000"), (3, 3, "#0000FF"), (14, 14, "#00FF00")):
                self.cli("edit", "--project", path, "--paint", x, y, color)
            before = load_project(path).to_source()
            self.cli("edit", "--project", path, "--resolution", 7, 7)
            self.cli("edit", "--project", path, "--resolution", 23, 17)
            report = json.loads(self.cli("inspect", "--project", path).stdout)
            self.assertEqual(report["resolution"], [23, 17])
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            self.assertEqual(load_project(path).to_source(), before)
            self.cli("edit", "--project", path, "--resolution", 7, 7)
            self.cli("edit", "--project", path, "--discard-detail", 1, 1)
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            actual = load_project(path)
            self.assertEqual(actual.sample(2, 2), (0, 0, 255, 255))
            self.assertEqual(actual.sample(14, 14), (0, 255, 0, 255))
            self.cli("export", "--project", path, "--output", output, "--resolution", 23, 17)
            with Image.open(output) as image:
                self.assertEqual(image.size, (23, 17))
                self.assertEqual(image.tobytes(), actual.render_resolution(23, 17).tobytes())

    # {
    #   責務: [test_cli_preserve_and_discard_match_backend: CLIの親画素編集がpreserve/discard双方でバックエンドと一致することを検証する]
    #   処理: [各ポリシーの期待Canvasを直接編集し、CLI保存後の完全な保存表現を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、CLIとバックエンドの結果が異なればassertionで失敗する]
    # }
    def test_cli_preserve_and_discard_match_backend(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            for policy in ("preserve", "discard"):
                model, _ = self.patterned()
                model.set_resolution(7)
                save_project(model, path)
                expected = PixelCanvas.from_source(model.to_source())
                expected.paint(1, 2, (120, 130, 140, 255), detail_policy=policy)
                self.cli("edit", "--project", path, "--paint", 1, 2, "#78828C", "--detail-policy", policy)
                self.assertEqual(load_project(path).to_source(), expected.to_source())

    # {
    #   責務: [test_cli_rectangular_new_and_bounds: CLIの長方形新規作成と上下端の座標検証を確認する]
    #   処理: [3x5を作成して有効画素を塗り、不正x/y座標での拒否後にファイル内容が変わらないことを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、寸法・座標検証・失敗時の保護が異なればassertionで失敗する]
    # }
    def test_cli_rectangular_new_and_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            self.cli("new", "--resolution", 3, 5, "--output", path)
            self.cli("edit", "--project", path, "--paint", 2, 4, "#123456")
            self.assertEqual(load_project(path).sample(2, 4), (18, 52, 86, 255))
            before = path.read_bytes()
            self.cli("edit", "--project", path, "--paint", 3, 4, "#123456", code=2)
            self.cli("edit", "--project", path, "--paint", 2, 5, "#123456", code=2)
            self.assertEqual(path.read_bytes(), before)

    # {
    #   責務: [test_cli_invalid_following_edit_does_not_save_resolution_change: 編集列の後続操作が失敗した場合に解像度変更を保存しないことを検証する]
    #   処理: [不正な塗りを解像度変更の後へ指定し、元JSONと既存の別出力ファイルが保たれることを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、部分的な解像度保存または出力上書きがあればassertionで失敗する]
    # }
    def test_cli_invalid_following_edit_does_not_save_resolution_change(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.json"
            save_project(self.patterned()[0], path)
            before = path.read_bytes()
            output.write_text("keep", encoding="utf-8")
            self.cli("edit", "--project", path, "--resolution", 7, 7,
                     "--paint", 7, 0, "#FFFFFF", "--output", output, code=2)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(output.read_text(), "keep")
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            self.assertEqual(path.read_bytes(), before)

    # {
    #   責務: [test_cli_export_resolution_is_read_only: 指定解像度でのCLI exportがプロジェクトJSONを書き換えないことを検証する]
    #   処理: [保持細部を持つ作品を別寸法へexportし、PNGを元画像と比較してJSON bytesの不変を確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、画像または入力ファイルが変化すればassertionで失敗する]
    # }
    def test_cli_export_resolution_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.png"
            model, original = self.patterned()
            model.set_resolution(7)
            save_project(model, path)
            before = path.read_bytes()
            self.cli("export", "--project", path, "--resolution", 16, 16, "--output", output)
            with Image.open(output) as image:
                self.assertEqual(image.tobytes(), original.tobytes())
            self.assertEqual(path.read_bytes(), before)

    # {
    #   責務: [test_gui_rectangle_pointer_maps_bottom_right: 長方形GUI Canvasの右下ポインター座標を正しい画素へ対応づけることを検証する]
    #   処理: [右下端を塗り、Canvas外の左右・下端座標では保存状態が変わらないことを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、座標変換または範囲外処理が誤ればassertionで失敗する]
    # }
    def test_gui_rectangle_pointer_maps_bottom_right(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.paint_pixel(SimpleNamespace(x=639, y=479))
        self.assertEqual(editor.backend.sample(22, 16), (255, 128, 64, 255))
        before = editor.backend.to_source()
        editor.paint_pixel(SimpleNamespace(x=-1, y=0))
        editor.paint_pixel(SimpleNamespace(x=640, y=480))
        self.assertEqual(editor.backend.to_source(), before)

    # {
    #   責務: [test_gui_pointer_after_zoom_and_pan: ズーム・パン適用後のGUIポインターを元グリッド画素へ対応づけることを検証する]
    #   処理: [座標変換モックに倍率とオフセットを設定し、入力位置が右下セルへ塗られることを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、変換後の対象セルが異なればassertionで失敗する]
    # }
    def test_gui_pointer_after_zoom_and_pan(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.zoom_factor = 2
        editor.canvas.canvasx.side_effect = lambda x: x+1000
        editor.canvas.canvasy.side_effect = lambda y: y+800
        editor.paint_pixel(SimpleNamespace(x=279, y=159))
        self.assertEqual(editor.backend.sample(22, 16), (255, 128, 64, 255))

    # {
    #   責務: [test_gui_resolution_larger_than_display_does_not_divide_by_zero: 表示サイズより大きな解像度でもGUI座標計算がゼロ除算しないことを検証する]
    #   処理: [1001x17のCanvasを100x100表示へ縮め、右下表示位置への入力が適切なセルへ届くことを確認する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、座標計算が失敗または別セルを編集すればassertionで失敗する]
    # }
    def test_gui_resolution_larger_than_display_does_not_divide_by_zero(self):
        editor = self.fake_editor(LayeredPixelCanvas(1001, 17))
        editor.set_display_size(100, 100)
        editor.paint_pixel(SimpleNamespace(x=99, y=99))
        self.assertEqual(editor.backend.sample(990, 16), (255, 128, 64, 255))

    # {
    #   責務: [test_gui_resolution_roundtrip_and_undo: GUIの解像度変更履歴をUndo/Redoし元画像へ戻せることを検証する]
    #   処理: [複数解像度へ変更して寸法を確認し、Undo/Redoと16x16復帰後の保存状態を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、GUI寸法または履歴状態が期待と異なればassertionで失敗する]
    # }
    def test_gui_resolution_roundtrip_and_undo(self):
        editor = self.fake_editor()
        editor.backend.active.import_image(self.patterned()[1])
        before = editor.backend.to_source()
        editor.resize_logical_canvas(7)
        editor.resize_logical_canvas(23, 17)
        self.assertEqual((editor.num_pixels_x, editor.num_pixels_y), (23, 17))
        editor.undo()
        self.assertEqual(editor.backend.resolution, (7, 7))
        editor.undo()
        self.assertEqual(editor.backend.to_source(), before)
        editor.redo()
        self.assertEqual(editor.backend.resolution, (7, 7))
        editor.resize_logical_canvas(16)
        self.assertEqual(editor.backend.to_source(), before)

    # {
    #   責務: [test_gui_policy_is_passed_to_backend: GUIで選んだ細部ポリシーを編集バックエンドへ渡すことを検証する]
    #   処理: [preserve/discardごとに期待レイヤーを直接編集し、ポインター塗り後の保存表現を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、GUIのポリシー伝達結果が異なればassertionで失敗する]
    # }
    def test_gui_policy_is_passed_to_backend(self):
        for policy in ("preserve", "discard"):
            editor = self.fake_editor()
            editor.backend.active.import_image(self.patterned()[1])
            editor.resize_logical_canvas(7)
            editor.detail_policy = SimpleNamespace(get=lambda: policy)
            expected = LayeredPixelCanvas.from_source(editor.backend.to_source())
            expected.paint(1, 1, (255, 128, 64, 255), detail_policy=policy)
            editor.paint_pixel(SimpleNamespace(x=100, y=100))
            self.assertEqual(editor.backend.to_source(), expected.to_source())

    # {
    #   責務: [test_gui_and_cli_project_roundtrip: GUI保存・CLI編集・GUI読込の往復で細分画素を保つことを検証する]
    #   処理: [GUIからJSONを保存しCLIで解像度変更後に読み戻し、元グリッドでの分割状態と半透明子画素を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、GUI・CLI間で保存互換が崩れればassertionで失敗する]
    # }
    def test_gui_and_cli_project_roundtrip(self):
        from dot_editor import filedialog
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.backend.paint(22, 16, (12, 34, 56, 128))
        editor.backend.split_cell(22, 16)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            with patch.object(filedialog, "asksaveasfilename", return_value=str(path)):
                editor.save_project()
            self.assertEqual(load_project(path).to_source(), editor.backend.to_source())
            self.cli("edit", "--project", path, "--resolution", 7, 5)
            with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                editor.load_project()
            self.assertEqual((editor.num_pixels_x, editor.num_pixels_y), (7, 5))
            editor.resize_logical_canvas(23, 17)
            self.assertTrue(editor.backend.is_split(22, 16))
            self.assertEqual(editor.backend.sample(22, 16, (0, 0)), (12, 34, 56, 128))

    # {
    #   責務: [test_display_resize_does_not_change_document_or_history: 表示領域の変更が作品・バックエンド参照・Redo履歴を変えないことを検証する]
    #   処理: [編集済みCanvasの表示寸法を変更し、バックエンド同一性・保存表現・future履歴を照合する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、表示変更で作品または履歴が変化すればassertionで失敗する]
    # }
    def test_display_resize_does_not_change_document_or_history(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.backend.paint(3, 2, (12, 34, 56, 255))
        before = editor.backend.to_source()
        backend = editor.backend
        editor.future.append("sentinel")
        editor.set_display_size(800, 300)
        self.assertIs(editor.backend, backend)
        self.assertEqual(editor.backend.to_source(), before)
        self.assertEqual(editor.future, ["sentinel"])

    # {
    #   責務: [test_optional_compaction_is_lossless: 保持タイル上限を小さくした圧縮後も描画結果を保つことを検証する]
    #   処理: [通常Canvasと上限1でdiscard編集したCanvasの37x31描画バイト列を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、圧縮後の描画が異なればassertionで失敗する]
    # }
    def test_optional_compaction_is_lossless(self):
        model, _ = self.patterned()
        expected, _ = self.patterned()
        expected.paint(1, 1, (12, 34, 56, 255), detail_policy="discard")
        with patch("resolution_field.MAX_TILES", 1):
            model.paint(1, 1, (12, 34, 56, 255), detail_policy="discard")
        self.assertEqual(model.retained_patch_count, 1)
        self.assertEqual(model.render_resolution(37, 31).tobytes(), expected.render_resolution(37, 31).tobytes())

    # {
    #   責務: [test_field_rejects_resource_limit_without_partial_mutation: 保持フィールドの予算超過を拒否しCanvasを部分変更しないことを検証する]
    #   処理: [ResolutionFieldの検証処理をValueErrorへ差し替えて描画編集し、例外後の保存状態を比較する]
    #   引数: [self: テスト対象のResolutionTestsケース]
    #   戻り値: [なし、予算超過時に状態が変化すればassertionで失敗する]
    # }
    def test_field_rejects_resource_limit_without_partial_mutation(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        before = model.to_source()
        with patch.object(ResolutionField, "_checked", side_effect=ValueError("simulated patch budget")):
            with self.assertRaises(ValueError):
                model.paint(1, 1, (12, 34, 56, 255))
        self.assertEqual(model.to_source(), before)


if __name__ == "__main__":
    unittest.main()
