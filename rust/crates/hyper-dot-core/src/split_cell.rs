use crate::field_bounds::FieldBounds;
use crate::raster::Color;
use crate::resolution::Resolution;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct SplitCell {
    pub(crate) resolution: Resolution,
    pub(crate) x: u32,
    pub(crate) y: u32,
    pub(crate) base: Color,
    pub(crate) expanded: bool,
}

impl SplitCell {
    pub(crate) fn bounds(self) -> FieldBounds {
        FieldBounds::cell(self.resolution, self.x, self.y)
    }

    pub(crate) fn matches(self, resolution: Resolution, x: u32, y: u32) -> bool {
        self.resolution == resolution && self.x == x && self.y == y
    }
}
