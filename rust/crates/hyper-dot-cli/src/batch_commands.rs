//! `batch apply`: run an ordered list of existing edits as one all-or-nothing transaction.

use std::fs;
use std::io::ErrorKind;
use std::path::Path;

use hyper_dot_core::layered_canvas::LayeredCanvas;
use hyper_dot_core::parse_strict_json;
use serde_json::{Map, Value, json};

use crate::cli_error::{CliError, EXIT_USAGE};
use crate::command_spec::{CommandSpec, EditResult, Handler};
use crate::command_table::COMMANDS;
use crate::parsed_command::ParsedCommand;

/// バッチファイルの大きさの上限（バイト）。
pub const MAX_BATCH_BYTES: u64 = 8 * 1024 * 1024;

/// 1つのバッチに入れられる操作数の上限。
pub const MAX_OPERATIONS: usize = 10_000;

/// {
///   責務: [invalid: バッチの内容の不備を表す失敗を作る]
///   処理: [
///     1: 種別invalid_batchで説明を付ける
///   ]
///   引数: [
///     message: 何が不正かの説明
///   ]
///   戻り値: [実行失敗]
/// }
fn invalid(message: impl Into<String>) -> CliError {
    CliError::failure("invalid_batch", message)
}

/// {
///   責務: [field_name: 位置引数に対応するJSONのフィールド名を返す]
///   処理: [
///     1: 表示状態の引数だけは、真偽値のvisibleとして扱う
///   ]
///   引数: [
///     positional: 位置引数の名前
///   ]
///   戻り値: [JSONのフィールド名]
/// }
fn field_name(positional: &str) -> &str {
    if positional == "state" {
        "visible"
    } else {
        positional
    }
}

/// {
///   責務: [flag_field: コマンド固有のフラグに対応するJSONのフィールド名を返す]
///   処理: [
///     1: バッチで使えるフラグだけを対応づける
///   ]
///   引数: [
///     flag: `--`付きのオプション名
///   ]
///   戻り値: [フィールド名。バッチで使えないフラグはNone]
/// }
fn flag_field(flag: &str) -> Option<&'static str> {
    match flag {
        "--child" => Some("child"),
        "--discard-detail" => Some("discard_detail"),
        "--layer" => Some("layer"),
        _ => None,
    }
}

/// {
///   責務: [find_spec: バッチで使えるopに対応するコマンド定義を探す]
///   処理: [
///     1: 操作名が一致する、作品を編集するコマンドだけを候補にする
///     2: バッチ自身は入れ子にできない
///   ]
///   引数: [
///     op: 操作名（例: pixel.paint）
///   ]
///   戻り値: [コマンド定義。無ければNone]
/// }
fn find_spec(op: &str) -> Option<&'static CommandSpec> {
    COMMANDS.iter().find(|spec| {
        spec.operation() == op && matches!(spec.handler, Handler::Edit(_)) && op != "batch.apply"
    })
}

/// {
///   責務: [unsigned_word: 0以上の整数のフィールドを引数の語にする]
///   処理: [
///     1: 小数・負数・文字列を拒否し、32ビットに収まる整数だけを文字列にする
///   ]
///   引数: [
///     index: 操作の番号
///     field: フィールド名
///     value: JSON値
///   ]
///   戻り値: [引数の語]
/// }
fn unsigned_word(index: usize, field: &str, value: &Value) -> Result<String, CliError> {
    match value.as_u64() {
        Some(number) if number <= u64::from(u32::MAX) => Ok(number.to_string()),
        _ => Err(invalid(format!(
            "operations[{index}].{field} must be an integer from 0 to {}",
            u32::MAX
        ))),
    }
}

/// {
///   責務: [string_word: 文字列のフィールドを引数の語にする]
///   処理: [
///     1: 文字列だけを受け付ける
///   ]
///   引数: [
///     index: 操作の番号
///     field: フィールド名
///     value: JSON値
///   ]
///   戻り値: [引数の語]
/// }
fn string_word(index: usize, field: &str, value: &Value) -> Result<String, CliError> {
    value
        .as_str()
        .map(str::to_owned)
        .ok_or_else(|| invalid(format!("operations[{index}].{field} must be a string")))
}

