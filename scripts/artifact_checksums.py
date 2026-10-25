"""Create or inspect checksums of final build outputs; this does not verify signatures."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile


# {
#   責務: [release_artifact_paths: 現行ビルドが生成する最終3成果物だけを選ぶ]
#   処理: [1: 種別ごとの一意性と版の一致を確認する, 2: 不明なファイル・リンク・空ファイルを拒否する]
#   引数: [directory: ビルド専用のdistディレクトリ]
#   戻り値: [ファイル名順の成果物パス。欠落・重複・不正な入力は例外]
# }
def release_artifact_paths(directory):
    # 古い版を含むdistを黙って署名せず、今回のwheel・sdist・Windows ZIPを一組として扱う。
    directory = Path(directory).resolve()
    selected = []
    for pattern in ("hyper_dot_editor-*.whl", "hyper_dot_editor-*.tar.gz", "HyperDotEditor-windows-x64.zip"):
        matches = list(directory.glob(pattern))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one artifact for {pattern}, found {len(matches)}")
        selected.append(matches[0])
    wheel_version = selected[0].name.split("-")[1]
    source_version = selected[1].name.removeprefix("hyper_dot_editor-").removesuffix(".tar.gz")
    if wheel_version != source_version:
        raise ValueError("Wheel and source distribution versions differ")
    for path in selected:
        if (not re.fullmatch(r"[A-Za-z0-9_.+-]+", path.name) or path.is_symlink()
                or not path.is_file() or path.stat().st_size == 0):
            raise ValueError(f"Artifact must be a non-empty regular file, not a symlink: {path}")
    # 新しい成果物が追加されたら一覧と検証対象も明示的に更新する。
    unexpected = {path.name for path in directory.iterdir() if path.is_file()}
    unexpected -= {path.name for path in selected} | {"SHA256SUMS"}
    if unexpected:
        raise ValueError(f"Unlisted output files: {sorted(unexpected)}")
    return sorted(selected, key=lambda path: path.name)


# {
#   責務: [checksum_manifest: 最終成果物の決定的なSHA256SUMS本文を計算する]
#   処理: [1: 検証済み成果物を名前順にストリーム読取する, 2: SHA-256とbasenameを並べる]
#   引数: [directory: ビルド専用のdistディレクトリ]
#   戻り値: [LF終端のASCII manifest本文。読取失敗時は例外]
# }
def checksum_manifest(directory):
    # 大きいZIPも1MiB単位で読み、メモリ使用量を成果物サイズに比例させない。
    lines = []
    for path in release_artifact_paths(directory):
        digest = hashlib.sha256()
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.name}\n")
    return "".join(lines)


# {
#   責務: [write_manifest: 完全に計算したmanifestだけを原子的に保存する]
#   処理: [1: 全成果物を検証して本文を計算する, 2: 同一ディレクトリの一時ファイルから置換する]
#   引数: [directory: ビルド専用のdistディレクトリ]
#   戻り値: [保存先パス。失敗時は既存manifestを維持し例外]
# }
def write_manifest(directory):
    content = checksum_manifest(directory)
    destination = Path(directory) / "SHA256SUMS"
    if destination.is_symlink():
        raise ValueError("SHA256SUMS must not be a symlink")
    temporary_path = None
    try:
        # 読込・計算が失敗した場合や書込途中の状態を、署名対象へ渡さない。
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", newline="",
                                         dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination


# {
#   責務: [verify_manifest: manifestを実成果物から再計算した本文と照合する]
#   処理: [1: 参照先リンクを拒否する, 2: 実成果物のhash・一覧と本文全体を比較する]
#   引数: [directory: ビルド専用のdistディレクトリ]
#   戻り値: [なし。不一致・欠落時は例外。ファイル変更はしない]
# }
def verify_manifest(directory):
    # 未信頼manifest内のパスは開かず、固定した成果物集合からだけ再計算する。
    manifest = Path(directory) / "SHA256SUMS"
    if manifest.is_symlink():
        raise ValueError("SHA256SUMS must not be a symlink")
    expected = checksum_manifest(directory).encode("ascii")
    # 不正に大きいmanifestでも必要な長さ+1byteまでしかメモリへ読み込まない。
    with manifest.open("rb") as stream:
        if stream.read(len(expected) + 1) != expected:
            raise ValueError("SHA256SUMS does not match the current final artifacts")


# {
#   責務: [main: manifestの生成または読取専用の整合性検査を実行する]
#   処理: [1: 引数で処理を選択する, 2: 結果を表示し失敗を非0で返す]
#   引数: [argv: CLI引数。Noneならプロセスの引数]
#   戻り値: [成功0、検査・保存失敗2]
# }
def main(argv=None):
    # hashの一致を、署名や配布許可の成功とは表示しない。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if not arguments.check:
            write_manifest(arguments.directory)
        verify_manifest(arguments.directory)
        print("SHA256SUMS matches final artifacts (signature verification is separate)")
        return 0
    except (OSError, ValueError) as error:
        print(f"Artifact checksum verification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
