"""領域分割の履歴単位・失敗時の原子性・保持色を検証する。"""
import unittest
from unittest.mock import patch

from pixel_backend import PixelCanvas
from pixel_commands import PixelCommandAPI

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


# {
#   責務: [RegionSplitTests: 単一・レイヤー作品の直接操作と共有APIで領域分割の契約を検証する]
#   フィールド: []
# }
class RegionSplitTests(unittest.TestCase):
    # {
    #   責務: [split_region: 指定経路でテスト対象の領域分割を実行する]
    #   処理: [共有API経由か作品モデルの直接呼び出しかを選んで結果を返す]
    #   引数: [self: テストケース, api: 対象作品のAPI, via_api: 共有APIを使うか, region: 領域の4引数]
    #   戻り値: [新たに分割されたセル数]
    # }
    def split_region(self, api, via_api, region):
        # どちらの公開入口でも同じ原子性を要求する。
        target = api if via_api else api.canvas
        return target.split_region(*region)

    # {
    #   責務: [assert_future_preserved: 失敗・変更なしの操作後に既存RedoとUndoが残ることを確認する]
    #   処理: [保存表現を比較し、既存の描画をRedoしてからUndoし元状態へ戻す]
    #   引数: [self: テストケース, api: Redo可能な作品, before: 操作前の保存表現]
    #   戻り値: [なし、画像や履歴が変わっていればテスト失敗]
    # }
    def assert_future_preserved(self, api, before):
        self.assertEqual(api.canvas.to_source(), before)
        # 履歴配列の内部形式ではなく、利用者が使うUndo/Redoの結果を比較する。
        self.assertTrue(api.canvas.redo())
        self.assertEqual(api.sample(3, 2), BLUE)
        self.assertTrue(api.canvas.undo())
        self.assertEqual(api.canvas.to_source(), before)

    # {
    #   責務: [test_rectangle_is_one_undoable_operation: 長方形領域の全セルを1回でUndo・Redoできることを確認する]
    #   処理: [各作品と入口で2x2領域を分割し、変更数とUndo前後の保存表現を比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、一部のセルだけ戻る場合はテスト失敗]
    # }
    def test_rectangle_is_one_undoable_operation(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.paint(1, 0, RED)
                    before = api.canvas.to_source()
                    self.assertEqual(self.split_region(api, via_api, (1, 0, 2, 2)), 4)
                    after = api.canvas.to_source()
                    for y in range(2):
                        for x in range(1, 3):
                            self.assertTrue(api.is_split(x, y))
                    # 最後の1セルだけでなく、領域全体が一度に戻る必要がある。
                    self.assertTrue(api.canvas.undo())
                    self.assertEqual(api.canvas.to_source(), before)
                    self.assertTrue(api.canvas.redo())
                    self.assertEqual(api.canvas.to_source(), after)

    # {
    #   責務: [test_budget_failure_does_not_publish_candidate: 候補の構築途中で分割上限を超えても部分更新しないことを確認する]
    #   処理: [既存1セルと上限2を用意し、2セル追加の失敗後に画像とRedoを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、先に処理したセルや履歴が変更されればテスト失敗]
    # }
    def test_budget_failure_does_not_publish_candidate(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.split(0, 0)
                    api.paint(3, 2, BLUE)
                    api.canvas.undo()
                    before = api.canvas.to_source()
                    # 先頭の候補は予算内、次の候補で上限を超える設定にする。
                    with patch.object(PixelCanvas, "MAX_SPLITS", 2):
                        with self.assertRaisesRegex(ValueError, "too many"):
                            self.split_region(api, via_api, (1, 0, 2, 1))
                    self.assert_future_preserved(api, before)

    # {
    #   責務: [test_sampling_failure_does_not_publish_candidate: 色の参照が途中で失敗しても候補と履歴を公開しないことを確認する]
    #   処理: [2セル目の色参照で例外を発生させ、保存表現と既存Redoを比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、途中まで分割が残ればテスト失敗]
    # }
    def test_sampling_failure_does_not_publish_candidate(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.paint(3, 2, BLUE)
                    api.canvas.undo()
                    before = api.canvas.to_source()
                    target = api.canvas.active if layered else api.canvas
                    # 実際の参照処理が失敗する境界を模擬し、成功した候補1件を残さない。
                    with patch.object(target, "sample", side_effect=[RED, RuntimeError("sample failed")]):
                        with self.assertRaisesRegex(RuntimeError, "sample failed"):
                            self.split_region(api, via_api, (0, 0, 2, 1))
                    self.assert_future_preserved(api, before)

    # {
    #   責務: [test_expanded_region_is_noop_and_keeps_redo: 展開済み領域を再分割しても履歴を増やさないことを確認する]
    #   処理: [展開済み領域とRedoを用意し、変更数0と既存履歴の保持を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、Redoが失われたり分割が変更されればテスト失敗]
    # }
    def test_expanded_region_is_noop_and_keeps_redo(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.split(0, 0)
                    api.split(1, 0)
                    api.paint(3, 2, BLUE)
                    api.canvas.undo()
                    before = api.canvas.to_source()
                    self.assertEqual(self.split_region(api, via_api, (0, 0, 2, 1)), 0)
                    self.assert_future_preserved(api, before)

    # {
    #   責務: [test_collapsed_cell_reuses_budget_and_preserves_colors: 折りたたみセルの再展開で親色・子色と予算を再利用することを確認する]
    #   処理: [異なる親子色を保持したセルを折りたたみ、予算上限のまま再展開して色とUndoを比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、既存記録の二重計上や色の消失があればテスト失敗]
    # }
    def test_collapsed_cell_reuses_budget_and_preserves_colors(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.split(0, 0)
                    api.paint(0, 0, BLUE, child=(1, 1))
                    api.paint(0, 0, RED)
                    api.collapse(0, 0)
                    before = api.canvas.to_source()
                    # 再展開は新規の保持記録を増やさないので、上限到達時にも成功する。
                    with patch.object(PixelCanvas, "MAX_SPLITS", 1):
                        self.assertEqual(self.split_region(api, via_api, (0, 0, 1, 1)), 1)
                    self.assertEqual(api.sample(0, 0), RED)
                    self.assertEqual(api.sample(0, 0, child=(1, 1)), BLUE)
                    self.assertTrue(api.canvas.undo())
                    self.assertEqual(api.canvas.to_source(), before)

    # {
    #   責務: [test_invalid_region_preserves_state_and_future: 型・寸法・境界が不正な領域で編集や履歴更新を行わないことを確認する]
    #   処理: [各入口に不正領域を渡し、ValueErrorと保存表現・Redoの保持を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不正領域が受理されればテスト失敗]
    # }
    def test_invalid_region_preserves_state_and_future(self):
        regions = (
            (True, 0, 1, 1), (0, 0.5, 1, 1), (0, 0, "1", 1),
            (0, 0, 1, False), (0, 0, 0, 1), (0, 0, 1, -1),
            (-1, 0, 1, 1), (0, -1, 1, 1), (3, 0, 2, 1), (0, 2, 1, 2),
        )
        for layered in (False, True):
            for via_api in (False, True):
                for region in regions:
                    with self.subTest(layered=layered, via_api=via_api, region=region):
                        api = PixelCommandAPI.new(4, 3, layered=layered)
                        api.paint(3, 2, BLUE)
                        api.canvas.undo()
                        before = api.canvas.to_source()
                        with self.assertRaises(ValueError):
                            self.split_region(api, via_api, region)
                        self.assert_future_preserved(api, before)

    # {
    #   責務: [test_only_active_layer_is_split: 領域分割が非選択レイヤーと作品の選択・可視状態を変更しないことを確認する]
    #   処理: [別レイヤーを追加して領域分割し、非選択層・表示状態・作品単位のUndoを比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、他レイヤーが変化した場合はテスト失敗]
    # }
    def test_only_active_layer_is_split(self):
        api = PixelCommandAPI.new(4, 3, layered=True)
        background = api.canvas.active_layer
        api.paint(0, 0, BLUE)
        api.add_layer("foreground")
        api.set_layer_visibility(False)
        before = api.canvas.to_source()
        unchanged = api.canvas.layers[background].to_source()
        # 非表示の選択層も編集できるが、背景の画素・分割記録は変更しない。
        self.assertEqual(api.split_region(0, 0, 2, 2), 4)
        self.assertEqual(api.canvas.layers[background].to_source(), unchanged)
        self.assertEqual(api.canvas.active_layer, "foreground")
        self.assertFalse(api.canvas.is_layer_visible())
        self.assertTrue(api.canvas.undo())
        self.assertEqual(api.canvas.to_source(), before)

    # {
    #   責務: [test_mixed_region_counts_only_new_expansions: 展開済み・折りたたみ済み・未記録セルが混在しても変更数と予算が正しいことを確認する]
    #   処理: [3種類のセルを含む領域を保持上限内で分割し、変更数2と全セルの展開状態を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、展開済みセルや再利用記録を二重計上すればテスト失敗]
    # }
    def test_mixed_region_counts_only_new_expansions(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.split(0, 0)
                    api.split(1, 0)
                    api.collapse(1, 0)
                    # 記録2件から3件への増加であり、再展開は追加予算を消費しない。
                    with patch.object(PixelCanvas, "MAX_SPLITS", 3):
                        self.assertEqual(self.split_region(api, via_api, (0, 0, 3, 1)), 2)
                    for x in range(3):
                        self.assertTrue(api.is_split(x, 0))

    # {
    #   責務: [test_child_render_budget_is_checked_before_editing: 分割後の描画予算を超える操作を編集開始前に拒否することを確認する]
    #   処理: [分割後の画素数だけが上限超過する予算を設定し、例外後の画像とRedoを比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、描画予算超過の操作が適用されればテスト失敗]
    # }
    def test_child_render_budget_is_checked_before_editing(self):
        for layered in (False, True):
            for via_api in (False, True):
                with self.subTest(layered=layered, via_api=via_api):
                    api = PixelCommandAPI.new(4, 3, layered=layered)
                    api.paint(3, 2, BLUE)
                    api.canvas.undo()
                    before = api.canvas.to_source()
                    # 現在の12画素は有効だが、分割後の48画素は上限を超える。
                    with patch("resolution_field.MAX_PIXELS", 47):
                        with self.assertRaises(ValueError):
                            self.split_region(api, via_api, (0, 0, 1, 1))
                    self.assert_future_preserved(api, before)
