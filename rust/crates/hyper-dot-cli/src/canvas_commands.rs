//! `canvas` commands: info and resolution set.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::command_input::{detail_policy, resolution_of};
use crate::document_summary::{size, summary};
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [canvas_info: キャンバスの解像度と層の概要を返す]
///   処理: [
///     1: 読み込み済みの作品から概要を作る
///   ]
///   引数: [
///     _command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [概要のJSON値]
/// }
pub fn canvas_info(_command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    Ok(summary(document))
}

/// {
///   責務: [set_resolution: 全レイヤーの論理解像度を変更する]
///   処理: [
///     1: 幅と高さを正の整数として読む
///     2: 細部の保持・破棄の方針とともにコアへ渡す
///     3: 変更後の解像度と変更の有無を返す
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [結果のJSON値と変更の有無、失敗時は作品を変えずエラー]
/// }
pub fn set_resolution(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let target = resolution_of(command.unsigned("width")?, command.unsigned("height")?)?;
    let changed = document.set_resolution(target, detail_policy(command))?;
    Ok((
        json!({"resolution": size(document.resolution()), "changed": changed}),
        changed,
    ))
}
