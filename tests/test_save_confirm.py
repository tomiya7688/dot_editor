"""Check dirty tracking and the save confirmation before losing changes (fake dialogs, no GUI)."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dot_editor import PixelEditor
from pixel_commands import PixelCommandAPI
from pixel_layers import LayeredPixelCanvas
import os


# {
#   責務: [make_editor: 保存確認の検査用に、実際の作品モデルと偽の部品を持つ編集部を作る]
#   処理: [
#     1: 4x4の作品と履歴を用意し、画面に関わる処理を何もしない関数に差し替える
#     2: 保存済みの基準を記録する
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
    editor.report_error = lambda error: None
    for name in ("refresh_layer_list", "update_canvas_size", "update_canvas", "refresh_composite"):
        setattr(editor, name, lambda: None)
    editor.mark_saved()
    return editor


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
#   責務: [SaveConfirmTests: 未保存の判定と、保存・破棄・取消の確認の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class SaveConfirmTests(unittest.TestCase):
    # {
    #   責務: [test_dirty_follows_meaning_not_history: 未保存の判定が履歴の長さでなく作品の意味で決まることを検証する]
    #   処理: [
    #     1: 保存直後は未保存でないことを確認する
    #     2: 編集すると未保存になり、元に戻して同じ作品になれば未保存でなくなることを確認する
    #     3: ツールや選択の変更では未保存にならないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_dirty_follows_meaning_not_history(self):
        editor = make_editor()
        self.assertFalse(editor.is_dirty())
        editor.selected_cell = (1, 1)
        editor.tool = "eraser"
        self.assertFalse(editor.is_dirty())
        before = editor.make_snapshot()
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        self.assertTrue(editor.is_dirty())
        editor.undo()
        self.assertEqual(editor.make_snapshot(), before)
        self.assertFalse(editor.is_dirty())

    # {
    #   責務: [test_confirm_cancel_discard_and_save: 取消・破棄・保存のそれぞれの結果を検証する]
    #   処理: [
    #     1: 未保存でなければ確認せずに続行することを確認する
    #     2: 取消では続行せず、確認の初期選択がキャンセルであることを確認する
    #     3: 「いいえ」では続行し、保存では保存して続行、保存先を選ばなければ続行しないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_confirm_cancel_discard_and_save(self):
        editor = make_editor()
        with patch("dot_editor.messagebox.askyesnocancel") as ask:
            self.assertTrue(editor.confirm_discard("終了"))
            ask.assert_not_called()
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        with patch("dot_editor.messagebox.askyesnocancel", return_value=None) as ask:
            self.assertFalse(editor.confirm_discard("終了"))
            self.assertEqual(ask.call_args.kwargs["default"], "cancel")
        self.assertTrue(editor.is_dirty())
        with patch("dot_editor.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(editor.confirm_discard("終了"))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "art.json"
            with (
                patch("dot_editor.messagebox.askyesnocancel", return_value=True),
                patch("dot_editor.filedialog.asksaveasfilename", return_value=""),
            ):
                self.assertFalse(editor.confirm_discard("終了"))
                self.assertTrue(editor.is_dirty())
            with (
                patch("dot_editor.messagebox.askyesnocancel", return_value=True),
                patch("dot_editor.filedialog.asksaveasfilename", return_value=str(target)),
            ):
                self.assertTrue(editor.confirm_discard("終了"))
            self.assertTrue(target.is_file())
            self.assertFalse(editor.is_dirty())

    # {
    #   責務: [test_failed_save_keeps_everything: 保存に失敗したら続行せず、作品も保存済みの基準も変わらないことを検証する]
    #   処理: [
    #     1: 保存先に書けない状況で保存を選ぶ
    #     2: 続行されず、未保存のままで、作品が残ることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_failed_save_keeps_everything(self):
        editor = make_editor()
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "no-such-folder" / "art.json"
            with (
                patch("dot_editor.messagebox.askyesnocancel", return_value=True),
                patch("dot_editor.filedialog.asksaveasfilename", return_value=str(missing)),
            ):
                self.assertFalse(editor.confirm_discard("別の作品を開く"))
        self.assertTrue(editor.is_dirty())
        self.assertEqual(editor.commands.sample(0, 0)[:3], (255, 0, 0))

    # {
    #   責務: [test_load_and_close_ask_first: 作品を開く操作と閉じる操作が、確認の結果に従うことを検証する]
    #   処理: [
    #     1: 取消のとき、開くダイアログも出ず、閉じる処理も呼ばれないことを確認する
    #     2: 未保存でなければ、確認なしで閉じる処理が呼ばれることを確認する
    #     3: 読み込みに成功したら保存済みの基準が更新され、未保存でなくなることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_load_and_close_ask_first(self):
        editor = make_editor()
        closed = []
        editor.master = SimpleNamespace(destroy=lambda: closed.append(True), focus_get=lambda: None)
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        with (
            patch("dot_editor.messagebox.askyesnocancel", return_value=None),
            patch("dot_editor.filedialog.askopenfilename") as opener,
        ):
            editor.load_project()
            opener.assert_not_called()
            editor.on_close()
        self.assertEqual(closed, [])
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other.json"
            api = PixelCommandAPI.new(4, layered=True)
            api.paint(2, 2, (0, 0, 255, 255))
            api.save(other)
            with (
                patch("dot_editor.messagebox.askyesnocancel", return_value=False),
                patch("dot_editor.filedialog.askopenfilename", return_value=str(other)),
            ):
                editor.load_project()
            self.assertEqual(editor.commands.sample(2, 2)[:3], (0, 0, 255))
            self.assertFalse(editor.is_dirty())
        with patch("dot_editor.messagebox.askyesnocancel") as ask:
            editor.on_close()
            ask.assert_not_called()
        self.assertEqual(closed, [True])


# {
#   責務: [NewProjectAndPathTests: 新規作品と、通常保存・名前を付けて保存の保存先管理の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class NewProjectAndPathTests(unittest.TestCase):
    # {
    #   責務: [test_new_project_cancel_keeps_everything: 新規作品のキャンセルで作品・履歴・パスが変わらないことを検証する]
    #   処理: [編集後に新規作品を取り消し、作品と履歴と保存先が元のままで未保存のままであることを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_new_project_cancel_keeps_everything(self):
        editor = make_editor()
        editor.current_path = "keep.json"
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        before = editor.make_snapshot()
        with patch("dot_editor.messagebox.askyesnocancel", return_value=None):
            self.assertFalse(editor.new_project())
        self.assertEqual((editor.make_snapshot(), editor.current_path), (before, "keep.json"))
        self.assertEqual(len(editor.history), 1)
        self.assertTrue(editor.is_dirty())

    # {
    #   責務: [test_new_project_discard_makes_untitled_clean_work: 破棄して新規作品を作ると保存先未定の保存済みの空の作品になることを検証する]
    #   処理: [編集後に破棄を選び、画素が空・履歴が空・パスが空・未保存でないことを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_new_project_discard_makes_untitled_clean_work(self):
        editor = make_editor()
        editor.current_path = "old.json"
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        with patch("dot_editor.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(editor.new_project())
        self.assertIsNone(editor.current_path)
        self.assertEqual(editor.history, [])
        self.assertFalse(editor.is_dirty())

    # {
    #   責務: [test_save_uses_current_path_and_save_as_switches: 通常保存は現在のパスへ、名前を付けて保存は新しい先へ保存しパスを切り替えることを検証する]
    #   処理: [
    #     1: 保存先未定の保存が名前を付けて保存になることを確認する
    #     2: 以後の保存がダイアログなしで同じ先へ上書きすることを確認する
    #     3: 名前を付けて保存のキャンセルでパスが変わらず、成功で切り替わることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_save_uses_current_path_and_save_as_switches(self):
        editor = make_editor()
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "a.json", Path(directory) / "b.json"
            with patch("dot_editor.filedialog.asksaveasfilename", return_value=str(first)) as ask:
                self.assertTrue(editor.save_project())
                self.assertEqual(ask.call_count, 1)
            editor.perform_edit(editor.commands.paint, 1, 1, (0, 255, 0, 255))
            with patch("dot_editor.filedialog.asksaveasfilename") as ask:
                self.assertTrue(editor.save_project())
                ask.assert_not_called()
            self.assertFalse(editor.is_dirty())
            with patch("dot_editor.filedialog.asksaveasfilename", return_value=""):
                self.assertFalse(editor.save_project_as())
            self.assertEqual(editor.current_path, str(first))
            with patch("dot_editor.filedialog.asksaveasfilename", return_value=str(second)):
                self.assertTrue(editor.save_project_as())
            self.assertEqual(editor.current_path, str(second))
            self.assertTrue(second.is_file())

    # {
    #   責務: [test_failed_save_and_reset_keep_path_rules: 保存失敗ではパスを変えず、リセットでは前の保存先を忘れることを検証する]
    #   処理: [書き込めない先への保存でパスと基準が変わらず、リセット後は保存先が未定になることを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_failed_save_and_reset_keep_path_rules(self):
        editor = make_editor()
        editor.current_path = "old.json"
        editor.perform_edit(editor.commands.paint, 0, 0, (255, 0, 0, 255))
        with tempfile.TemporaryDirectory() as directory:
            bad = str(Path(directory) / "missing" / "x.json")
            with patch("dot_editor.filedialog.asksaveasfilename", return_value=bad):
                self.assertFalse(editor.save_project_as())
        self.assertEqual(editor.current_path, "old.json")
        self.assertTrue(editor.is_dirty())
        with patch("dot_editor.messagebox.askyesno", return_value=True):
            editor.reset_canvas()
        self.assertIsNone(editor.current_path)


if __name__ == "__main__":
    unittest.main()
