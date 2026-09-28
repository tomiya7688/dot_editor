"""Issue #5: display dialogs preserve artwork; reset requires consent."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from dot_editor import PixelEditor
from pixel_layers import LayeredPixelCanvas


class DisplaySafetyTests(unittest.TestCase):
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
