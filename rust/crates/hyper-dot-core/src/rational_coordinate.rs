use std::cmp::Ordering;

/// Exact normalized coordinate in the closed unit interval.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct RationalCoordinate {
    numerator: u64,
    denominator: u64,
}

impl RationalCoordinate {
    /// Exact pixel position inside a source extent, independently of its origin.
    pub(crate) fn relative_floor(self, start: Self, end: Self, pixels: u32) -> u32 {
        let (numerator, denominator) = self.relative_ratio(start, end, pixels);
        (numerator / denominator) as u32
    }

    pub(crate) fn relative_ceil(self, start: Self, end: Self, pixels: u32) -> u32 {
        let (numerator, denominator) = self.relative_ratio(start, end, pixels);
        numerator.div_ceil(denominator) as u32
    }

    fn relative_ratio(self, start: Self, end: Self, pixels: u32) -> (u128, u128) {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let distance = u128::from(self.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(self.denominator);
        (
            distance * u128::from(end.denominator) * u128::from(pixels),
            u128::from(self.denominator) * span,
        )
    }

    pub(crate) fn interpolate(start: Self, end: Self, position: u32, pixels: u32) -> Self {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let numerator =
            u128::from(start.numerator) * u128::from(end.denominator) * u128::from(pixels)
                + span * u128::from(position);
        let denominator =
            u128::from(start.denominator) * u128::from(end.denominator) * u128::from(pixels);
        let (mut a, mut b) = (numerator, denominator);
        while b != 0 {
            (a, b) = (b, a % b);
        }
        // Original extents are bounded JSON fractions or the unit rectangle;
        // origins always refer to that original extent, never interpolated ones.
        Self::new((numerator / a) as u64, (denominator / a) as u64)
    }

    pub(crate) fn density(start: Self, end: Self, pixels: u32) -> u32 {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let numerator =
            u128::from(pixels) * u128::from(start.denominator) * u128::from(end.denominator);
        // Retained resolution is a u32 summary; sampling still uses exact extents.
        numerator.div_ceil(span).min(u128::from(u32::MAX)) as u32
    }

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
