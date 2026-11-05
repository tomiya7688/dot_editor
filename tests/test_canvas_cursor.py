"""Check the pure keyboard cursor logic and geometry helpers."""

import unittest

from canvas_cursor import CanvasCursor, cell_bounds, scroll_offset


# {
#   責務: [CanvasCursorTests: セルカーソルの移動・子セル・補正・幾何の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class CanvasCursorTests(unittest.TestCase):
    # {
    #   責務: [test_corners_stop_without_wrapping: 四隅で止まり回り込まないことを検証する]
    #   処理: [1: 非正方形の四隅から外向きに動かす 2: 位置が変わらず偽が返ることを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_corners_stop_without_wrapping(self):
        cursor = CanvasCursor(0, 0)
        self.assertFalse(cursor.move(-1, 0, 5, 3))
        self.assertFalse(cursor.move(0, -1, 5, 3))
        cursor.place(4, 2)
        self.assertFalse(cursor.move(1, 0, 5, 3))
        self.assertFalse(cursor.move(0, 1, 5, 3))
        self.assertEqual((cursor.x, cursor.y), (4, 2))
        self.assertTrue(cursor.move(-1, 0, 5, 3))
        self.assertEqual((cursor.x, cursor.y), (3, 2))

    # {
    #   責務: [test_child_mode_moves_inside_then_exits: 子セルのモードの移動と脱出を検証する]
    #   処理: [
    #     1: 分割済みセルで入り、2x2の中を動くことを確認する
    #     2: 端を越えると隣の親セルへ移りモードが解除されることを確認する
    #     3: 分割されていないセルには入れないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_child_mode_moves_inside_then_exits(self):
        cursor = CanvasCursor(1, 1)
        self.assertFalse(cursor.enter_child(lambda x, y: False))
        self.assertTrue(cursor.enter_child(lambda x, y: (x, y) == (1, 1)))
        self.assertEqual(cursor.child, (0, 0))
        self.assertTrue(cursor.move(1, 0, 4, 4))
        self.assertEqual((cursor.x, cursor.child), (1, (1, 0)))
        self.assertTrue(cursor.move(1, 0, 4, 4))
        self.assertEqual((cursor.x, cursor.y, cursor.child), (2, 1, None))
        cursor.place(1, 1)
        cursor.enter_child(lambda x, y: True)
        self.assertTrue(cursor.leave_child())
        self.assertFalse(cursor.leave_child())
        self.assertEqual((cursor.x, cursor.y, cursor.child), (1, 1, None))

    # {
    #   責務: [test_clamp_after_resolution_or_detail_change: 解像度や分割の変化後の補正を検証する]
    #   処理: [
    #     1: 解像度が小さくなると座標が範囲内に戻ることを確認する
    #     2: 親セルが分割済みでなくなると子セルのモードが解除されることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_clamp_after_resolution_or_detail_change(self):
        cursor = CanvasCursor(7, 6)
        cursor.child = (1, 1)
        cursor.clamp(3, 2, lambda x, y: True)
        self.assertEqual((cursor.x, cursor.y, cursor.child), (2, 1, (1, 1)))
        cursor.clamp(3, 2, lambda x, y: False)
        self.assertIsNone(cursor.child)

    # {
    #   責務: [test_cell_bounds_and_scroll_offset: 外枠の計算と表示への追従量を検証する]
    #   処理: [
    #     1: 非正方形の画像でセルと子セルの外枠を確認する
    #     2: 表示内では動かさず、はみ出す側へ最小量だけ動かすことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_cell_bounds_and_scroll_offset(self):
        self.assertEqual(cell_bounds((10, 20), (40, 20), (4, 2), 1, 1), (20, 30, 30, 40))
        self.assertEqual(cell_bounds((10, 20), (40, 20), (4, 2), 1, 1, (1, 0)), (25, 30, 30, 35))
        self.assertIsNone(scroll_offset(10, 20, 0, 100))
        self.assertEqual(scroll_offset(120, 130, 0, 100), 30)
        self.assertEqual(scroll_offset(-5, 5, 0, 100), -5)
        self.assertEqual(scroll_offset(0, 300, 50, 150), 0)


if __name__ == "__main__":
    unittest.main()
