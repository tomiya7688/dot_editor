//! Validated single-canvas project loading; construction never touches a caller's canvas.
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::sync::Arc;

use crate::canvas::Canvas;
use crate::field_bounds::FieldBounds;
use crate::field_patch::FieldPatch;
use crate::project_json::ProjectJsonError;
use crate::raster::{Color, Raster};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;
use crate::resolution_field::{DetailPolicy, ResolutionField};
use crate::split_cell::SplitCell;
use crate::strict_json::StrictJson;

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

impl Canvas {
    /// Loads a legacy version 1 or current version 2 single-canvas project.
    /// Undo/redo start empty. Duplicates, invalid partitions, mismatched previews
    /// and unsafe allocations are rejected before a canvas is returned.
    /// {
    ///   責務: [from_json: 旧形式またはversion 2の単一Canvasを読み込む]
    ///   処理: [
    ///     1: 入力サイズと重複キー・深さを検査する
    ///     2: ルートと版番号を検証する
    ///     3: 対応する形式の保持状態を復元する
    ///   ]
    ///   引数: [
    ///     text: 解析対象のJSON文字列
    ///   ]
    ///   戻り値: [履歴のないCanvasまたは入力検証エラー]
    /// }
    pub fn from_json(text: &str) -> Result<Self> {
        if text.len() > 256 * 1024 * 1024 {
            return Err(invalid("project exceeds the JSON byte limit"));
        }
        let mut parser = serde_json::Deserializer::from_str(text);
        // The visitor enforces precisely 128 containers (including the root),
        // rather than serde_json's slightly stricter default recursion budget.
        parser.disable_recursion_limit();
        let StrictJson(source, _) = StrictJson::deserialize(&mut parser)?;
        parser.end()?;
        if !source.is_object() {
            return Err(invalid("project root must be an object"));
        }
        if source.get("layers").is_some() {
            return Err(invalid("layered project loading is not implemented yet"));
        }
        match source.get("version").unwrap_or(&Value::from(1)).as_u64() {
            Some(1) => legacy_canvas(&source),
            Some(2) => current_canvas(&source),
            _ => Err(invalid("unsupported project version")),
        }
    }
}

