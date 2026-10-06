use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::canvas::CanvasError;
use crate::raster::RasterError;

#[derive(Debug)]
pub enum ProjectJsonError {
    Raster(RasterError),
    Canvas(CanvasError),
    CoordinateLimitExceeded,
    Json(serde_json::Error),
}

impl From<RasterError> for ProjectJsonError {
    fn from(error: RasterError) -> Self {
        Self::Raster(error)
    }
}

impl From<CanvasError> for ProjectJsonError {
    fn from(error: CanvasError) -> Self {
        Self::Canvas(error)
    }
}

impl From<serde_json::Error> for ProjectJsonError {
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

impl Display for ProjectJsonError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Raster(error) => Display::fmt(error, formatter),
            Self::Canvas(error) => Display::fmt(error, formatter),
            Self::CoordinateLimitExceeded => {
                formatter.write_str("patch coordinate exceeds the project JSON limit")
            }
            Self::Json(error) => Display::fmt(error, formatter),
        }
    }
}

impl Error for ProjectJsonError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            Self::Canvas(error) => Some(error),
            Self::Json(error) => Some(error),
            Self::CoordinateLimitExceeded => None,
        }
    }
}
