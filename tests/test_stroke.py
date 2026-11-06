"""Check stroke interpolation and session state."""

import unittest

from stroke import StrokeSession, line_cells


# {
#   責務: [StrokeTests: ストロークの補間と状態遷移の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class StrokeTests(unittest.TestCase):
    # {
    #   責務: [test_line_cells_has_no_gaps: 直線補間が連続し端点を含むことを検証する]
    #   処理: [1: 水平・斜め・急な線を補間する 2: 隣り合うセルの差が1以下であることを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_line_cells_has_no_gaps(self):
        for start, end in (((0, 0), (5, 0)), ((0, 0), (4, 4)), ((2, 7), (3, 0)), ((6, 1), (0, 3))):
            cells = line_cells(start, end)
            self.assertEqual((cells[0], cells[-1]), (start, end))
            for a, b in zip(cells, cells[1:]):
                self.assertLessEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 1)
        self.assertEqual(line_cells((3, 3), (3, 3)), [(3, 3)])

    # {
    #   責務: [test_session_lifecycle: 開始・延長・終了と取消の動作を検証する]
    #   処理: [
    #     1: 開始時は現在のセルだけを返すことを確認する
    #     2: 延長は前のセルを除いた補間を返し、同じセルでは何も返さないことを確認する
    #     3: 終了後や開始前の延長は何も描かないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_session_lifecycle(self):
        session = StrokeSession()
        self.assertEqual(session.extend((1, 1)), [])
        self.assertEqual(session.begin((0, 0)), [(0, 0)])
        self.assertEqual(session.extend((0, 0)), [])
        self.assertEqual(session.extend((3, 0)), [(1, 0), (2, 0), (3, 0)])
        self.assertTrue(session.end())
        self.assertFalse(session.end())
        self.assertEqual(session.extend((4, 0)), [])


if __name__ == "__main__":
    unittest.main()
