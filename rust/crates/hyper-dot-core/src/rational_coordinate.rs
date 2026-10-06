use std::cmp::Ordering;

/// Exact normalized coordinate in the closed unit interval.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct RationalCoordinate {
    numerator: u64,
    denominator: u64,
}

impl RationalCoordinate {
    pub(crate) const fn fraction(self) -> [u64; 2] {
        [self.numerator, self.denominator]
    }

    pub(crate) fn new(numerator: u64, denominator: u64) -> Self {
        debug_assert!(denominator > 0 && numerator <= denominator);
        let (mut a, mut b) = (numerator, denominator);
        while b != 0 {
            (a, b) = (b, a % b);
        }
        Self {
            numerator: numerator / a,
            denominator: denominator / a,
        }
    }

    pub(crate) fn center(position: u32, extent: u32) -> Self {
        Self::new(2 * u64::from(position) + 1, 2 * u64::from(extent))
    }

    pub(crate) fn floor_on_grid(self, extent: u32) -> u32 {
        ((u128::from(self.numerator) * u128::from(extent)) / u128::from(self.denominator)) as u32
    }

    pub(crate) fn ceil_on_grid(self, extent: u32) -> u32 {
        (u128::from(self.numerator) * u128::from(extent)).div_ceil(u128::from(self.denominator))
            as u32
    }
}

impl Ord for RationalCoordinate {
    fn cmp(&self, other: &Self) -> Ordering {
        (u128::from(self.numerator) * u128::from(other.denominator))
            .cmp(&(u128::from(other.numerator) * u128::from(self.denominator)))
    }
}

impl PartialOrd for RationalCoordinate {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
