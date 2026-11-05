//! The machine-readable command catalog (`--commands-json`), generated from the command table.

use serde_json::{Value, json};

use crate::command_docs::{self, DOCS};
use crate::command_spec::{CommandSpec, FlagSpec, Handler};
use crate::command_table::COMMANDS;

/// {
///   責務: [option_entry: 1つのオプションをカタログの項目にする]
///   処理: [
///     1: 長い名前・短い名前・値の個数・種類・説明を並べる
///     2: 値を取らないものは真偽値、取るものは登録された種類にする
///   ]
///   引数: [
///     name: `--`付きの名前
///     short: 短い名前
///     values: 値の個数
///     kind: 値の種類
///     required: 必須か
///     description_ja: 日本語の説明
///   ]
///   戻り値: [オプションのJSON値]
/// }
fn option_entry(
    name: &str,
    short: Option<&str>,
    values: usize,
    kind: &str,
    required: bool,
    description_ja: &str,
) -> Value {
    let aliases: Vec<&str> = short.into_iter().collect();
    json!({
        "name": name,
        "aliases": aliases,
        "kind": if values == 0 { "boolean" } else { kind },
        "min_values": values,
        "max_values": values,
        "required": required,
        "description_ja": description_ja,
    })
}

/// {
///   責務: [global_options: すべてのコマンドに共通するオプションの一覧を作る]
///   処理: [
///     1: 実際に受け付ける共通オプションを、解析の定義と同じ順に並べる
///   ]
///   引数: []
///   戻り値: [共通オプションのJSON配列]
/// }
fn global_options() -> Vec<Value> {
    let mut lock = option_entry(
        "--lock-timeout-ms",
        None,
        1,
        "integer",
        false,
        "同じ作品のロックを待つ最長時間（0〜60000ミリ秒）",
    );
    lock["default"] = json!(5000);
    vec![
        option_entry(
            "--project",
            Some("-p"),
            1,
            "path",
            false,
            "対象のプロジェクトファイル（ほとんどのコマンドで必須）",
        ),
        option_entry(
            "--json",
            None,
            0,
            "boolean",
            false,
            "標準出力を1つのJSONだけにする",
        ),
        option_entry(
            "--dry-run",
            None,
            0,
            "boolean",
            false,
            "保存や書き出しをせず、結果だけを評価する",
        ),
        option_entry(
            "--if-revision",
            None,
            1,
            "string",
            false,
            "statusのrevisionと同じときだけ保存する。違えばrevision_conflictで何も保存しない",
        ),
        lock,
        option_entry(
            "--help",
            Some("-h"),
            0,
            "boolean",
            false,
            "ヘルプを表示する",
        ),
        option_entry(
            "--version",
            Some("-V"),
            0,
            "boolean",
            false,
            "バージョンを表示する",
        ),
        option_entry(
            "--commands-json",
            None,
            0,
            "boolean",
            false,
            "このコマンド表をJSONで表示する（他の引数とは併用できない）",
        ),
    ]
}

/// {
///   責務: [usage: コマンドの書式の1行を作る]
///   処理: [
///     1: 語、位置引数、各オプションを順に並べる
///     2: 必須でないオプションは角括弧で囲む
///   ]
///   引数: [
///     spec: コマンドの定義
///   ]
///   戻り値: [書式の文字列]
/// }
fn usage(spec: &CommandSpec) -> String {
    let mut line = spec.path.join(" ");
    for name in spec.positionals {
        line.push_str(&format!(" <{name}>"));
    }
    for flag in spec.flags {
        let values = " <v>".repeat(flag.values);
        if flag.name == "--output" {
            line.push_str(&format!(" {}{values}", flag.name));
        } else {
            line.push_str(&format!(" [{}{values}]", flag.name));
        }
    }
    line
}

/// {
///   責務: [flag_entry: コマンド固有のフラグをカタログのオプション項目にする]
///   処理: [
///     1: 登録された種類と日本語の説明を引く（無ければ失敗させる）
///     2: 必須かどうかを名前から決める
///   ]
///   引数: [
///     flag: フラグの定義
///   ]
///   戻り値: [オプションのJSON値]
/// }
fn flag_entry(flag: &FlagSpec) -> Value {
    let (kind, description) = command_docs::option_ja(flag.name)
        .unwrap_or_else(|| panic!("no Japanese description for {}", flag.name));
    option_entry(
        flag.name,
        flag.short,
        flag.values,
        kind,
        flag.name == "--output",
        description,
    )
}

