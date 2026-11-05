"""Check the always-visible toolbar wiring with fake Tk parts (no GUI is opened)."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dot_editor import TOOLBAR_ACTIONS, PixelEditor, menu_spec


# {
#   責務: [ToolbarTests: 固定ツールバーの項目と配置の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class ToolbarTests(unittest.TestCase):
    # {
    #   責務: [test_actions_exist_and_match_menu: ツールバーの操作が実在し、メニューの同じ操作と対応することを検証する]
    #   処理: [
    #     1: すべての項目のメソッドが編集部に存在することを確認する
    #     2: ファイル・編集メニューの動作名のうち、ツールバーに載せたものが両方に存在することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_actions_exist_and_match_menu(self):
        menu_actions = set()
        for _, _, entries in menu_spec():
            for entry in entries:
                if entry[0] == "command":
                    menu_actions.add(entry[3])
        for label, action in TOOLBAR_ACTIONS:
            self.assertTrue(label.strip())
            self.assertTrue(callable(getattr(PixelEditor, action)), action)
            self.assertIn(action, menu_actions, f"{action} is not reachable from a menu")
        self.assertEqual(len({action for _, action in TOOLBAR_ACTIONS}), len(TOOLBAR_ACTIONS))

    # {
    #   責務: [test_toolbar_sits_below_the_canvas_and_calls_the_actions: ツールバーがキャンバスの下の行に置かれ、ボタンが各操作を呼ぶことを検証する]
    #   処理: [
    #     1: 偽のFrameとButtonでbuild_toolbarを実行する
    #     2: 枠が1行目の0列に横いっぱいで置かれ、ボタンが項目の数だけ並ぶことを確認する
    #     3: 各ボタンの命令が、対応するメソッドであることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_toolbar_sits_below_the_canvas_and_calls_the_actions(self):
        placed = {}
        buttons = []
        frame = SimpleNamespace(grid=lambda **kwargs: placed.update(kwargs))

        fake_button = lambda parent, **kwargs: (
            buttons.append(SimpleNamespace(options=kwargs, grid=lambda **g: None)) or buttons[-1]
        )

        editor = PixelEditor.__new__(PixelEditor)
        editor.master = SimpleNamespace()
        for _, action in TOOLBAR_ACTIONS:
            setattr(editor, action, lambda name=action: name)
        with (
            patch("dot_editor.tk.Frame", return_value=frame),
            patch("dot_editor.tk.Button", fake_button),
        ):
            editor.build_toolbar()
        self.assertEqual((placed["row"], placed["column"], placed["sticky"]), (1, 0, "ew"))
        self.assertEqual(len(buttons), len(TOOLBAR_ACTIONS))
        for button, (label, action) in zip(buttons, TOOLBAR_ACTIONS):
            self.assertEqual(button.options["text"], label)
            self.assertEqual(button.options["command"](), action)


if __name__ == "__main__":
    unittest.main()
