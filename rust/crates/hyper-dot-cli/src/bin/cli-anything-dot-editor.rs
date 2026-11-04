//! `cli-anything-dot-editor`: the CLI-Anything compatible name of `pixel-cli`.
//!
//! It reaches exactly the same code, so arguments, output and exit codes match.

#![forbid(unsafe_code)]

use std::process::ExitCode;

/// {
///   責務: [main: 共通の実行処理を呼び出して終了値を返す]
///   処理: [
///     1: pixel-cliと同じライブラリの入口へそのまま渡す
///   ]
///   引数: []
///   戻り値: [プロセスの終了値]
/// }
fn main() -> ExitCode {
    hyper_dot_cli::run_from_environment()
}
