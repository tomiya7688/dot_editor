use hyper_dot_core::canvas::{Canvas, CanvasError, ChildCoordinate};
use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

fn patterned() -> Raster {
    let mut raster = Raster::new(grid(16, 12)).unwrap();
    for y in 0..12 {
        for x in 0..16 {
            raster.paint(x, y, [40 + x as u8, 60 + y as u8, 80 + (x + y) as u8, 255]);
        }
    }
    raster
}

const CHILDREN: [ChildCoordinate; 4] = [(0, 0), (1, 0), (0, 1), (1, 1)];

#[test]
fn split_children_are_independent_and_collapse_restores_the_parent_view() {
    let mut canvas = Canvas::from_raster(patterned());
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    let parent = canvas.sample(1, 1).unwrap();

    assert!(canvas.split_cell(1, 1).unwrap());
    assert!(canvas.is_split(1, 1));
    assert_eq!(canvas.sample(1, 1), Ok(parent));
    assert_eq!(canvas.native_resolution(), Ok(grid(8, 6)));
    let siblings: Vec<_> = CHILDREN
        .iter()
        .map(|child| canvas.sample_child(1, 1, *child).unwrap())
        .collect();

    let replacement = [240, 10, 30, 128];
    assert!(
        canvas
            .paint_child(1, 1, (1, 0), replacement, DetailPolicy::Preserve)
            .unwrap()
    );
    assert_eq!(canvas.sample(1, 1), Ok(parent));
    assert_eq!(canvas.sample_child(1, 1, (1, 0)), Ok(replacement));
    for (index, child) in CHILDREN.iter().enumerate() {
        if *child != (1, 0) {
            assert_eq!(canvas.sample_child(1, 1, *child), Ok(siblings[index]));
        }
    }
    let native = canvas.render_native().unwrap();
    assert_eq!(native.resolution(), grid(8, 6));
    assert_eq!(native.sample(3, 2), Ok(replacement));
    assert_eq!(native.sample(2, 2), Ok(siblings[0]));

    assert!(canvas.collapse_cell(1, 1).unwrap());
    assert!(!canvas.is_split(1, 1));
    assert_eq!(canvas.native_resolution(), Ok(grid(4, 3)));
    assert_eq!(canvas.render().unwrap().sample(1, 1), Ok(parent));
    assert_eq!(canvas.sample_child(1, 1, (1, 0)), Ok(replacement));
    assert!(canvas.split_cell(1, 1).unwrap());
    assert_eq!(canvas.sample_child(1, 1, (1, 0)), Ok(replacement));
}

#[test]
fn child_erase_and_both_detail_policies_keep_the_parent_and_siblings() {
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        for child in CHILDREN {
            let mut canvas = Canvas::from_raster(patterned());
            canvas
                .set_resolution(grid(4, 3), DetailPolicy::Preserve)
                .unwrap();
            canvas.split_cell(1, 1).unwrap();
            let parent = canvas.sample(1, 1).unwrap();
            let siblings: Vec<_> = CHILDREN
                .iter()
                .map(|position| canvas.sample_child(1, 1, *position).unwrap())
                .collect();

            assert!(canvas.erase_child(1, 1, child, policy).unwrap());
            assert_eq!(canvas.sample(1, 1), Ok(parent));
            assert_eq!(canvas.sample_child(1, 1, child), Ok([0; 4]));
            for (index, other) in CHILDREN.iter().enumerate() {
                if *other != child {
                    assert_eq!(canvas.sample_child(1, 1, *other), Ok(siblings[index]));
                }
            }
            assert!(canvas.undo().unwrap());
            for (index, position) in CHILDREN.iter().enumerate() {
                assert_eq!(canvas.sample_child(1, 1, *position), Ok(siblings[index]));
            }
            assert!(canvas.redo().unwrap());
            assert_eq!(canvas.sample_child(1, 1, child), Ok([0; 4]));
        }
    }
}

#[test]
fn child_write_changes_only_its_exact_spatial_region() {
    let mut canvas = Canvas::from_raster(patterned());
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    let before = canvas.render_at(grid(73, 61)).unwrap();
    canvas
        .paint_child(1, 1, (1, 1), [3, 4, 5, 6], DetailPolicy::Preserve)
        .unwrap();
    let after = canvas.render_at(grid(73, 61)).unwrap();

    for y in 0..61 {
        for x in 0..73 {
            let gx = (2 * u64::from(x) + 1) * 8 / (2 * 73);
            let gy = (2 * u64::from(y) + 1) * 6 / (2 * 61);
            let in_child = gx == 3 && gy == 3;
            if !in_child {
                assert_eq!(after.sample(x, y), before.sample(x, y), "pixel ({x}, {y})");
            }
        }
    }
}

