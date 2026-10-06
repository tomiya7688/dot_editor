//! GUI-independent logical canvas with retained samples and bounded history.

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::flood_region::flood_region;
use crate::raster::{Color, MAX_DIMENSION, MAX_PIXELS, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;
use crate::resolution_field::{DetailPolicy, ResolutionField, ResolutionFieldError};
use crate::split_cell::SplitCell;

const HISTORY_LIMIT: usize = 50;
const MAX_SPLIT_CELLS: usize = 4096;

pub type ChildCoordinate = (u8, u8);

#[derive(Clone, Debug, Eq, PartialEq)]
struct CanvasState {
    resolution: Resolution,
    field: ResolutionField,
    splits: Arc<Vec<SplitCell>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Canvas {
    resolution: Resolution,
    pub(crate) field: ResolutionField,
    pub(crate) splits: Arc<Vec<SplitCell>>,
    history: Vec<CanvasState>,
    future: Vec<CanvasState>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanvasError {
    Raster(RasterError),
    Field(ResolutionFieldError),
    AllocationFailed,
    HistoryAllocationFailed,
    SplitLimitExceeded,
    SplitResolutionOverflow,
    InvalidRegionSize,
    RegionOutOfBounds {
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    },
    ChildCoordinateOutOfBounds {
        x: u8,
        y: u8,
    },
    CellNotSplit {
        x: u32,
        y: u32,
    },
    CellNotExpanded {
        x: u32,
        y: u32,
    },
}

impl Canvas {
    pub(crate) fn from_parts(
        resolution: Resolution,
        field: ResolutionField,
        splits: Vec<SplitCell>,
    ) -> Self {
        Self {
            resolution,
            field,
            splits: Arc::new(splits),
            history: Vec::new(),
            future: Vec::new(),
        }
    }

    pub fn new(resolution: Resolution) -> Result<Self, CanvasError> {
        Ok(Self::from_raster(Raster::new(resolution)?))
    }

    pub fn from_raster(raster: Raster) -> Self {
        let resolution = raster.resolution();
        Self {
            resolution,
            field: ResolutionField::from_raster(raster),
            splits: Arc::new(Vec::new()),
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
        if x < self.resolution.width() && y < self.resolution.height() {
            if let Some(split) = self
                .splits
                .iter()
                .find(|split| split.matches(self.resolution, x, y))
            {
                return Ok(split.base);
            }
        }
        self.field.sample(self.resolution, x, y)
    }

    pub fn sample_child(
        &self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
    ) -> Result<Color, CanvasError> {
        self.validate_parent(x, y)?;
        Self::validate_child(child)?;
        if !self
            .splits
            .iter()
            .any(|split| split.matches(self.resolution, x, y))
        {
            return Err(CanvasError::CellNotSplit { x, y });
        }
        // Sampling a collapsed child does not allocate a doubled raster.
        let grid = self.child_sampling_resolution()?;
        Ok(self
            .field
            .sample(grid, 2 * x + u32::from(child.0), 2 * y + u32::from(child.1))?)
    }

    pub fn render(&self) -> Result<Raster, RasterError> {
        self.projection(self.resolution)
    }

    pub fn render_at(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        self.field.render(resolution)
    }

    pub fn native_resolution(&self) -> Result<Resolution, CanvasError> {
        if self
            .splits
            .iter()
            .any(|split| split.resolution == self.resolution && split.expanded)
        {
            self.child_resolution()
        } else {
            Ok(self.resolution)
        }
    }

    pub fn render_native(&self) -> Result<Raster, CanvasError> {
        let target = self.native_resolution()?;
        if target == self.resolution {
            return Ok(self.render()?);
        }
        let source = self.render()?;
        let mut output = Raster::new(target)?;
        for y in 0..self.resolution.height() {
            for x in 0..self.resolution.width() {
                let color = source.sample(x, y)?;
                for child_y in 0..2 {
                    for child_x in 0..2 {
                        output.paint(2 * x + child_x, 2 * y + child_y, color);
                    }
                }
            }
        }
        for split in self
            .splits
            .iter()
            .copied()
            .filter(|split| split.resolution == self.resolution && split.expanded)
        {
            for child_y in 0..2u8 {
                for child_x in 0..2u8 {
                    let color = self.sample_child(split.x, split.y, (child_x, child_y))?;
                    output.paint(
                        2 * split.x + u32::from(child_x),
                        2 * split.y + u32::from(child_y),
                        color,
                    );
                }
            }
        }
        Ok(output)
    }

    pub fn has_detail_at(&self, x: u32, y: u32) -> Result<bool, RasterError> {
        if self.field.has_detail_at(self.resolution, x, y)? {
            return Ok(true);
        }
        let bounds = FieldBounds::cell(self.resolution, x, y);
        for split in self.splits.iter().copied() {
            let split_bounds = split.bounds();
            if let Some(overlap) = split_bounds.intersection(bounds) {
                if overlap == split_bounds {
                    return Ok(true);
                }
                let center_x = Coordinate::center(split.x, split.resolution.width());
                let center_y = Coordinate::center(split.y, split.resolution.height());
                if bounds.contains(center_x, center_y)
                    && split.base != self.field.sample(split.resolution, split.x, split.y)?
                {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    pub fn is_split(&self, x: u32, y: u32) -> bool {
        self.splits
            .iter()
            .any(|split| split.matches(self.resolution, x, y) && split.expanded)
    }

    pub fn split_cell(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() || self.is_split(x, y) {
            return Ok(false);
        }
        Ok(self.split_region(x, y, 1, 1)? != 0)
    }

    /// Expands every cell in a positive, fully contained rectangle. Returns the
    /// number newly expanded, including previously collapsed cells. Existing
    /// parent overrides and children survive re-expansion. The whole operation
    /// is one undo step; invalid bounds or budgets leave state/history intact.
    pub fn split_region(
        &mut self,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<usize, CanvasError> {
        if width == 0 || height == 0 {
            return Err(CanvasError::InvalidRegionSize);
        }
        let end_x = x.checked_add(width);
        let end_y = y.checked_add(height);
        let (Some(end_x), Some(end_y)) = (end_x, end_y) else {
            return Err(CanvasError::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            });
        };
        if end_x > self.resolution.width() || end_y > self.resolution.height() {
            return Err(CanvasError::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            });
        }
        self.child_resolution()?;
        let area = u64::from(width) * u64::from(height);
        let mut retained = 0;
        let mut expanded = 0;
        for split in self.splits.iter().filter(|split| {
            split.resolution == self.resolution
                && (x..end_x).contains(&split.x)
                && (y..end_y).contains(&split.y)
        }) {
            retained += 1;
            expanded += u64::from(split.expanded);
        }
        let additional = area - retained;
        if additional > (MAX_SPLIT_CELLS - self.splits.len()) as u64 {
            return Err(CanvasError::SplitLimitExceeded);
        }
        let changed = area - expanded;
        if changed == 0 {
            return Ok(0);
        }
        // The budget check bounds both conversions and iteration to 4096 cells.
        let mut splits = self.copy_splits(additional as usize)?;
        for py in y..end_y {
            for px in x..end_x {
                if let Some(split) = splits
                    .iter_mut()
                    .find(|split| split.matches(self.resolution, px, py))
                {
                    split.expanded = true;
                } else {
                    splits.push(SplitCell {
                        resolution: self.resolution,
                        x: px,
                        y: py,
                        base: self.field.sample(self.resolution, px, py)?,
                        expanded: true,
                    });
                }
            }
        }
        self.commit(self.resolution, self.field.clone(), Arc::new(splits))?;
        Ok(changed as usize)
    }

    pub fn collapse_cell(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        let Some(index) = self
            .splits
            .iter()
            .position(|split| split.matches(self.resolution, x, y) && split.expanded)
        else {
            return Ok(false);
        };
        let mut splits = self.copy_splits(0)?;
        splits[index].expanded = false;
        self.commit(self.resolution, self.field.clone(), Arc::new(splits))?;
        Ok(true)
    }

    pub fn paint_child(
        &mut self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        Self::validate_child(child)?;
        if !self.is_split(x, y) {
            return Err(CanvasError::CellNotExpanded { x, y });
        }
        let grid = self.child_resolution()?;
        let child_x = 2 * x + u32::from(child.0);
        let child_y = 2 * y + u32::from(child.1);
        let has_detail = self.field.has_detail_at(grid, child_x, child_y)?;
        let current = self.field.sample(grid, child_x, child_y)?;
        if current == color && !(policy == DetailPolicy::Discard && has_detail) {
            return Ok(false);
        }
        let raw = self.field.sample_raw_cell(grid, child_x, child_y)?;
        let delta = std::array::from_fn(|i| i64::from(color[i]) - raw[i]);
        let mut field = self.field.clone();
        let field_changed = field.paint(grid, child_x, child_y, color, policy)?;
        let mut splits = self.copy_splits(0)?;
        let metadata_changed = Self::update_splits(
            &mut splits,
            FieldBounds::cell(grid, child_x, child_y),
            policy,
            color,
            delta,
            Some((self.resolution, x, y)),
        );
        if !field_changed && !metadata_changed {
            return Ok(false);
        }
        self.commit(self.resolution, field, Arc::new(splits))?;
        Ok(true)
    }

    pub fn erase_child(
        &mut self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        self.paint_child(x, y, child, [0; 4], policy)
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
            DetailPolicy::Discard => ResolutionField::from_raster(self.projection(resolution)?),
        };
        let splits = match policy {
            DetailPolicy::Preserve => self.splits.clone(),
            DetailPolicy::Discard => Arc::new(Vec::new()),
        };
        self.commit(resolution, field, splits)?;
        Ok(true)
    }

    pub fn paint(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        let has_detail = self.has_detail_at(x, y)?;
        let current = self.sample(x, y)?;
        if current == color && !(policy == DetailPolicy::Discard && has_detail) {
            return Ok(false);
        }
        let mut splits = self.copy_splits(0)?;
        let mut field = self.field.clone();
        if !Self::edit_cell(
            self.resolution,
            &mut field,
            &mut splits,
            (x, y),
            color,
            policy,
        )? {
            return Ok(false);
        }
        self.commit(self.resolution, field, Arc::new(splits))?;
        Ok(true)
    }

    /// Fills a four-connected region of equal logical RGBA samples. Returns the
    /// number of targeted cells; same-color discard targets only detailed cells.
    /// All edits form one undo step. Any error leaves state and history intact.
    pub fn fill(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<usize, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(0);
        }
        let original = self.sample(x, y)?;
        if original == color && policy == DetailPolicy::Preserve {
            return Ok(0);
        }
        let view = self.render()?;
        let mut points = flood_region(&view, x, y)?;
        let pixel_count = self.resolution.width() as usize * self.resolution.height() as usize;
        let mut has_detail = !self.splits.is_empty();
        let mut count = 0;
        for index in 0..points.len() {
            let (px, py) = points[index];
            let detail = self.has_detail_at(px, py)?;
            has_detail |= detail;
            if original != color || detail {
                points[count] = (px, py);
                count += 1;
            }
        }
        points.truncate(count);
        if count == 0 {
            return Ok(0);
        }
        // Avoid one patch per pixel for a uniform whole-canvas replacement.
        // Preserve must never flatten fine samples or saved split metadata.
        if count == pixel_count && (policy == DetailPolicy::Discard || !has_detail) {
            let mut solid = Raster::new(Resolution::new(1, 1).expect("positive resolution"))?;
            solid.paint(0, 0, color);
            self.commit(
                self.resolution,
                ResolutionField::from_raster(solid),
                Arc::new(Vec::new()),
            )?;
        } else {
            let mut field = self.field.clone();
            let mut splits = self.copy_splits(0)?;
            for point in points {
                Self::edit_cell(
                    self.resolution,
                    &mut field,
                    &mut splits,
                    point,
                    color,
                    policy,
                )?;
            }
            self.commit(self.resolution, field, Arc::new(splits))?;
        }
        Ok(count)
    }

    fn edit_cell(
        grid: Resolution,
        field: &mut ResolutionField,
        splits: &mut Vec<SplitCell>,
        (x, y): (u32, u32),
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if policy == DetailPolicy::Preserve {
            if let Some(split) = splits.iter_mut().find(|split| split.matches(grid, x, y)) {
                let changed = split.base != color;
                split.base = color;
                return Ok(changed);
            }
        }
        let raw = field.sample_raw_cell(grid, x, y)?;
        let delta = std::array::from_fn(|i| i64::from(color[i]) - raw[i]);
        let field_changed = field.paint(grid, x, y, color, policy)?;
        let metadata_changed = Self::update_splits(
            splits,
            FieldBounds::cell(grid, x, y),
            policy,
            color,
            delta,
            None,
        );
        Ok(field_changed || metadata_changed)
    }

    pub fn erase(&mut self, x: u32, y: u32, policy: DetailPolicy) -> Result<bool, CanvasError> {
        self.paint(x, y, [0; 4], policy)
    }

    pub fn discard_detail(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if !self.has_detail_at(x, y)? {
            return Ok(false);
        }
        let color = self.sample(x, y)?;
        self.paint(x, y, color, DetailPolicy::Discard)
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
        splits: Arc<Vec<SplitCell>>,
    ) -> Result<(), CanvasError> {
        self.reserve_history_slot()?;
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(self.snapshot());
        self.future.clear();
        self.resolution = resolution;
        self.field = field;
        self.splits = splits;
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
            splits: self.splits.clone(),
        }
    }

    fn restore(&mut self, state: CanvasState) {
        self.resolution = state.resolution;
        self.field = state.field;
        self.splits = state.splits;
    }

    fn copy_splits(&self, additional: usize) -> Result<Vec<SplitCell>, CanvasError> {
        let capacity = self
            .splits
            .len()
            .checked_add(additional)
            .ok_or(CanvasError::SplitLimitExceeded)?;
        let mut splits = Vec::new();
        splits
            .try_reserve_exact(capacity)
            .map_err(|_| CanvasError::AllocationFailed)?;
        splits.extend(self.splits.iter().copied());
        Ok(splits)
    }

    fn child_resolution(&self) -> Result<Resolution, CanvasError> {
        let resolution = self.child_sampling_resolution()?;
        let width = resolution.width();
        let height = resolution.height();
        if width > MAX_DIMENSION || height > MAX_DIMENSION {
            return Err(CanvasError::Raster(RasterError::DimensionLimitExceeded {
                width,
                height,
            }));
        }
        if u64::from(width) * u64::from(height) > MAX_PIXELS as u64 {
            return Err(CanvasError::Raster(RasterError::PixelBudgetExceeded));
        }
        Ok(resolution)
    }

    fn child_sampling_resolution(&self) -> Result<Resolution, CanvasError> {
        let width = self
            .resolution
            .width()
            .checked_mul(2)
            .ok_or(CanvasError::SplitResolutionOverflow)?;
        let height = self
            .resolution
            .height()
            .checked_mul(2)
            .ok_or(CanvasError::SplitResolutionOverflow)?;
        Resolution::new(width, height).map_err(|_| CanvasError::SplitResolutionOverflow)
    }

    fn validate_parent(&self, x: u32, y: u32) -> Result<(), CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Err(CanvasError::Raster(RasterError::CoordinateOutOfBounds {
                x,
                y,
            }));
        }
        Ok(())
    }

    fn validate_child(child: ChildCoordinate) -> Result<(), CanvasError> {
        if child.0 > 1 || child.1 > 1 {
            return Err(CanvasError::ChildCoordinateOutOfBounds {
                x: child.0,
                y: child.1,
            });
        }
        Ok(())
    }

    fn projection(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        let mut raster = self.field.render(resolution)?;
        for split in self
            .splits
            .iter()
            .filter(|split| split.resolution == resolution)
        {
            raster.paint(split.x, split.y, split.base);
        }
        Ok(raster)
    }

    fn update_splits(
        splits: &mut Vec<SplitCell>,
        target: FieldBounds,
        policy: DetailPolicy,
        replacement: Color,
        delta: [i64; 4],
        skip: Option<(Resolution, u32, u32)>,
    ) -> bool {
        let mut changed = false;
        splits.retain_mut(|split| {
            if skip.is_some_and(|(resolution, x, y)| split.matches(resolution, x, y)) {
                return true;
            }
            let bounds = split.bounds();
            let Some(overlap) = bounds.intersection(target) else {
                return true;
            };
            let center_x = Coordinate::center(split.x, split.resolution.width());
            let center_y = Coordinate::center(split.y, split.resolution.height());
            match policy {
                DetailPolicy::Preserve => {
                    if target.contains(center_x, center_y) {
                        let updated = std::array::from_fn(|channel| {
                            (i64::from(split.base[channel]) + delta[channel]).clamp(0, 255) as u8
                        });
                        if updated != split.base {
                            split.base = updated;
                            changed = true;
                        }
                    }
                    true
                }
                DetailPolicy::Discard => {
                    if overlap == bounds {
                        changed = true;
                        false
                    } else {
                        if target.contains(center_x, center_y) && split.base != replacement {
                            split.base = replacement;
                            changed = true;
                        }
                        true
                    }
                }
            }
        });
        changed
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
            Self::AllocationFailed => formatter.write_str("unable to allocate canvas state"),
            Self::HistoryAllocationFailed => {
                formatter.write_str("unable to allocate canvas history")
            }
            Self::SplitLimitExceeded => formatter.write_str("canvas exceeds its split-cell limit"),
            Self::SplitResolutionOverflow => {
                formatter.write_str("split resolution exceeds the integer range")
            }
            Self::InvalidRegionSize => formatter.write_str("region dimensions must be positive"),
            Self::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            } => {
                write!(
                    formatter,
                    "region ({x}, {y}, {width}, {height}) is outside the canvas"
                )
            }
            Self::ChildCoordinateOutOfBounds { x, y } => {
                write!(formatter, "child coordinate ({x}, {y}) is out of bounds")
            }
            Self::CellNotSplit { x, y } => write!(formatter, "cell ({x}, {y}) is not split"),
            Self::CellNotExpanded { x, y } => {
                write!(formatter, "cell ({x}, {y}) is not expanded")
            }
        }
    }
}

impl Error for CanvasError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            Self::Field(error) => Some(error),
            Self::AllocationFailed
            | Self::HistoryAllocationFailed
            | Self::SplitLimitExceeded
            | Self::SplitResolutionOverflow
            | Self::InvalidRegionSize
            | Self::RegionOutOfBounds { .. }
            | Self::ChildCoordinateOutOfBounds { .. }
            | Self::CellNotSplit { .. }
            | Self::CellNotExpanded { .. } => None,
        }
    }
}
