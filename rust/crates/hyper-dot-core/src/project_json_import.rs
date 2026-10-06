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
fn invalid(message: &'static str) -> ProjectJsonError {
    ProjectJsonError::Invalid(message)
}

impl Canvas {
    /// Loads a legacy version 1 or current version 2 single-canvas project.
    /// Undo/redo start empty. Duplicates, invalid partitions, mismatched previews
    /// and unsafe allocations are rejected before a canvas is returned.
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

fn uint(value: &Value) -> Result<u32> {
    value
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| invalid("expected an unsigned integer"))
}
fn array(value: &Value) -> Result<&Vec<Value>> {
    value
        .as_array()
        .ok_or_else(|| invalid("expected a JSON array"))
}
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
