"""Headless checks for keyboard movement between the canvas and sidebar."""
import unittest
from unittest.mock import Mock

from dot_editor import PixelEditor


class FakeRoot:
    def __init__(self, master=None):
        self.master = master
        self.is_toplevel = True
        self.focused = None
        self.bindings = {}

    def focus_get(self):
        return self.focused

    def after_idle(self, callback):
        callback()

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)


class FakeWidget:
    def __init__(self, master=None, state="normal", exists=True, class_name="Button"):
        self.master = master
        self.state = state
        self.exists = exists
        self.class_name = class_name
        self.focus_count = 0
        self.configured = {}
        self.bindings = {}

    def focus_set(self):
        self.focus_count += 1
        root = self
        while getattr(root, "master", None) is not None:
            root = root.master
        root.focused = self

    def cget(self, name):
        if name == "state":
            return self.state
        raise KeyError(name)

    def winfo_exists(self):
        return self.exists

    def winfo_class(self):
        return self.class_name

    def winfo_toplevel(self):
        widget = self
        while widget is not None and not getattr(widget, "is_toplevel", False):
            widget = getattr(widget, "master", None)
        return widget

    def configure(self, **options):
        self.configured.update(options)

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)


class FakeViewport:
    def __init__(self, root_y=100, height=100, scroll_offset=0):
        self.root_y = root_y
        self.height = height
        self.scroll_offset = scroll_offset
        self.scroll_to = None

    def bbox(self, _tag):
        return (0, 0, 240, 500)

    def winfo_rooty(self):
        return self.root_y

    def winfo_height(self):
        return self.height

    def canvasy(self, y):
        return y + self.scroll_offset

    def yview_moveto(self, fraction):
        self.scroll_to = fraction


class FocusableGeometry(FakeWidget):
    def __init__(self, root_y, height=20):
        super().__init__()
        self.root_y = root_y
        self.height = height

    def winfo_rooty(self):
        return self.root_y

    def winfo_height(self):
        return self.height


class KeyboardFocusRegionTests(unittest.TestCase):
    def setUp(self):
        self.editor = PixelEditor.__new__(PixelEditor)
        self.editor.master = FakeRoot()
        self.editor.canvas = FakeWidget(self.editor.master)
        self.editor.sidebar_frame = FakeWidget(self.editor.master)
        self.editor.sidebar_focus_targets = []
        self.first = FakeWidget(self.editor.sidebar_frame)
        self.last = FakeWidget(self.editor.sidebar_frame)
        self.editor.sidebar_focus_targets.extend((self.first, self.last))

    def test_f6_enters_sidebar_at_first_target_and_shift_f6_at_last(self):
        self.editor.master.focused = self.editor.canvas

        self.assertEqual(self.editor.focus_adjacent_region(), "break")
        self.assertIs(self.editor.master.focused, self.first)

        self.editor.master.focused = self.editor.canvas
        self.assertEqual(self.editor.focus_adjacent_region(reverse=True), "break")
        self.assertIs(self.editor.master.focused, self.last)

    def test_f6_from_any_nested_sidebar_control_returns_to_canvas(self):
        nested = FakeWidget(FakeWidget(self.editor.sidebar_frame))
        self.editor.master.focused = nested

        self.editor.focus_adjacent_region()

        self.assertIs(self.editor.master.focused, self.editor.canvas)
        self.assertEqual(self.editor.canvas.focus_count, 1)

    def test_sidebar_entry_skips_destroyed_and_disabled_controls(self):
        destroyed = FakeWidget(self.editor.sidebar_frame, exists=False)
        disabled = FakeWidget(self.editor.sidebar_frame, state="disabled")
        self.editor.sidebar_focus_targets = [destroyed, disabled, self.last]

        self.assertTrue(self.editor.focus_sidebar())
        self.assertIs(self.editor.master.focused, self.last)

    def test_registered_controls_receive_tabbable_focus_feedback(self):
        widget = FakeWidget(self.editor.sidebar_frame)

        self.editor.register_sidebar_focus_target(widget)

        self.assertEqual(widget.configured["takefocus"], 1)
        self.assertEqual(widget.configured["highlightthickness"], 2)
        self.assertEqual(widget.configured["highlightcolor"], "#80d4ff")
        self.assertIn("<FocusIn>", widget.bindings)
        self.assertIn(widget, self.editor.sidebar_focus_targets)

    def test_focus_outside_scrolls_sidebar_and_focus_inside_does_not(self):
        self.editor.sidebar_viewport = FakeViewport()
        below = FocusableGeometry(root_y=260)
        self.editor.scroll_sidebar_focus_into_view(below)
        self.assertAlmostEqual(self.editor.sidebar_viewport.scroll_to, 0.16)

        self.editor.sidebar_viewport = FakeViewport(scroll_offset=200)
        above = FocusableGeometry(root_y=90)
        self.editor.scroll_sidebar_focus_into_view(above)
        self.assertAlmostEqual(self.editor.sidebar_viewport.scroll_to, 0.38)

        self.editor.sidebar_viewport = FakeViewport(scroll_offset=200)
        visible = FocusableGeometry(root_y=150)
        self.editor.scroll_sidebar_focus_into_view(visible)
        self.assertIsNone(self.editor.sidebar_viewport.scroll_to)

    def test_history_shortcuts_run_only_in_editor_not_text_inputs_or_dialogs(self):
        self.editor.undo = Mock()
        self.editor.redo = Mock()
        self.editor.bind_global_shortcuts()
        undo = self.editor.master.bindings["<Control-z>"][0]
        redo = self.editor.master.bindings["<Control-y>"][0]

        self.editor.master.focused = FakeWidget(self.editor.master)
        self.assertEqual(undo(None), "break")
        self.assertEqual(redo(None), "break")
        self.editor.undo.assert_called_once_with()
        self.editor.redo.assert_called_once_with()

        for widget_class in ("Entry", "Text", "Spinbox", "TEntry", "TSpinbox", "TCombobox"):
            with self.subTest(widget_class=widget_class):
                self.editor.master.focused = FakeWidget(
                    self.editor.master, class_name=widget_class
                )
                self.assertIsNone(undo(None))
                self.assertIsNone(redo(None))

        dialog = FakeRoot(master=self.editor.master)
        self.editor.master.focused = FakeWidget(dialog)
        self.assertIsNone(undo(None))
        self.assertIsNone(redo(None))
        self.assertEqual(self.editor.undo.call_count, 1)
        self.assertEqual(self.editor.redo.call_count, 1)

    def test_f6_does_not_steal_focus_from_a_dialog(self):
        dialog = FakeRoot(master=self.editor.master)
        dialog_entry = FakeWidget(dialog, class_name="Entry")
        self.editor.master.focused = dialog_entry

        self.assertIsNone(self.editor.focus_adjacent_region())
        self.assertIs(self.editor.master.focused, dialog_entry)


if __name__ == "__main__":
    unittest.main()
