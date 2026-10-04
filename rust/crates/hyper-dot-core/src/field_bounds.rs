use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct FieldBounds {
    pub(crate) left: Coordinate,
    pub(crate) top: Coordinate,
    pub(crate) right: Coordinate,
    pub(crate) bottom: Coordinate,
}

impl FieldBounds {
    pub(crate) fn full() -> Self {
        Self {
            left: Coordinate::new(0, 1),
            top: Coordinate::new(0, 1),
            right: Coordinate::new(1, 1),
            bottom: Coordinate::new(1, 1),
        }
    }

    pub(crate) fn cell(grid: Resolution, x: u32, y: u32) -> Self {
        Self {
            left: Coordinate::new(u64::from(x), u64::from(grid.width())),
            top: Coordinate::new(u64::from(y), u64::from(grid.height())),
            right: Coordinate::new(u64::from(x) + 1, u64::from(grid.width())),
            bottom: Coordinate::new(u64::from(y) + 1, u64::from(grid.height())),
        }
    }

    pub(crate) fn contains(self, x: Coordinate, y: Coordinate) -> bool {
        self.left <= x && x < self.right && self.top <= y && y < self.bottom
    }

    pub(crate) fn intersection(self, other: Self) -> Option<Self> {
        let overlap = Self {
            left: self.left.max(other.left),
            top: self.top.max(other.top),
            right: self.right.min(other.right),
            bottom: self.bottom.min(other.bottom),
        };
        (overlap.left < overlap.right && overlap.top < overlap.bottom).then_some(overlap)
    }

    /// Disjoint remainder strips. The cut must lie inside this rectangle.
    pub(crate) fn outside(self, cut: Self) -> impl Iterator<Item = Self> {
        [
            Self {
                bottom: cut.top,
                ..self
            },
            Self {
                top: cut.bottom,
                ..self
            },
            Self {
                top: cut.top,
                bottom: cut.bottom,
                right: cut.left,
                ..self
            },
            Self {
                top: cut.top,
                bottom: cut.bottom,
                left: cut.right,
                ..self
            },
        ]
        .into_iter()
        .filter(|piece| piece.left < piece.right && piece.top < piece.bottom)
    }
}
