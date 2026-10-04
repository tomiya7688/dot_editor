use hyper_dot_core::canvas::{Canvas, CanvasError};
use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

fn patterned() -> Raster {
    let mut raster = Raster::new(grid(16, 16)).unwrap();
    for y in 0..16 {
        for x in 0..16 {
            raster.paint(x, y, [70 + x as u8, 90 + y as u8, 110 + (x + y) as u8, 255]);
        }
    }
    raster
}

#[test]
fn logical_resolution_changes_without_resampling_the_retained_field() {
    let original = patterned();
    let mut canvas = Canvas::from_raster(original.clone());

    assert!(
        canvas
            .set_resolution(grid(7, 7), DetailPolicy::Preserve)
            .unwrap()
    );
    assert_eq!(canvas.resolution(), grid(7, 7));
    assert_eq!(canvas.retained_resolution(), grid(16, 16));
    assert_eq!(
        canvas.render_at(grid(23, 17)).unwrap().resolution(),
        grid(23, 17)
    );
    assert_eq!(canvas.render_at(grid(16, 16)).unwrap(), original);
}

#[test]
fn undo_redo_restores_logical_resolution_and_preserved_detail() {
    let original = patterned();
    let mut canvas = Canvas::from_raster(original.clone());
    canvas
        .set_resolution(grid(7, 7), DetailPolicy::Preserve)
        .unwrap();
    let anchor = canvas.sample(2, 3).unwrap();
    let color = [120, 130, 140, 200];

    assert!(canvas.paint(2, 3, color, DetailPolicy::Preserve).unwrap());
    assert_eq!(canvas.sample(2, 3), Ok(color));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.sample(2, 3), Ok(anchor));
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.sample(2, 3), Ok(color));
    assert_eq!(canvas.retained_resolution(), grid(16, 16));

    assert!(canvas.undo().unwrap());
    assert!(
        canvas
            .set_resolution(grid(16, 16), DetailPolicy::Preserve)
            .unwrap()
    );
    assert_eq!(canvas.render().unwrap(), original);
}

#[test]
fn discard_is_local_and_undo_restores_the_discarded_samples() {
    let original = patterned();
    let mut canvas = Canvas::from_raster(original.clone());
    canvas
        .set_resolution(grid(7, 7), DetailPolicy::Preserve)
        .unwrap();
    let edited = [23, 45, 67, 255];
    assert!(canvas.paint(1, 1, edited, DetailPolicy::Discard).unwrap());
    assert_eq!(canvas.has_detail_at(1, 1), Ok(false));
    assert_eq!(canvas.has_detail_at(2, 1), Ok(true));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.has_detail_at(1, 1), Ok(true));
    assert_eq!(canvas.render_at(grid(16, 16)).unwrap(), original);
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.has_detail_at(1, 1), Ok(false));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.render_at(grid(16, 16)).unwrap(), original);
}

#[test]
fn discard_resolution_can_be_undone_without_losing_the_previous_grid() {
    let original = patterned();
    let mut canvas = Canvas::from_raster(original.clone());
    assert!(
        canvas
            .set_resolution(grid(7, 5), DetailPolicy::Discard)
            .unwrap()
    );
    assert_eq!(canvas.resolution(), grid(7, 5));
    assert_eq!(canvas.retained_resolution(), grid(7, 5));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.resolution(), grid(16, 16));
    assert_eq!(canvas.render().unwrap(), original);
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.resolution(), grid(7, 5));
}

#[test]
fn no_op_edits_keep_history_and_real_edits_clear_redo() {
    let mut canvas = Canvas::new(grid(16, 16)).unwrap();
    assert!(!canvas.erase(0, 0, DetailPolicy::Preserve).unwrap());
    assert!(!canvas.can_undo());
    assert!(
        canvas
            .paint(0, 0, [1, 2, 3, 4], DetailPolicy::Preserve)
            .unwrap()
    );
    assert!(canvas.undo().unwrap());
    assert!(canvas.can_redo());
    assert!(
        !canvas
            .paint(0, 0, [0, 0, 0, 0], DetailPolicy::Preserve)
            .unwrap()
    );
    assert!(canvas.can_redo());
    assert!(
        canvas
            .paint(1, 0, [4, 3, 2, 1], DetailPolicy::Discard)
            .unwrap()
    );
    assert!(!canvas.can_redo());
    assert!(canvas.undo().unwrap());
}

#[test]
fn history_is_bounded_to_fifty_states() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    for index in 0..60u8 {
        assert!(
            canvas
                .paint(0, 0, [index, 0, 0, 255], DetailPolicy::Discard)
                .unwrap()
        );
    }
    for _ in 0..50 {
        assert!(canvas.undo().unwrap());
    }
    assert!(!canvas.can_undo());
    assert_eq!(canvas.sample(0, 0), Ok([9, 0, 0, 255]));
}

#[test]
fn failed_discard_resolution_change_keeps_the_canvas_and_history() {
    let mut canvas = Canvas::new(grid(3, 2)).unwrap();
    assert!(matches!(
        canvas.set_resolution(grid(5000, 1), DetailPolicy::Discard),
        Err(CanvasError::Raster(
            RasterError::DimensionLimitExceeded { .. }
        ))
    ));
    assert_eq!(canvas.resolution(), grid(3, 2));
    assert!(!canvas.can_undo());
    assert!(!canvas.can_redo());
}
