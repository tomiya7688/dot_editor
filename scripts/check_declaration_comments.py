"""Check this repository's Japanese declaration-comment convention, not the full spec.

Default: migrated Rust core and compatibility/checker scripts. With --changed-base,
also audit every declaration in owned Python/Rust files changed since that revision.
Python uses AST; Rust scans ordinary declarations outside literals/comments, so
macro-generated declarations require code review. Semantic accuracy needs review.
"""
from __future__ import annotations

import argparse
import ast
import io
from pathlib import Path
import re
import subprocess
import tokenize

ROOT = Path(__file__).resolve().parents[1]
RUST_DECLARATION = re.compile(
    r"\b(?:(?:pub(?:\([^)]*\))?|const|async|unsafe|extern(?:\s+\"[^\"]*\")?)\s+)*"
    r"(fn|struct|enum|trait)\s+(\w+)", re.MULTILINE
)
RUST_NONCODE = re.compile(
    r'//[^\n]*|/\*|(?:br|r)(?P<hashes>\#*)"|(?:b|c)?"(?:\\[\s\S]|[^"\\])*"'
    r"|b?'(?:\\(?:[^\n]|u\{[^}]*\})|[^'\\\n])'"
)
FIELDS = {"function": ("責務", "処理", "引数", "戻り値"), "type": ("責務", "フィールド")}


# {
#   責務: [rust_code: Rustの非コードを改行位置を維持してマスクする]
#   処理: [
#     1: 文字列・raw文字列・文字リテラル・コメントを検出する
#     2: 入れ子コメントとraw終端まで読み飛ばす
#     3: 改行以外を空白へ置換する
#   ]
#   引数: [
#     text: 検査するソース文字列
#   ]
#   戻り値: [同じ長さの宣言検出用ソース]
# }
def rust_code(text):
    masked = list(text)
    position = 0
    while match := RUST_NONCODE.search(text, position):
        end = match.end()
        if match.group() == "/*":
            depth = 1
            while depth and end < len(text):
                if text.startswith("/*", end):
                    depth += 1
                    end += 2
                elif text.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
        elif match.group("hashes") is not None:
            closing = '"' + match.group("hashes")
            close = text.find(closing, end)
            end = len(text) if close < 0 else close + len(closing)
        for index in range(match.start(), end):
            if masked[index] != "\n":
                masked[index] = " "
        position = end
    return "".join(masked)


# {
#   責務: [declarations: ソース内の関数・型の宣言位置を列挙する]
#   処理: [
#     1: PythonはASTで内部宣言も走査する
#     2: Rustは非コードを除外して宣言と直前属性を検出する
#   ]
#   引数: [
#     text: 検査するソース文字列
#     suffix: 対象言語の拡張子
#   ]
#   戻り値: [先頭行番号・宣言名・種別のイテレータ]
# }
def declarations(text, suffix):
    if suffix == ".py":
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                anchor = min([node.lineno] + [item.lineno for item in node.decorator_list])
                kind = "type" if isinstance(node, ast.ClassDef) else "function"
                yield anchor - 1, node.name, kind
    elif suffix == ".rs":
        code = rust_code(text)
        for match in RUST_DECLARATION.finditer(code):
            anchor = code.count("\n", 0, match.start())
            lines = code.splitlines()
            while anchor and lines[anchor - 1].strip().endswith("]"):
                candidate = anchor - 1
                while candidate and not lines[candidate].lstrip().startswith("#["):
                    candidate -= 1
                if not lines[candidate].lstrip().startswith("#["):
                    break
                anchor = candidate
            yield anchor, match[2], "function" if match[1] == "fn" else "type"
    else:
        raise ValueError(f"unsupported source suffix: {suffix}")


# {
#   責務: [comment_lines: 独立した文書コメント行の本文を取得する]
#   処理: [
#     1: Pythonはtokenizeでコメント行を検出する
#     2: Rustは三重スラッシュの文書コメントを取得する
#   ]
#   引数: [
#     text: 検査するソース文字列
#     suffix: 対象言語の拡張子
#   ]
#   戻り値: [ゼロ始まり行番号から本文への辞書]
# }
def comment_lines(text, suffix):
    if suffix == ".py":
        return {item.start[0] - 1: item.string[1:].strip()
                for item in tokenize.generate_tokens(io.StringIO(text).readline)
                if item.type == tokenize.COMMENT and not item.line[:item.start[1]].strip()}
    return {index: match[1].strip() for index, line in enumerate(text.splitlines())
            if (match := re.match(r"\s*///(?!/)(.*)$", line))}


# {
#   責務: [attached_block: 宣言に直接付いた構造化コメントを取得する]
#   処理: [
#     1: 直前の閉じ括弧を確認する
#     2: 連続コメントを開始括弧まで逆に読む
#   ]
#   引数: [
#     comments: 行番号とコメント本文の辞書
#     anchor: 属性を含む宣言の先頭行番号
#   ]
#   戻り値: [本文、存在しなければNone]
# }
def attached_block(comments, anchor):
    cursor = anchor - 1
    if comments.get(cursor) != "}":
        return None
    content = []
    while cursor in comments:
        line = comments[cursor]
        content.append(line)
        if line == "{":
            return "\n".join(reversed(content))
        cursor -= 1
    return None


