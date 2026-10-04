//! Resolution-independent field with exact, locally clipped raster patches.

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::field_patch::FieldPatch;
use crate::raster::{Color, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

const MAX_PATCHES: usize = 4096;
const MAX_STORED_PIXELS: usize = 16_777_216;
const MAX_OFFSET: i64 = 1_000_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DetailPolicy {
    Preserve,
    Discard,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolutionFieldError {
    Raster(RasterError),
    PatchBudgetExceeded,
    StoredPixelBudgetExceeded,
    OffsetLimitExceeded,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn whole_canvas_discard_drops_old_raster_storage() {
        let source = Raster::new(Resolution::new(16, 16).unwrap()).unwrap();
        let mut field = ResolutionField::from_raster(source);
        assert!(
            field
                .discard_detail(Resolution::new(1, 1).unwrap(), 0, 0)
                .unwrap()
        );
        assert_eq!(field.patches.len(), 1);
        assert_eq!(field.patches[0].stored_pixels(), 1);
        assert_eq!(field.retained_resolution(), Resolution::new(1, 1).unwrap());
    }

    #[test]
    fn patch_budget_failure_is_atomic() {
        let grid = Resolution::new(MAX_PATCHES as u32, 1).unwrap();
        let patches = (0..grid.width())
            .map(|x| FieldPatch::solid(FieldBounds::cell(grid, x, 0), grid, [0; 4]))
            .collect();
        let mut field = ResolutionField {
            patches: Arc::new(patches),
        };
        let before = field.clone();
        let finer = Resolution::new(2 * grid.width(), 1).unwrap();
        assert_eq!(
            field.paint(finer, 0, 0, [255; 4], DetailPolicy::Discard),
            Err(ResolutionFieldError::PatchBudgetExceeded)
        );
        assert_eq!(field, before);
        assert_eq!(field.sample(finer, 0, 0), Ok([0; 4]));
    }
}

impl From<RasterError> for ResolutionFieldError {
    fn from(error: RasterError) -> Self {
        Self::Raster(error)
    }
}

impl Display for ResolutionFieldError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Raster(error) => Display::fmt(error, formatter),
            Self::PatchBudgetExceeded => {
                formatter.write_str("retained field exceeds its patch budget")
            }
            Self::StoredPixelBudgetExceeded => {
                formatter.write_str("retained field exceeds its stored pixel budget")
            }
            Self::OffsetLimitExceeded => {
                formatter.write_str("retained color offset exceeds its safety limit")
            }
        }
    }
}

impl Error for ResolutionFieldError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            _ => None,
        }
    }
}

/// A partition of retained samples independent of the logical display grid.
/// Clones share an immutable snapshot; an edit installs a new partition only
/// after all cropping, allocation and budget checks succeed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolutionField {
    patches: Arc<Vec<FieldPatch>>,
}

impl ResolutionField {
    pub fn from_raster(source: Raster) -> Self {
        Self {
            patches: Arc::new(vec![FieldPatch::from_raster(source)]),
        }
    }

    pub fn retained_resolution(&self) -> Resolution {
        let width = self.patches.iter().map(|p| p.grid.width()).max().unwrap();
        let height = self.patches.iter().map(|p| p.grid.height()).max().unwrap();
        Resolution::new(width, height).expect("a field always has nonempty positive patches")
    }

    /// Samples at the exact center of a cell on the requested logical grid.
    pub fn sample(&self, resolution: Resolution, x: u32, y: u32) -> Result<Color, RasterError> {
        let raw = self.sample_raw(resolution, x, y)?;
        Ok(raw.map(|channel| channel.clamp(0, 255) as u8))
    }

