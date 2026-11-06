"""Check the recent-works list and its use by the editor (settings in a temp folder, no GUI)."""

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import recent_files
from dot_editor import PixelEditor
from pixel_commands import PixelCommandAPI
from pixel_layers import LayeredPixelCanvas


# {
#   責務: [make_editor: 最近の作品の検査用に、実際の作品モデルと偽の部品を持つ編集部を作る]
#   処理: [4x4の作品を用意し、画面に関わる処理を何もしない関数に差し替える]
#   引数: []
#   戻り値: [編集部]
# }
def make_editor():
    editor = PixelEditor.__new__(PixelEditor)
    editor.backend = LayeredPixelCanvas(4)
    editor.num_pixels_x = editor.num_pixels_y = 4
    editor.history, editor.future = [], []
    editor.selected_cell = None
    editor.report_error = lambda error: None
    for name in ("refresh_layer_list", "update_canvas_size", "update_canvas", "refresh_composite"):
        setattr(editor, name, lambda: None)
    editor.mark_saved()
    return editor


# {
#   責務: [RecentFilesTests: 最近使った作品の一覧と、その利用の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class RecentFilesTests(unittest.TestCase):
    # {
    #   責務: [test_list_is_deduplicated_limited_and_tolerant: 一覧が重複せず、上限を守り、壊れた設定でも動くことを検証する]
    #   処理: [
    #     1: 同じ作品を2回覚えても1件で、先頭に来ることを確認する
    #     2: 上限を超えると古いものが落ちることを確認する
    #     3: 設定ファイルが壊れていても空の一覧になることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_list_is_deduplicated_limited_and_tolerant(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"HYPER_DOT_EDITOR_CONFIG_DIR": directory}),
        ):
            self.assertEqual(recent_files.load_recent(), [])
            first = Path(directory) / "a.json"
            recent_files.remember(first)
            recent_files.remember(Path(directory) / "b.json")
            paths = recent_files.remember(first)
            self.assertEqual(paths[0], recent_files.normalize(first))
            self.assertEqual(len(paths), 2)
            for number in range(20):
                recent_files.remember(Path(directory) / f"w{number}.json")
            self.assertEqual(len(recent_files.load_recent()), recent_files.MAX_RECENT)
            (Path(directory) / recent_files.FILE_NAME).write_text("{not json", encoding="utf-8")
            self.assertEqual(recent_files.load_recent(), [])
            (Path(directory) / recent_files.FILE_NAME).write_text('{"paths": 5}', encoding="utf-8")
            self.assertEqual(recent_files.load_recent(), [])

    # {
    #   責務: [test_save_open_and_failure_update_the_list: 保存・読込で一覧が更新され、開けなかった作品が外れてもファイルは消えないことを検証する]
    #   処理: [
    #     1: 作品を保存すると一覧の先頭に入ることを確認する
    #     2: 最近の一覧から開くと、保存確認を経て読み込まれることを確認する
    #     3: 存在しない作品を開こうとすると、一覧から外れて既存の作品が残ることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_save_open_and_failure_update_the_list(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ, {"HYPER_DOT_EDITOR_CONFIG_DIR": str(Path(directory) / "config")}
            ),
        ):
            editor = make_editor()
            target = Path(directory) / "art.json"
            editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
            with patch("dot_editor.filedialog.asksaveasfilename", return_value=str(target)):
                self.assertTrue(editor.save_project())
            self.assertEqual(recent_files.load_recent(), [recent_files.normalize(target)])
            other = Path(directory) / "other.json"
            api = PixelCommandAPI.new(4, layered=True)
            api.paint(3, 3, (0, 0, 255, 255))
            api.save(other)
            editor.open_recent(str(other))
            self.assertEqual(editor.commands.sample(3, 3)[:3], (0, 0, 255))
            self.assertEqual(recent_files.load_recent()[0], recent_files.normalize(other))
            missing = Path(directory) / "gone.json"
            recent_files.remember(missing)
            editor.open_recent(str(missing))
            self.assertNotIn(recent_files.normalize(missing), recent_files.load_recent())
            self.assertEqual(editor.commands.sample(3, 3)[:3], (0, 0, 255))
            self.assertTrue(target.is_file() and other.is_file())

    # {
    #   責務: [test_recent_menu_lists_entries_and_respects_cancel: メニューの項目と、保存確認の取消で開かないことを検証する]
    #   処理: [
    #     1: 偽のメニューへ項目が作られ、空のときは選べない案内になることを確認する
    #     2: 未保存の変更があり、確認で取り消すと、作品が読み込まれないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_recent_menu_lists_entries_and_respects_cancel(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ, {"HYPER_DOT_EDITOR_CONFIG_DIR": str(Path(directory) / "config")}
            ),
        ):
            editor = make_editor()
            added = []
            menu = SimpleNamespace(
                delete=lambda *args: added.clear(),
                add_command=lambda **kwargs: added.append(kwargs),
            )
            editor.populate_recent_menu(menu)
            self.assertEqual(len(added), 1)
            self.assertEqual(added[0]["state"], "disabled")
            other = Path(directory) / "other.json"
            PixelCommandAPI.new(4, layered=True).save(other)
            recent_files.remember(other)
            editor.populate_recent_menu(menu)
            self.assertEqual(len(added), 1)
            self.assertIn("other.json", added[0]["label"])
            editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
            with patch("dot_editor.messagebox.askyesnocancel", return_value=None):
                added[0]["command"]()
            self.assertEqual(editor.commands.sample(0, 0)[:3], (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