/// {
///   責務: [uint: JSON値を符号なし32ビット整数として検証する]
///   処理: [
///     1: 符号・整数型とu32範囲を確認する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [u32値または型・範囲エラー]
/// }
fn uint(value: &Value) -> Result<u32> {
    value
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| invalid("expected an unsigned integer"))
}
/// {
///   責務: [array: JSON値が配列か検証する]
///   処理: [
///     1: 配列としての参照を取得する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [配列参照または型エラー]
/// }
fn array(value: &Value) -> Result<&Vec<Value>> {
    value
        .as_array()
        .ok_or_else(|| invalid("expected a JSON array"))
}
/// {
///   責務: [shape: JSON解像度と描画予算を検証する]
///   処理: [
///     1: 二つの正の整数を読む
///     2: 辺長と画素数の上限を検査する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [解像度または入力・予算エラー]
/// }
fn shape(value: &Value) -> Result<Resolution> {
    let values = array(value)?;
    if values.len() != 2 {
        return Err(invalid("resolution must contain two integers"));
    }
    let resolution = Resolution::new(uint(&values[0])?, uint(&values[1])?)
        .map_err(|_| invalid("resolution must be positive"))?;
    // Validate bounds before allocating a raster or iterating over coordinates.
    let width = resolution.width();
    let height = resolution.height();
    if width > crate::raster::MAX_DIMENSION || height > crate::raster::MAX_DIMENSION {
        return Err(crate::raster::RasterError::DimensionLimitExceeded { width, height }.into());
    }
    if u64::from(width) * u64::from(height) > crate::raster::MAX_PIXELS as u64 {
        return Err(crate::raster::RasterError::PixelBudgetExceeded.into());
    }
    Ok(resolution)
}
/// {
///   責務: [color: 互換色を透明黒またはRGBAへ復号する]
///   処理: [
///     1: nullと16進文字列形式を検査する
///     2: 色成分を復号し省略アルファを255にする
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [RGBA色または形式エラー]
/// }
fn color(value: &Value) -> Result<Color> {
    if value.is_null() {
        return Ok([0; 4]);
    }
    let text = value
        .as_str()
        .ok_or_else(|| invalid("pixel must be null or a hex color"))?;
    let bytes = text.as_bytes();
    if !matches!(bytes.len(), 7 | 9)
        || bytes[0] != b'#'
        || !bytes[1..].iter().all(u8::is_ascii_hexdigit)
    {
        return Err(invalid("pixel must use #RRGGBB or #RRGGBBAA"));
    }
    let mut channels = [0, 0, 0, 255];
    for (index, pair) in bytes[1..].chunks_exact(2).enumerate() {
        let nibble = |c: u8| {
            if c.is_ascii_digit() {
                c - b'0'
            } else {
                c.to_ascii_lowercase() - b'a' + 10
            }
        };
        channels[index] = nibble(pair[0]) * 16 + nibble(pair[1]);
    }
    Ok(channels)
}
/// {
///   責務: [raster: JSON画素行列を予算内のラスタへ復元する]
///   処理: [
///     1: 行数・列数を解像度と照合する
///     2: 各色を復号してラスタへ格納する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///     resolution: 対象の解像度
///   ]
///   戻り値: [ラスタまたは画素・確保エラー]
/// }
fn raster(value: &Value, resolution: Resolution) -> Result<Raster> {
    let rows = array(value)?;
    if rows.len() != resolution.height() as usize {
        return Err(invalid("pixel height disagrees with resolution"));
    }
    let mut raster = Raster::new(resolution)?;
    for (y, row) in rows.iter().enumerate() {
        let cells = array(row)?;
        if cells.len() != resolution.width() as usize {
            return Err(invalid("pixel width disagrees with resolution"));
        }
        for (x, value) in cells.iter().enumerate() {
            raster.paint(x as u32, y as u32, color(value)?);
        }
    }
    Ok(raster)
}
/// {
///   責務: [bounds: JSONの分数から正確な領域を復元する]
///   処理: [
///     1: 四つの分子・分母と上限を検査する
///     2: 分数を正規化して正の面積を確認する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [正確な領域または座標形式エラー]
/// }
fn bounds(value: &Value) -> Result<FieldBounds> {
    let values = array(value)?;
    if values.len() != 4 {
        return Err(invalid("bounds must contain four fractions"));
    }
    let mut coords = [Coordinate::new(0, 1); 4];
    for (index, value) in values.iter().enumerate() {
        let pair = array(value)?;
        if pair.len() != 2 {
            return Err(invalid("coordinate must contain numerator and denominator"));
        }
        let numerator = uint(&pair[0])?;
        let denominator = uint(&pair[1])?;
        if denominator == 0 || numerator > denominator || denominator > 16_777_216 {
            return Err(invalid("invalid rational patch coordinate"));
        }
        coords[index] = Coordinate::new(u64::from(numerator), u64::from(denominator));
    }
    let [left, top, right, bottom] = coords;
    if left >= right || top >= bottom {
        return Err(invalid("patch bounds must have positive area"));
    }
    Ok(FieldBounds {
        left,
        top,
        right,
        bottom,
    })
}
/// {
///   責務: [field: JSON保持パッチを分割されたフィールドへ復元する]
///   処理: [
///     1: 個数・範囲・画像予算・色差分を検査する
///     2: 元画素からパッチを作る
///     3: Canvas全体を重複なく覆うことを検証する
///   ]
///   引数: [
///     value: 変換・検査するJSON値
///   ]
///   戻り値: [保持フィールドまたは入力検証エラー]
/// }
fn field(value: &Value) -> Result<ResolutionField> {
    let entries = array(value)?;
    if entries.is_empty() || entries.len() > 4096 {
        return Err(invalid("invalid retained patch count"));
    }
    let mut patches = Vec::new();
    let mut pixel_count = 0u64;
    for entry in entries {
        if !entry.is_object() {
            return Err(invalid("patch must be an object"));
        }
        let clip = bounds(&entry["clip"])?;
        let extent = bounds(&entry["extent"])?;
        if clip.intersection(extent) != Some(clip) {
            return Err(invalid("patch clip must be inside its extent"));
        }
        let size = shape(&entry["resolution"])?;
        pixel_count += u64::from(size.width()) * u64::from(size.height());
        if pixel_count > 16_777_216 {
            return Err(invalid("retained field exceeds its stored pixel budget"));
        }
        let offsets = array(&entry["offset"])?;
        if offsets.len() != 4 {
            return Err(invalid("offset must contain four integers"));
        }
        let mut offset = [0; 4];
        for (i, value) in offsets.iter().enumerate() {
            offset[i] = value
                .as_i64()
                .filter(|n| (-1_000_000..=1_000_000).contains(n))
                .ok_or_else(|| invalid("invalid retained color offset"))?;
        }
        patches.push(FieldPatch::from_source(
            clip,
            extent,
            raster(&entry["pixels"], size)?,
            offset,
        ));
    }
    validate_partition(&patches)?;
    Ok(ResolutionField {
        patches: Arc::new(patches),
    })
}

