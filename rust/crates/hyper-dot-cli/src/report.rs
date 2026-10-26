//! Rendering of results and errors for humans and for `--json` callers.

use serde_json::{Value, json};

use crate::cli_error::CliError;

/// {
///   責務: [Outcome: 標準出力・標準エラー・終了値をまとめて保持する]
///   フィールド: [
///     stdout: 標準出力へ書く内容（結果）
///     stderr: 標準エラーへ書く内容（診断・エラー）
///     exit_code: プロセスの終了値
///   ]
/// }
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct Outcome {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: u8,
}

/// {
///   責務: [success: 成功した操作の結果を出力にまとめる]
///   処理: [
///     1: --jsonなら、status・operation・project・resultを持つ1つのJSONだけを標準出力へ書く
///     2: そうでなければ、1行目に操作名、続けて結果を整形したJSONで書く
///   ]
///   引数: [
///     json: JSON出力か
///     operation: 操作名
///     project: プロジェクトのパス
///     extras: dry_runやsavedなど、結果とは別に載せる項目
///     result: コマンド固有の結果
///   ]
///   戻り値: [終了値0の出力]
/// }
pub fn success(
    json: bool,
    operation: &str,
    project: Option<&str>,
    extras: &[(&str, Value)],
    result: Value,
) -> Outcome {
    let mut document = json!({
        "status": "ok",
        "operation": operation,
        "project": project,
        "result": result,
    });
    for (key, value) in extras {
        document[*key] = value.clone();
    }
    let stdout = if json {
        format!("{document}\n")
    } else {
        let notes: Vec<String> = extras
            .iter()
            .filter(|(_, value)| value.as_bool() == Some(true))
            .map(|(key, _)| (*key).to_owned())
            .collect();
        let suffix = if notes.is_empty() {
            String::new()
        } else {
            format!(" ({})", notes.join(", "))
        };
        let body = serde_json::to_string_pretty(&document["result"]).unwrap_or_default();
        format!("ok {operation}{suffix}\n{body}\n")
    };
    Outcome {
        stdout,
        stderr: String::new(),
        exit_code: 0,
    }
}

/// {
///   責務: [failure: 失敗を出力にまとめる]
///   処理: [
///     1: 説明を標準エラーへ書く
///     2: --jsonなら、status・operation・error・messageを持つJSONを標準出力へも書く
///   ]
///   引数: [
///     json: JSON出力か
///     operation: 操作名。コマンドを特定できなければ`usage`
///     error: 失敗の内容
///   ]
///   戻り値: [失敗の終了値を持つ出力]
/// }
pub fn failure(json: bool, operation: &str, error: &CliError) -> Outcome {
    let stdout = if json {
        let document = json!({
            "status": "error",
            "operation": operation,
            "error": error.code,
            "message": error.message,
        });
        format!("{document}\n")
    } else {
        String::new()
    };
    Outcome {
        stdout,
        stderr: format!("error: {} ({})\n", error.message, error.code),
        exit_code: error.exit_code,
    }
}

/// {
///   責務: [text: 結果としての文章（ヘルプやバージョン）を標準出力にまとめる]
///   処理: [
///     1: 文章をそのまま標準出力へ書く
///   ]
///   引数: [
///     text: 出力する文章
///   ]
///   戻り値: [終了値0の出力]
/// }
pub fn text(text: String) -> Outcome {
    Outcome {
        stdout: text,
        stderr: String::new(),
        exit_code: 0,
    }
}
