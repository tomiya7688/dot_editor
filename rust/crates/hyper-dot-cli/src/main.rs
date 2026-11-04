//! `pixel-cli`: the official Rust command line for Hyper Dot projects.

#![forbid(unsafe_code)]

use std::process::ExitCode;

/// {
///   責務: [main: 共通の実行処理を呼び出して終了値を返す]
///   処理: [
///     1: ライブラリの入口へそのまま渡す。名前による動作の違いはない
///   ]
///   引数: []
///   戻り値: [プロセスの終了値]
/// }
fn main() -> ExitCode {
    hyper_dot_cli::run_from_environment()
}
