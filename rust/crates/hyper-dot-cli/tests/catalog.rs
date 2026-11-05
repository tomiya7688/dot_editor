//! `--commands-json`: the catalog printed by the real binary matches the real command set and help.

use std::collections::HashSet;
use std::process::{Command, Stdio};

use serde_json::Value;

/// {
///   責務: [run: 標準入力を閉じてpixel-cliを実行し、終了値・標準出力・標準エラーを返す]
///   処理: [
///     1: ビルド済みのバイナリを指定の引数で起動して出力を集める
///   ]
///   引数: [
///     arguments: コマンド行の語
///   ]
///   戻り値: [終了値、標準出力、標準エラー]
/// }
fn run(arguments: &[&str]) -> (i32, String, String) {
    let output = Command::new(env!("CARGO_BIN_EXE_pixel-cli"))
        .args(arguments)
        .stdin(Stdio::null())
        .output()
        .expect("pixel-cli starts");
    (
        output.status.code().expect("exit code"),
        String::from_utf8(output.stdout).unwrap(),
        String::from_utf8(output.stderr).unwrap(),
    )
}

/// {
///   責務: [catalog: コマンド表を取得してJSONとして読む]
///   処理: [
///     1: --commands-jsonを実行し、成功・標準エラー空・JSON1個とLFを確認する
///   ]
///   引数: []
///   戻り値: [カタログのJSON値]
/// }
fn catalog() -> Value {
    let (code, stdout, stderr) = run(&["--commands-json"]);
    assert_eq!(code, 0);
    assert!(stderr.is_empty(), "{stderr}");
    assert!(stdout.ends_with('\n') && !stdout.ends_with("\n\n"));
    serde_json::from_str(&stdout).expect("one JSON value")
}

/// {
///   責務: [catalog_matches_help_for_every_command: 全コマンドのカタログと個別ヘルプが一致することを検証する]
///   処理: [
///     1: 22件のコマンドがあり、IDが一意で日本語説明が空でないことを確認する
///     2: 各コマンドの個別ヘルプに、カタログのオプション名と別名がすべて載っていることを確認する
///     3: 位置引数の数が書式と一致することを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn catalog_matches_help_for_every_command() {
    let catalog = catalog();
    assert_eq!(catalog["schema_version"], 1);
    assert_eq!(catalog["cli_implementation"], "rust");
    assert_eq!(catalog["cli_version"], env!("CARGO_PKG_VERSION"));
    let commands = catalog["commands"].as_array().unwrap();
    assert_eq!(commands.len(), 22);
    let mut ids = HashSet::new();
    for command in commands {
        let id = command["id"].as_str().unwrap();
        assert!(ids.insert(id.to_owned()), "duplicate {id}");
        assert!(!command["summary_ja"].as_str().unwrap().trim().is_empty());
        let words: Vec<&str> = command["path"]
            .as_array()
            .unwrap()
            .iter()
            .map(|word| word.as_str().unwrap())
            .collect();
        let mut arguments = words.clone();
        arguments.push("--help");
        let (code, help, _) = run(&arguments);
        assert_eq!(code, 0, "{id}");
        for option in command["options"].as_array().unwrap() {
            assert!(
                help.contains(option["name"].as_str().unwrap()),
                "{id}: {help}"
            );
            for alias in option["aliases"].as_array().unwrap() {
                assert!(help.contains(alias.as_str().unwrap()), "{id}: {help}");
            }
        }
        for positional in command["positionals"].as_array().unwrap() {
            let name = positional["name"].as_str().unwrap();
            assert!(help.contains(&format!("<{name}>")), "{id}: {help}");
        }
        let example = command["examples"][0]["argv"].as_array().unwrap();
        assert_eq!(example[0], "pixel-cli");
        assert!(example.len() > 4, "{id}");
    }
}

/// {
///   責務: [catalog_is_deterministic_and_exclusive: 2回の出力が同一で、他の引数との併用は使い方の誤りになることを検証する]
///   処理: [
///     1: 2回取得したバイト列が一致することを確認する
///     2: --jsonとの併用だけは同じ出力になることを確認する
///     3: プロジェクト指定・dry-run・help・version・コマンド語との併用は終了値2で、ファイルを作らないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn catalog_is_deterministic_and_exclusive() {
    let (_, first, _) = run(&["--commands-json"]);
    let (_, second, _) = run(&["--commands-json"]);
    assert_eq!(first, second);
    let (code, with_json, _) = run(&["--commands-json", "--json"]);
    assert_eq!((code, with_json.as_str()), (0, first.as_str()));
    let missing =
        std::path::Path::new(env!("CARGO_TARGET_TMPDIR")).join("catalog-never-created.json");
    let project = missing.to_string_lossy().into_owned();
    for arguments in [
        vec!["--commands-json", "-p", project.as_str()],
        vec!["--commands-json", "--dry-run"],
        vec!["--commands-json", "--help"],
        vec!["--commands-json", "--version"],
        vec!["--commands-json", "status"],
        vec![
            "--commands-json",
            "--if-revision",
            "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        ],
    ] {
        let (code, stdout, stderr) = run(&arguments);
        assert_eq!(code, 2, "{arguments:?}: {stdout}");
        assert!(stderr.contains("--commands-json"), "{stderr}");
    }
    assert!(!missing.exists());
}
