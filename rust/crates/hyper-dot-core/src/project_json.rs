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

fn shape(resolution: Resolution) -> [u32; 2] {
    [resolution.width(), resolution.height()]
}

fn encoded_color([r, g, b, a]: Color) -> Option<String> {
    if [r, g, b, a] == [0; 4] {
        None
    } else if a == 255 {
        Some(format!("#{r:02X}{g:02X}{b:02X}"))
    } else {
        Some(format!("#{r:02X}{g:02X}{b:02X}{a:02X}"))
    }
}

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