#[test]
fn parent_preserve_override_keeps_children_and_parent_discard_removes_split_metadata() {
    let mut canvas = Canvas::from_raster(patterned());
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    let children: Vec<_> = CHILDREN
        .iter()
        .map(|child| canvas.sample_child(1, 1, *child).unwrap())
        .collect();
    let parent = [210, 30, 90, 180];

    assert!(canvas.paint(1, 1, parent, DetailPolicy::Preserve).unwrap());
    assert_eq!(canvas.sample(1, 1), Ok(parent));
    for (index, child) in CHILDREN.iter().enumerate() {
        assert_eq!(canvas.sample_child(1, 1, *child), Ok(children[index]));
    }

    assert!(canvas.paint(1, 1, parent, DetailPolicy::Discard).unwrap());
    assert!(!canvas.is_split(1, 1));
    assert_eq!(
        canvas.sample_child(1, 1, (0, 0)),
        Err(CanvasError::CellNotSplit { x: 1, y: 1 })
    );
    assert!(canvas.undo().unwrap());
    assert!(canvas.is_split(1, 1));
    assert_eq!(canvas.sample(1, 1), Ok(parent));
    assert_eq!(canvas.sample_child(1, 1, (1, 1)), Ok(children[3]));
}

#[test]
fn split_metadata_survives_grid_changes_and_history_restores_it() {
    let mut canvas = Canvas::from_raster(patterned());
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    let child = [7, 8, 9, 10];
    canvas
        .paint_child(1, 1, (0, 1), child, DetailPolicy::Discard)
        .unwrap();
    let before = canvas.clone();

    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    assert!(!canvas.is_split(1, 1));
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    assert!(canvas.is_split(1, 1));
    assert_eq!(canvas.sample_child(1, 1, (0, 1)), Ok(child));

    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.resolution(), grid(7, 5));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas.resolution(), before.resolution());
    assert_eq!(canvas.render_native(), before.render_native());
    assert_eq!(canvas.sample_child(1, 1, (0, 1)), Ok(child));
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.resolution(), grid(7, 5));
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.resolution(), grid(4, 3));
}

#[test]
fn invalid_children_unexpanded_cells_and_unsafe_split_grids_are_rejected() {
    let mut canvas = Canvas::new(grid(4, 3)).unwrap();
    assert_eq!(
        canvas.sample_child(0, 0, (0, 0)),
        Err(CanvasError::CellNotSplit { x: 0, y: 0 })
    );
    assert_eq!(
        canvas.paint_child(0, 0, (0, 0), [1; 4], DetailPolicy::Preserve),
        Err(CanvasError::CellNotExpanded { x: 0, y: 0 })
    );
    assert!(canvas.split_cell(0, 0).unwrap());
    assert_eq!(
        canvas.sample_child(0, 0, (2, 0)),
        Err(CanvasError::ChildCoordinateOutOfBounds { x: 2, y: 0 })
    );
    assert!(!canvas.split_cell(4, 0).unwrap());
    assert!(!canvas.collapse_cell(4, 0).unwrap());

    let mut edge = Canvas::new(grid(4096, 1)).unwrap();
    assert!(matches!(
        edge.split_cell(0, 0),
        Err(CanvasError::Raster(
            RasterError::DimensionLimitExceeded { .. }
        ))
    ));
    assert!(!edge.can_undo());
}

#[test]
fn splitting_is_local_noop_safe_and_collapse_does_not_discard_children() {
    let mut canvas = Canvas::new(grid(4, 3)).unwrap();
    assert!(!canvas.split_cell(4, 0).unwrap());
    assert!(!canvas.can_undo());
    assert!(canvas.split_cell(1, 1).unwrap());
    assert!(!canvas.split_cell(1, 1).unwrap());
    assert!(canvas.collapse_cell(1, 1).unwrap());
    assert!(!canvas.collapse_cell(1, 1).unwrap());
    assert!(!canvas.is_split(1, 1));
    assert!(canvas.undo().unwrap());
    assert!(canvas.is_split(1, 1));
}

