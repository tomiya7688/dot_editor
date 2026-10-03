use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::ResolutionField;

fn resolution(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

fn patterned(width: u32, height: u32) -> Raster {
    let mut raster = Raster::new(resolution(width, height)).unwrap();
    for y in 0..height {
        for x in 0..width {
            raster.paint(
                x,
                y,
                [
                    (70 + x % 40) as u8,
                    (90 + y % 40) as u8,
                    (110 + (x + y) % 40) as u8,
                    (150 + (x * y) % 70) as u8,
                ],
            );
        }
    }
    raster
}

#[test]
fn arbitrary_resolution_roundtrip() {
    let original = patterned(16, 16);
    let field = ResolutionField::from_raster(original.clone());
    let before = field.clone();

    for (width, height) in [(7, 7), (23, 17), (1, 31), (31, 1), (16, 16)] {
        let projected = field.render(resolution(width, height)).unwrap();
        assert_eq!(projected.resolution(), resolution(width, height));
        assert_eq!(field.retained_resolution(), resolution(16, 16));
    }
    assert_eq!(field.render(resolution(16, 16)), Ok(original));
    assert_eq!(field, before);
}

#[test]
fn rectangular_source_roundtrip() {
    let original = patterned(23, 17);
    let field = ResolutionField::from_raster(original.clone());
    field.render(resolution(7, 5)).unwrap();
    field.render(resolution(41, 13)).unwrap();

    assert_eq!(field.render(resolution(23, 17)), Ok(original));
    assert_eq!(field.retained_resolution(), resolution(23, 17));
}

#[test]
fn center_on_source_boundary_selects_right_and_bottom_pixel() {
    let mut source = Raster::new(resolution(2, 2)).unwrap();
    source.paint(0, 0, [255, 0, 0, 255]);
    source.paint(1, 0, [0, 255, 0, 255]);
    source.paint(0, 1, [0, 0, 255, 255]);
    source.paint(1, 1, [10, 20, 30, 40]);
    let field = ResolutionField::from_raster(source);

    assert_eq!(field.sample(resolution(1, 1), 0, 0), Ok([10, 20, 30, 40]));
    assert_eq!(field.sample(resolution(4, 4), 1, 1), Ok([255, 0, 0, 255]));
    assert_eq!(field.sample(resolution(4, 4), 2, 1), Ok([0, 255, 0, 255]));
}

#[test]
fn unaligned_projection_matches_exact_center_fixture() {
    let mut source = Raster::new(resolution(3, 2)).unwrap();
    let colors = [
        [[1, 0, 0, 11], [2, 0, 0, 22], [3, 0, 0, 33]],
        [[4, 0, 0, 44], [5, 0, 0, 55], [6, 0, 0, 66]],
    ];
    for (y, row) in colors.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            source.paint(x as u32, y as u32, *color);
        }
    }
    let field = ResolutionField::from_raster(source);
    let projected = field.render(resolution(5, 3)).unwrap();
    let expected = [
        [
            colors[0][0],
            colors[0][0],
            colors[0][1],
            colors[0][2],
            colors[0][2],
        ],
        [
            colors[1][0],
            colors[1][0],
            colors[1][1],
            colors[1][2],
            colors[1][2],
        ],
        [
            colors[1][0],
            colors[1][0],
            colors[1][1],
            colors[1][2],
            colors[1][2],
        ],
    ];
    for (y, row) in expected.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            assert_eq!(projected.sample(x as u32, y as u32), Ok(*color));
        }
    }
}

#[test]
fn downscale_retains_unsampled_detail_and_views_are_independent() {
    let mut source = Raster::new(resolution(16, 16)).unwrap();
    source.paint(0, 0, [255, 0, 0, 255]);
    let field = ResolutionField::from_raster(source.clone());
    let mut view = field.render(resolution(1, 1)).unwrap();
    assert_eq!(view.sample(0, 0), Ok([0, 0, 0, 0]));
    view.paint(0, 0, [0, 255, 0, 255]);

    assert_eq!(field.render(resolution(16, 16)), Ok(source));
    assert_eq!(
        field.clone().sample(resolution(16, 16), 0, 0),
        Ok([255, 0, 0, 255])
    );
}

#[test]
fn sample_handles_largest_logical_grid_and_rejects_outside_coordinates() {
    let source = patterned(23, 17);
    let last = source.sample(22, 16).unwrap();
    let field = ResolutionField::from_raster(source);
    let grid = resolution(u32::MAX, u32::MAX);

    assert_eq!(field.sample(grid, u32::MAX - 1, u32::MAX - 1), Ok(last));
    assert_eq!(
        field.sample(grid, u32::MAX, 0),
        Err(RasterError::CoordinateOutOfBounds { x: u32::MAX, y: 0 })
    );
    assert_eq!(
        field.sample(resolution(2, 3), 0, 3),
        Err(RasterError::CoordinateOutOfBounds { x: 0, y: 3 })
    );
}

#[test]
fn rejected_output_allocation_keeps_retained_source() {
    let original = patterned(3, 2);
    let field = ResolutionField::from_raster(original.clone());

    assert_eq!(
        field.render(resolution(4096, 4096)),
        Err(RasterError::PixelBudgetExceeded)
    );
    assert_eq!(field.render(resolution(3, 2)), Ok(original));
}
