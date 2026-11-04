//! The two executable names must reach exactly the same behavior.

use std::fs;
use std::path::Path;
use std::process::{Command, Stdio};

/// {
///   責務: [Observed: 1回の実行の終了値と両方の出力を保持する]
///   フィールド: [
///     code: 終了値
///     stdout: 標準出力
///     stderr: 標準エラー
///   ]
/// }
#[derive(Debug, Eq, PartialEq)]
struct Observed {
    code: Option<i32>,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

/// {
///   責務: [observe: 指定の実行ファイルを標準入力なしで起動して出力を集める]
///   処理: [
///     1: 実行ファイルと引数を起動し、終了値と出力を集める
///   ]
///   引数: [
///     executable: 実行ファイルのパス
///     arguments: コマンド行の語
///   ]
///   戻り値: [観測結果]
/// }
fn observe(executable: &str, arguments: &[&str]) -> Observed {
    let output = Command::new(executable)
        .args(arguments)
        .stdin(Stdio::null())
        .output()
        .expect("executable starts");
    Observed {
        code: output.status.code(),
        stdout: output.stdout,
        stderr: output.stderr,
    }
}

/// {
///   責務: [both_names_behave_identically: 2つの名前で、成功・失敗・使い方の誤りの出力が一致することを回帰検証する]
///   処理: [
///     1: 同じプロジェクトを2つの名前で別々に作り、ヘルプ・バージョン・状態・失敗を同じ引数で実行する
///     2: 終了値と標準出力・標準エラーが同一であることを比べる
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn both_names_behave_identically() {
    let folder = Path::new(env!("CARGO_TARGET_TMPDIR")).join("cli-alias");
    let _ = fs::remove_dir_all(&folder);
    fs::create_dir_all(&folder).unwrap();
    let primary = env!("CARGO_BIN_EXE_pixel-cli");
    let alias = env!("CARGO_BIN_EXE_cli-anything-dot-editor");
    let project = folder.join("art.json").to_string_lossy().into_owned();
    let created = observe(
        alias,
        &["--json", "-p", &project, "project", "new", "--size", "3"],
    );
    assert_eq!(created.code, Some(0));
    let missing = folder.join("missing.json").to_string_lossy().into_owned();
    let cases: [Vec<&str>; 7] = [
        vec!["--help"],
        vec!["--version"],
        vec!["--json", "--version"],
        vec!["pixel", "paint", "--help"],
        vec!["--json", "-p", &project, "status"],
        vec!["--json", "-p", &missing, "status"],
        vec!["--json", "-p", &project, "frobnicate"],
    ];
    for arguments in cases {
        let first = observe(primary, &arguments);
        let second = observe(alias, &arguments);
        assert_eq!(first, second, "{arguments:?}");
    }
}
