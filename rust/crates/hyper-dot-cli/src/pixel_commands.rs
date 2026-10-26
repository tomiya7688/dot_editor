//! `pixel` commands: paint, erase, fill and sample on the selected layer.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::command_input::{cell, child, detail_policy, format_color, parse_color};
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [paint_pixel: 選択中レイヤーの親画素または子セルを塗る]
///   処理: [
///     1: 座標・色・子セル指定・細部方針を読む
///     2: 子セル指定があれば子セルへ、なければ親画素へ塗る
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [結果のJSON値と変更の有無、失敗時は作品を変えずエラー]
/// }
pub fn paint_pixel(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = cell(command, document)?;
    let color = parse_color(command.text("color"))?;
    let policy = detail_policy(command);
    let changed = match child(command)? {
        Some(part) => document.paint_child(x, y, part, color, policy)?,
        None => document.paint(x, y, color, policy)?,
    };
    Ok((
        json!({"x": x, "y": y, "color": format_color(color), "changed": changed}),
        changed,
    ))
}

/// {
///   責務: [erase_pixel: 選択中レイヤーの親画素または子セルを透明にする]
///   処理: [
///     1: 座標・子セル指定・細部方針を読む
///     2: 子セル指定があれば子セルを、なければ親画素を消す
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [結果のJSON値と変更の有無、失敗時は作品を変えずエラー]
/// }
pub fn erase_pixel(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = cell(command, document)?;
    let policy = detail_policy(command);
    let changed = match child(command)? {
        Some(part) => document.paint_child(x, y, part, [0; 4], policy)?,
        None => document.erase(x, y, policy)?,
    };
    Ok((json!({"x": x, "y": y, "changed": changed}), changed))
}

/// {
///   責務: [fill_region: 選択中レイヤーの同色の4近傍領域を塗りつぶす]
///   処理: [
///     1: 起点・色・細部方針を読む
///     2: コアの塗りつぶしを1回の操作として実行する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [対象にしたセル数を含む結果と変更の有無、失敗時は作品を変えずエラー]
/// }
pub fn fill_region(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let (x, y) = cell(command, document)?;
    let color = parse_color(command.text("color"))?;
    let cells = document.fill(x, y, color, detail_policy(command))?;
    Ok((
        json!({"x": x, "y": y, "color": format_color(color), "cells": cells, "changed": cells > 0}),
        cells > 0,
    ))
}

/// {
///   責務: [sample_pixel: 選択中レイヤーの親画素または子セルの色を読む]
///   処理: [
///     1: 座標と子セル指定を読む
///     2: 色を#RRGGBBAAと4成分の両方で返す
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [色を含む結果、範囲外や未分割の子セルは失敗]
/// }
pub fn sample_pixel(command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    let (x, y) = cell(command, document)?;
    let color = match child(command)? {
        Some(part) => document.active().sample_child(x, y, part)?,
        None => document.sample(x, y)?,
    };
    Ok(json!({"x": x, "y": y, "color": format_color(color), "rgba": color}))
}
