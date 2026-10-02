use hyper_dot_core::raster::{Color, Raster};
use hyper_dot_core::resolution::Resolution;

const CLEAR: Color = [0, 0, 0, 0];
const RED: Color = [255, 0, 0, 255];
const BLUE: Color = [0, 0, 255, 128];

fn raster(width: u32, height: u32) -> Raster {
    Raster::new(Resolution::new(width, height).unwrap()).unwrap()
}

#[test]
fn fills_only_four_connected_region() {
    let mut image = raster(4, 3);
    for (x, y) in [(0, 0), (1, 0), (1, 1), (2, 2), (3, 2)] {
        image.paint(x, y, RED);
    }

    assert_eq!(image.fill(0, 0, BLUE), Ok(3));
    let expected = [
        [BLUE, BLUE, CLEAR, CLEAR],
        [CLEAR, BLUE, CLEAR, CLEAR],
        [CLEAR, CLEAR, RED, RED],
    ];
    for (y, row) in expected.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            assert_eq!(image.sample(x as u32, y as u32), Ok(*color));
        }
    }
}

#[test]
fn non_square_fill_stays_on_its_side_of_a_wall() {
    let mut image = raster(5, 3);
    for y in 0..3 {
        image.paint(2, y, RED);
    }

    assert_eq!(image.fill(0, 1, BLUE), Ok(6));
    for y in 0..3 {
        for x in 0..5 {
            let expected = match x {
                0 | 1 => BLUE,
                2 => RED,
                _ => CLEAR,
            };
            assert_eq!(image.sample(x, y), Ok(expected));
        }
    }
}

#[test]
fn paint_fill_erase() {
    let mut image = raster(3, 2);
    assert!(image.paint(2, 1, RED));
    assert_eq!(image.fill(0, 0, RED), Ok(5));
    assert!(image.erase(0, 0));
    assert_eq!(image.fill(1, 0, CLEAR), Ok(5));
    assert_eq!(image, raster(3, 2));
}

#[test]
fn rgba_matching_includes_alpha_and_hidden_rgb() {
    let mut image = raster(3, 1);
    image.paint(0, 0, [10, 20, 30, 128]);
    image.paint(1, 0, [10, 20, 30, 255]);
    image.paint(2, 0, [10, 20, 30, 0]);

    assert_eq!(image.fill(0, 0, BLUE), Ok(1));
    assert_eq!(image.fill(2, 0, CLEAR), Ok(1));
    assert_eq!(image.sample(0, 0), Ok(BLUE));
    assert_eq!(image.sample(1, 0), Ok([10, 20, 30, 255]));
    assert_eq!(image.sample(2, 0), Ok(CLEAR));
}

#[test]
fn unchanged_color_and_out_of_bounds_seed_do_not_mutate() {
    let mut image = raster(2, 3);
    image.paint(0, 0, RED);
    let before = image.clone();

    assert_eq!(image.fill(0, 0, RED), Ok(0));
    assert_eq!(image.fill(2, 0, BLUE), Ok(0));
    assert_eq!(image.fill(0, 3, BLUE), Ok(0));
    assert_eq!(image.fill(u32::MAX, u32::MAX, BLUE), Ok(0));
    assert_eq!(image, before);
}

#[test]
fn fills_long_single_row_and_column() {
    for (width, height) in [(4096, 1), (1, 4096)] {
        let mut image = raster(width, height);
        assert_eq!(image.fill(0, 0, BLUE), Ok(4096));
        assert_eq!(image.sample(width - 1, height - 1), Ok(BLUE));
        assert_eq!(image.fill(width - 1, height - 1, BLUE), Ok(0));
    }
}
