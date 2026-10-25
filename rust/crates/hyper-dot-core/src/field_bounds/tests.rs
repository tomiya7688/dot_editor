use super::FieldBounds;
use crate::canvas::{Canvas, CanvasError};
use crate::raster::{Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;
use crate::resolution_field::{DetailPolicy, ResolutionField, ResolutionFieldError};

/// {
///   責務: [bounds: 整数格子の端点からテスト用の有理数矩形を構成する]
///   処理: [左右上下の端点を対応する格子寸法で割る]
///   引数: [grid: 正の格子寸法, rectangle: 左・上・右・下の格子端点]
///   戻り値: [比較用の正確な矩形]
/// }
fn bounds(grid: Resolution, rectangle: (u32, u32, u32, u32)) -> FieldBounds {
    let (left, top, right, bottom) = rectangle;
    // 終端はセル番号ではないため、幅・高さと一致する格子端も許可する。
    FieldBounds {
        left: Coordinate::new(u64::from(left), u64::from(grid.width())),
        top: Coordinate::new(u64::from(top), u64::from(grid.height())),
        right: Coordinate::new(u64::from(right), u64::from(grid.width())),
        bottom: Coordinate::new(u64::from(bottom), u64::from(grid.height())),
    }
}

/// {
///   責務: [lattice_rectangles: 小さなテスト格子内の正の面積を持つ矩形を列挙する]
///   処理: [左右上下の端点を順序付きで列挙し矩形を格納する]
///   引数: [grid: 列挙対象の小さな格子]
///   戻り値: [整数端点の矩形一覧]
/// }
fn lattice_rectangles(grid: Resolution) -> Vec<(u32, u32, u32, u32)> {
    let mut rectangles = Vec::new();
    // 列挙は4x3のテスト格子だけに使い、製品側の大きな画像は確保しない。
    for left in 0..grid.width() {
        for right in left + 1..=grid.width() {
            for top in 0..grid.height() {
                for bottom in top + 1..=grid.height() {
                    rectangles.push((left, top, right, bottom));
                }
            }
        }
    }
    rectangles
}

/// {
///   責務: [assert_partition: 切除後の矩形群に重複・欠落・空領域がないことを確認する]
///   処理: [包含と交差を検査し、全格子セルの中心で整数矩形の期待被覆数と比較する]
///   引数: [grid: 小さな格子, outer: 元矩形の整数端点, cut: 内包する切除矩形の整数端点]
///   戻り値: [なし、分割契約に違反すればテスト失敗]
/// }
fn assert_partition(grid: Resolution, outer: (u32, u32, u32, u32), cut: (u32, u32, u32, u32)) {
    let source = bounds(grid, outer);
    let removed = bounds(grid, cut);
    let pieces: Vec<_> = source.outside(removed).collect();
    assert!(pieces.len() <= 4);
    for (index, piece) in pieces.iter().copied().enumerate() {
        assert!(piece.left < piece.right && piece.top < piece.bottom);
        assert_eq!(source.intersection(piece), Some(piece));
        assert_eq!(piece.intersection(removed), None);
        for other in &pieces[index + 1..] {
            assert_eq!(piece.intersection(*other), None);
        }
    }
    // 期待被覆数は有理数の矩形演算ではなく、整数格子の包含から計算する。
    for y in 0..grid.height() {
        for x in 0..grid.width() {
            let in_source = x >= outer.0 && x < outer.2 && y >= outer.1 && y < outer.3;
            let in_cut = x >= cut.0 && x < cut.2 && y >= cut.1 && y < cut.3;
            let count = pieces
                .iter()
                .filter(|piece| {
                    piece.contains(
                        Coordinate::center(x, grid.width()),
                        Coordinate::center(y, grid.height()),
                    )
                })
                .count();
            assert_eq!(
                count,
                usize::from(in_source && !in_cut),
                "outer={outer:?}, cut={cut:?}, cell=({x},{y})"
            );
        }
    }
}

/// {
///   責務: [cells_keep_non_square_and_maximum_grid_edges_exact: 長方形とu32上限のセル境界を正確に構成することを確認する]
///   処理: [通常格子と最大格子の端セルを独立した分数値で比較する]
///   引数: []
///   戻り値: [なし、座標の取り違えや桁あふれがあればテスト失敗]
/// }
#[test]
fn cells_keep_non_square_and_maximum_grid_edges_exact() {
    let grid = Resolution::new(3, 2).unwrap();
    let last = FieldBounds::cell(grid, 2, 1);
    assert_eq!(last.left.fraction(), [2, 3]);
    assert_eq!(last.top.fraction(), [1, 2]);
    assert_eq!(last.right.fraction(), [1, 1]);
    assert_eq!(last.bottom.fraction(), [1, 1]);
    // 大きな格子の数値だけを構成し、画像バッファは作らない。
    let maximum = Resolution::new(u32::MAX, u32::MAX).unwrap();
    let last = FieldBounds::cell(maximum, u32::MAX - 1, u32::MAX - 1);
    assert_eq!(last.left.fraction(), [4_294_967_294, 4_294_967_295]);
    assert_eq!(last.right.fraction(), [1, 1]);
    assert_eq!(last.bottom.fraction(), [1, 1]);
}

/// {
///   責務: [half_open_edges_belong_to_only_one_adjacent_cell: 隣接セルの共有辺を片方だけに所属させることを確認する]
///   処理: [左上・右下・共有辺の包含と全体の終端除外を照合する]
///   引数: []
///   戻り値: [なし、辺で重複や欠落があればテスト失敗]
/// }
#[test]
fn half_open_edges_belong_to_only_one_adjacent_cell() {
    let grid = Resolution::new(2, 2).unwrap();
    let first = FieldBounds::cell(grid, 0, 0);
    let right = FieldBounds::cell(grid, 1, 0);
    let zero = Coordinate::new(0, 1);
    let half = Coordinate::new(1, 2);
    let quarter = Coordinate::new(1, 4);
    assert!(first.contains(zero, zero));
    // 共有辺は右側へ、共有する下端は下側へ所属する。
    assert!(!first.contains(half, quarter));
    assert!(right.contains(half, quarter));
    assert!(!first.contains(quarter, half));
    assert!(FieldBounds::cell(grid, 0, 1).contains(quarter, half));
    assert!(!FieldBounds::full().contains(Coordinate::new(1, 1), quarter));
    assert!(!FieldBounds::full().contains(quarter, Coordinate::new(1, 1)));
}

/// {
///   責務: [intersection_requires_positive_area_and_is_symmetric: 交差が正の面積を要求し順序に依存しないことを確認する]
///   処理: [自己・包含・部分重複・辺接触・角接触・非接触の交差結果を比較する]
///   引数: []
///   戻り値: [なし、空交差や順序で結果が変わればテスト失敗]
/// }
#[test]
fn intersection_requires_positive_area_and_is_symmetric() {
    let grid = Resolution::new(4, 4).unwrap();
    let source = bounds(grid, (0, 0, 2, 2));
    for (rectangle, expected) in [
        ((0, 0, 2, 2), Some(source)),
        ((0, 0, 1, 1), Some(bounds(grid, (0, 0, 1, 1)))),
        ((1, 1, 3, 3), Some(bounds(grid, (1, 1, 2, 2)))),
        ((2, 0, 4, 2), None),
        ((2, 2, 4, 4), None),
        ((3, 0, 4, 1), None),
    ] {
        // 辺・角が接するだけの場合は切り抜き対象を作らない。
        let other = bounds(grid, rectangle);
        assert_eq!(source.intersection(other), expected);
        assert_eq!(other.intersection(source), expected);
    }
}

/// {
///   責務: [all_small_lattice_cuts_partition_without_overlap_or_gaps: 小格子の全有効切除で重複と欠落がないことを確認する]
///   処理: [4x3格子の525通りの包含関係を列挙し残り領域を検証する]
///   引数: []
///   戻り値: [なし、被覆の過不足があればテスト失敗]
/// }
#[test]
fn all_small_lattice_cuts_partition_without_overlap_or_gaps() {
    let grid = Resolution::new(4, 3).unwrap();
    let rectangles = lattice_rectangles(grid);
    let mut checked = 0;
    for outer in rectangles.iter().copied() {
        for cut in rectangles.iter().copied() {
            // 試験対象のintersectionではなく整数端点で有効な切除を選別する。
            if cut.0 >= outer.0 && cut.1 >= outer.1 && cut.2 <= outer.2 && cut.3 <= outer.3 {
                assert_partition(grid, outer, cut);
                checked += 1;
            }
        }
    }
    assert_eq!(checked, 525);
}

/// {
///   責務: [empty_strips_are_removed_for_full_and_edge_cuts: 全体・辺・角の切除で面積0の帯を返さないことを確認する]
///   処理: [代表的な切除の残り矩形数を比較し分割契約も確認する]
///   引数: []
///   戻り値: [なし、空の帯や残り数の誤りがあればテスト失敗]
/// }
#[test]
fn empty_strips_are_removed_for_full_and_edge_cuts() {
    let grid = Resolution::new(4, 4).unwrap();
    for (cut, expected) in [
        ((1, 1, 3, 3), 4),
        ((0, 0, 4, 4), 0),
        ((1, 0, 3, 4), 2),
        ((0, 1, 4, 3), 2),
        ((0, 0, 2, 2), 2),
        ((0, 0, 4, 2), 1),
    ] {
        assert_eq!(
            FieldBounds::full().outside(bounds(grid, cut)).count(),
            expected
        );
        assert_partition(grid, (0, 0, 4, 4), cut);
    }
}

/// {
///   責務: [partial_external_cut_is_intersected_before_subtraction: 一部だけ重なる要求を交差領域へ限定して切除することを確認する]
///   処理: [元領域の外へはみ出す要求を交差へ変換し残りが正しい1矩形になることを確認する]
///   引数: []
///   戻り値: [なし、呼び出し元の交差後の切除契約が不正ならテスト失敗]
/// }
#[test]
fn partial_external_cut_is_intersected_before_subtraction() {
    let grid = Resolution::new(4, 4).unwrap();
    let source = bounds(grid, (1, 1, 3, 3));
    let request = bounds(grid, (0, 0, 2, 4));
    // outsideは任意の要求ではなく、検証済みの交差を受け取る内部API。
    let overlap = source.intersection(request).unwrap();
    assert_eq!(overlap, bounds(grid, (1, 1, 2, 3)));
    assert_eq!(
        source.outside(overlap).collect::<Vec<_>>(),
        vec![bounds(grid, (2, 1, 3, 3))]
    );
}

/// {
///   責務: [public_field_entry_points_validate_coordinates_before_bounds: 公開フィールド操作が範囲外座標を矩形生成前に処理することを確認する]
///   処理: [範囲端とu32上限の座標で読み取りエラー・描画消去の変更なし・状態不変を比較する]
///   引数: []
///   戻り値: [なし、範囲外入力でパニックや編集が起きればテスト失敗]
/// }
#[test]
fn public_field_entry_points_validate_coordinates_before_bounds() {
    let grid = Resolution::new(4, 3).unwrap();
    let mut field = ResolutionField::from_raster(Raster::new(grid).unwrap());
    let before = field.clone();
    for (x, y) in [(4, 0), (0, 3), (u32::MAX, 0), (0, u32::MAX)] {
        let error = RasterError::CoordinateOutOfBounds { x, y };
        assert_eq!(field.sample(grid, x, y), Err(error));
        assert_eq!(field.has_detail_at(grid, x, y), Err(error));
        // 既存契約では範囲外の描画・消去はエラーではなく変更なし。
        assert_eq!(
            field.paint(grid, x, y, [255; 4], DetailPolicy::Discard),
            Ok(false)
        );
        assert_eq!(field.erase(grid, x, y, DetailPolicy::Preserve), Ok(false));
        assert_eq!(
            field.discard_detail(grid, x, y),
            Err(ResolutionFieldError::Raster(error))
        );
        assert_eq!(field, before);
    }
}

/// {
///   責務: [invalid_canvas_operations_preserve_pixels_and_history: Canvas経由の範囲外操作でも画像とUndo/Redoを保護することを確認する]
///   処理: [履歴付き作品へ範囲外操作を行い、状態一致と既存のRedo・Undoを実行して比較する]
///   引数: []
///   戻り値: [なし、範囲外操作で画像や履歴が変わればテスト失敗]
/// }
#[test]
fn invalid_canvas_operations_preserve_pixels_and_history() {
    let mut canvas = Canvas::new(Resolution::new(4, 3).unwrap()).unwrap();
    canvas
        .paint(0, 0, [255, 0, 0, 255], DetailPolicy::Preserve)
        .unwrap();
    canvas
        .paint(3, 2, [0, 0, 255, 255], DetailPolicy::Preserve)
        .unwrap();
    assert!(canvas.undo().unwrap());
    let before = canvas.clone();
    for (x, y) in [(4, 0), (0, 3), (u32::MAX, 0), (0, u32::MAX)] {
        let error = RasterError::CoordinateOutOfBounds { x, y };
        assert_eq!(canvas.has_detail_at(x, y), Err(error));
        assert_eq!(
            canvas.paint(x, y, [255; 4], DetailPolicy::Discard),
            Ok(false)
        );
        assert_eq!(canvas.erase(x, y, DetailPolicy::Preserve), Ok(false));
        assert_eq!(canvas.discard_detail(x, y), Err(CanvasError::Raster(error)));
        assert_eq!(canvas, before);
    }
    // 比較だけでなく、操作前から残る未来と過去を実際に復元する。
    assert!(canvas.redo().unwrap());
    assert_eq!(canvas.sample(3, 2), Ok([0, 0, 255, 255]));
    assert!(canvas.undo().unwrap());
    assert_eq!(canvas, before);
}