/// {
///   責務: [operation_words: バッチの1操作を、単独のコマンドと同じ引数の語に変換する]
///   処理: [
///     1: opを探し、許されたフィールド以外（未知のフィールド）を拒否する
///     2: 必須の位置引数を順に型検査して語にする
///     3: 任意のフラグ（child・discard_detail・layer）を語に追加する
///   ]
///   引数: [
///     index: 操作の番号
///     entry: 操作のJSON値
///   ]
///   戻り値: [コマンドの定義と引数の語]
/// }
fn operation_words(
    index: usize,
    entry: &Value,
) -> Result<(&'static CommandSpec, Vec<String>), CliError> {
    let object = entry
        .as_object()
        .ok_or_else(|| invalid(format!("operations[{index}] must be an object")))?;
    let op = object
        .get("op")
        .and_then(Value::as_str)
        .ok_or_else(|| invalid(format!("operations[{index}].op must be a string")))?;
    let spec =
        find_spec(op).ok_or_else(|| invalid(format!("operations[{index}]: unknown op `{op}`")))?;
    let mut allowed: Vec<&str> = vec!["op"];
    allowed.extend(spec.positionals.iter().map(|name| field_name(name)));
    allowed.extend(spec.flags.iter().filter_map(|flag| flag_field(flag.name)));
    if let Some(unknown) = object.keys().find(|key| !allowed.contains(&key.as_str())) {
        return Err(invalid(format!(
            "operations[{index}]: unknown field `{unknown}` for `{op}`"
        )));
    }
    let mut words: Vec<String> = spec.path.iter().map(|word| (*word).to_owned()).collect();
    for positional in spec.positionals {
        let field = field_name(positional);
        let value = object
            .get(field)
            .ok_or_else(|| invalid(format!("operations[{index}]: `{op}` needs `{field}`")))?;
        let word = match *positional {
            "x" | "y" | "width" | "height" => unsigned_word(index, field, value)?,
            "state" => match value.as_bool() {
                Some(true) => "on".to_owned(),
                Some(false) => "off".to_owned(),
                None => {
                    return Err(invalid(format!(
                        "operations[{index}].visible must be true or false"
                    )));
                }
            },
            _ => string_word(index, field, value)?,
        };
        words.push(word);
    }
    for flag in spec.flags {
        let Some(field) = flag_field(flag.name) else {
            continue;
        };
        let Some(value) = object.get(field) else {
            continue;
        };
        match flag.name {
            "--child" => {
                let pair = value
                    .as_array()
                    .filter(|pair| pair.len() == 2)
                    .ok_or_else(|| {
                        invalid(format!("operations[{index}].child must be [cx, cy]"))
                    })?;
                words.push("--child".to_owned());
                for part in pair {
                    words.push(unsigned_word(index, "child", part)?);
                }
            }
            "--discard-detail" => match value.as_bool() {
                Some(true) => words.push("--discard-detail".to_owned()),
                Some(false) => {}
                None => {
                    return Err(invalid(format!(
                        "operations[{index}].discard_detail must be true or false"
                    )));
                }
            },
            _ => {
                words.push(flag.name.to_owned());
                words.push(string_word(index, field, value)?);
            }
        }
    }
    Ok((spec, words))
}

/// {
///   責務: [read_batch: バッチファイルを読み、厳密に検査して操作の列にする]
///   処理: [
///     1: 大きさの上限を確認して読む
///     2: 重複キー・深すぎる入れ子を拒否してJSONにする
///     3: versionと許されたトップレベルのキーだけを確認する
///     4: 操作数の上限を確認し、各操作を引数の語へ変換する
///   ]
///   引数: [
///     path: バッチファイルのパス
///   ]
///   戻り値: [コマンドの定義と引数の語の並び]
/// }
fn read_batch(path: &Path) -> Result<Vec<(&'static CommandSpec, Vec<String>)>, CliError> {
    let metadata = fs::metadata(path).map_err(|error| {
        let code = if error.kind() == ErrorKind::NotFound {
            "file_not_found"
        } else {
            "io_error"
        };
        CliError::failure(code, format!("cannot read {}: {error}", path.display()))
    })?;
    if !metadata.is_file() || metadata.len() > MAX_BATCH_BYTES {
        return Err(invalid(format!(
            "{} must be a regular file of at most {MAX_BATCH_BYTES} bytes",
            path.display()
        )));
    }
    let text = fs::read_to_string(path)
        .map_err(|error| invalid(format!("cannot read {} as UTF-8: {error}", path.display())))?;
    let document =
        parse_strict_json(&text).map_err(|error| invalid(format!("not valid JSON: {error}")))?;
    let object: &Map<String, Value> = document
        .as_object()
        .ok_or_else(|| invalid("the batch must be a JSON object"))?;
    if let Some(unknown) = object
        .keys()
        .find(|key| *key != "version" && *key != "operations")
    {
        return Err(invalid(format!("unknown top-level field `{unknown}`")));
    }
    if object.get("version").and_then(Value::as_u64) != Some(1) {
        return Err(invalid("version must be the integer 1"));
    }
    let operations = object
        .get("operations")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("operations must be an array"))?;
    if operations.len() > MAX_OPERATIONS {
        return Err(invalid(format!(
            "operations has {} items; the limit is {MAX_OPERATIONS}",
            operations.len()
        )));
    }
    operations
        .iter()
        .enumerate()
        .map(|(index, entry)| operation_words(index, entry))
        .collect()
}

/// {
///   責務: [apply_batch: バッチの操作を順に適用する]
///   処理: [
///     1: --fileを必須として読み、全体を検査してから適用を始める
///     2: 各操作を単独のコマンドと同じ解析・処理に通し、同じ作品へ順に適用する
///     3: 1件でも失敗したらその番号と操作名を添えて失敗にする（保存はされない）
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [操作数と変更の有無、失敗時は何も保存されないエラー]
/// }
pub fn apply_batch(command: &ParsedCommand, document: &mut LayeredCanvas) -> EditResult {
    let file = command
        .flag_values("--file")
        .and_then(|values| values.first())
        .ok_or_else(|| CliError::usage("batch apply needs --file PATH"))?;
    let planned = read_batch(Path::new(file))?;
    let mut changed = false;
    for (index, (spec, words)) in planned.iter().enumerate() {
        let operation = spec.operation();
        let parsed = ParsedCommand::parse(&COMMANDS, words).map_err(|error| {
            invalid(format!("operations[{index}]: {}", error.message))
                .with_details(json!({"failed_index": index, "op": operation}))
        })?;
        let Handler::Edit(handler) = &parsed.spec.handler else {
            return Err(invalid("only editing operations are allowed in a batch"));
        };
        let (_, step_changed) = handler(&parsed, document).map_err(|error| {
            // ファイルの中の値の誤りは、コマンド行の使い方の誤り(終了値2)ではなくバッチの不備として扱う。
            let error = if error.exit_code == EXIT_USAGE {
                invalid(format!("operations[{index}]: {}", error.message))
            } else {
                error
            };
            error.with_details(json!({"failed_index": index, "op": operation}))
        })?;
        changed |= step_changed;
    }
    Ok((
        json!({"operation_count": planned.len(), "changed": changed}),
        changed,
    ))
}
