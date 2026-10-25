"""Format explicitly owned Python files, or check a committed diff without writing."""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = {"src", "scripts", "tests"}


# {
#   責務: [validate_paths: 明示されたPythonファイルを所有ソースの範囲に限定する]
#   処理: [1: ディレクトリと範囲外パスを拒否する, 2: 重複を除いて相対パスを返す]
#   引数: [paths: リポジトリルート相対または絶対のファイル名一覧]
#   戻り値: [検証済み相対パス一覧。不正な対象はValueError]
# }
def validate_paths(paths):
    # ディレクトリ再帰や外部へのリンクで担当外のコードを書き換えない。
    selected = set()
    for name in paths:
        path = ROOT / name
        relative = path.resolve().relative_to(ROOT)
        if (
            path.is_symlink()
            or not path.is_file()
            or relative.suffix != ".py"
            or relative.parts[0] not in SOURCE_DIRECTORIES
        ):
            raise ValueError(f"Expected an owned Python file: {name}")
        selected.add(relative.as_posix())
    return sorted(selected)


# {
#   責務: [changed_python_paths: 基準コミットからHEADまでのPython変更を列挙する]
#   処理: [1: 基準をコミットとして解決する, 2: NUL区切り差分から存在する所有ソースを選ぶ]
#   引数: [revision: 比較元のコミットまたはref]
#   戻り値: [検証済み相対パス一覧。Git失敗時は例外]
# }
def changed_python_paths(revision):
    # HEADとの比較だけを行い、無関係な未コミット差分を自動選択しない。
    base = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
        cwd=ROOT,
        text=True,
    ).strip()
    changed = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            "-z",
            base,
            "HEAD",
            "--",
            "src",
            "scripts",
            "tests",
        ],
        cwd=ROOT,
    )
    paths = [
        name.decode("utf-8") for name in changed.split(b"\0") if name and name.endswith(b".py")
    ]
    return validate_paths(paths)


# {
#   責務: [main: 明示ファイルの整形またはコミット差分の非書込検査を実行する]
#   処理: [1: 書換範囲と引数を検証する, 2: 固定設定のRuffへ渡して終了値を維持する]
#   引数: [argv: CLI引数。Noneならプロセス引数]
#   戻り値: [Ruffの終了値。不正な指定・Git失敗は2、対象なしは0]
# }
def main(argv=None):
    # 引数なしや差分からの自動整形は許可せず、利用者が対象を選ぶ。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--base", help="Check committed changes from this revision to HEAD")
    arguments = parser.parse_args(argv)
    if arguments.base and (not arguments.check or arguments.paths):
        parser.error("--base requires --check and cannot be combined with explicit paths")
    if not arguments.base and not arguments.paths:
        parser.error("Specify the files owned by this task; recursive formatting is disabled")
    try:
        paths = (
            changed_python_paths(arguments.base)
            if arguments.base
            else validate_paths(arguments.paths)
        )
        if not paths:
            print("No committed Python changes to check")
            return 0
        # shellを使わず、設定はルートの正本を明示し、版不一致もRuff自身が拒否する。
        command = [sys.executable, "-m", "ruff", "format", "--config", str(ROOT / "pyproject.toml")]
        if arguments.check:
            command.append("--check")
        return subprocess.call(command + ["--", *paths], cwd=ROOT)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Python formatting failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
