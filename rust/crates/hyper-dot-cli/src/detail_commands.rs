//! `detail` commands: split, split-region, discard and info on the selected layer.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::command_input::cell;
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [split_cell: 選択中レイヤーの1画素を4つの子セルへ分割する]
///   処理: [
///     1: 座標を読み、範囲内か確認する
///     2: コアの分割を実行する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [結果のJSON値と変更の有無（既に分割済みなら無変更）]
/// }
pub fn split_cell(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = cell(command, document)?;
    let changed = document.split_cell(x, y)?;
    Ok((json!({"x": x, "y": y, "changed": changed}), changed))
}

/// {
///   責務: [split_region: 選択中レイヤーの長方形領域をまとめて分割する]
///   処理: [
///     1: 左上の座標と幅・高さを読む
///     2: コアの領域分割を1回の操作として実行する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [新たに展開したセル数を含む結果と変更の有無、領域が不正なら失敗]
/// }
pub fn split_region(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = (command.unsigned("x")?, command.unsigned("y")?);
    let (width, height) = (command.unsigned("width")?, command.unsigned("height")?);
    let expanded = document.split_region(x, y, width, height)?;
    Ok((
        json!({"x": x, "y": y, "width": width, "height": height,
               "expanded": expanded, "changed": expanded > 0}),
        expanded > 0,
    ))
}

/// {
///   責務: [discard_detail: 選択中レイヤーの1画素の保持細部を破棄する]
///   処理: [
///     1: 座標を読み、範囲内か確認する
///     2: 表示色を保ったままコアで細部を破棄する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [結果のJSON値と変更の有無（細部がなければ無変更）]
/// }
pub fn discard_detail(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = cell(command, document)?;
    let changed = document.discard_detail(x, y)?;
    Ok((json!({"x": x, "y": y, "changed": changed}), changed))
}

/// {
///   責務: [detail_info: 選択中レイヤーの1画素の分割状態と細部の有無を返す]
///   処理: [
///     1: 座標を読み、範囲内か確認する
///     2: 分割済みか、保持細部があるかを調べる
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [splitとhas_detailを含む結果]
/// }
pub fn detail_info(command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    let (x, y) = cell(command, document)?;
    Ok(json!({
        "x": x,
        "y": y,
        "split": document.active().is_split(x, y),
        "has_detail": document.active().has_detail_at(x, y)?,
    }))
}
