"""Check the Tk-free help text builders."""

import sys
import unittest

import help_content


# {
#   責務: [HelpContentTests: オフラインヘルプの文章生成の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class HelpContentTests(unittest.TestCase):
    # {
    #   責務: [test_texts_are_built_from_real_definitions: 文章が実際の定義から作られることを検証する]
    #   処理: [
    #     1: キー割当表から作った文章に全キーと動作が含まれることを確認する
    #     2: コマンド表の文章に、全コマンドの説明と書式が含まれることを確認する
    #     3: バージョン情報に版が含まれることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_texts_are_built_from_real_definitions(self):
        from command_catalog import build_catalog, cli_version
        from dot_editor import KEY_BINDINGS

        keyboard = help_content.keyboard_text(KEY_BINDINGS)
        for key, action in KEY_BINDINGS:
            self.assertIn(key, keyboard)
            self.assertIn(action, keyboard)
        catalog = build_catalog()
        commands = help_content.commands_text(catalog)
        for command in catalog["commands"]:
            self.assertIn(command["summary_ja"], commands)
            self.assertIn(command["usage"], commands)
        self.assertIn(catalog["cli_version"], commands)
        self.assertIn(cli_version(), help_content.about_text(cli_version()))
        self.assertIn("Ctrl+Z", help_content.basic_text())

    # {
    #   責務: [test_missing_catalog_is_reported_not_replaced: 表を作れないときに理由を示し、別の資料で代用しないことを検証する]
    #   処理: [
    #     1: command_catalogの読み込みを失敗させて理由つきの文章が返ることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_missing_catalog_is_reported_not_replaced(self):
        saved = sys.modules.get("command_catalog")
        sys.modules["command_catalog"] = None
        try:
            text = help_content.load_commands_text()
        finally:
            sys.modules.pop("command_catalog", None)
            if saved is not None:
                sys.modules["command_catalog"] = saved
        self.assertIn("この版のヘルプを表示できません", text)
        self.assertNotIn("pixel-cli", text)


if __name__ == "__main__":
    unittest.main()
