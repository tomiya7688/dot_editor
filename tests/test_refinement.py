"""Issue #3: refinement isolation across resolution, persistence and history."""
from __future__ import annotations

from fractions import Fraction
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_layers import LayeredPixelCanvas
from resolution_field import ResolutionField

CHILDREN = ((0, 0), (1, 0), (0, 1), (1, 1))
CLEAR = (0, 0, 0, 0)
RED = (180, 40, 50, 255)
BLUE = (40, 60, 180, 128)


# {
#   責務: [patterned_canvas: 解像度変更と細分編集の比較に使う規則的なPixelCanvasを作る]
#   処理: [
#     1: 16x12のRGBAパターンを作り、PixelCanvasへ読み込む
#     2: 論理解像度を4x3へ変更し、比較対象セルを分割する
#   ]
#   引数: [なし]
#   戻り値: [パターン画素と分割状態を持つPixelCanvas]
# }
def patterned_canvas() -> PixelCanvas:
    image = Image.new("RGBA", (16, 12))
    image.putdata([(60 + 2*x, 80 + 3*y, 100 + x + y, 200)
                   for y in range(12) for x in range(16)])
    canvas = PixelCanvas(16, 12)
    canvas.import_image(image)
    canvas.set_resolution(4, 3)
    canvas.split_cell(1, 1)
    return canvas


# {
#   責務: [reload_canvas: 保存形式をJSON往復してPixelCanvasを再構築する]
#   処理: [Canvasの保存表現をJSON文字列へ変換し、JSON値へ戻してPixelCanvasへ読み込む]
#   引数: [canvas: 保存・再読込するPixelCanvas]
#   戻り値: [保存形式から復元したPixelCanvas]
# }
def reload_canvas(canvas: PixelCanvas) -> PixelCanvas:
    return PixelCanvas.from_source(json.loads(json.dumps(canvas.to_source())))


# {
#   責務: [metadata_canvas: 色付き親画素だけが保持された細部メタデータ用Canvasを作る]
#   処理: [
#     1: 指定解像度の透明Canvasで指定セルを分割する
#     2: 親セルへ赤色を設定し、expandedが偽なら折りたたむ
#   ]
#   引数: [expanded: 分割状態を保つか、point: 対象座標、size: Canvas解像度]
#   戻り値: [親画素の細部情報を持つPixelCanvas]
# }
def metadata_canvas(expanded: bool = False, point=(0, 0), size=16) -> PixelCanvas:
    # Canvas本体は透明で、色付き画素は保持された親セルだけに存在する。
    canvas = PixelCanvas(size)
    canvas.split_cell(*point)
    canvas.paint(*point, RED)
    if not expanded:
        canvas.collapse_cell(*point)
    return canvas


