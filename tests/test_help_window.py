"""Check the help window wiring with fake Tk parts (no GUI is opened)."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dot_editor import PixelEditor


# {
#   責務: [make_editor: ヘルプ窓の検査用に、偽のウィンドウと作品状態を持つ編集部を作る]
#   処理: [フォーカスを持つ偽の部品と、作品・履歴・フォーカスを記録する偽の親ウィンドウを用意する]
#   引数: [focused: フォーカスしたことを記録するリスト]
#   戻り値: [編集部]
# }
def make_editor(focused):
    editor = PixelEditor.__new__(PixelEditor)
    saved = SimpleNamespace(winfo_exists=lambda: True, focus_set=lambda: focused.append("saved"))
    editor.master = SimpleNamespace(focus_get=lambda: saved)
    editor.canvas = SimpleNamespace(
        winfo_exists=lambda: True, focus_set=lambda: focused.append("canvas")
    )
    editor.history, editor.future = [], []
    editor.selected_cell = None
    return editor


# {
#   責務: [make_fake_text: 挿入された文章と状態を記録する偽のText部品を作る]
#   処理: [挿入と設定の呼び出しを記録するオブジェクトを作り、記録用のリストへ加える]
#   引数: [created: 作った部品を集めるリスト]
#   戻り値: [偽のText部品]
# }
def make_fake_text(created):
    fake = SimpleNamespace(
        text="",
        state="normal",
        pack=lambda **kw: None,
        yview=lambda *a: None,
        focus_set=lambda: None,
    )
    fake.insert = lambda index, text: setattr(fake, "text", text)
    fake.configure = lambda **kw: setattr(fake, "state", kw.get("state", fake.state))
    created.append(fake)
    return fake


# {
#   責務: [HelpWindowTests: ヘルプ窓が作品を変えず、閉じると元のフォーカスへ戻ることを検証する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class HelpWindowTests(unittest.TestCase):
    # {
    #   責務: [test_help_opens_read_only_and_restores_focus: 読み取り専用で開き、閉じると元のフォーカスへ戻ることを検証する]
    #   処理: [
    #     1: 偽のTkで4つのヘルプを開き、文章が入って読み取り専用になることを確認する
    #     2: 閉じると開く前の要素へフォーカスが戻り、作品の履歴や選択が変わらないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_help_opens_read_only_and_restores_focus(self):
        focused = []
        editor = make_editor(focused)
        created = []

        window = SimpleNamespace(
            title=lambda text: None,
            transient=lambda master: None,
            bind=lambda event, handler: None,
            protocol=lambda name, handler: None,
            winfo_exists=lambda: True,
            destroy=lambda: focused.append("destroyed"),
        )
        scrollbar = SimpleNamespace(configure=lambda **kw: None, pack=lambda **kw: None, set=None)
        with (
            patch("dot_editor.tk.Toplevel", return_value=window),
            patch("dot_editor.tk.Scrollbar", return_value=scrollbar),
            patch("dot_editor.tk.Text", lambda *args, **kwargs: make_fake_text(created)),
        ):
            editor.help_basic()
            editor.help_keyboard()
            editor.help_commands()
            editor.help_about()
        self.assertEqual(len(created), 4)
        for text in created:
            self.assertEqual(text.state, "disabled")
            self.assertTrue(text.text.strip())
        editor.close_help(editor.master.focus_get())
        self.assertEqual(editor.history, [])
        self.assertIsNone(editor.selected_cell)
        self.assertIsNone(editor.help_window)
        self.assertEqual(focused[-1], "saved")


if __name__ == "__main__":
    unittest.main()
