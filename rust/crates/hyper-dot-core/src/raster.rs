//! Bounded RGBA raster storage for one logical resolution.

use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::resolution::Resolution;

pub const MAX_DIMENSION: u32 = 4096;
pub const MAX_PIXELS: usize = 4_194_304;

pub type Color = [u8; 4];

const TRANSPARENT: Color = [0, 0, 0, 0];

/// A row-major raster. Resolution changes and retained-detail behavior live above
/// this storage primitive; this type never resamples its own pixels.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Raster {
    resolution: Resolution,
    pixels: Vec<Color>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RasterError {
    DimensionLimitExceeded { width: u32, height: u32 },
    PixelBudgetExceeded,
    AllocationFailed,
    CoordinateOutOfBounds { x: u32, y: u32 },
}

impl Raster {
    pub fn new(resolution: Resolution) -> Result<Self, RasterError> {
        let width = resolution.width();
        let height = resolution.height();
        if width > MAX_DIMENSION || height > MAX_DIMENSION {
            return Err(RasterError::DimensionLimitExceeded { width, height });
        }

        let pixel_count = usize::try_from(width)
            .ok()
            .and_then(|width| {
                usize::try_from(height)
                    .ok()
                    .and_then(|height| width.checked_mul(height))
            })
            .filter(|count| *count <= MAX_PIXELS)
            .ok_or(RasterError::PixelBudgetExceeded)?;

        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(pixel_count)
            .map_err(|_| RasterError::AllocationFailed)?;
        pixels.resize(pixel_count, TRANSPARENT);

        Ok(Self { resolution, pixels })
    }

    pub const fn resolution(&self) -> Resolution {
        self.resolution
    }

    pub fn sample(&self, x: u32, y: u32) -> Result<Color, RasterError> {
        let index = self
            .index(x, y)
            .ok_or(RasterError::CoordinateOutOfBounds { x, y })?;
        Ok(self.pixels[index])
    }

    /// Writes a pixel and reports whether its value changed. Out-of-range writes
    /// are ignored, matching the editor's paint operation.
    pub fn paint(&mut self, x: u32, y: u32, color: Color) -> bool {
        let Some(index) = self.index(x, y) else {
            return false;
        };
        if self.pixels[index] == color {
            return false;
        }
        self.pixels[index] = color;
        true
    }

    pub fn erase(&mut self, x: u32, y: u32) -> bool {
        self.paint(x, y, TRANSPARENT)
    }

    fn index(&self, x: u32, y: u32) -> Option<usize> {
        let width = self.resolution.width();
        let height = self.resolution.height();
        if x >= width || y >= height {
            return None;
        }
        usize::try_from(y)
            .ok()?
            .checked_mul(usize::try_from(width).ok()?)?
            .checked_add(usize::try_from(x).ok()?)
    }
}

impl Display for RasterError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::DimensionLimitExceeded { width, height } => write!(
                formatter,
                "raster dimensions {width}x{height} exceed the {MAX_DIMENSION} limit"
            ),
            Self::PixelBudgetExceeded => {
                write!(formatter, "raster exceeds the {MAX_PIXELS}-pixel budget")
            }
            Self::AllocationFailed => formatter.write_str("unable to allocate raster storage"),
            Self::CoordinateOutOfBounds { x, y } => {
                write!(formatter, "pixel coordinate ({x}, {y}) is out of bounds")
            }
        }
    }
}

impl Error for RasterError {}

#[cfg(test)]
mod tests {
    use super::{Color, MAX_DIMENSION, Raster, RasterError};
    use crate::resolution::Resolution;

    fn raster(width: u32, height: u32) -> Raster {
        Raster::new(Resolution::new(width, height).expect("test dimensions are positive"))
            .expect("test raster is within the storage budget")
    }

    #[test]
    fn starts_transparent_at_non_square_resolution() {
        let raster = raster(23, 17);

        assert_eq!(raster.resolution(), Resolution::new(23, 17).unwrap());
        assert_eq!(raster.sample(22, 16), Ok([0, 0, 0, 0]));
    }

    #[test]
    fn paint_and_sample_preserve_rgba_and_do_not_alias_neighbors() {
        let mut raster = raster(3, 2);
        let color: Color = [12, 34, 56, 78];

        assert!(raster.paint(2, 1, color));
        assert_eq!(raster.sample(2, 1), Ok(color));
        assert_eq!(raster.sample(1, 1), Ok([0, 0, 0, 0]));
    }

    #[test]
    fn painting_the_existing_color_is_a_no_op() {
        let mut raster = raster(1, 1);
        let color = [1, 2, 3, 255];

        assert!(raster.paint(0, 0, color));
        assert!(!raster.paint(0, 0, color));
    }

    #[test]
    fn erase_restores_transparency_and_is_idempotent() {
        let mut raster = raster(1, 1);
        raster.paint(0, 0, [255, 0, 0, 255]);

        assert!(raster.erase(0, 0));
        assert_eq!(raster.sample(0, 0), Ok([0, 0, 0, 0]));
        assert!(!raster.erase(0, 0));
    }

    #[test]
    fn paint_outside_resolution_is_ignored() {
        let mut raster = raster(2, 3);

        assert!(!raster.paint(2, 0, [1, 2, 3, 255]));
        assert!(!raster.paint(0, 3, [1, 2, 3, 255]));
    }

    #[test]
    fn sample_outside_resolution_returns_an_error() {
        let raster = raster(2, 3);

        assert_eq!(
            raster.sample(2, 0),
            Err(RasterError::CoordinateOutOfBounds { x: 2, y: 0 })
        );
    }

    #[test]
    fn rejects_dimensions_above_the_storage_limit() {
        let resolution = Resolution::new(MAX_DIMENSION + 1, 1).unwrap();

        assert_eq!(
            Raster::new(resolution),
            Err(RasterError::DimensionLimitExceeded {
                width: MAX_DIMENSION + 1,
                height: 1
            })
        );
    }

    #[test]
    fn rejects_pixel_count_above_the_storage_budget() {
        let resolution = Resolution::new(MAX_DIMENSION, MAX_DIMENSION).unwrap();

        assert_eq!(
            Raster::new(resolution),
            Err(RasterError::PixelBudgetExceeded)
        );
    }
}
