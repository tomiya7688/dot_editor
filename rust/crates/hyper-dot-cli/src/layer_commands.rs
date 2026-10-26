//! `layer` commands: add, remove, select, rename, move, visibility and list.

use hyper_dot_core::layered_canvas::{LayeredCanvas, MoveDirection};
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::document_summary::layer_list;
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [target_layer: --layerで指定された対象の名前を取り出す]
///   処理: [
///     1: 指定があれば名前を返し、なければNoneを返す
///   ]
///   引数: [
///     command: 解析済みコマンド
///   ]
///   戻り値: [対象の層名。省略時は選択中のレイヤーを表すNone]
/// }
fn target_layer(command: &ParsedCommand) -> Option<&str> {
    command
        .flag_values("--layer")
        .map(|values| values[0].as_str())
}

/// {
///   責務: [add_layer: 空のレイヤーを最上層へ追加して選択する]
///   処理: [
///     1: 名前をコアへ渡し、検証と追加を任せる
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [追加後のレイヤー一覧を含む結果。常に変更あり]
/// }
pub fn add_layer(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    document.add_layer(command.text("name"))?;
    Ok((
        json!({"layers": layer_list(document), "changed": true}),
        true,
    ))
}

/// {
///   責務: [remove_layer: 少なくとも1層を残して対象レイヤーを削除する]
///   処理: [
///     1: --layerまたは選択中のレイヤーを削除する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [削除後のレイヤー一覧を含む結果。常に変更あり]
/// }
pub fn remove_layer(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    document.remove_layer(target_layer(command))?;
    Ok((
        json!({"layers": layer_list(document), "changed": true}),
        true,
    ))
}

/// {
///   責務: [select_layer: 既存のレイヤーを編集対象にする]
///   処理: [
///     1: 選択前後の層名を比べ、変わる場合だけ変更ありとする
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [選択中の層名を含む結果と変更の有無]
/// }
pub fn select_layer(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let before = document.active_layer().to_owned();
    document.select_layer(command.text("name"))?;
    let changed = document.active_layer() != before;
    Ok((
        json!({"active_layer": document.active_layer(), "changed": changed}),
        changed,
    ))
}

/// {
///   責務: [rename_layer: 合成順と選択を保ってレイヤー名を変更する]
///   処理: [
///     1: --layerまたは選択中のレイヤーを新しい名前へ変更する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [変更後のレイヤー一覧を含む結果と変更の有無]
/// }
pub fn rename_layer(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let changed = document.rename_layer(command.text("new_name"), target_layer(command))?;
    Ok((
        json!({"layers": layer_list(document), "changed": changed}),
        changed,
    ))
}

/// {
///   責務: [move_layer: レイヤーを合成順で1段入れ替える]
///   処理: [
///     1: upまたはdownを読み取り、それ以外を拒否する
///     2: --layerまたは選択中のレイヤーを動かす
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [移動後のレイヤー一覧を含む結果と変更の有無（端なら無変更）]
/// }
pub fn move_layer(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let direction = match command.text("direction") {
        "up" => MoveDirection::Up,
        "down" => MoveDirection::Down,
        other => {
            return Err(CliError::usage(format!(
                "direction must be `up` or `down`, got `{other}`"
            )));
        }
    };
    let changed = document.move_layer(direction, target_layer(command))?;
    Ok((
        json!({"layers": layer_list(document), "changed": changed}),
        changed,
    ))
}

/// {
///   責務: [set_visibility: レイヤーの表示・非表示を切り替える]
///   処理: [
///     1: onまたはoffを読み取り、それ以外を拒否する
///     2: --layerまたは選択中のレイヤーの表示状態を変える
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 変更する作品
///   ]
///   戻り値: [変更後のレイヤー一覧を含む結果と変更の有無]
/// }
pub fn set_visibility(
    command: &ParsedCommand,
    document: &mut LayeredCanvas,
) -> Result<(Value, bool), CliError> {
    let visible = match command.text("state") {
        "on" => true,
        "off" => false,
        other => {
            return Err(CliError::usage(format!(
                "state must be `on` or `off`, got `{other}`"
            )));
        }
    };
    let changed = document.set_layer_visibility(visible, target_layer(command))?;
    Ok((
        json!({"layers": layer_list(document), "changed": changed}),
        changed,
    ))
}

/// {
///   責務: [list_layers: 合成順のレイヤー一覧を返す]
///   処理: [
///     1: 下層から順に名前・表示状態・選択中かを並べる
///   ]
///   引数: [
///     _command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [レイヤー一覧を含む結果]
/// }
pub fn list_layers(_command: &ParsedCommand, document: &LayeredCanvas) -> Result<Value, CliError> {
    Ok(json!({"layers": layer_list(document)}))
}