/// Sweep exact rational edges. Every nonzero x slab must cover y=[0,1)
/// once, which rejects both holes and overlaps without rasterizing the field.
/// {
///   責務: [validate_partition: パッチがCanvas全体を一度ずつ覆うか検査する]
///   処理: [
///     1: 有理数の開始・終了端を整列する
///     2: 各縦帯の区間を走査する
///     3: 重なり・穴・不正な終端を拒否する
///   ]
///   引数: [
///     patches: 被覆範囲を検証するパッチ列
///   ]
///   戻り値: [成功時は単位値、被覆不正なら検証エラー]
/// }
fn validate_partition(patches: &[FieldPatch]) -> Result<()> {
    let mut events = Vec::new();
    for patch in patches {
        let b = patch.bounds;
        events.extend([
            (b.left, true, b.top, b.bottom),
            (b.right, false, b.top, b.bottom),
        ]);
    }
    events.sort_unstable();
    let mut active = BTreeSet::new();
    let mut previous = Coordinate::new(0, 1);
    for (x, start, y0, y1) in events {
        if x != previous {
            let mut covered = Coordinate::new(0, 1);
            for &(top, bottom) in &active {
                if top != covered {
                    return Err(invalid(
                        "patches must partition the entire canvas without overlaps",
                    ));
                }
                covered = bottom;
            }
            if covered != Coordinate::new(1, 1) {
                return Err(invalid("retained field has uncovered coordinates"));
            }
            previous = x;
        }
        if start {
            if !active.insert((y0, y1)) {
                return Err(invalid("retained patches overlap"));
            }
        } else if !active.remove(&(y0, y1)) {
            return Err(invalid("invalid patch partition"));
        }
    }
    if previous != Coordinate::new(1, 1) || !active.is_empty() {
        return Err(invalid("retained field does not cover the canvas"));
    }
    Ok(())
}

