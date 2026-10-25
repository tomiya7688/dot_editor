//! Layered project JSON that matches the Python reference format.
//!
//! Version 2 stores each layer as a full single-canvas source, in compositing
//! order. Version 1 layered documents are accepted and migrated on load.
//! Undo/redo history is never stored.

use serde_json::{Value, json};

use crate::canvas::Canvas;
use crate::layered_canvas::{LayerEntry, LayeredCanvas, MAX_LAYERS};
use crate::project_json::ProjectJsonError;
use crate::project_json_import::parse_project;
use crate::resolution::Resolution;

type Result<T> = std::result::Result<T, ProjectJsonError>;

/// {
///   責務: [invalid: 入力検証の失敗理由を読み込みエラーにする]
///   処理: [
///     1: 理由をInvalidエラーへ格納する
///   ]
///   引数: [
///     message: 不正文書の理由
///   ]
///   戻り値: [JSON検証エラー]
/// }
fn invalid(message: &'static str) -> ProjectJsonError {
    ProjectJsonError::Invalid(message)
}

/// {
///   責務: [layer_entry: 1枚分のレイヤー定義を検証して復元する]
///   処理: [
///     1: オブジェクトであることと、空でない名前を確認する
///     2: 表示状態が省略または真偽値であることを確認する
///     3: 単一Canvasの読み込みを再利用して画素状態を復元する
///   ]
///   引数: [
///     entry: レイヤー定義のJSON値
///   ]
///   戻り値: [履歴のないレイヤーまたは入力検証エラー]
/// }
fn layer_entry(entry: &Value) -> Result<LayerEntry> {
    if !entry.is_object() {
        return Err(invalid("invalid layer entry"));
    }
    let name = entry
        .get("name")
        .and_then(Value::as_str)
        .filter(|name| !name.trim().is_empty())
        .ok_or_else(|| invalid("layer name must not be empty"))?;
    let visible = match entry.get("visible") {
        None => true,
        Some(value) => value
            .as_bool()
            .ok_or_else(|| invalid("layer visible must be a boolean"))?,
    };
    let source = entry
        .get("source")
        .filter(|source| source.is_object())
        .ok_or_else(|| invalid("layer source must be an object"))?;
    Ok(LayerEntry {
        name: name.to_owned(),
        canvas: Canvas::from_source(source)?,
        visible,
    })
}

/// {
///   責務: [check_root_shape: ルートの寸法が全レイヤーの解像度と一致するか検査する]
///   処理: [
///     1: 宣言されたcanvas_sizeが幅と一致するか確認する
///     2: version 2ではresolutionの必須と一致を確認する
///   ]
///   引数: [
///     source: ルートのJSON値
///     version: 文書の版番号
///     expected: 全レイヤーに共通する解像度
///   ]
///   戻り値: [成功時は単位値、不一致なら入力検証エラー]
/// }
fn check_root_shape(source: &Value, version: u64, expected: Resolution) -> Result<()> {
    if let Some(declared) = source.get("canvas_size").filter(|value| !value.is_null()) {
        if declared.as_u64() != Some(u64::from(expected.width())) {
            return Err(invalid("layered canvas_size does not match layer size"));
        }
    }
    if version == 2 {
        let shape = source.get("resolution").and_then(Value::as_array);
        let matches = shape.is_some_and(|values| {
            values.len() == 2
                && values[0].as_u64() == Some(u64::from(expected.width()))
                && values[1].as_u64() == Some(u64::from(expected.height()))
        });
        if !matches {
            return Err(invalid(
                "layered resolution does not match layer resolution",
            ));
        }
    }
    Ok(())
}

impl LayeredCanvas {
    /// Writes a version 2 layered project: every layer in compositing order,
    /// including hidden layers. Undo/redo history is not stored.
    /// {
    ///   責務: [to_json: レイヤー付き作品を互換version 2 JSONに書き出す]
    ///   処理: [
    ///     1: 各レイヤーを名前・表示状態・単一Canvasのデータ値にする
    ///     2: 解像度と選択中の名前を添えて直列化する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [JSON文字列または描画・座標・直列化エラー]
    /// }
    pub fn to_json(&self) -> Result<String> {
        let layers = self
            .layers
            .iter()
            .map(|entry| {
                Ok(json!({
                    "name": entry.name,
                    "visible": entry.visible,
                    "source": entry.canvas.to_source()?,
                }))
            })
            .collect::<Result<Vec<_>>>()?;
        let resolution = self.resolution();
        let source = json!({
            "version": 2,
            "canvas_size": resolution.width(),
            "resolution": [resolution.width(), resolution.height()],
            "active_layer": self.active_layer(),
            "layers": layers,
        });
        Ok(serde_json::to_string(&source)?)
    }

    /// Loads a layered project of version 1 or 2. Undo/redo start empty and any
    /// invalid layer rejects the whole document.
    /// {
    ///   責務: [from_json: レイヤー付きversion 1または2の作品を読み込む]
    ///   処理: [
    ///     1: 重複キー・深さ・サイズを検査して解析し、版番号を確認する
    ///     2: 全レイヤーを検証し、解像度の一致と重複名を拒否する
    ///     3: ルートの寸法と選択名を照合して履歴のない作品にする
    ///   ]
    ///   引数: [
    ///     text: 解析対象のJSON文字列
    ///   ]
    ///   戻り値: [履歴のない作品または入力検証エラー]
    /// }
    pub fn from_json(text: &str) -> Result<Self> {
        let source = parse_project(text)?;
        let version = match source.get("version") {
            None => 1,
            Some(value) => value
                .as_u64()
                .filter(|version| matches!(version, 1 | 2))
                .ok_or_else(|| invalid("unsupported layered project version"))?,
        };
        let entries = source
            .get("layers")
            .and_then(Value::as_array)
            .filter(|entries| (1..=MAX_LAYERS).contains(&entries.len()))
            .ok_or_else(|| invalid("layer source must contain 1..256 layers"))?;
        let mut layers: Vec<LayerEntry> = Vec::new();
        for entry in entries {
            let layer = layer_entry(entry)?;
            if layers.iter().any(|existing| existing.name == layer.name) {
                return Err(invalid("duplicate layer name"));
            }
            if layers
                .first()
                .is_some_and(|first| first.canvas.resolution() != layer.canvas.resolution())
            {
                return Err(invalid(
                    "all layers must use the same canvas size and resolution",
                ));
            }
            layers.push(layer);
        }
        check_root_shape(&source, version, layers[0].canvas.resolution())?;
        let active = match source.get("active_layer") {
            None => 0,
            Some(value) => value
                .as_str()
                .and_then(|name| layers.iter().position(|layer| layer.name == name))
                .ok_or_else(|| invalid("active_layer must reference an existing layer"))?,
        };
        Ok(Self::from_entries(layers, active))
    }
}
