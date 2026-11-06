"""Check that one mouse drag is one undo step (fake canvas, no GUI)."""

from types import SimpleNamespace
import unittest

from dot_editor import PixelEditor
from pixel_layers import LayeredPixelCanvas


# {
#   責務: [make_editor: マウス操作の検査用に、実際の作品モデルと偽の部品を持つ編集部を作る]
#   処理: [
#     1: 4x4の作品と履歴を用意し、画面に関わる処理を何もしない関数に差し替える
#     2: paint_pixelは、イベントのxの位置の画素を赤く塗る編集に置き換える
#   ]
#   引数: []
#   戻り値: [編集部]
# }
def make_editor():
    editor = PixelEditor.__new__(PixelEditor)
    editor.backend = LayeredPixelCanvas(4)
    editor.num_pixels_x = editor.num_pixels_y = 4
    editor.history, editor.future = [], []
    editor.selected_cell = None
    editor.tool = "brush"
    editor.transaction_before = None
    editor.transaction_changed = False
    editor.canvas = SimpleNamespace(focus_set=lambda: None)
    for name in ("refresh_composite", "update_canvas", "refresh_layer_list", "update_canvas_size"):
        setattr(editor, name, lambda: None)
    editor.paint_pixel = lambda event: editor.perform_edit(
        editor.commands.paint, event.x, 0, (255, 0, 0, 255)
    )
    return editor


# {
#   責務: [MouseStrokeTests: マウスのドラッグが1回の取り消しになることの回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class MouseStrokeTests(unittest.TestCase):
    # {
    #   責務: [test_one_drag_is_one_undo_step: 押してから離すまでのドラッグが1件の履歴になることを検証する]
    #   処理: [
    #     1: 押して3か所を塗り、離す前は履歴が増えていないことを確認する
    #     2: 離すと履歴が1件になり、1回の取り消しで3か所とも消えることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_one_drag_is_one_undo_step(self):
        editor = make_editor()
        editor.on_canvas_press(SimpleNamespace(x=0))
        editor.paint_pixel(SimpleNamespace(x=1))
        editor.paint_pixel(SimpleNamespace(x=2))
        self.assertEqual(len(editor.history), 0)
        editor.on_canvas_release()
        self.assertEqual(len(editor.history), 1)
        for x in range(3):
            self.assertEqual(editor.commands.sample(x, 0)[3], 255)
        editor.undo()
        for x in range(3):
            self.assertEqual(editor.commands.sample(x, 0)[3], 0)

    # {
    #   責務: [test_fill_click_and_missed_release: 塗りつぶしの1回クリックと、離し損ねた後の次の押下を検証する]
    #   処理: [
    #     1: 塗りつぶしは、押しただけでは取り消しのまとまりを作らず、通常の1編集として履歴に入ることを確認する
    #     2: ブラシで離しを取りこぼしても、次の押下で前のドラッグが確定し、次のドラッグと混ざらないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_fill_click_and_missed_release(self):
        editor = make_editor()
        editor.tool = "fill"
        editor.on_canvas_press(SimpleNamespace(x=0))
        self.assertIsNone(editor.transaction_before)
        self.assertEqual(len(editor.history), 1)
        editor.tool = "brush"
        editor.on_canvas_press(SimpleNamespace(x=1))
        editor.paint_pixel(SimpleNamespace(x=2))
        editor.on_canvas_press(SimpleNamespace(x=3))
        self.assertEqual(len(editor.history), 2)
        editor.on_canvas_release()
        self.assertEqual(len(editor.history), 3)


if __name__ == "__main__":
    unittest.main()
