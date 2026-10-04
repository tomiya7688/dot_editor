//! GUI-independent logical canvas with retained samples and bounded history.

use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::raster::{Color, Raster, RasterError};
use crate::resolution::Resolution;
use crate::resolution_field::{DetailPolicy, ResolutionField, ResolutionFieldError};

const HISTORY_LIMIT: usize = 50;

#[derive(Clone, Debug, Eq, PartialEq)]
struct CanvasState {
    resolution: Resolution,
    field: ResolutionField,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Canvas {
    resolution: Resolution,
    field: ResolutionField,
    history: Vec<CanvasState>,
    future: Vec<CanvasState>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanvasError {
    Raster(RasterError),
    Field(ResolutionFieldError),
    HistoryAllocationFailed,
}

impl Canvas {
    pub fn new(resolution: Resolution) -> Result<Self, CanvasError> {
        Ok(Self::from_raster(Raster::new(resolution)?))
    }

    pub fn from_raster(raster: Raster) -> Self {
        let resolution = raster.resolution();
        Self {
            resolution,
            field: ResolutionField::from_raster(raster),
            history: Vec::new(),
            future: Vec::new(),
        }
    }

    pub const fn resolution(&self) -> Resolution {
        self.resolution
    }

    pub fn retained_resolution(&self) -> Resolution {
        self.field.retained_resolution()
    }

    pub fn can_undo(&self) -> bool {
        !self.history.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.future.is_empty()
    }

    pub fn sample(&self, x: u32, y: u32) -> Result<Color, RasterError> {
        self.field.sample(self.resolution, x, y)
    }

    pub fn render(&self) -> Result<Raster, RasterError> {
        self.field.render(self.resolution)
    }

    pub fn render_at(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        self.field.render(resolution)
    }

    pub fn has_detail_at(&self, x: u32, y: u32) -> Result<bool, RasterError> {
        self.field.has_detail_at(self.resolution, x, y)
    }

    pub fn set_resolution(
        &mut self,
        resolution: Resolution,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if resolution == self.resolution && policy == DetailPolicy::Preserve {
            return Ok(false);
        }
        let field = match policy {
            DetailPolicy::Preserve => self.field.clone(),
            DetailPolicy::Discard => ResolutionField::from_raster(self.field.render(resolution)?),
        };
        self.commit(resolution, field)?;
        Ok(true)
    }

    pub fn paint(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        let mut field = self.field.clone();
        if !field.paint(self.resolution, x, y, color, policy)? {
            return Ok(false);
        }
        self.commit(self.resolution, field)?;
        Ok(true)
    }

    pub fn erase(&mut self, x: u32, y: u32, policy: DetailPolicy) -> Result<bool, CanvasError> {
        let mut field = self.field.clone();
        if !field.erase(self.resolution, x, y, policy)? {
            return Ok(false);
        }
        self.commit(self.resolution, field)?;
        Ok(true)
    }

    pub fn undo(&mut self) -> Result<bool, CanvasError> {
        if self.history.is_empty() {
            return Ok(false);
        }
        self.future
            .try_reserve(1)
            .map_err(|_| CanvasError::HistoryAllocationFailed)?;
        self.future.push(self.snapshot());
        let state = self.history.pop().expect("history was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    pub fn redo(&mut self) -> Result<bool, CanvasError> {
        if self.future.is_empty() {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(self.snapshot());
        let state = self.future.pop().expect("future was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    fn commit(
        &mut self,
        resolution: Resolution,
        field: ResolutionField,
    ) -> Result<(), CanvasError> {
        self.reserve_history_slot()?;
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(self.snapshot());
        self.future.clear();
        self.resolution = resolution;
        self.field = field;
        Ok(())
    }

    fn reserve_history_slot(&mut self) -> Result<(), CanvasError> {
        if self.history.len() < HISTORY_LIMIT {
            self.history
                .try_reserve(1)
                .map_err(|_| CanvasError::HistoryAllocationFailed)?;
        }
        Ok(())
    }

    fn snapshot(&self) -> CanvasState {
        CanvasState {
            resolution: self.resolution,
            field: self.field.clone(),
        }
    }

    fn restore(&mut self, state: CanvasState) {
        self.resolution = state.resolution;
        self.field = state.field;
    }
}

impl From<RasterError> for CanvasError {
    fn from(error: RasterError) -> Self {
        Self::Raster(error)
    }
}

impl From<ResolutionFieldError> for CanvasError {
    fn from(error: ResolutionFieldError) -> Self {
        Self::Field(error)
    }
}

impl Display for CanvasError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Raster(error) => Display::fmt(error, formatter),
            Self::Field(error) => Display::fmt(error, formatter),
            Self::HistoryAllocationFailed => {
                formatter.write_str("unable to allocate canvas history")
            }
        }
    }
}

impl Error for CanvasError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            Self::Field(error) => Some(error),
            Self::HistoryAllocationFailed => None,
        }
    }
}
