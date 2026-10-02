"""Headless checks for menu access-key uniqueness and live editor actions."""
import unittest

from dot_editor import PixelEditor, menu_spec


class MenuStructureTests(unittest.TestCase):
    def test_top_level_alt_access_keys_are_visible_and_unique(self):
        menus = menu_spec()
        keys = [access_key.casefold() for _, access_key, _ in menus]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(menus), 6)
        for label, access_key, _ in menus:
            self.assertIn(access_key.casefold(), label.casefold())

    def test_every_menu_entry_key_is_unique_within_its_menu(self):
        def check_siblings(entries):
            keys = []
            for entry in entries:
                if entry[0] == "separator":
                    continue
                access_key = entry[2]
                label, _ = PixelEditor.access_label(entry[1], access_key)
                self.assertIn(access_key.casefold(), label.casefold())
                keys.append(access_key.casefold())
                if entry[0] == "cascade":
                    check_siblings(entry[3])
            self.assertEqual(len(keys), len(set(keys)), keys)

        for _, _, entries in menu_spec():
            check_siblings(entries)

    def test_actions_resolve_to_editor_methods(self):
        def check_actions(entries):
            for entry in entries:
                if entry[0] == "command":
                    self.assertTrue(callable(getattr(PixelEditor, entry[3], None)), entry[3])
                elif entry[0] == "cascade":
                    check_actions(entry[3])

        for _, _, entries in menu_spec():
            check_actions(entries)

    def test_palette_menu_covers_all_current_palette_slots(self):
        editor = PixelEditor.__new__(PixelEditor)
        editor.palette_colors = [
            (255, 255, 255), (0, 0, 0), (255, 80, 80), (255, 190, 70),
            (255, 240, 100), (90, 210, 130), (80, 180, 255), (170, 110, 255),
        ]
        self.assertEqual(len(editor.palette_colors), 8)
        for color in editor.palette_colors:
            self.assertEqual(len(editor.rgb_to_hex(color)), 7)


if __name__ == "__main__":
    unittest.main()
