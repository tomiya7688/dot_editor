"""Issue #5: display dialogs preserve artwork; reset requires consent."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from dot_editor import PixelEditor
from pixel_layers import LayeredPixelCanvas


# {
#   責務: [DisplaySafetyTests: 画面サイズ変更とリセット確認が作品の状態を保護することを検証する]
#   フィールド: [self.editor: 各テストが操作するモック付きレイヤーエディター]
#   処理: [サイズ変更の取消・確定とリセット確認の拒否・承認を独立して検証する]
# }
class DisplaySafetyTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各ダイアログ検証用に細部と非表示レイヤーを持つエディターを準備する]
    #   処理: [
    #     1: モック付きエディターにレイヤー・分割セル・履歴・表示寸法を設定する
    #     2: 表示寸法を計算し、テスト対象をself.editorへ保存する
    #   ]
    #   引数: [self: unittestが初期化する各テストケース]
    #   戻り値: [なし、各テストで使うエディターを設定する]
    # }
    def setUp(self):
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = LayeredPixelCanvas(4, 3)
        editor.backend.add_layer("人物")
        editor.backend.split_cell(1, 1)
        editor.backend.paint(1, 1, (255, 0, 0, 255), child=(1, 0))
        editor.backend.set_layer_visibility(False, "背景")
        editor.num_pixels_x, editor.num_pixels_y = editor.backend.resolution
        editor.canvas_width, editor.canvas_height = 640, 480
        editor.zoom_factor = 1.0
        editor.canvas = Mock()
        editor.history, editor.future = [], []
        editor.selected_cell = (1, 1)
        editor.create_grid = Mock()
        editor.update_canvas = Mock()
        editor.refresh_layer_list = Mock()
        editor.update_canvas_size()
        self.editor = editor

    # {
    #   責務: [test_resize_dialog_preserves_layers_detail_and_undo_redo: 表示サイズ変更が文書と編集履歴を変えないことを検証する]
    #   処理: [
    #     1: Undo可能な編集を作って変更前後の文書と履歴を保存する
    #     2: 表示サイズダイアログを確定しCanvas・履歴・画面寸法を照合する
    #     3: RedoとUndoの結果が元の文書を維持することを確かめる
    #   ]
    #   引数: [self: テスト対象のDisplaySafetyTestsケース]
    #   戻り値: [なし、期待する状態が違えばassertionで失敗する]
    # }
    def test_resize_dialog_preserves_layers_detail_and_undo_redo(self):
        editor = self.editor
        before_edit = editor.backend.to_source()
        editor.perform_edit(editor.commands.paint, 0, 0, (0, 0, 255, 255))
        after_edit = editor.backend.to_source()
        editor.undo()
        backend = editor.backend
        history, future = deepcopy(editor.history), deepcopy(editor.future)
        with patch("dot_editor.simpledialog.askinteger", side_effect=[800, 300]):
            editor.change_canvas_size()
        self.assertIs(editor.backend, backend)
        self.assertEqual(editor.backend.to_source(), before_edit)
        self.assertEqual((editor.history, editor.future), (history, future))
        self.assertEqual((editor.canvas_width, editor.canvas_height), (800, 300))
        editor.redo()
        self.assertEqual(editor.backend.to_source(), after_edit)
        editor.undo()
        self.assertEqual(editor.backend.to_source(), before_edit)
        self.assertEqual((editor.canvas_width, editor.canvas_height), (800, 300))

    # {
    #   責務: [test_cancel_either_dimension_does_not_resize_or_mutate: 片方の寸法入力を取消しても作品を変更しないことを検証する]
    #   処理: [
    #     1: 文書とUndo・Redo履歴の基準状態を保存する
    #     2: 幅入力と高さ入力のそれぞれでダイアログを取消する
    #     3: 表示寸法・文書・両履歴が基準状態のままか比較する
    #   ]
    #   引数: [self: テスト対象のDisplaySafetyTestsケース]
    #   戻り値: [なし、状態が変化すればassertionで失敗する]
    # }
    def test_cancel_either_dimension_does_not_resize_or_mutate(self):
        editor = self.editor
        before = editor.backend.to_source()
        editor.history.append(editor.make_snapshot())
        editor.future.append(editor.make_snapshot())
        histories = deepcopy((editor.history, editor.future))
        for answers in ([None], [800, None]):
            with self.subTest(answers=answers):
                with patch("dot_editor.simpledialog.askinteger", side_effect=answers):
                    editor.change_canvas_size()
                self.assertEqual((editor.canvas_width, editor.canvas_height), (640, 480))
                self.assertEqual(editor.backend.to_source(), before)
                self.assertEqual((editor.history, editor.future), histories)

    # {
    #   責務: [test_reset_cancel_keeps_document_selection_and_history: リセット拒否が文書・選択・履歴を保持することを検証する]
    #   処理: [
    #     1: 確認前のCanvas・選択・Undo・Redoを保存する
    #     2: リセット確認で拒否を返し、既定ボタンが「いいえ」か確認する
    #     3: 元のCanvas・選択・両履歴が維持されたか照合する
    #   ]
    #   引数: [self: テスト対象のDisplaySafetyTestsケース]
    #   戻り値: [なし、確認設定や状態が違えばassertionで失敗する]
    # }
    def test_reset_cancel_keeps_document_selection_and_history(self):
        editor = self.editor
        backend = editor.backend
        before = backend.to_source()
        editor.history.append(editor.make_snapshot())
        editor.future.append(editor.make_snapshot())
        histories = deepcopy((editor.history, editor.future))
        with patch("dot_editor.messagebox.askyesno", return_value=False) as confirm:
            editor.reset_canvas()
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        self.assertIs(editor.backend, backend)
        self.assertEqual(editor.backend.to_source(), before)
        self.assertEqual((editor.history, editor.future), histories)
        self.assertEqual(editor.selected_cell, (1, 1))

    # {
    #   責務: [test_confirmed_reset_clears_document_and_history_not_geometry: リセット承認が作品と履歴を消し表示寸法を保つことを検証する]
    #   処理: [
    #     1: Undo・Redo履歴を用意して確認ダイアログを承認する
    #     2: Canvas・選択・両履歴が初期状態になることを照合する
    #     3: 表示領域の幅と高さが維持されたことを確認する
    #   ]
    #   引数: [self: テスト対象のDisplaySafetyTestsケース]
    #   戻り値: [なし、期待するリセット結果が違えばassertionで失敗する]
    # }
    def test_confirmed_reset_clears_document_and_history_not_geometry(self):
        editor = self.editor
        editor.history.append(editor.make_snapshot())
        editor.future.append(editor.make_snapshot())
        with patch("dot_editor.messagebox.askyesno", return_value=True):
            editor.reset_canvas()
        self.assertEqual(editor.backend.to_source(), LayeredPixelCanvas(4, 3).to_source())
        self.assertEqual((editor.history, editor.future), ([], []))
        self.assertIsNone(editor.selected_cell)
        self.assertEqual((editor.canvas_width, editor.canvas_height), (640, 480))


if __name__ == "__main__":
    unittest.main()
