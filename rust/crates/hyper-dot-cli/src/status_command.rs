//! `status`: a one-call overview for inspect-before-mutate workflows.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::Value;

use crate::cli_error::CliError;
use crate::document_summary::{layer_list, summary};
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [status: 解像度・選択中の層・レイヤー一覧を1回で返す]
///   処理: [
///     1: 作品の概要を作る
///     2: レイヤー一覧を添える
///   ]
///   引数: [
///     _command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [概要とlayersを含む結果]
/// }
pub fn status(_command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    let mut result = summary(document);
    result["layers"] = layer_list(document);
    Ok(result)
}