# {
#   責務: [validate_block: 必須リストと括弧の構造を検査する]
#   処理: [
#     1: 引用文字列を区別して括弧と直下の項目を読む
#     2: 必須項目の欠落・重複・空の説明を検査する
#   ]
#   引数: [
#     block: コメント本文またはNone
#     kind: 関数または型の種別
#   ]
#   戻り値: [構造エラーのリスト、意味の正しさは判定しない]
# }
def validate_block(block, kind):
    if block is None:
        return ["宣言直前の構造化コメントがない"]
    stack = []
    fields = {}
    pending = None
    value_start = 0
    quoted = escaped = False
    line_start = 0
    for index, character in enumerate(block):
        if index == line_start and stack == ["{"]:
            match = re.match(r'\s*(?:"([^"\n]+)"|([^:\n]+?))\s*:\s*\[', block[index:])
            if match:
                pending = match[1] or match[2]
                value_start = index + match.end()
        if character == "\n":
            line_start = index + 1
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
            continue
        if character in "[{":
            stack.append(character)
        elif character in "]}":
            if not stack or stack.pop() != {"]": "[", "}": "{"}[character]:
                return ["コメントの括弧が対応していない"]
            if pending and character == "]" and stack == ["{"]:
                fields.setdefault(pending, []).append(block[value_start:index])
                pending = None
    if stack or quoted:
        return ["コメントの括弧が閉じていない"]
    errors = []
    for key in FIELDS[kind]:
        values = fields.get(key, [])
        if len(values) != 1:
            errors.append(f"{key}のリストがない、または重複している")
        elif key not in ("引数", "フィールド") and not values[0].strip():
            errors.append(f"{key}の説明が空")
    return errors


# {
#   責務: [audit_text: 1ソース内の全宣言を検査する]
#   処理: [
#     1: コメント行と宣言位置を取得する
#     2: 付属ブロックを検査して位置・名前付き診断を集める
#   ]
#   引数: [
#     text: 検査するソース文字列
#     suffix: 対象言語の拡張子
#   ]
#   戻り値: [宣言数とエラー文字列の組]
# }
def audit_text(text, suffix):
    comments = comment_lines(text, suffix)
    errors = []
    count = 0
    for anchor, name, kind in declarations(text, suffix):
        count += 1
        for error in validate_block(attached_block(comments, anchor), kind):
            errors.append(f"{anchor + 1}: {name}: {error}")
    return count, errors


# {
#   責務: [default_paths: 移行済み宣言の継続検査対象を取得する]
#   処理: [
#     1: Rust Coreのソース・テスト・exampleを列挙する
#     2: 移行済みCLI・互換スクリプト・検査器・宣言コメント移行済みテストを加える
#   ]
#   引数: []
#   戻り値: [対象パスのリスト]
# }
def default_paths():
    return sorted((ROOT / "rust" / "crates" / "hyper-dot-core").rglob("*.rs")) + [
        ROOT / "src" / "pixel_cli.py",
        ROOT / "scripts" / "test_rust_json_compat.py",
        ROOT / "scripts" / "distribution_notices.py",
        ROOT / "scripts" / "smoke_distribution.py",
        ROOT / "scripts" / "check_declaration_comments.py",
        ROOT / "tests" / "test_declaration_comments.py",
        ROOT / "tests" / "test_display_safety.py",
        ROOT / "tests" / "test_keyboard_focus_regions.py",
        ROOT / "tests" / "test_menu_structure.py",
        ROOT / "tests" / "test_palette.py",
        ROOT / "tests" / "test_project_json.py",
        ROOT / "tests" / "test_commands.py",
    ]


# {
#   責務: [changed_paths: 指定履歴からHEADまでに変わった所有ソースを取得する]
#   処理: [
#     1: Gitで追加・変更・複製・改名パスを取得する
#     2: 存在するPython・Rustファイルへ絞る
#   ]
#   引数: [
#     base: 比較元のGitリビジョン
#   ]
#   戻り値: [対象パスのリスト、Git失敗なら例外]
# }
def changed_paths(base):
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "-z", base, "HEAD", "--",
         "src", "scripts", "tests", "rust"], cwd=ROOT, check=True, capture_output=True,
    )
    paths = [ROOT / name for name in result.stdout.decode("utf-8").split("\0") if name]
    return [path for path in paths if path.suffix in (".py", ".rs") and path.is_file()]


# {
#   責務: [main: 宣言コメント検査を実行する]
#   処理: [
#     1: 明示または既定パスと履歴の変更対象を集める
#     2: 宣言不備と読み取り・構文エラーを集める
#     3: 診断と集計を出力する
#   ]
#   引数: []
#   戻り値: [不備があればTrueで異常終了、正常ならFalse]
# }
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--changed-base", help="also audit owned sources changed from revision to HEAD")
    options = parser.parse_args()
    paths = options.paths or default_paths()
    if options.changed_base:
        paths += changed_paths(options.changed_base)
    total = 0
    failures = []
    for path in sorted(set(path.resolve() for path in paths)):
        try:
            count, errors = audit_text(path.read_text(encoding="utf-8-sig"), path.suffix)
            total += count
            failures.extend(f"{path}:{error}" for error in errors)
        except (OSError, SyntaxError, tokenize.TokenError, ValueError) as error:
            failures.append(f"{path}: {error}")
    for failure in failures:
        print(failure)
    print(f"Declaration comments: {total} declarations, {len(failures)} errors")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
