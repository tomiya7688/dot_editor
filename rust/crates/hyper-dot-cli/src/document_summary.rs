//! The read-only description of a document shared by `project info`, `canvas info` and `status`.

use hyper_dot_core::layered_canvas::LayeredCanvas;
use hyper_dot_core::resolution::Resolution;
use serde_json::{Value, json};

/// {
///   責務: [size: 解像度をJSONの幅・高さの組にする]
///   処理: [
///     1: widthとheightを持つ辞書にする
///   ]
///   引数: [
///     resolution: 対象の解像度
///   ]
///   戻り値: [JSON値]
/// }
pub fn size(resolution: Resolution) -> Value {
    json!({"width": resolution.width(), "height": resolution.height()})
}

/// {
///   責務: [retained_resolution: 全レイヤーが保持する解像度の最大値を求める]
///   処理: [
///     1: 各層の保持解像度から幅・高さそれぞれの最大を取る
///   ]
///   引数: [
///     document: 対象の作品
///   ]
///   戻り値: [保持解像度の最大の幅と高さ]
/// }
fn retained_resolution(document: &LayeredCanvas) -> (u32, u32) {
    document
        .layer_names()
        .into_iter()
        .filter_map(|name| document.layer(name).ok())
        .map(|canvas| canvas.retained_resolution())
        .fold((1, 1), |(width, height), retained| {
            (width.max(retained.width()), height.max(retained.height()))
        })
}

/// {
///   責務: [summary: 作品の解像度・層数・選択中の層をまとめる]
///   処理: [
///     1: 論理解像度、展開セルを含む自然な解像度、保持解像度を集める
///     2: 層数と選択中の層名を添える
///   ]
///   引数: [
///     document: 対象の作品
///   ]
///   戻り値: [概要のJSON値。自然な解像度が描画予算を超える場合はnull]
/// }
pub fn summary(document: &LayeredCanvas) -> Value {
    let (retained_width, retained_height) = retained_resolution(document);
    json!({
        "resolution": size(document.resolution()),
        "native_resolution": document.native_resolution().ok().map(size),
        "retained_resolution": {"width": retained_width, "height": retained_height},
        "layer_count": document.layer_names().len(),
        "active_layer": document.active_layer(),
    })
}

/// {
///   責務: [layer_list: 合成順のレイヤー一覧を作る]
///   処理: [
///     1: 下層から順に名前・表示状態・選択中かを並べる
///   ]
///   引数: [
///     document: 対象の作品
///   ]
///   戻り値: [レイヤーのJSON配列]
/// }
pub fn layer_list(document: &LayeredCanvas) -> Value {
    let layers: Vec<Value> = document
        .layer_names()
        .into_iter()
        .map(|name| {
            json!({
                "name": name,
                "visible": document.is_layer_visible(Some(name)).unwrap_or(true),
                "active": name == document.active_layer(),
            })
        })
        .collect();
    Value::Array(layers)
}
