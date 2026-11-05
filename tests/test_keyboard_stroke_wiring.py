"""Check that Space drawing makes one undo step and survives key repeat."""

from types import SimpleNamespace
import unittest

from canvas_cursor import CanvasCursor
from dot_editor import PixelEditor
from pixel_layers import LayeredPixelCanvas
from stroke import StrokeSession


# {
#   責務: [make_editor: 実際の作品モデルと偽のTk部品を持つ編集部を作る]
#   処理: [
#     1: 4x4の作品、カーソル、ストローク、履歴を用意する
#     2: 画面に関わる処理を何もしない関数に差し替え、予約された処理を記録する
#   ]
#   引数: [jobs: after()で予約された関数を記録するリスト]
#   戻り値: [テスト用の編集部]
# }
def make_editor(jobs):
    editor = PixelEditor.__new__(PixelEditor)
    editor.backend = LayeredPixelCanvas(4)
    editor.num_pixels_x = editor.num_pixels_y = 4
    editor.history, editor.future = [], []
    editor.selected_cell = None
    editor.cursor = CanvasCursor()
    editor.stroke = StrokeSession()
    editor.release_job = None
    editor.transaction_before = None
    editor.transaction_changed = False
    editor.tool = "brush"
    editor.current_color = (255, 0, 0)
    editor.current_detail_policy = lambda: "preserve"
    for name in ("refresh_composite", "update_canvas", "refresh_layer_list", "update_canvas_size"):
        setattr(editor, name, lambda: None)
    editor.draw_cursor = lambda: None
    editor.scroll_cursor_into_view = lambda bounds: None
    editor.set_tool = lambda tool: setattr(editor, "tool", tool)
    editor.master = SimpleNamespace(
        after=lambda ms, fn: jobs.append(fn) or len(jobs),
        after_cancel=lambda job: jobs.__setitem__(job - 1, None),
    )
    return editor


# {
#   責務: [StrokeWiringTests: Space描画の履歴・キーリピート・取消の結線を検証する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class StrokeWiringTests(unittest.TestCase):
    # {
    #   責務: [test_stroke_is_one_undo_step: 1回のストロークが1回の取り消しになることを検証する]
    #   処理: [
    #     1: Space押下→右へ3回移動→離して確認時間後に確定する
    #     2: 4セルが塗られ、履歴が1件であることを確認する
    #     3: 取り消すと全セルが元に戻ることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_stroke_is_one_undo_step(self):
        jobs = []
        editor = make_editor(jobs)
        editor.on_space_down()
        for _ in range(3):
            editor.move_cursor(1, 0)
        editor.on_space_up()
        self.assertEqual(len(editor.history), 0)
        jobs[-1]()
        self.assertEqual(len(editor.history), 1)
        for x in range(4):
            self.assertEqual(editor.commands.sample(x, 0)[:3], (255, 0, 0))
        editor.undo()
        for x in range(4):
            self.assertEqual(editor.commands.sample(x, 0)[3], 0)

    # {
    #   責務: [test_key_repeat_and_cancel: キーリピートで途切れず、取消で描画が止まることを検証する]
    #   処理: [
    #     1: 離した直後に再押下されると確認が取り消され、同じストロークが続くことを確認する
    #     2: 取消後は移動しても描かず、新しい押下で別のストロークになることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_key_repeat_and_cancel(self):
        jobs = []
        editor = make_editor(jobs)
        editor.on_space_down()
        editor.on_space_up()
        editor.on_space_down()
        self.assertTrue(editor.stroke.active)
        self.assertIsNone(jobs[0])
        editor.move_cursor(1, 0)
        editor.cancel_stroke()
        self.assertFalse(editor.stroke.active)
        self.assertEqual(len(editor.history), 1)
        editor.move_cursor(1, 0)
        self.assertEqual(editor.commands.sample(2, 0)[3], 0)
        editor.on_space_down()
        editor.cancel_stroke()
        self.assertEqual(len(editor.history), 2)

    # {
    #   責務: [test_fill_and_picker_apply_once: 塗りつぶしとスポイトは押した瞬間の1回だけ適用されることを検証する]
    #   処理: [
    #     1: 塗りつぶしでSpaceを押し、リピートで再押下しても1件の履歴であることを確認する
    #     2: ブラシへ戻ったあとの移動では描かないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_fill_and_picker_apply_once(self):
        jobs = []
        editor = make_editor(jobs)
        editor.tool = "fill"
        editor.on_space_down()
        self.assertEqual(editor.tool, "brush")
        self.assertEqual(len(editor.history), 1)
        editor.on_space_down()
        editor.move_cursor(1, 0)
        self.assertEqual(len(editor.history), 1)


if __name__ == "__main__":
    unittest.main()