#[test]
fn same_color_discard_removes_cross_grid_split_metadata_and_is_undoable() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(16, 16), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(0, 0).unwrap();
    canvas
        .paint(0, 0, [180, 40, 50, 255], DetailPolicy::Preserve)
        .unwrap();
    canvas.collapse_cell(0, 0).unwrap();
    canvas
        .set_resolution(grid(7, 7), DetailPolicy::Preserve)
        .unwrap();

    assert!(canvas.has_detail_at(0, 0).unwrap());
    assert!(canvas.discard_detail(0, 0).unwrap());
    assert!(!canvas.has_detail_at(0, 0).unwrap());
    assert!(!canvas.discard_detail(0, 0).unwrap());
    assert!(canvas.undo().unwrap());
    assert!(canvas.has_detail_at(0, 0).unwrap());
    assert!(canvas.redo().unwrap());
    assert!(!canvas.has_detail_at(0, 0).unwrap());
}

#[test]
fn coarse_preserve_updates_split_parent_bases_at_their_centers() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(16, 16), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    let original_base = [40, 60, 80, 100];
    canvas
        .paint(1, 1, original_base, DetailPolicy::Preserve)
        .unwrap();
    canvas.collapse_cell(1, 1).unwrap();
    canvas
        .set_resolution(grid(2, 1), DetailPolicy::Preserve)
        .unwrap();
    let replacement = [5, 6, 7, 8];
    canvas
        .paint(0, 0, replacement, DetailPolicy::Preserve)
        .unwrap();
    let expected = [45, 66, 87, 108];
    canvas
        .set_resolution(grid(16, 16), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(canvas.sample(1, 1), Ok(expected));
}

#[test]
fn discard_updates_only_split_bases_whose_centers_fall_inside_the_cell() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(16, 12), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(2, 2).unwrap();
    canvas
        .paint(2, 2, [180, 40, 50, 255], DetailPolicy::Preserve)
        .unwrap();
    canvas.collapse_cell(2, 2).unwrap();
    canvas.split_cell(1, 2).unwrap();
    let outside = [40, 60, 180, 128];
    canvas.paint(1, 2, outside, DetailPolicy::Preserve).unwrap();
    canvas.collapse_cell(1, 2).unwrap();
    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();

    assert!(canvas.has_detail_at(1, 1).unwrap());
    assert!(canvas.discard_detail(1, 1).unwrap());
    assert!(!canvas.has_detail_at(1, 1).unwrap());
    canvas
        .set_resolution(grid(16, 12), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(canvas.sample(2, 2), Ok([0; 4]));
    assert_eq!(canvas.sample(1, 2), Ok(outside));
}

#[test]
fn half_open_bounds_assign_boundary_split_metadata_to_one_cell() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(6, 6), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    canvas
        .paint(1, 1, [180, 40, 50, 255], DetailPolicy::Preserve)
        .unwrap();
    canvas.collapse_cell(1, 1).unwrap();
    canvas
        .set_resolution(grid(4, 4), DetailPolicy::Preserve)
        .unwrap();

    assert!(!canvas.has_detail_at(0, 0).unwrap());
    assert!(!canvas.discard_detail(0, 0).unwrap());
    assert!(canvas.has_detail_at(1, 1).unwrap());
    assert!(canvas.discard_detail(1, 1).unwrap());
    assert!(!canvas.has_detail_at(1, 1).unwrap());
    canvas
        .set_resolution(grid(6, 6), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(canvas.sample(1, 1), Ok([0; 4]));
}

#[test]
fn discard_resolution_bakes_parent_overrides_at_the_requested_grid() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(16, 16), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_cell(1, 1).unwrap();
    let parent = [180, 40, 50, 255];
    canvas.paint(1, 1, parent, DetailPolicy::Preserve).unwrap();
    canvas.collapse_cell(1, 1).unwrap();
    canvas
        .set_resolution(grid(4, 4), DetailPolicy::Preserve)
        .unwrap();

    canvas
        .set_resolution(grid(16, 16), DetailPolicy::Discard)
        .unwrap();
    assert_eq!(canvas.sample(1, 1), Ok(parent));
    assert!(!canvas.is_split(1, 1));
    assert_eq!(canvas.retained_resolution(), grid(16, 16));
}

#[test]
fn split_metadata_limit_rejects_the_next_cell_without_changing_canvas() {
    let mut canvas = Canvas::new(grid(65, 64)).unwrap();
    for y in 0..64 {
        for x in 0..64 {
            assert!(canvas.split_cell(x, y).unwrap());
        }
    }
    assert!(canvas.can_undo());
    assert_eq!(
        canvas.split_cell(64, 0),
        Err(CanvasError::SplitLimitExceeded)
    );
    assert!(!canvas.is_split(64, 0));
    assert!(canvas.is_split(63, 63));
}
