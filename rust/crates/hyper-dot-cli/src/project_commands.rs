//! `project` commands: new, info and validate.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::command_input::resolution_of;
use crate::document_summary::summary;
use crate::parsed_command::{ParsedCommand, parse_unsigned};

/// {
///   責務: [new_project: 空のプロジェクトを作る]
///   処理: [
///     1: --sizeまたは--resolutionのどちらか一方から解像度を決める
///     2: 背景1層だけの作品を作る
///   ]
///   引数: [
///     command: 解析済みコマンド
///   ]
///   戻り値: [作品と結果の概要、解像度の指定や確保の誤りは失敗]
/// }
pub fn new_project(command: &ParsedCommand) -> Result<(LayeredCanvas, Value), CliError> {
    let size = command.flag_values("--size");
    let shape = command.flag_values("--resolution");
    let (width, height) = match (size, shape) {
        (Some(_), Some(_)) => {
            return Err(CliError::usage("choose --size or --resolution, not both"));
        }
        (Some(values), None) => {
            let side = parse_unsigned("--size", &values[0])?;
            (side, side)
        }
        (None, Some(values)) => (
            parse_unsigned("--resolution width", &values[0])?,
            parse_unsigned("--resolution height", &values[1])?,
        ),
        (None, None) => {
            return Err(CliError::usage(
                "project new needs --size N or --resolution W H",
            ));
        }
    };
    let document = LayeredCanvas::new(resolution_of(width, height)?)?;
    let result = summary(&document);
    Ok((document, result))
}

/// {
///   責務: [project_info: プロジェクトの概要を返す]
///   処理: [
///     1: 読み込み済みの作品から概要を作る
///   ]
///   引数: [
///     _command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [概要のJSON値]
/// }
pub fn project_info(_command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    Ok(summary(document))
}

/// {
///   責務: [validate_project: プロジェクトが正しく読み込めることを報告する]
///   処理: [
///     1: 読み込みと検証は実行前に済んでいるため、有効であることと概要を返す
///   ]
///   引数: [
///     _command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [validとlayer_countなどを含むJSON値]
/// }
pub fn validate_project(
    _command: &ParsedCommand,
    document: &LayeredCanvas,
) -> Result<Value, CliError> {
    let mut result = summary(document);
    result["valid"] = json!(true);
    Ok(result)
}