/// {
///   責務: [positional_entry: 位置引数をカタログの項目にする]
///   処理: [
///     1: 登録された種類・説明・選択肢を引く（無ければ失敗させる）
///   ]
///   引数: [
///     name: 位置引数の名前
///   ]
///   戻り値: [位置引数のJSON値]
/// }
fn positional_entry(name: &str) -> Value {
    let (kind, description) = command_docs::positional_ja(name)
        .unwrap_or_else(|| panic!("no Japanese description for positional {name}"));
    let mut entry = json!({"name": name, "kind": kind, "description_ja": description});
    let choices = command_docs::positional_choices(name);
    if !choices.is_empty() {
        entry["choices"] = json!(choices);
    }
    entry
}

/// {
///   責務: [side_effects: コマンドが取り得る副作用の上限を求める]
///   処理: [
///     1: 操作の種類から、作成・書き込み・書き出しを決める
///     2: --forceがあれば置き換え、細部を捨てる可能性があれば破棄を加える
///   ]
///   引数: [
///     spec: コマンドの定義
///   ]
///   戻り値: [副作用名の並び]
/// }
fn side_effects(spec: &CommandSpec) -> Vec<&'static str> {
    let mut effects = match spec.handler {
        Handler::Create(_) => vec!["creates_project"],
        Handler::Read(_) => vec![],
        Handler::Edit(_) => vec!["writes_project"],
        Handler::Export(_) => vec!["writes_output"],
    };
    if spec.flags.iter().any(|flag| flag.name == "--force") {
        effects.push("overwrites_existing");
    }
    if spec
        .flags
        .iter()
        .any(|flag| flag.name == "--discard-detail")
        || spec.path == ["detail", "discard"]
    {
        effects.push("discards_detail");
    }
    effects
}

/// {
///   責務: [command_entry: 1つのコマンドをカタログの項目にする]
///   処理: [
///     1: 定義と日本語の説明表から、書式・引数・オプション・副作用・使用例を作る
///     2: 使用例は、プログラム名と共通オプションを先頭に付けた引数の配列にする
///   ]
///   引数: [
///     spec: コマンドの定義
///   ]
///   戻り値: [コマンドのJSON値]
/// }
fn command_entry(spec: &CommandSpec) -> Value {
    let id = spec.operation();
    let doc = DOCS
        .iter()
        .find(|doc| doc.id == id)
        .unwrap_or_else(|| panic!("no Japanese documentation for {id}"));
    let effect = match spec.handler {
        Handler::Create(_) => "create",
        Handler::Read(_) => "read",
        Handler::Edit(_) => "edit",
        Handler::Export(_) => "export",
    };
    let mut argv = vec!["pixel-cli", "--json", "-p", "art.json"];
    argv.extend_from_slice(doc.example);
    json!({
        "id": id,
        "path": spec.path,
        "usage": usage(spec),
        "summary": spec.summary,
        "summary_ja": doc.summary_ja,
        "effect": effect,
        "requires_project": true,
        "positionals": spec.positionals.iter().map(|name| positional_entry(name)).collect::<Vec<_>>(),
        "options": spec.flags.iter().map(flag_entry).collect::<Vec<_>>(),
        "side_effects": side_effects(spec),
        "examples": [{"argv": argv, "description_ja": doc.example_ja}],
    })
}

/// {
///   責務: [build: コマンド表全体をカタログ（schema v1）のJSON値にする]
///   処理: [
///     1: 実装の種類・版・入口・共通オプションを記す
///     2: コマンド表の順にコマンドを並べる
///   ]
///   引数: []
///   戻り値: [カタログのJSON値]
/// }
pub fn build() -> Value {
    json!({
        "schema_version": 1,
        "cli_implementation": "rust",
        "cli_version": env!("CARGO_PKG_VERSION"),
        "entrypoint": "pixel-cli",
        "global_options": global_options(),
        "commands": COMMANDS.iter().map(command_entry).collect::<Vec<_>>(),
    })
}

/// {
///   責務: [render: カタログを「JSON1個とLF」の標準出力用の文字列にする]
///   処理: [
///     1: カタログを整形したJSONにし、末尾にLFを付ける
///   ]
///   引数: []
///   戻り値: [標準出力へ出す文字列]
/// }
pub fn render() -> String {
    let mut text = serde_json::to_string_pretty(&build()).expect("catalog serializes");
    text.push('\n');
    text
}