# {
#   責務: [RefinementTests: 細分セルの編集・保持・破棄・互換性をCanvas・GUI・CLIで検証する]
#   フィールド: [なし。各テストがCanvasと一時ファイルを個別に作る]
# }
class RefinementTests(unittest.TestCase):
    # {
    #   責務: [test_child_paint_keeps_parent_in_all_quadrants_and_policies: 全子象限と細部ポリシーで子画素編集が親画素を変えないことを検証する]
    #   処理: [
    #     1: preserve/discardと4象限の組み合わせごとに編集前の親・兄弟子画素を保存する
    #     2: 子画素を青に変更し、親・兄弟・表示画素への影響を照合する
    #     3: Undo/Redo・JSON往復・折りたたみ・複数解像度往復後の状態を比較する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、親子画素や履歴が期待と異なればassertionで失敗する]
    # }
    def test_child_paint_keeps_parent_in_all_quadrants_and_policies(self):
        for policy in ("preserve", "discard"):
            for child in CHILDREN:
                with self.subTest(policy=policy, child=child):
                    canvas = patterned_canvas()
                    parent = canvas.sample(1, 1)
                    before = canvas.to_source()  # 投影キャッシュもこの時点で生成する。
                    siblings = {p: canvas.sample(1, 1, p) for p in CHILDREN}
                    self.assertTrue(canvas.paint(1, 1, BLUE, child=child, detail_policy=policy))
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.image.getpixel((1, 1)), parent)
                    self.assertEqual(canvas.sample(1, 1, child), BLUE)
                    for other in CHILDREN:
                        if other != child:
                            self.assertEqual(canvas.sample(1, 1, other), siblings[other])
                    after = canvas.to_source()
                    self.assertTrue(canvas.undo())
                    self.assertEqual(canvas.to_source(), before)
                    self.assertTrue(canvas.redo())
                    self.assertEqual(canvas.to_source(), after)
                    canvas = reload_canvas(canvas)
                    canvas.collapse_cell(1, 1)
                    self.assertEqual(canvas.render().getpixel((1, 1)), parent)
                    canvas.set_resolution(7, 5)
                    canvas.set_resolution(23, 17)
                    canvas = reload_canvas(canvas)
                    canvas.set_resolution(4, 3)
                    canvas.split_cell(1, 1)
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.sample(1, 1, child), BLUE)
                    self.assertEqual(canvas.to_source(), after)

    # {
    #   責務: [test_child_erase_keeps_parent_in_all_quadrants_and_policies: 全子象限と細部ポリシーで子画素消去が親画素を変えないことを検証する]
    #   処理: [
    #     1: preserve/discardと4象限の組み合わせごとに親画素と兄弟子画素を記録する
    #     2: 指定子画素を透明化し、親・兄弟・対象子画素を照合する
    #     3: JSON往復・折りたたみ・再分割後にも消去状態が残ることを確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、消去範囲や親画素が期待と異なればassertionで失敗する]
    # }
    def test_child_erase_keeps_parent_in_all_quadrants_and_policies(self):
        for policy in ("preserve", "discard"):
            for child in CHILDREN:
                with self.subTest(policy=policy, child=child):
                    canvas = patterned_canvas()
                    parent = canvas.sample(1, 1)
                    siblings = {p: canvas.sample(1, 1, p) for p in CHILDREN}
                    canvas.paint(1, 1, CLEAR, erase=True, child=child, detail_policy=policy)
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.sample(1, 1, child), CLEAR)
                    for other in CHILDREN:
                        if other != child:
                            self.assertEqual(canvas.sample(1, 1, other), siblings[other])
                    canvas = reload_canvas(canvas)
                    canvas.collapse_cell(1, 1)
                    self.assertEqual(canvas.render().getpixel((1, 1)), parent)
                    canvas.split_cell(1, 1)
                    self.assertEqual(canvas.sample(1, 1, child), CLEAR)

    # {
    #   責務: [test_child_edit_without_finer_field_keeps_parent: より細かい保持フィールドがなくても子画素編集が親を保つことを検証する]
    #   処理: [空の細部フィールドでセルを分割して子を編集し、preserve/discard双方の親色と子色を確認する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、親画素または子画素が期待と異なればassertionで失敗する]
    # }
    def test_child_edit_without_finer_field_keeps_parent(self):
        for policy in ("preserve", "discard"):
            canvas = PixelCanvas(4)
            canvas.paint(1, 1, RED)
            canvas.split_cell(1, 1)
            canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            self.assertEqual(canvas.sample(1, 1), RED)
            self.assertEqual(canvas.sample(1, 1, (1, 1)), BLUE)

    # {
    #   責務: [test_child_edits_do_not_touch_spatial_exterior: 子画素編集が対象矩形外の任意解像度描画を変えないことを検証する]
    #   処理: [
    #     1: 編集前の73x61描画画像を保存する
    #     2: 対象子画素を編集し、変更後の描画画像を作る
    #     3: 有理座標で対象範囲外と判定された全画素を編集前と比較する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、対象範囲外に差があればassertionで失敗する]
    # }
    def test_child_edits_do_not_touch_spatial_exterior(self):
        for policy in ("preserve", "discard"):
            canvas = patterned_canvas()
            reference = canvas.render_resolution(73, 61)
            canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            result = canvas.render_resolution(73, 61)
            for y in range(61):
                for x in range(73):
                    px, py = Fraction(2*x+1, 146), Fraction(2*y+1, 122)
                    inside = Fraction(3, 8) <= px < Fraction(1, 2) and Fraction(1, 2) <= py < Fraction(2, 3)
                    if not inside:
                        self.assertEqual(result.getpixel((x, y)), reference.getpixel((x, y)))

    # {
    #   責務: [test_parent_preserve_still_keeps_independent_children: 親画素のpreserve編集後も独立した子画素と細部情報を保持することを検証する]
    #   処理: [
    #     1: 編集前の保持フィールドと4子画素を保存する
    #     2: 親画素を変更し、親・子画素・保持フィールドを照合する
    #     3: JSON往復と解像度変更後にも親子画素を確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、親編集が子画素や細部情報を変えればassertionで失敗する]
    # }
    def test_parent_preserve_still_keeps_independent_children(self):
        canvas = patterned_canvas()
        field = canvas.to_source()["retained_field"]
        children = [canvas.sample(1, 1, p) for p in CHILDREN]
        canvas.paint(1, 1, RED)
        self.assertEqual(canvas.sample(1, 1), RED)
        self.assertEqual([canvas.sample(1, 1, p) for p in CHILDREN], children)
        self.assertEqual(canvas.to_source()["retained_field"], field)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(23, 17)
        canvas.set_resolution(4, 3)
        self.assertEqual(canvas.sample(1, 1), RED)
        self.assertEqual([canvas.sample(1, 1, p) for p in CHILDREN], children)

    # {
    #   責務: [test_other_grid_coarse_edit_still_updates_retained_bases: 別グリッド上の粗い編集が保持ベース画素へ反映されることを検証する]
    #   処理: [
    #     1: 細分Canvasを2x1グリッドへ変更して基準画素を取得する
    #     2: その画素へ色差分を加え、元の4x3グリッドへ戻す
    #     3: 対象の親画素に差分が反映されたことを確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、保持ベースへの反映が異なればassertionで失敗する]
    # }
    def test_other_grid_coarse_edit_still_updates_retained_bases(self):
        canvas = patterned_canvas()
        parent = canvas.sample(1, 1)
        canvas.set_resolution(2, 1)
        anchor = canvas.sample(0, 0)
        replacement = tuple(v+5 if i < 3 else v for i, v in enumerate(anchor))
        canvas.paint(0, 0, replacement)
        canvas.set_resolution(4, 3)
        self.assertEqual(canvas.sample(1, 1), tuple(v+5 if i < 3 else v for i, v in enumerate(parent)))

    # {
    #   責務: [test_cross_grid_discard_detects_parent_only_detail: 別グリッド上の破棄が親メタデータだけの細部を検出し、対象外を保つことを検証する]
    #   処理: [
    #     1: 展開・折りたたみ両状態で対象外にも細部を持つCanvasを用意する
    #     2: 解像度変更後に対象細部を破棄し、対象外とUndo/Redo結果を照合する
    #     3: JSON往復後の元グリッドで対象セルが透明、対象外セルの色が保持されたことを確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、細部検出・局所性・履歴が期待と異なればassertionで失敗する]
    # }
    def test_cross_grid_discard_detects_parent_only_detail(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                canvas = metadata_canvas(expanded)
                canvas.split_cell(15, 15)
                canvas.paint(15, 15, BLUE)
                canvas.collapse_cell(15, 15)
                canvas.set_resolution(7)
                before = canvas.to_source()
                self.assertTrue(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.discard_detail(0, 0), 1)
                after = canvas.to_source()
                self.assertFalse(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.discard_detail(0, 0), 0)
                self.assertTrue(canvas.undo())
                self.assertEqual(canvas.to_source(), before)
                self.assertTrue(canvas.redo())
                self.assertEqual(canvas.to_source(), after)
                canvas = reload_canvas(canvas)
                canvas.set_resolution(16)
                self.assertEqual(canvas.sample(0, 0), CLEAR)
                self.assertFalse(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.sample(15, 15), BLUE)
                canvas.split_cell(0, 0)
                for child in CHILDREN:
                    self.assertEqual(canvas.sample(0, 0, child), CLEAR)

    # {
    #   責務: [test_cross_grid_same_color_discard_paint_is_not_noop: 色が同じでも別グリッド上の破棄指定が細部を削除することを検証する]
    #   処理: [親メタデータを持つセルを別解像度で同色discard編集し、初回だけ変更扱いとなり元グリッドで細部が消えることを確認する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、変更判定や破棄結果が期待と異なればassertionで失敗する]
    # }
    def test_cross_grid_same_color_discard_paint_is_not_noop(self):
        canvas = metadata_canvas()
        canvas.set_resolution(7)
        self.assertTrue(canvas.paint(0, 0, CLEAR, detail_policy="discard"))
        self.assertFalse(canvas.paint(0, 0, CLEAR, detail_policy="discard"))
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    # {
    #   責務: [test_cross_grid_same_color_discard_fill_is_not_noop: 同色fillでも別グリッド上のdiscard指定が細部を削除し、履歴に記録されることを検証する]
    #   処理: [
    #     1: 細部メタデータを持つCanvasを別解像度にし、透明色でdiscard fillする
    #     2: 初回の変更数・2回目のno-op・Undo/Redoを確認する
    #     3: 元グリッドへ戻し、親色と保持分割情報の破棄を確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、fill件数や履歴結果が期待と異なればassertionで失敗する]
    # }
    def test_cross_grid_same_color_discard_fill_is_not_noop(self):
        canvas = metadata_canvas()
        canvas.set_resolution(7)
        before = canvas.to_source()
        self.assertEqual(canvas.fill(0, 0, CLEAR, detail_policy="discard"), 1)
        self.assertEqual(canvas.fill(0, 0, CLEAR, detail_policy="discard"), 0)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    # {
    #   責務: [test_cross_grid_discard_removes_contained_unpainted_split: 別グリッドから領域に含まれる未描画分割も破棄することを検証する]
    #   処理: [未描画セルを分割して別解像度から細部破棄し、再読込・元解像度復帰後に分割記録がないことを確認する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、未描画分割が残ればassertionで失敗する]
    # }
    def test_cross_grid_discard_removes_contained_unpainted_split(self):
        canvas = PixelCanvas(16)
        canvas.split_cell(0, 0)
        canvas.set_resolution(7)
        self.assertEqual(canvas.discard_detail(0, 0), 1)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(16)
        self.assertFalse(canvas.is_split(0, 0))
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    # {
    #   責務: [test_partial_metadata_overlap_updates_only_included_base: 領域に含まれる親メタデータだけを破棄し、部分的に重なる対象外を保つことを検証する]
    #   処理: [
    #     1: 対象セル内に中心がある親細部と、中心が対象外にある分割セルを用意する
    #     2: 別解像度の対象セルで細部を破棄し、該当メタデータだけの変化を確認する
    #     3: JSON往復後に両セルの色を比較する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、対象外の親画素まで変化すればassertionで失敗する]
    # }
    def test_partial_metadata_overlap_updates_only_included_base(self):
        canvas = metadata_canvas(point=(2, 2))  # 中心は7x7上のセル(1,1)に含まれる。
        canvas.split_cell(1, 2)  # このセルの中心は対象セルの外側にある。
        canvas.paint(1, 2, BLUE)
        canvas.collapse_cell(1, 2)
        canvas.set_resolution(7)
        self.assertTrue(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 1)
        self.assertFalse(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 0)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(2, 2), CLEAR)
        self.assertEqual(canvas.sample(1, 2), BLUE)

    # {
    #   責務: [test_metadata_discard_uses_half_open_sample_bounds: 細部破棄の標本境界が半開区間として扱われることを検証する]
    #   処理: [
    #     1: 標本中心が境界座標に一致する親細部を作る
    #     2: 隣接セルごとの細部判定と破棄件数を確認する
    #     3: 元解像度で破棄後の親画素を照合する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、境界セルの包含判定が異なればassertionで失敗する]
    # }
    def test_metadata_discard_uses_half_open_sample_bounds(self):
        canvas = metadata_canvas(point=(1, 1), size=6)  # 標本中心が(1/4,1/4)に一致する。
        canvas.set_resolution(4)
        self.assertFalse(canvas.has_detail_at(0, 0))
        self.assertEqual(canvas.discard_detail(0, 0), 0)
        self.assertTrue(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 1)
        self.assertEqual(canvas.discard_detail(1, 1), 0)
        canvas.set_resolution(6)
        self.assertEqual(canvas.sample(1, 1), CLEAR)

    # {
    #   責務: [test_discard_across_split_grids_preserves_exact_exterior: 異なる分割グリッド間の細部破棄で領域外の描画を厳密に保持することを検証する]
    #   処理: [
    #     1: 子画素を編集して解像度を変更し、破棄前の高解像度画像を保存する
    #     2: 指定範囲の細部を破棄し、再読込後の各画素を有理座標で対象内外に分類する
    #     3: 対象内は粗い画像、対象外は基準画像と比較し、Undo/Redoも照合する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、領域内外の描画や履歴が期待と異なればassertionで失敗する]
    # }
    def test_discard_across_split_grids_preserves_exact_exterior(self):
        canvas = patterned_canvas()
        canvas.paint(1, 1, BLUE, child=(1, 1))
        canvas.set_resolution(7, 5)
        reference = canvas.render_resolution(73, 61)
        coarse = canvas.image
        before = canvas.to_source()
        canvas.discard_detail(1, 1, 2, 2)
        after = canvas.to_source()
        result = reload_canvas(canvas).render_resolution(73, 61)
        for y in range(61):
            for x in range(73):
                gx, gy = Fraction(2*x+1, 146)*7, Fraction(2*y+1, 122)*5
                inside = 1 <= gx < 3 and 1 <= gy < 3
                expected = coarse.getpixel((int(gx), int(gy))) if inside else reference.getpixel((x, y))
                self.assertEqual(result.getpixel((x, y)), expected)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)

    # {
    #   責務: [test_failed_child_write_preserves_state_history_and_redo: 子画素書き込み失敗時にCanvas・履歴・Redoを保持することを検証する]
    #   処理: [
    #     1: preserve/discardそれぞれでRedo可能なCanvas状態を準備する
    #     2: ResolutionFieldの保持処理を予算超過例外に差し替えて子画素編集する
    #     3: 例外後の保存表現・Undo/Redo履歴を比較し、Redo可能なことを確認する
    #   ]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、失敗時に状態や履歴が変化すればassertionで失敗する]
    # }
    def test_failed_child_write_preserves_state_history_and_redo(self):
        for policy, method in (("preserve", "shift"), ("discard", "replace")):
            canvas = patterned_canvas()
            canvas.paint(0, 0, RED)
            canvas.undo()
            before = canvas.to_source()
            history, future = list(canvas._history), list(canvas._future)
            with patch.object(ResolutionField, method, side_effect=ValueError("budget exceeded")):
                with self.assertRaises(ValueError):
                    canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            self.assertEqual(canvas.to_source(), before)
            self.assertEqual(canvas._history, history)
            self.assertEqual(canvas._future, future)
            self.assertTrue(canvas.redo())

    # {
    #   責務: [test_read_only_views_and_child_noop_keep_history: 読み取り用画像の変更と子画素no-opが保存状態・履歴を変えないことを検証する]
    #   処理: [全子画素への同色編集と公開画像の直接変更後に描画し、保存表現と履歴件数が維持されることを確認する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、読み取り操作で状態または履歴が変化すればassertionで失敗する]
    # }
    def test_read_only_views_and_child_noop_keep_history(self):
        canvas = patterned_canvas()
        before = canvas.to_source()
        history = len(canvas._history)
        for child in CHILDREN:
            self.assertFalse(canvas.paint(1, 1, canvas.sample(1, 1, child), child=child))
        canvas.image.putpixel((1, 1), RED)
        canvas.render()
        canvas.render_resolution(23, 17)
        self.assertEqual(canvas.to_source(), before)
        self.assertEqual(len(canvas._history), history)

    # {
    #   責務: [test_legacy_refinement_migration_roundtrip: 旧形式の子画素データを解像度往復後も維持することを検証する]
    #   処理: [展開状態の異なる旧形式を読み込み、解像度変更・JSON往復後に親子色と分割状態を比較する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、旧形式の移行結果が変化すればassertionで失敗する]
    # }
    def test_legacy_refinement_migration_roundtrip(self):
        for expanded in (False, True):
            cell = {"x": 0, "y": 0, "children": [["#FF0000", "#0000FF80"], [None, "#00FF00"]]}
            if not expanded:
                cell["expanded"] = False
            canvas = PixelCanvas.from_source({"canvas_size": 2,
                "pixels": [["#112233", None], [None, None]], "refined_cells": [cell]})
            before = canvas.to_source()
            canvas.set_resolution(7, 5)
            canvas = reload_canvas(canvas)
            canvas.set_resolution(2)
            self.assertEqual(canvas.to_source(), before)
            self.assertEqual(canvas.sample(0, 0), (17, 34, 51, 255))
            self.assertEqual(canvas.sample(0, 0, (1, 0)), (0, 0, 255, 128))
            self.assertEqual(canvas.is_split(0, 0), expanded)

    # {
    #   責務: [test_child_edit_layer_switch_save_load_and_png: レイヤー上の子画素編集が切替・保存・PNG出力後も維持されることを検証する]
    #   処理: [背景と人物レイヤーを編集し、履歴・合成・解像度変更・JSON保存読込・PNG画素を照合する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、レイヤー状態または出力画像が一致しなければassertionで失敗する]
    # }
    def test_child_edit_layer_switch_save_load_and_png(self):
        canvas = LayeredPixelCanvas(4, 3)
        canvas.fill(0, 0, (20, 30, 40, 255))
        background = canvas.active.to_source()
        canvas.add_layer("人物")
        canvas.layers["人物"] = patterned_canvas()
        parent = canvas.sample(1, 1)
        before = canvas.to_source()
        canvas.paint(1, 1, BLUE, child=(1, 1))
        self.assertEqual(canvas.sample(1, 1), parent)
        after = canvas.to_source()
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)
        rendered = canvas.composite()
        canvas.select_layer("背景")
        self.assertEqual(canvas.composite().tobytes(), rendered.tobytes())
        self.assertEqual(canvas.active.to_source(), background)
        canvas.set_resolution(7, 5)
        canvas.set_resolution(23, 17)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)/"project.json"
            project.write_text(json.dumps(canvas.to_source(), ensure_ascii=False), encoding="utf-8")
            restored = LayeredPixelCanvas.from_source(json.loads(project.read_text(encoding="utf-8")))
            restored.set_resolution(4, 3)
            restored.select_layer("人物")
            self.assertEqual(restored.sample(1, 1), parent)
            self.assertEqual(restored.sample(1, 1, (1, 1)), BLUE)
            self.assertEqual(restored.layers["背景"].to_source(), background)
            self.assertEqual(restored.composite().tobytes(), rendered.tobytes())
            path = Path(directory)/"result.png"
            restored.save_png(path)
            with Image.open(path) as image:
                self.assertEqual(image.size, rendered.size)
                self.assertEqual(image.tobytes(), rendered.tobytes())
            restored.paint(1, 1, CLEAR, erase=True, child=(1, 1), detail_policy="discard")
            self.assertEqual(restored.composite().getpixel((3, 3)), (20, 30, 40, 255))
            self.assertEqual(restored.sample(1, 1), parent)

    # {
    #   責務: [test_metadata_discard_is_layer_local_and_undoable: 細部破棄が選択レイヤーだけに作用しUndo/Redoできることを検証する]
    #   処理: [両レイヤーに親メタデータを用意し、片方だけを破棄して履歴・JSON往復後の各レイヤーを比較する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、対象外レイヤーまたは履歴状態が変化すればassertionで失敗する]
    # }
    def test_metadata_discard_is_layer_local_and_undoable(self):
        canvas = LayeredPixelCanvas(16)
        canvas.layers["背景"] = metadata_canvas()
        canvas.add_layer("人物")
        canvas.layers["人物"] = metadata_canvas()
        canvas.set_resolution(7)
        before = canvas.to_source()
        background = canvas.layers["背景"].to_source()
        self.assertEqual(canvas.discard_detail(0, 0), 1)
        self.assertEqual(canvas.layers["背景"].to_source(), background)
        after = canvas.to_source()
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)
        canvas = LayeredPixelCanvas.from_source(json.loads(json.dumps(canvas.to_source())))
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        canvas.select_layer("背景")
        self.assertEqual(canvas.sample(0, 0), RED)

    # {
    #   責務: [fake_editor: GUIを起動せずバックエンド編集テスト用PixelEditorを組み立てる]
    #   処理: [座標変換・履歴・表示更新をモックへ差し替え、描画領域サイズを初期化する]
    #   引数: [self: テスト対象のRefinementTestsケース、backend: 接続するPixelCanvasまたはLayeredPixelCanvas]
    #   戻り値: [テスト用のPixelEditorインスタンス]
    # }
    def fake_editor(self, backend):
        from dot_editor import PixelEditor
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = backend
        editor.num_pixels_x, editor.num_pixels_y = backend.resolution
        editor.canvas_width, editor.canvas_height = 640, 480
        editor.zoom_factor = 1.25
        editor.canvas = Mock()
        editor.canvas.canvasx.side_effect = lambda x: x + 60
        editor.canvas.canvasy.side_effect = lambda y: y + 40
        editor.history, editor.future = [], []
        editor.selected_cell = (1, 1)
        editor.tool = "brush"
        editor.current_color = (0, 0, 255)
        editor.current_detail_policy = lambda: "preserve"
        editor.create_grid = lambda: None
        editor.update_canvas = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.report_error = lambda error: self.fail(str(error))
        editor.update_canvas_size()
        return editor

    # {
    #   責務: [cli: テスト用CLIコマンドを実行し正常終了結果を返す]
    #   処理: [src/pixel_cli.pyをUTF-8・色なし・30秒制限で起動し、終了値と例外出力を検査する]
    #   引数: [self: テスト対象のRefinementTestsケース、arguments: CLIへ渡す引数列]
    #   戻り値: [標準出力・標準エラー・終了値を含むsubprocess.CompletedProcess]
    # }
    def cli(self, *arguments):
        root = Path(__file__).resolve().parents[1] / "src"
        result = subprocess.run(
            [sys.executable, str(root / "pixel_cli.py"), *map(str, arguments)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    # {
    #   責務: [test_gui_child_edit_recompose_history_and_cross_load: GUI経由の子画素編集と保存読込後の合成・履歴を検証する]
    #   処理: [両細部ポリシーでGUI編集し、Undo/Redo・折りたたみ・解像度往復・保存読込後の子画素と描画を照合する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、GUIバックエンドや再合成結果が期待と異なればassertionで失敗する]
    # }
    def test_gui_child_edit_recompose_history_and_cross_load(self):
        from pixel_cli import load_project
        for policy in ("preserve", "discard"):
            with self.subTest(policy=policy):
                layers = LayeredPixelCanvas(4, 3)
                layers.add_layer("人物")
                layers.layers["人物"] = patterned_canvas()
                parent = layers.sample(1, 1)
                editor = self.fake_editor(layers)
                editor.current_detail_policy = lambda: policy
                before = editor.backend.to_source()
                # ズームとパンを反映した右下子画素の中心座標を入力する。
                editor.paint_pixel(SimpleNamespace(x=290, y=310))
                self.assertEqual(editor.backend.sample(1, 1, (1, 1)), (0, 0, 255, 255))
                self.assertEqual(editor.backend.sample(1, 1), parent)
                after = editor.backend.to_source()
                self.assertEqual(len(editor.history), 1)
                editor.undo()
                self.assertEqual(editor.backend.to_source(), before)
                editor.redo()
                self.assertEqual(editor.backend.to_source(), after)
                editor.selected_cell = (1, 1)
                editor.current_detail_policy = lambda: "preserve"
                editor.collapse_selected_cell()
                self.assertEqual(editor.backend.sample(1, 1), parent)
                editor.resize_logical_canvas(7, 5)
                editor.resize_logical_canvas(23, 17)
                saved = editor.backend.to_source()
                with tempfile.TemporaryDirectory() as directory:
                    project = Path(directory) / "gui.json"
                    with patch("dot_editor.filedialog.asksaveasfilename", return_value=str(project)):
                        editor.save_project()
                    loaded = load_project(project)
                    self.assertEqual(loaded.to_source(), saved)
                    with patch("dot_editor.filedialog.askopenfilename", return_value=str(project)):
                        editor.load_project()
                    editor.resize_logical_canvas(4, 3)
                    editor.selected_cell = (1, 1)
                    editor.split_selected_cell()
                    self.assertEqual(editor.backend.sample(1, 1), parent)
                    self.assertEqual(editor.backend.sample(1, 1, (1, 1)), (0, 0, 255, 255))
                    editor.refresh_composite()
                    self.assertEqual(editor.image.getpixel((280, 280)), (0, 0, 255, 255))

    # {
    #   責務: [test_gui_cross_grid_discard_and_undo: GUIの別グリッド細部破棄が履歴に一度だけ記録されることを検証する]
    #   処理: [選択セルの細部を破棄し、再実行時のno-op・Undo/Redo・元解像度での結果を比較する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、GUIの破棄範囲または履歴が期待と異なればassertionで失敗する]
    # }
    def test_gui_cross_grid_discard_and_undo(self):
        layers = LayeredPixelCanvas(16)
        layers.layers["背景"] = metadata_canvas()
        editor = self.fake_editor(layers)
        editor.resize_logical_canvas(7)
        editor.selected_cell = (0, 0)
        before = editor.backend.to_source()
        history = len(editor.history)
        editor.discard_selected_detail()
        after = editor.backend.to_source()
        self.assertNotEqual(after, before)
        self.assertEqual(len(editor.history), history + 1)
        editor.discard_selected_detail()
        self.assertEqual(len(editor.history), history + 1)
        editor.undo()
        self.assertEqual(editor.backend.to_source(), before)
        editor.redo()
        self.assertEqual(editor.backend.to_source(), after)
        editor.resize_logical_canvas(16)
        self.assertEqual(editor.backend.sample(0, 0), CLEAR)

    # {
    #   責務: [test_cli_child_parent_and_png_survive_resolution_roundtrip: CLIの子画素編集が解像度往復・保存・PNG出力後も親子に保持されることを検証する]
    #   処理: [CLIで画像読込・分割・子画素編集・解像度変更・再分割を行い、JSON標本とPNG画素を照合する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、親子画素またはPNG出力が期待と異なればassertionで失敗する]
    # }
    def test_cli_child_parent_and_png_survive_resolution_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, source, output = root/"art.json", root/"source.png", root/"art.png"
            Image.new("RGBA", (16, 12), (80, 100, 120, 255)).save(source)
            self.cli("new", "--resolution", 16, 12, "--output", project)
            self.cli("edit", "--project", project, "--import-image", source)
            self.cli("edit", "--project", project, "--resolution", 4, 3, "--split", 1, 1)
            self.cli("edit", "--project", project, "--paint-child", 1, 1, 1, 1, "#0000FF")
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 1, 1).stdout)
            self.assertEqual(report["sample"]["rgba"], [80, 100, 120, 255])
            self.cli("edit", "--project", project, "--collapse", 1, 1)
            self.cli("edit", "--project", project, "--resolution", 7, 5)
            self.cli("edit", "--project", project, "--resolution", 23, 17)
            self.cli("edit", "--project", project, "--resolution", 4, 3, "--split", 1, 1)
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 1, 1).stdout)
            self.assertEqual(report["sample"]["rgba"], [80, 100, 120, 255])
            self.cli("export", "--project", project, "--output", output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (8, 6))
                self.assertEqual(image.getpixel((3, 3)), (0, 0, 255, 255))
                self.assertEqual(image.getpixel((2, 2)), (80, 100, 120, 255))

    # {
    #   責務: [test_cli_discard_does_not_resurrect_hidden_parent: CLIで親メタデータだけの細部を破棄しても再表示されないことを検証する]
    #   処理: [分割後に親だけを着色した領域を別解像度で破棄し、再実行のno-op・元解像度の対象内外を照合する]
    #   引数: [self: テスト対象のRefinementTestsケース]
    #   戻り値: [なし、破棄した親色が復活するか対象外画素が変わればassertionで失敗する]
    # }
    def test_cli_discard_does_not_resurrect_hidden_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)/"art.json"
            self.cli("new", "--size", 16, "--output", project)
            # 分割後に塗るため、赤色は親メタデータだけに存在する。
            self.cli("edit", "--project", project, "--split", 0, 0,
                     "--paint", 0, 0, "#FF0000", "--collapse", 0, 0)
            self.cli("edit", "--project", project, "--split", 15, 15,
                     "--paint", 15, 15, "#0000FF", "--collapse", 15, 15)
            self.cli("edit", "--project", project, "--resolution", 7, 7)
            self.cli("edit", "--project", project, "--discard-detail", 0, 0)
            before = project.read_bytes(), project.stat().st_mtime_ns
            self.cli("edit", "--project", project, "--discard-detail", 0, 0)
            self.assertEqual((project.read_bytes(), project.stat().st_mtime_ns), before)
            self.cli("edit", "--project", project, "--resolution", 16, 16)
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 0, 0).stdout)
            self.assertEqual(report["sample"]["rgba"], list(CLEAR))
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 15, 15).stdout)
            self.assertEqual(report["sample"]["rgba"], [0, 0, 255, 255])


if __name__ == "__main__":
    unittest.main()