    fn sample_raw(&self, resolution: Resolution, x: u32, y: u32) -> Result<[i64; 4], RasterError> {
        if x >= resolution.width() || y >= resolution.height() {
            return Err(RasterError::CoordinateOutOfBounds { x, y });
        }
        let cx = Coordinate::center(x, resolution.width());
        let cy = Coordinate::center(y, resolution.height());
        Ok(self
            .patches
            .iter()
            .find(|patch| patch.bounds.contains(cx, cy))
            .expect("retained patches partition the full canvas")
            .sample_raw(cx, cy))
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

    pub fn has_detail_at(&self, grid: Resolution, x: u32, y: u32) -> Result<bool, RasterError> {
        if x >= grid.width() || y >= grid.height() {
            return Err(RasterError::CoordinateOutOfBounds { x, y });
        }
        let bounds = FieldBounds::cell(grid, x, y);
        let mut overlapping = self
            .patches
            .iter()
            .filter(|p| p.bounds.intersection(bounds).is_some());
        let first = overlapping
            .next()
            .expect("retained patches cover every logical cell");
        Ok(overlapping.next().is_some()
            || first.grid.width() > grid.width()
            || first.grid.height() > grid.height())
    }

    /// Paints one logical cell. Preserve retains fine samples as reversible raw
    /// color offsets; discard crops old support and installs a solid patch.
    /// Out-of-range writes and unchanged preserve writes return false.
    pub fn paint(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, ResolutionFieldError> {
        if x >= grid.width() || y >= grid.height() {
            return Ok(false);
        }
        let detail = self.has_detail_at(grid, x, y)?;
        if self.sample(grid, x, y)? == color && !(policy == DetailPolicy::Discard && detail) {
            return Ok(false);
        }
        let preserve = policy == DetailPolicy::Preserve && detail;
        let bounds = FieldBounds::cell(grid, x, y);
        let reference = self.sample_raw(grid, x, y)?;
        let delta: [i64; 4] = std::array::from_fn(|i| i64::from(color[i]) - reference[i]);
        let mut patches = Vec::new();
        patches
            .try_reserve_exact((self.patches.len() * 5 + 1).min(MAX_PATCHES))
            .map_err(|_| RasterError::AllocationFailed)?;
        let mut pixels = 0;
        for patch in self.patches.iter() {
            if let Some(overlap) = patch.bounds.intersection(bounds) {
                for remainder in patch.bounds.outside(overlap) {
                    Self::push_checked(&mut patches, &mut pixels, patch.cropped(remainder)?)?;
                }
                if preserve {
                    let mut shifted = patch.cropped(overlap)?;
                    for (offset, change) in shifted.offset.iter_mut().zip(delta) {
                        *offset += change;
                        if offset.abs() > MAX_OFFSET {
                            return Err(ResolutionFieldError::OffsetLimitExceeded);
                        }
                    }
                    Self::push_checked(&mut patches, &mut pixels, shifted)?;
                }
            } else {
                Self::push_checked(&mut patches, &mut pixels, patch.clone())?;
            }
        }
        if !preserve {
            Self::push_checked(
                &mut patches,
                &mut pixels,
                FieldPatch::solid(bounds, grid, color),
            )?;
        }
        self.patches = Arc::new(patches);
        Ok(true)
    }

    pub fn erase(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
        policy: DetailPolicy,
    ) -> Result<bool, ResolutionFieldError> {
        self.paint(grid, x, y, [0; 4], policy)
    }

    pub fn discard_detail(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
    ) -> Result<bool, ResolutionFieldError> {
        if !self.has_detail_at(grid, x, y)? {
            return Ok(false);
        }
        self.paint(grid, x, y, self.sample(grid, x, y)?, DetailPolicy::Discard)
    }

    fn push_checked(
        patches: &mut Vec<FieldPatch>,
        pixels: &mut usize,
        patch: FieldPatch,
    ) -> Result<(), ResolutionFieldError> {
        if patches.len() == MAX_PATCHES {
            return Err(ResolutionFieldError::PatchBudgetExceeded);
        }
        *pixels += patch.stored_pixels();
        if *pixels > MAX_STORED_PIXELS {
            return Err(ResolutionFieldError::StoredPixelBudgetExceeded);
        }
        patches.push(patch);
        Ok(())
    }
}
