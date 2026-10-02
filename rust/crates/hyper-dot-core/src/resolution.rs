//! Logical canvas dimensions shared by project data and rendering operations.

use std::error::Error;
use std::fmt::{Display, Formatter};

/// A positive logical width and height. This value does not allocate a pixel buffer.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Resolution {
    width: u32,
    height: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolutionError {
    ZeroWidth,
    ZeroHeight,
}

impl Resolution {
    pub const fn new(width: u32, height: u32) -> Result<Self, ResolutionError> {
        if width == 0 {
            return Err(ResolutionError::ZeroWidth);
        }
        if height == 0 {
            return Err(ResolutionError::ZeroHeight);
        }
        Ok(Self { width, height })
    }

    pub const fn width(self) -> u32 {
        self.width
    }

    pub const fn height(self) -> u32 {
        self.height
    }
}

impl Display for ResolutionError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::ZeroWidth => formatter.write_str("resolution width must be greater than zero"),
            Self::ZeroHeight => formatter.write_str("resolution height must be greater than zero"),
        }
    }
}

impl Error for ResolutionError {}

#[cfg(test)]
mod tests {
    use super::{Resolution, ResolutionError};

    #[test]
    fn accepts_non_square_resolution() {
        let resolution = Resolution::new(23, 17).expect("positive dimensions are valid");

        assert_eq!(resolution.width(), 23);
        assert_eq!(resolution.height(), 17);
    }

    #[test]
    fn accepts_single_pixel_resolution() {
        assert_eq!(Resolution::new(1, 1).unwrap().width(), 1);
    }

    #[test]
    fn rejects_zero_width() {
        assert_eq!(Resolution::new(0, 17), Err(ResolutionError::ZeroWidth));
    }

    #[test]
    fn rejects_zero_height() {
        assert_eq!(Resolution::new(23, 0), Err(ResolutionError::ZeroHeight));
    }
}
