from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import startup_check  # noqa: E402


# {
#   責務: [StartupCheckTests: ワンクリック起動確認の判定・入力・結果保存を確かめる]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class StartupCheckTests(unittest.TestCase):
    # {
    #   責務: [test_exit_code_rules: 総合判定の終了値が 成功0/失敗1/未実行2 になることを確かめる]
    #   処理: [1: 結果の組み合わせを作る, 2: 未実行が失敗より優先されることも確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_exit_code_rules(self):
        ok = startup_check.Report()
        self.assertEqual(ok.exit_code(), startup_check.EXIT_OK)
        failed = startup_check.Report(failed=["目視2"])
        self.assertEqual(failed.exit_code(), startup_check.EXIT_FAILED)
        not_run = startup_check.Report(failed=["目視2"], not_run=True)
        self.assertEqual(not_run.exit_code(), startup_check.EXIT_NOT_RUN)

    # {
    #   責務: [test_skipped_is_not_hidden: 試せなかった項目が成功の文に残ることを確かめる]
    #   処理: [1: skippedを入れて判定文を作る, 2: 項目名が含まれ、終了値は0のままと確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_skipped_is_not_hidden(self):
        report = startup_check.Report(skipped=["目視4"])
        self.assertIn("目視4", report.verdict())
        self.assertEqual(report.exit_code(), startup_check.EXIT_OK)

    # {
    #   責務: [test_ask_yes_no_retries_until_valid: 不正な入力では聞き直し、EOFは試せない扱いになることを確かめる]
    #   処理: [1: 不正な答えのあとyを返す入力を与える, 2: EOFならsを返すことを確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_ask_yes_no_retries_until_valid(self):
        answers = iter(["", "はい", " Y "])
        with mock.patch("builtins.print"):
            self.assertEqual(startup_check.ask_yes_no("?", lambda _prompt: next(answers)), "y")

        def at_eof(_prompt):
            raise EOFError

        self.assertEqual(startup_check.ask_yes_no("?", at_eof), "s")

    # {
    #   責務: [test_main_stops_before_visual_when_smoke_fails: 自動確認Aの失敗では窓を開かず、失敗で終わることを確かめる]
    #   処理: [1: run_smokeを失敗にする, 2: 目視確認が呼ばれず終了値1で、結果ファイルが書かれることを確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_main_stops_before_visual_when_smoke_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            result = Path(folder) / "result.txt"
            with (
                mock.patch.object(startup_check, "run_smoke", return_value=(False, "壊れた")),
                mock.patch.object(startup_check, "_visual_checks") as visual,
                mock.patch("builtins.print"),
            ):
                code = startup_check.main(read=lambda _p: "y", result_path=result)
            text = result.read_text(encoding="utf-8-sig")
        self.assertEqual(code, startup_check.EXIT_FAILED)
        visual.assert_not_called()
        self.assertIn("自動確認A（窓を作らない）: 失敗", text)

    # {
    #   責務: [test_main_not_run_when_window_cannot_open: 窓を作れない環境は未実行(2)になり、目視へ進まないことを確かめる]
    #   処理: [1: smokeは成功、測定は未実行にする, 2: 終了値2と、結果の「未実行」を確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_main_not_run_when_window_cannot_open(self):
        with tempfile.TemporaryDirectory() as folder:
            result = Path(folder) / "result.txt"
            with (
                mock.patch.object(startup_check, "run_smoke", return_value=(True, "ok")),
                mock.patch.object(startup_check, "run_measure", return_value=("not_run", "窓なし")),
                mock.patch.object(startup_check, "_visual_checks") as visual,
                mock.patch("builtins.print"),
            ):
                code = startup_check.main(read=lambda _p: "y", result_path=result)
            text = result.read_text(encoding="utf-8-sig")
        self.assertEqual(code, startup_check.EXIT_NOT_RUN)
        visual.assert_not_called()
        self.assertIn("総合判定: 未実行", text)

    # {
    #   責務: [test_visual_answers_are_recorded: 目視の答えが結果に残り、nは失敗・sは試せない扱いになることを確かめる]
    #   処理: [1: 窓の起動を偽物にして y,n,s,y と答える, 2: failedとskippedと窓を閉じたことを確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_visual_answers_are_recorded(self):
        answers = iter(["y", "n", "s", "y"])
        report = startup_check.Report()
        window = mock.Mock()
        with (
            mock.patch.object(startup_check.subprocess, "Popen", return_value=window),
            mock.patch("builtins.print"),
        ):
            startup_check._visual_checks(report, lambda _p: next(answers))
        self.assertEqual(report.failed, ["目視2"])
        self.assertEqual(report.skipped, ["目視3"])
        window.terminate.assert_called_once()
        self.assertEqual(len(report.lines), len(startup_check.VISUAL_ITEMS))

    # {
    #   責務: [test_write_report_reports_failure: 結果ファイルを書けないとき理由を返すことを確かめる]
    #   処理: [1: 存在しないフォルダへ書かせる, 2: 理由の文字列が返ることを確かめる]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_write_report_reports_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "none" / "result.txt"
            self.assertIsInstance(startup_check.write_report(startup_check.Report(), missing), str)


if __name__ == "__main__":
    unittest.main()