/// {
///   責務: [current_canvas: version 2の保持状態と表示情報を復元・照合する]
///   処理: [
///     1: 解像度と保持パッチを検証する
///     2: 分割記録の座標・展開状態・重複を検査する
///     3: 保持状態の描画と保存プレビュー・子色を照合する
///   ]
///   引数: [
///     source: 変換・検査する元データ
///   ]
///   戻り値: [復元したCanvasまたは保持・表示不一致エラー]
/// }
fn current_canvas(source: &Value) -> Result<Canvas> {
    let resolution = shape(&source["resolution"])?;
    if uint(&source["canvas_size"])? != resolution.width() {
        return Err(invalid("canvas_size disagrees with resolution"));
    }
    let field = field(&source["retained_field"])?;
    let entries = array(&source["retained_splits"])?;
    if entries.len() > 4096 {
        return Err(invalid("too many retained splits"));
    }
    let mut splits = Vec::new();
    let mut keys = BTreeSet::new();
    for entry in entries {
        if !entry.is_object() {
            return Err(invalid("split must be an object"));
        }
        let grid = shape(&entry["resolution"])?;
        let x = uint(&entry["x"])?;
        let y = uint(&entry["y"])?;
        let expanded = entry["expanded"]
            .as_bool()
            .ok_or_else(|| invalid("expanded must be a boolean"))?;
        if x >= grid.width() || y >= grid.height() {
            return Err(invalid("split coordinate is outside its grid"));
        }
        if expanded {
            shape(&serde_json::json!([2 * grid.width(), 2 * grid.height()]))?;
        }
        if !keys.insert((grid.width(), grid.height(), x, y)) {
            return Err(invalid("duplicate retained split"));
        }
        splits.push(SplitCell {
            resolution: grid,
            x,
            y,
            expanded,
            base: color(&entry["base"])?,
        });
    }
    let canvas = Canvas::from_parts(resolution, field, splits);
    if canvas.render()? != raster(&source["pixels"], resolution)? {
        return Err(invalid("project pixels disagree with retained field"));
    }
    let canonical: Value = serde_json::from_str(&canvas.to_json()?)?;
    if source
        .get("refined_cells")
        .unwrap_or(&serde_json::json!([]))
        != canonical
            .get("refined_cells")
            .unwrap_or(&serde_json::json!([]))
    {
        return Err(invalid("refined_cells disagree with retained field"));
    }
    Ok(canvas)
}

/// {
///   責務: [legacy_canvas: version 1の親画素と子色を保持モデルへ移行する]
///   処理: [
///     1: 親ラスタと細分化記録を検証する
///     2: 子色を局所パッチへ置換する
///     3: 親色と展開状態を保存してCanvasを構成する
///   ]
///   引数: [
///     source: 変換・検査する元データ
///   ]
///   戻り値: [移行したCanvasまたは旧形式・保持予算エラー]
/// }
fn legacy_canvas(source: &Value) -> Result<Canvas> {
    let size = uint(&source["canvas_size"])?;
    let resolution = shape(&serde_json::json!([size, size]))?;
    let image = raster(&source["pixels"], resolution)?;
    let mut field = ResolutionField::from_raster(image.clone());
    let empty = serde_json::json!([]);
    let entries = array(source.get("refined_cells").unwrap_or(&empty))?;
    if entries.len() > 4096 {
        return Err(invalid("too many legacy refined cells"));
    }
    let mut splits = Vec::new();
    let mut keys = BTreeSet::new();
    for entry in entries {
        if !entry.is_object() {
            return Err(invalid("refined cell must be an object"));
        }
        let x = uint(&entry["x"])?;
        let y = uint(&entry["y"])?;
        if x >= size || y >= size || !keys.insert((x, y)) {
            return Err(invalid("invalid or duplicate refined cell coordinate"));
        }
        let expanded = entry
            .get("expanded")
            .unwrap_or(&Value::Bool(true))
            .as_bool()
            .ok_or_else(|| invalid("expanded must be a boolean"))?;
        if expanded {
            shape(&serde_json::json!([size * 2, size * 2]))?;
        }
        let child_grid = Resolution::new(size * 2, size * 2).expect("bounded positive size");
        let children = raster(&entry["children"], Resolution::new(2, 2).unwrap())?;
        for cy in 0..2 {
            for cx in 0..2 {
                field
                    .paint(
                        child_grid,
                        x * 2 + cx,
                        y * 2 + cy,
                        children.sample(cx, cy)?,
                        DetailPolicy::Discard,
                    )
                    .map_err(|_| invalid("legacy refinement exceeds the retained field budget"))?;
            }
        }
        splits.push(SplitCell {
            resolution,
            x,
            y,
            base: image.sample(x, y)?,
            expanded,
        });
    }
    Ok(Canvas::from_parts(resolution, field, splits))
}
