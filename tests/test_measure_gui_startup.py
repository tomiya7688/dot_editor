import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import measure_gui_startup  # noqa: E402


# {
#   責務: [MeasureGuiStartupTests: 起動測定スクリプトの集計と未実行判定を確かめる]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class MeasureGuiStartupTests(unittest.TestCase):
    # {
    #   責務: [test_reports_median_and_max: 中央値と最大値が正しく出ることを確かめる]
    #   処理: [1: 3件の測定値を与える, 2: JSON出力を検査する]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_reports_median_and_max(self):
        samples = [
            {"seconds": 1.0, "peak_bytes": 100 * 1048576},
            {"seconds": 3.0, "peak_bytes": 300 * 1048576},
            {"seconds": 2.0, "peak_bytes": 200 * 1048576},
        ]
        out = io.StringIO()
        with (
            mock.patch.object(measure_gui_startup, "run_once", side_effect=samples),
            contextlib.redirect_stdout(out),
        ):
            code = measure_gui_startup.main(["--runs", "3"])
        report = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["seconds_median"], 2.0)
        self.assertEqual(report["seconds_max"], 3.0)
        self.assertEqual(report["peak_mib_median"], 200.0)

    # {
    #   責務: [test_not_run_when_gui_cannot_start: 起動できない時に1回で諦め終了値2になることを確かめる]
    #   処理: [1: run_onceをNoneにする, 2: 呼出し回数と終了値を検査する]
    #   引数: [なし]
    #   戻り値: [なし]
    # }
    def test_not_run_when_gui_cannot_start(self):
        err = io.StringIO()
        with (
            mock.patch.object(measure_gui_startup, "run_once", return_value=None) as run,
            contextlib.redirect_stderr(err),
        ):
            code = measure_gui_startup.main(["--runs", "5"])
        self.assertEqual(code, 2)
        self.assertEqual(run.call_count, 1)
        self.assertIn("not run", err.getvalue())


if __name__ == "__main__":
    unittest.main()
