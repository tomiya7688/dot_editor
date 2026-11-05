"""Check the unsaved mark in the window title (fake window, no GUI)."""

import os
import tempfile
from types import SimpleNamespace
import unittest

from dot_editor import PixelEditor
from pixel_layers import LayeredPixelCanvas

_CONFIG = None


# {
#   責務: [setUpModule: このテストが本物の設定フォルダへ書かないよう、一時フォルダへ向ける]
#   処理: [最近使った作品の設定フォルダを、このモジュールの間だけ一時フォルダにする]
#   引数: []
#   戻り値: [なし]
# }
def setUpModule():
    global _CONFIG
    _CONFIG = tempfile.TemporaryDirectory()
    os.environ["HYPER_DOT_EDITOR_CONFIG_DIR"] = _CONFIG.name


# {
#   責務: [tearDownModule: 設定フォルダの向け先を元に戻し、一時フォルダを消す]
#   処理: [環境変数を外し、一時フォルダを片付ける]
#   引数: []
#   戻り値: [なし]
# }
def tearDownModule():
    os.environ.pop("HYPER_DOT_EDITOR_CONFIG_DIR", None)
    _CONFIG.cleanup()


# {
#   責務: [make_editor: 題名を記録する偽のウィンドウと実際の作品モデルを持つ編集部を作る]
#   処理: [画面に関わる処理を何もしない関数に差し替え、題名の履歴を記録する]
#   引数: [titles: 設定された題名を記録するリスト]
#   戻り値: [編集部]
# }
def make_editor(titles):
    editor = PixelEditor.__new__(PixelEditor)
    editor.master = SimpleNamespace(title=titles.append)
    editor.backend = LayeredPixelCanvas(4)
    editor.num_pixels_x = editor.num_pixels_y = 4
    editor.history, editor.future = [], []
    editor.selected_cell = None
    editor.transaction_before = None
    editor.transaction_changed = False
    for name in ("refresh_layer_list", "update_canvas_size", "update_canvas", "refresh_composite"):
        setattr(editor, name, lambda: None)
    editor.mark_saved()
    return editor


# {
#   責務: [TitleMarkTests: 題名の未保存マークの回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class TitleMarkTests(unittest.TestCase):
    # {
    #   責務: [test_mark_follows_edits_undo_and_save: 編集で付き、元に戻して同じ作品になれば外れ、保存で外れることを検証する]
    #   処理: [
    #     1: 保存直後は印が無いことを確認する
    #     2: 編集すると印が付くことを確認する
    #     3: 元に戻して保存時と同じ作品になると印が外れ、やり直すと再び付くことを確認する
    #     4: 保存の基準を更新すると印が外れることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_mark_follows_edits_undo_and_save(self):
        titles = []
        editor = make_editor(titles)
        self.assertEqual(titles[-1], "ドット絵エディタ")
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        self.assertEqual(titles[-1], "*ドット絵エディタ")
        editor.undo()
        self.assertEqual(titles[-1], "ドット絵エディタ")
        editor.redo()
        self.assertEqual(titles[-1], "*ドット絵エディタ")
        editor.mark_saved()
        self.assertEqual(titles[-1], "ドット絵エディタ")

    # {
    #   責務: [test_drag_transaction_and_no_window: ドラッグ全体の確定で印が付き、窓が無くても動くことを検証する]
    #   処理: [
    #     1: 編集取引の確定後に印が付くことを確認する
    #     2: 窓の無い編集部でもrefresh_titleが何もせず成功することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_drag_transaction_and_no_window(self):
        titles = []
        editor = make_editor(titles)
        editor.begin_edit_transaction()
        editor.perform_edit(editor.commands.paint, 1, 1, (0, 255, 0, 255))
        editor.end_edit_transaction()
        self.assertEqual(titles[-1], "*ドット絵エディタ")
        bare = PixelEditor.__new__(PixelEditor)
        bare.history, bare.future = [], []
        bare.refresh_title()


if __name__ == "__main__":
    unittest.main()
