//! Shell-first command line for Hyper Dot projects.
//!
//! One invocation performs one logical operation and never waits on stdin.
//! Results go to stdout, diagnostics to stderr; see `docs/CLI契約.md`.
//! The `pixel-cli` and `cli-anything-dot-editor` executables both call
//! [`run_from_environment`], so the two names behave identically.

#![forbid(unsafe_code)]

mod canvas_commands;
mod catalog;
mod cli_error;
mod command_docs;
mod command_input;
mod command_spec;
mod command_table;
mod detail_commands;
mod document_summary;
mod export_commands;
mod global_options;
mod help_text;
mod layer_commands;
mod parsed_command;
mod pixel_commands;
mod project_commands;
mod project_file;
mod report;
mod runner;
mod sha256;
mod status_command;

use std::io::Write;
use std::process::ExitCode;

use cli_error::CliError;

/// {
///   責務: [arguments: プログラム名を除くコマンド行をUTF-8の文字列として集める]
///   処理: [
///     1: 各語をUTF-8へ変換する
///     2: 変換できない語があれば、別のファイルを指さないよう使い方の誤りにする
///   ]
///   引数: []
///   戻り値: [語の並びまたは使い方の誤り]
/// }
fn arguments() -> Result<Vec<String>, CliError> {
    std::env::args_os()
        .skip(1)
        .map(|word| {
            word.into_string()
                .map_err(|_| CliError::usage("arguments must be valid UTF-8"))
        })
        .collect()
}

/// {
///   責務: [run_from_environment: プロセスのコマンド行を実行し、結果を標準出力・標準エラーへ書いて終了値を返す]
///   処理: [
///     1: 引数を集めてrunnerへ渡す
///     2: 標準出力と標準エラーへ書く。閉じたパイプへの書き込み失敗は終了値を変えない
///   ]
///   引数: []
///   戻り値: [プロセスの終了値]
/// }
pub fn run_from_environment() -> ExitCode {
    let outcome = match arguments() {
        Ok(words) => runner::run(&words),
        Err(error) => report::failure(false, "usage", &error),
    };
    // 親プロセスが出力の末尾を確実に受け取れるよう、終了前に明示的に書き出す。
    let mut stdout = std::io::stdout();
    let _ = stdout.write_all(outcome.stdout.as_bytes());
    let _ = stdout.flush();
    let mut stderr = std::io::stderr();
    let _ = stderr.write_all(outcome.stderr.as_bytes());
    let _ = stderr.flush();
    ExitCode::from(outcome.exit_code)
}
