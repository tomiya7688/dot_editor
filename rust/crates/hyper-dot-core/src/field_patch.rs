use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::raster::{Color, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

#[derive(Clone, Debug, Eq, PartialEq)]
enum PatchSource {
    Raster {
        raster: Arc<Raster>,
        origin_x: u32,
        origin_y: u32,
    },
    Solid(Color),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct FieldPatch {
    pub(crate) bounds: FieldBounds,
    pub(crate) grid: Resolution,
    pub(crate) offset: [i64; 4],
    source: PatchSource,
}

impl FieldPatch {
    pub(crate) fn from_raster(source: Raster) -> Self {
        Self {
            bounds: FieldBounds::full(),
            grid: source.resolution(),
            offset: [0; 4],
            source: PatchSource::Raster {
                raster: Arc::new(source),
                origin_x: 0,
                origin_y: 0,
            },
        }
    }

    pub(crate) fn solid(bounds: FieldBounds, grid: Resolution, color: Color) -> Self {
        Self {
            bounds,
            grid,
            offset: [0; 4],
            source: PatchSource::Solid(color),
        }
    }

    pub(crate) fn sample_raw(&self, x: Coordinate, y: Coordinate) -> [i64; 4] {
        let color = match &self.source {
            PatchSource::Solid(color) => *color,
            PatchSource::Raster {
                raster,
                origin_x,
                origin_y,
            } => raster
                .sample(
                    x.floor_on_grid(self.grid.width()) - origin_x,
                    y.floor_on_grid(self.grid.height()) - origin_y,
                )
                .expect("patch clip lies inside the cropped source"),
        };
        std::array::from_fn(|channel| i64::from(color[channel]) + self.offset[channel])
    }

    pub(crate) fn stored_pixels(&self) -> usize {
        match &self.source {
            PatchSource::Solid(_) => 1,
            PatchSource::Raster { raster, .. } => {
                let size = raster.resolution();
                size.width() as usize * size.height() as usize
            }
        }
    }

    /// Removes inaccessible source pixels without moving their spatial boundaries.
    pub(crate) fn cropped(&self, bounds: FieldBounds) -> Result<Self, RasterError> {
        let source = match &self.source {
            PatchSource::Solid(color) => PatchSource::Solid(*color),
            PatchSource::Raster {
                raster,
                origin_x,
                origin_y,
            } => {
                let x0 = bounds.left.floor_on_grid(self.grid.width());
                let y0 = bounds.top.floor_on_grid(self.grid.height());
                let x1 = bounds.right.ceil_on_grid(self.grid.width());
                let y1 = bounds.bottom.ceil_on_grid(self.grid.height());
                let size = raster.resolution();
                if x0 == *origin_x
                    && y0 == *origin_y
                    && x1 == origin_x + size.width()
                    && y1 == origin_y + size.height()
                {
                    self.source.clone()
                } else {
                    let size = Resolution::new(x1 - x0, y1 - y0)
                        .expect("positive patch bounds retain at least one source pixel");
                    let mut crop = Raster::new(size)?;
                    for y in 0..size.height() {
                        for x in 0..size.width() {
                            crop.paint(x, y, raster.sample(x0 + x - origin_x, y0 + y - origin_y)?);
                        }
                    }
                    PatchSource::Raster {
                        raster: Arc::new(crop),
                        origin_x: x0,
                        origin_y: y0,
                    }
                }
            }
        };
        Ok(Self {
            bounds,
            grid: self.grid,
            offset: self.offset,
            source,
        })
    }
}
