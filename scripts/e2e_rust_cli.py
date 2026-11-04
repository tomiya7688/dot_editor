"""End-to-end check of the release Rust CLI, using only separate processes.

Usage: python scripts/e2e_rust_cli.py <folder holding pixel-cli and cli-anything-dot-editor>

The script imports no project code: it starts the executables, reads their
stdout/stderr/exit codes and decodes the PNG files they write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

PRIMARY = "pixel-cli"
ALIAS = "cli-anything-dot-editor"
DEFAULT_SKILL = Path(__file__).resolve().parents[1] / "skills" / ALIAS / "SKILL.md"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# {
#   責務: [clean_environment: 親のPython環境に頼らない最小の環境変数を作る]
#   処理: [
#     1: PATHを空にし、Windowsの起動に必要なSystemRootだけを引き継ぐ
#   ]
#   引数: []
#   戻り値: [子プロセスに渡す環境変数の辞書]
# }
def clean_environment():
    environment = {"PATH": ""}
    for name in ("SystemRoot", "SYSTEMROOT"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


# {
#   責務: [Process: 1回のプロセス実行の結果を保持する]
#   フィールド: [code: 終了値, stdout: 標準出力, stderr: 標準エラー]
# }
class Process:
    # {
    #   責務: [__init__: 1回のプロセス実行の結果を格納する]
    #   処理: [1: 終了値と両方の出力をそのまま保持する]
    #   引数: [code: 終了値, stdout: 標準出力, stderr: 標準エラー]
    #   戻り値: [なし]
    # }
    def __init__(self, code, stdout, stderr):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    # {
    #   責務: [json: 標準出力が1つのJSONだけであることを確認して解析する]
    #   処理: [1: 標準出力全体をJSONとして解析する。余分な出力があれば失敗にする]
    #   引数: []
    #   戻り値: [解析したJSON値]
    # }
    def json(self):
        try:
            return json.loads(self.stdout)
        except ValueError as error:
            raise AssertionError(f"stdout is not one JSON value: {self.stdout!r}") from error


# {
#   責務: [start: 実行ファイルを標準入力なしで別プロセスとして起動する]
#   処理: [
#     1: 作業フォルダと最小の環境変数を指定して起動する
#     2: 終了値と両方の出力を集める
#   ]
#   引数: [executable: 実行ファイルのパス, arguments: コマンド行の語, cwd: 作業フォルダ]
#   戻り値: [Process]
# }
def start(executable, arguments, cwd):
    result = subprocess.run(
        [str(executable), *arguments],
        cwd=cwd,
        env=clean_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    return Process(result.returncode, result.stdout, result.stderr)


# {
#   責務: [expect: 終了値を確認してから結果を返す]
#   処理: [1: 終了値が期待と違えば、手順名と標準エラーを添えて失敗にする]
#   引数: [step: 手順の名前, process: 実行結果, code: 期待する終了値]
#   戻り値: [同じProcess]
# }
def expect(step, process, code=0):
    assert process.code == code, (step, process.code, process.stderr)
    return process


# {
#   責務: [file_hash: ファイルのSHA-256を求める]
#   処理: [1: ファイル全体のバイト列をハッシュする]
#   引数: [path: 対象のファイル]
#   戻り値: [16進文字列]
# }
def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# {
#   責務: [decode_png: PNGをチャンクごとに検査して画素の行列に戻す]
#   処理: [
#     1: 署名と各チャンクのCRCを確認する
#     2: IHDRが8bit RGBAであることを確認する
#     3: データを伸長し、フィルタ0の走査線を画素へ戻す
#   ]
#   引数: [path: PNGファイル]
#   戻り値: [幅, 高さ, 行ごとのRGBAの行列]
# }
def decode_png(path):
    data = Path(path).read_bytes()
    assert data[:8] == PNG_SIGNATURE, "not a PNG"
    position, header, compressed, kinds = 8, None, b"", []
    while position < len(data):
        # 切り詰められたファイルや、チャンクの長さがファイルを超える壊れ方を先に拒否する。
        assert position + 12 <= len(data), "truncated chunk header"
        (length,) = struct.unpack(">I", data[position : position + 4])
        assert position + 12 + length <= len(data), "chunk runs past the end of the file"
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        (stored,) = struct.unpack(">I", data[position + 8 + length : position + 12 + length])
        assert stored == zlib.crc32(kind + body), f"bad CRC in {kind!r}"
        kinds.append(kind)
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            assert length == 0, "IEND must be empty"
            assert position + 12 == len(data), "extra data after IEND"
        position += 12 + length
    assert kinds[0] == b"IHDR" and kinds[-1] == b"IEND", kinds
    assert kinds.count(b"IHDR") == 1 and kinds.count(b"IEND") == 1, kinds
    idat_positions = [index for index, kind in enumerate(kinds) if kind == b"IDAT"]
    assert idat_positions, "no IDAT chunk"
    assert idat_positions == list(range(idat_positions[0], idat_positions[-1] + 1)), (
        "IDAT chunks must be contiguous"
    )
    assert header is not None, "missing IHDR"
    width, height, depth, color_type, _, _, interlace = header
    assert (depth, color_type, interlace) == (8, 6, 0), header
    raw = zlib.decompress(compressed)
    stride = width * 4 + 1
    assert len(raw) == stride * height, "unexpected pixel data size"
    rows = []
    for y in range(height):
        line = raw[y * stride : (y + 1) * stride]
        assert line[0] == 0, "only filter type 0 is expected"
        rows.append([list(line[1 + x * 4 : 5 + x * 4]) for x in range(width)])
    return width, height, rows


# {
#   責務: [Session: 1つの実行ファイルで、作業フォルダ内のプロジェクトを操作する]
#   フィールド: [executable: 実行ファイル, folder: 作業フォルダ, project: プロジェクトのパス, log: 手順ごとの正規化した結果]
# }
class Session:
    # {
    #   責務: [__init__: 実行ファイルと作業フォルダを結びつけ、プロジェクトの場所と記録を用意する]
    #   処理: [1: 作業フォルダ内のart.jsonを対象にし、空の記録を作る]
    #   引数: [executable: 実行ファイルのパス, folder: 作業フォルダ]
    #   戻り値: [なし]
    # }
    def __init__(self, executable, folder):
        self.executable = executable
        self.folder = Path(folder)
        self.project = str(self.folder / "art.json")
        self.log = []

    # {
    #   責務: [run: --jsonでコマンドを実行し、成功を確認して結果を記録する]
    #   処理: [
    #     1: 共通オプションとプロジェクトを付けて別プロセスで実行する
    #     2: 終了値0とstatus okを確認し、resultを手順ごとに記録する
    #   ]
    #   引数: [step: 手順の名前, words: コマンドの語]
    #   戻り値: [result辞書]
    # }
    def run(self, step, *words):
        process = expect(
            step, start(self.executable, ["--json", "-p", self.project, *words], self.folder)
        )
        document = process.json()
        assert document["status"] == "ok", (step, document)
        # 作業フォルダの場所は名前ごとに違うので、比較用の記録では置き換える。
        folder_text = json.dumps(str(self.folder))[1:-1]
        recorded = json.loads(json.dumps(document).replace(folder_text, "<dir>"))
        self.log.append((step, recorded))
        return document["result"]

    # {
    #   責務: [fail: 失敗するはずのコマンドを実行し、終了値と種別名を確認する]
    #   処理: [
    #     1: 期待する終了値で終わることと、標準出力がエラーJSON、標準エラーに説明があることを確認する
    #   ]
    #   引数: [step: 手順の名前, code: 期待する終了値, error: 期待するerror種別, words: コマンドの語]
    #   戻り値: [なし]
    # }
    def fail(self, step, code, error, *words):
        process = expect(
            step, start(self.executable, ["--json", "-p", self.project, *words], self.folder), code
        )
        document = process.json()
        assert (document["status"], document["error"]) == ("error", error), (step, document)
        assert process.stderr.startswith("error: "), (step, process.stderr)
        self.log.append((step, error, process.stderr.replace(str(self.folder), "<dir>")))

    # {
    #   責務: [export: PNGを書き出し、検査して画素の行列を返す]
    #   処理: [1: export renderを実行し、PNGを検査する]
    #   引数: [name: ファイル名, options: export renderの追加オプション]
    #   戻り値: [幅, 高さ, 画素の行列]
    # }
    def export(self, name, *options):
        path = self.folder / name
        self.run(f"export {name}", "export", "render", "-o", str(path), *options)
        return decode_png(path)


# {
#   責務: [scenario: 別プロセスだけで、作成から書き出しまでを通しで確認する]
#   処理: [
#     1: 作成・塗り・分割・解像度の縮小と復元・細部の破棄・レイヤーを別々のプロセスで行う
#     2: dry-runの不変、失敗系、PNGの寸法・画素・アルファを確認する
#   ]
#   引数: [session: 実行ファイルと作業フォルダを持つSession]
#   戻り値: [手順ごとの結果と、PNGのSHA-256の一覧]
# }
def scenario(session):
    created = session.run("new", "project", "new", "--size", "4")
    assert created["resolution"]["width"] == 4 and created["layer_count"] == 1, created
    assert session.run("status", "status")["resolution"]["width"] == 4
    assert session.run("paint", "pixel", "paint", "1", "1", "#FF0000")["changed"] is True
    assert session.run("sample", "pixel", "sample", "1", "1")["color"] == "#FF0000FF"
    assert session.run("split", "detail", "split", "1", "1")["changed"] is True
    assert session.run("detail info", "detail", "info", "1", "1")["split"] is True
    shrunk = session.run("shrink", "canvas", "resolution", "set", "2", "2")
    assert shrunk["resolution"]["width"] == 2 and shrunk["changed"] is True, shrunk
    _, _, rows = session.export("detail.png", "--resolution", "4", "4")
    assert rows[1][1] == [255, 0, 0, 255] and rows[0][0] == [0, 0, 0, 0], "detail was not kept"
    assert session.run("discard", "detail", "discard", "0", "0")["changed"] is True
    _, _, rows = session.export("discarded.png", "--resolution", "4", "4")
    assert rows[0][0] == [255, 0, 0, 255], "the cell color was not kept after discarding detail"
    restored = session.run("restore", "canvas", "resolution", "set", "4", "4")
    assert restored["resolution"]["width"] == 4 and restored["changed"] is True, restored
    added = session.run("layer add", "layer", "add", "上")
    assert len(added["layers"]) == 2 and added["changed"] is True, added
    assert session.run("paint on layer", "pixel", "paint", "3", "3", "#00FF0080")["changed"] is True
    layers = session.run("layer list", "layer", "list")["layers"]
    assert [layer["name"] for layer in layers] == ["背景", "上"] and layers[1]["active"]
    assert session.run("reload", "status")["layer_count"] == 2
    width, height, rows = session.export("natural.png")
    assert (width, height) == (4, 4)
    assert (
        rows[0][0] == [255, 0, 0, 255]
        and rows[2][2] == [0, 0, 0, 0]
        and rows[3][3] == [0, 255, 0, 128]
    )
    assert session.export("scaled.png", "--size", "9")[:2] == (9, 9)
    assert session.export("resolution.png", "--resolution", "6", "3")[:2] == (6, 3)
    before = file_hash(session.project)
    dry = session.run("dry run", "--dry-run", "pixel", "paint", "0", "3", "#112233")
    assert dry["changed"] is True and file_hash(session.project) == before, (
        "dry-run changed the project"
    )
    session.fail("out of bounds", 1, "out_of_bounds", "pixel", "paint", "9", "9", "#000000")
    assert file_hash(session.project) == before, "a failed edit changed the project"
    session.fail("usage", 2, "usage", "pixel", "paint", "x")
    missing = Session(session.executable, session.folder)
    missing.project = str(session.folder / "missing.json")
    missing.fail("missing file", 1, "file_not_found", "status")
    hashes = [
        file_hash(session.folder / name) for name in ("detail.png", "natural.png", "scaled.png")
    ]
    return session.log, hashes


# {
#   責務: [command_paths: --helpの一覧からコマンドの語の並びを取り出す]
#   処理: [1: commands:以降の行から、<引数>より前の語を集める]
#   引数: [help_text: --helpの標準出力]
#   戻り値: [`pixel paint`のような文字列の一覧]
# }
def command_paths(help_text):
    paths, in_commands = [], False
    for line in help_text.splitlines():
        if line.startswith("commands:"):
            in_commands = True
        elif in_commands and line.startswith("  ") and line.strip():
            words = []
            for word in line.strip().split("  ")[0].split():
                if word.startswith("<"):
                    break
                words.append(word)
            paths.append(" ".join(words))
    return paths


# {
#   責務: [check_help_and_skill: ヘルプ・バージョンの一致と、SKILL.mdの網羅を確認する]
#   処理: [
#     1: 2つの名前で--help・--versionの出力と終了値が一致することを確認する
#     2: ヘルプに出るすべてのコマンドがSKILL.mdに書かれていることを確認する
#   ]
#   引数: [folder: 実行ファイルのフォルダ, suffix: 実行ファイルの拡張子, skill: SKILL.mdのパス, cwd: 作業フォルダ]
#   戻り値: [なし]
# }
def check_help_and_skill(folder, suffix, skill, cwd):
    outputs = {}
    for name in (PRIMARY, ALIAS):
        executable = Path(folder) / f"{name}{suffix}"
        help_run = expect(f"{name} --help", start(executable, ["--help"], cwd))
        version_run = expect(f"{name} --version", start(executable, ["--version"], cwd))
        assert help_run.stderr == "" and version_run.stderr == ""
        outputs[name] = (help_run.stdout, version_run.stdout)
    assert outputs[PRIMARY] == outputs[ALIAS], "the two names print different help or version"
    text = Path(skill).read_text(encoding="utf-8")
    assert text.startswith("---\n") and f"name: {ALIAS}" in text.split("---")[1], (
        "SKILL.md frontmatter"
    )
    paths = command_paths(outputs[PRIMARY][0])
    assert paths, "no commands found in --help"
    missing = [path for path in paths if path not in text]
    assert not missing, f"SKILL.md does not mention: {missing}"


# {
#   責務: [main: リリースバイナリを別プロセスだけで通しで検証する]
#   処理: [
#     1: 引数のフォルダにある2つの実行ファイルを確かめる
#     2: ヘルプ・SKILL.mdを確認し、各名前で同じ手順を新しいフォルダで実行する
#     3: 2つの名前の結果とPNGが同一であることを確認する
#   ]
#   引数: []
#   戻り値: [終了値。成功は0]
# }
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="folder holding the executables")
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL, help="path of SKILL.md")
    arguments = parser.parse_args()
    # 子プロセスは別の作業フォルダで動くため、相対パスのままでは実行ファイルを見失う。
    arguments.folder = arguments.folder.resolve()
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in (PRIMARY, ALIAS):
        assert (arguments.folder / f"{name}{suffix}").is_file(), (
            f"missing executable: {name}{suffix}"
        )
    results = {}
    with tempfile.TemporaryDirectory() as root:
        check_help_and_skill(arguments.folder, suffix, arguments.skill, root)
        for name in (PRIMARY, ALIAS):
            folder = Path(root) / name
            folder.mkdir()
            session = Session(arguments.folder / f"{name}{suffix}", folder)
            results[name] = scenario(session)
    assert results[PRIMARY] == results[ALIAS], "the two names produced different results"
    print("rust cli end-to-end ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
