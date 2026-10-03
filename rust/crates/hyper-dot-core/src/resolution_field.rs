//! Resolution-independent sampling of an immutable source raster.

use std::sync::Arc;

use crate::raster::{Color, Raster, RasterError};
use crate::resolution::Resolution;

/// Retains one full-canvas source raster while projecting it onto arbitrary grids.
/// Local patches and detail-preserving edits will build on this read-only field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolutionField {
    source: Arc<Raster>,
}

impl ResolutionField {
    pub fn from_raster(source: Raster) -> Self {
        Self {
            source: Arc::new(source),
        }
    }

    pub fn retained_resolution(&self) -> Resolution {
        self.source.resolution()
    }

    /// Samples at the exact center of a cell on the requested logical grid.
    pub fn sample(&self, resolution: Resolution, x: u32, y: u32) -> Result<Color, RasterError> {
        if x >= resolution.width() || y >= resolution.height() {
            return Err(RasterError::CoordinateOutOfBounds { x, y });
        }
        let retained = self.retained_resolution();
        let source_x = Self::source_coordinate(x, resolution.width(), retained.width());
        let source_y = Self::source_coordinate(y, resolution.height(), retained.height());
        self.source.sample(source_x, source_y)
    }

    /// Builds a projected raster without replacing or resampling retained data.
    pub fn render(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        let mut output = Raster::new(resolution)?;
        for y in 0..resolution.height() {
            for x in 0..resolution.width() {
                output.paint(x, y, self.sample(resolution, x, y)?);
            }
        }
        Ok(output)
    }

    fn source_coordinate(position: u32, output_extent: u32, source_extent: u32) -> u32 {
        // floor((position + 1/2) * source_extent / output_extent).
        // Source dimensions are bounded by Raster, so u64 also covers the
        // largest u32 logical grid without floating-point boundary errors.
        let numerator = (2 * u64::from(position) + 1) * u64::from(source_extent);
        let denominator = 2 * u64::from(output_extent);
        (numerator / denominator) as u32
    }
}
