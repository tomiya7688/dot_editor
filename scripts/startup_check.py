"""ワンクリック起動確認: 自動確認と目視確認を順に行い、結果を表示してファイルへ保存する (Issue #113)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import platform
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
RESULT_FILE = ROOT / "起動確認の結果.txt"

# 終了値。2は「確認できなかった」で、成功とは区別する。
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_RUN = 2

# 目視で確認する項目。キーボード操作の通し確認(#26〜#30)は別の手順で行う。
VISUAL_ITEMS = [
    "窓が開き、上のメニュー（ファイル・編集など）の文字が読めますか",
    "キャンバスをクリックすると、その場所が塗られますか",
    "メニューの ファイル から保存し、もう一度開いても絵が残っていますか",
    "Alt+H（またはヘルプメニュー）で、基本操作のヘルプが開きますか",
]

# 手順書: 結果を貼る先。
PASTE_TARGET = "Issue #67 と #26〜#30 に、結果ファイルの中身をそのまま貼ってください"


# {
#   責務: [Report: 確認の結果を集め、総合判定と保存用の文章を作る]
#   フィールド: [
#     lines: 結果ファイルに書く行
#     failed: 失敗した項目の名前
#     skipped: 試せなかった項目の名前
#     not_run: 窓を作れず確認できなかったか
#   ]
# }
@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    not_run: bool = False

    # {
    #   責務: [add: 結果の1行を追加する]
    #   処理: [1: 行を末尾へ足す]
    #   引数: [text: 追加する1行]
    #   戻り値: [なし]
    # }
    def add(self, text: str) -> None:
        self.lines.append(text)

    # {
    #   責務: [exit_code: 総合判定の終了値を返す]
    #   処理: [
    #     1: 窓を作れず確認できなかったなら2（成功扱いにしない）
    #     2: 失敗が1つでもあれば1
    #     3: それ以外は0
    #   ]
    #   引数: [なし]
    #   戻り値: [0=成功, 1=失敗, 2=未実行]
    # }
    def exit_code(self) -> int:
        if self.not_run:
            return EXIT_NOT_RUN
        if self.failed:
            return EXIT_FAILED
        return EXIT_OK

    # {
    #   責務: [verdict: 総合判定を日本語の1行にする]
    #   処理: [1: 終了値に対応する文を選ぶ。試せなかった項目があれば添える]
    #   引数: [なし]
    #   戻り値: [総合判定の文]
    # }
    def verdict(self) -> str:
        code = self.exit_code()
        if code == EXIT_NOT_RUN:
            text = "未実行: この画面では窓を開けませんでした。デスクトップに接続したWindowsで実行してください"
        elif code == EXIT_FAILED:
            text = "失敗: " + "、".join(self.failed)
        else:
            text = "成功"
        if self.skipped:
            text += "（試せなかった項目: " + "、".join(self.skipped) + "）"
        return text


# {
#   責務: [ask_yes_no: はい/いいえ/試せない を入力で受け取る]
#   処理: [
#     1: y/n/s のどれかが入力されるまで繰り返し尋ねる
#     2: 入力が尽きた(EOF)ときは試せなかったものとして s を返す
#   ]
#   引数: [prompt: 質問文, read: 1行を読む関数（テストで差し替える）]
#   戻り値: ["y"か"n"か"s"]
# }
def ask_yes_no(prompt: str, read: Callable[[str], str] = input) -> str:
    while True:
        try:
            answer = read(f"{prompt} [y=はい / n=いいえ / s=試せない]: ").strip().lower()
        except EOFError:
            return "s"
        if answer in ("y", "n", "s"):
            return answer
        print("  y か n か s を入力してEnterを押してください。")


# {
#   責務: [run_smoke: 窓を作らない確認(--smoke-test)を実行する]
#   処理: [
#     1: dot_editor.py を --smoke-test 付きで30秒の上限で実行する
#     2: 終了値0なら成功、それ以外は標準エラーの末尾を理由にする
#   ]
#   引数: [なし]
#   戻り値: [(成功したか, 理由の文)]
# }
def run_smoke() -> tuple[bool, str]:
    try:
        done = subprocess.run(
            [sys.executable, str(ROOT / "src" / "dot_editor.py"), "--smoke-test"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "30秒以内に終わりませんでした"
    if done.returncode == 0:
        return True, "窓を作らない確認に成功"
    return False, (done.stderr.strip()[-300:] or f"終了値 {done.returncode}")


# {
#   責務: [run_measure: 起動時間とメモリを3回測る]
#   処理: [
#     1: measure_gui_startup.py を --runs 3 で実行する
#     2: 終了値0なら標準出力のJSONを、2なら未実行を返す
#   ]
#   引数: [なし]
#   戻り値: [(状態 "ok"/"not_run"/"failed", 説明の文)]
# }
def run_measure() -> tuple[str, str]:
    try:
        done = subprocess.run(
            [
                sys.executable,
                "-I",
                str(ROOT / "scripts" / "measure_gui_startup.py"),
                "--runs",
                "3",
                "--timeout",
                "30",
            ],
            capture_output=True,
            text=True,
            timeout=150,
        )
    except subprocess.TimeoutExpired:
        return "not_run", "測定が時間内に終わりませんでした（窓を開けない環境の可能性）"
    if done.returncode == 0:
        return "ok", done.stdout.strip()
    if done.returncode == EXIT_NOT_RUN:
        return "not_run", "窓を作れず測定できませんでした"
    return "failed", (done.stderr.strip()[-300:] or f"終了値 {done.returncode}")


# {
#   責務: [write_report: 結果ファイルを書く]
#   処理: [1: UTF-8(BOM付き)で書く。書けなければ理由を返して画面表示だけにする]
#   引数: [report: 結果, path: 書き出し先]
#   戻り値: [書けたらNone、書けなかったら理由の文]
# }
def write_report(report: Report, path: Path) -> str | None:
    try:
        # BOM付きにして、メモ帳でも文字化けしないようにする。
        path.write_text("\n".join(report.lines) + "\n", encoding="utf-8-sig")
    except OSError as error:
        return str(error)
    return None


# {
#   責務: [main: 自動確認→目視確認の順に行い、結果を表示・保存する]
#   処理: [
#     1: 環境を記録する
#     2: 自動確認A(窓を作らない確認)。失敗なら目視へ進まない
#     3: 自動確認B(測定)。窓を作れないなら未実行にして目視へ進まない
#     4: 実際の窓を開き、目視項目を1つずつ尋ねる
#     5: 総合判定を表示し、結果ファイルへ保存する
#   ]
#   引数: [read: 入力関数(テストで差し替える), result_path: 結果ファイルの場所]
#   戻り値: [総合判定の終了値]
# }
def main(read: Callable[[str], str] = input, result_path: Path = RESULT_FILE) -> int:
    report = Report()
    report.add(f"日時: {datetime.now().isoformat(timespec='seconds')}")
    report.add(f"Python: {platform.python_version()} / OS: {platform.platform()}")
    print("== Dot Editor 起動確認 ==")

    smoke_ok, smoke_text = run_smoke()
    report.add(f"自動確認A（窓を作らない）: {'成功' if smoke_ok else '失敗'} - {smoke_text}")
    print(report.lines[-1])
    if not smoke_ok:
        report.failed.append("自動確認A")
    else:
        state, measured = run_measure()
        report.add(f"自動確認B（起動時間とメモリ）: {measured}")
        print(report.lines[-1])
        if state == "not_run":
            report.not_run = True
        elif state == "failed":
            report.failed.append("自動確認B")
        else:
            _visual_checks(report, read)

    report.add(f"総合判定: {report.verdict()}")
    print(report.lines[-1])
    problem = write_report(report, result_path)
    if problem:
        print(f"結果ファイルを書けませんでした（画面の結果をコピーしてください）: {problem}")
    else:
        print(f"結果を {result_path.name} に保存しました。{PASTE_TARGET}")
    return report.exit_code()


# {
#   責務: [_visual_checks: 実際の窓を開き、目視の確認項目を尋ねる]
#   処理: [
#     1: dot_editor.py を窓つきで起動する（待たない）
#     2: 項目を1つずつ尋ね、答えを結果へ書く（nは失敗、sは試せなかった）
#     3: 最後に窓を閉じる
#   ]
#   引数: [report: 結果, read: 入力関数]
#   戻り値: [なし]
# }
def _visual_checks(report: Report, read: Callable[[str], str]) -> None:
    window = subprocess.Popen([sys.executable, str(ROOT / "src" / "dot_editor.py")])
    print("\n実際の窓を開きました。窓を操作しながら、次の質問に答えてください。")
    try:
        for index, item in enumerate(VISUAL_ITEMS, 1):
            answer = ask_yes_no(f"({index}/{len(VISUAL_ITEMS)}) {item}", read)
            label = {"y": "はい", "n": "いいえ", "s": "試せない"}[answer]
            report.add(f"目視{index}: {item} -> {label}")
            if answer == "n":
                report.failed.append(f"目視{index}")
            elif answer == "s":
                report.skipped.append(f"目視{index}")
    finally:
        # 質問が終わったら（途中で中断されても）窓を閉じる。
        window.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
