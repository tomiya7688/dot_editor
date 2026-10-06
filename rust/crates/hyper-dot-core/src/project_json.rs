//! Single-canvas JSON export compatible with the Python reference.
//! Exports retained sources and raw offsets, never flattened display samples.

use serde_json::{Value, json};

use crate::canvas::Canvas;
use crate::field_bounds::FieldBounds;
use crate::field_patch::FieldPatch;
pub use crate::project_json_error::ProjectJsonError;
use crate::raster::{Color, Raster};
use crate::resolution::Resolution;

const MAX_COORDINATE: u64 = 16_777_216;

impl Canvas {
    /// Returns a version 2 project without changing state, undo or redo history.
    /// Large logical grids that cannot be rendered are rejected, as are retained
    /// coordinates outside the existing JSON format's exact fraction budget.
    /// Layered projects are not supported yet; see `from_json` for loading.
    /// {
    ///   責務: [to_json: 単一Canvasを互換version 2 JSONに書き出す]
    ///   処理: [
    ///     1: 表示ラスタと保持元画像を取得する
    ///     2: 分割記録を整列して子色を付ける
    ///     3: version 2形式へ直列化する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [JSON文字列または描画・座標・直列化エラー]
    /// }
    pub fn to_json(&self) -> Result<String, ProjectJsonError> {
        let preview = self.render()?;
        let patches = self
            .field
            .patches
            .iter()
            .map(patch_source)
            .collect::<Result<Vec<_>, _>>()?;
        let mut splits: Vec<_> = self.splits.iter().collect();
        splits.sort_by_key(|split| {
            (
                split.resolution.width(),
                split.resolution.height(),
                split.x,
                split.y,
            )
        });
        let retained_splits: Vec<_> = splits
            .iter()
            .map(|split| {
                json!({
                    "resolution": shape(split.resolution), "x": split.x, "y": split.y,
                    "base": encoded_color(split.base), "expanded": split.expanded,
                })
            })
            .collect();
        let mut cells = Vec::new();
        for split in splits
            .into_iter()
            .filter(|split| split.resolution == self.resolution())
        {
            let mut children = Vec::new();
            for cy in 0..2 {
                let mut row = Vec::new();
                for cx in 0..2 {
                    row.push(encoded_color(self.sample_child(
                        split.x,
                        split.y,
                        (cx, cy),
                    )?));
                }
                children.push(row);
            }
            cells.push(json!({"x": split.x, "y": split.y, "expanded": split.expanded, "children": children}));
        }
        let mut source = json!({
            "version": 2, "canvas_size": self.resolution().width(),
            "resolution": shape(self.resolution()), "pixels": raster_source(&preview)?,
            "retained_field": patches, "retained_splits": retained_splits,
        });
        if !cells.is_empty() {
            source["refined_cells"] = Value::Array(cells);
        }
        Ok(serde_json::to_string(&source)?)
    }
}

/// {
///   責務: [shape: 解像度をJSON用の縦横ペアにする]
///   処理: [
///     1: 幅と高さを順に配列へ格納する
///   ]
///   引数: [
///     resolution: 対象の解像度
///   ]
///   戻り値: [幅・高さの配列]
/// }
fn shape(resolution: Resolution) -> [u32; 2] {
    [resolution.width(), resolution.height()]
}

/// {
///   責務: [encoded_color: RGBAを互換16進色またはnullに変換する]
///   処理: [
///     1: 完全な透明黒はNoneにする
///     2: 不透明色は6桁、それ以外は8桁で符号化する
///   ]
///   引数: [
///     [r, g, b, a]: 直列化するRGBA各成分
///   ]
///   戻り値: [色文字列、透明黒の場合はNone]
/// }
fn encoded_color([r, g, b, a]: Color) -> Option<String> {
    if [r, g, b, a] == [0; 4] {
        None
    } else if a == 255 {
        Some(format!("#{r:02X}{g:02X}{b:02X}"))
    } else {
        Some(format!("#{r:02X}{g:02X}{b:02X}{a:02X}"))
    }
}

/// {
///   責務: [raster_source: ラスタを行ごとの互換色配列へ変換する]
///   処理: [
///     1: 各行の画素を順に読む
///     2: 各RGBAを互換色へ変換する
///   ]
///   引数: [
///     raster: 元となるRGBAラスタ
///   ]
///   戻り値: [色行列または画素読み取りエラー]
/// }
fn raster_source(raster: &Raster) -> Result<Vec<Vec<Option<String>>>, ProjectJsonError> {
    let resolution = raster.resolution();
    (0..resolution.height())
        .map(|y| {
            (0..resolution.width())
                .map(|x| Ok(encoded_color(raster.sample(x, y)?)))
                .collect()
        })
        .collect()
}

/// {
///   責務: [bounds_source: 正確な領域をJSONの分数配列へ変換する]
///   処理: [
///     1: 各端の分子・分母を取得する
///     2: 既存形式の座標上限を検査する
///   ]
///   引数: [
///     bounds: 処理する正規化長方形
///   ]
///   戻り値: [四つの分数または座標上限エラー]
/// }
fn bounds_source(bounds: FieldBounds) -> Result<[[u64; 2]; 4], ProjectJsonError> {
    let fractions =
        [bounds.left, bounds.top, bounds.right, bounds.bottom].map(|value| value.fraction());
    if fractions
        .iter()
        .flatten()
        .any(|value| *value > MAX_COORDINATE)
    {
        return Err(ProjectJsonError::CoordinateLimitExceeded);
    }
    Ok(fractions)
}

/// {
///   責務: [patch_source: 保持パッチの元画素と色差分をJSONへ変換する]
///   処理: [
///     1: 切り取り前の元画像範囲を取得する
///     2: 保存画素・範囲・未飽和の色差分を格納する
///   ]
///   引数: [
///     patch: 直列化する保持パッチ
///   ]
///   戻り値: [保持パッチのJSON値または変換エラー]
/// }
fn patch_source(patch: &FieldPatch) -> Result<Value, ProjectJsonError> {
    let (extent, raster, color) = patch.source_data();
    let (resolution, pixels) = match raster {
        Some(raster) => (shape(raster.resolution()), raster_source(raster)?),
        None => ([1, 1], vec![vec![encoded_color(color)]]),
    };
    Ok(json!({
        "clip": bounds_source(patch.bounds)?, "extent": bounds_source(extent)?,
        "resolution": resolution, "pixels": pixels, "offset": patch.offset,
    }))
}
