use super::{Coordinate, FieldBounds, FieldPatch, PatchSource};
use crate::raster::Raster;
use crate::resolution::Resolution;
use std::sync::Arc;

/// {
///   責務: [pattern: 透明画素のRGBも区別できる3×2の元画像を作る]
///   処理: [1: 各座標に異なるRGBAを書き込む]
///   引数: []
///   戻り値: [座標ごとの色を持つ小さいラスタ]
/// }
fn pattern() -> Raster {
    // 透明度0でもRGBを残し、切り抜きで色が失われる実装を検出する。
    let mut raster = Raster::new(Resolution::new(3, 2).unwrap()).unwrap();
    for y in 0..2 {
        for x in 0..3 {
            raster.paint(
                x,
                y,
                [
                    20 + x as u8 * 60,
                    30 + y as u8 * 90,
                    40 + x as u8 * 11 + y as u8 * 7,
                    if (x + y) % 2 == 0 { 0 } else { 180 },
                ],
            );
        }
    }
    raster
}

/// {
///   責務: [mapped_bounds: 元画像内の半画素格子を非単位の有理数範囲へ写す]
///   処理: [1: 整数格子の各端を独立した分数式で構成する]
///   引数: [rectangle: 6×4格子上の左・上・右・下]
///   戻り値: [横1/7から6/7・縦2/9から8/9内の矩形]
/// }
fn mapped_bounds(rectangle: [u32; 4]) -> FieldBounds {
    // 製品の補間関数を期待値に使わず、分数式を直接評価する。
    let [left, top, right, bottom] = rectangle.map(u64::from);
    FieldBounds {
        left: Coordinate::new(6 + 5 * left, 42),
        top: Coordinate::new(4 + 3 * top, 18),
        right: Coordinate::new(6 + 5 * right, 42),
        bottom: Coordinate::new(4 + 3 * bottom, 18),
    }
}

/// {
///   責務: [mapped_patch: 非単位の元画像範囲と色差分を持つパッチを作る]
///   処理: [1: 固定の元画像と有理数範囲からパッチを復元する]
///   引数: [offset: 飽和させず保持するRGBA差分]
///   戻り値: [切り抜き検証用のラスタパッチ]
/// }
fn mapped_patch(offset: [i64; 4]) -> FieldPatch {
    // 元画像原点が0ではない入力を全テストで共通に使用する。
    let extent = mapped_bounds([0, 0, 6, 4]);
    FieldPatch::from_source(extent, extent, pattern(), offset)
}

/// {
///   責務: [rectangles: 半画素格子の正の面積を持つ全矩形を列挙する]
///   処理: [1: 開始端より終了端が大きい組だけを作る]
///   引数: []
///   戻り値: [6×4格子の210矩形]
/// }
fn rectangles() -> Vec<[u32; 4]> {
    // 全矩形は210個に限定し、巨大なラスタや乱数に依存しない。
    let mut rectangles = Vec::new();
    for left in 0..6 {
        for right in left + 1..=6 {
            for top in 0..4 {
                for bottom in top + 1..=4 {
                    rectangles.push([left, top, right, bottom]);
                }
            }
        }
    }
    rectangles
}

/// {
///   責務: [assert_crop: 切り抜きの保存範囲・元画素・標本を整数の期待値と照合する]
///   処理: [
///     1: 外向き丸めで必要な元画素の範囲を計算する
///     2: 保存範囲と全元画素を確認する
///     3: 表示範囲内の各半画素中心の未飽和色を確認する
///   ]
///   引数: [
///     patch: 検証対象の切り抜きパッチ
///     rectangle: 6×4格子上の表示範囲
///     offset: 期待するRGBA差分
///   ]
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
fn assert_crop(patch: &FieldPatch, rectangle: [u32; 4], offset: [i64; 4]) {
    // 半画素格子の整数演算を正解とし、製品の丸め処理を再利用しない。
    let [left, top, right, bottom] = rectangle;
    let (x0, y0, x1, y1) = (left / 2, top / 2, right.div_ceil(2), bottom.div_ceil(2));
    let original = pattern();
    let (extent, raster, solid_color) = patch.source_data();
    let raster = raster.expect("raster patch retains its source");
    assert_eq!(patch.bounds, mapped_bounds(rectangle));
    assert_eq!(patch.grid, Resolution::new(5, 3).unwrap());
    assert_eq!(patch.offset, offset);
    assert_eq!(extent, mapped_bounds([x0 * 2, y0 * 2, x1 * 2, y1 * 2]));
    assert_eq!(
        raster.resolution(),
        Resolution::new(x1 - x0, y1 - y0).unwrap()
    );
    assert_eq!(patch.stored_pixels(), ((x1 - x0) * (y1 - y0)) as usize);
    assert_eq!(solid_color, [0; 4]);
    for y in y0..y1 {
        for x in x0..x1 {
            assert_eq!(raster.sample(x - x0, y - y0), original.sample(x, y));
        }
    }
    // 表示中心からの参照が元画像の整数画素を指すことも独立に確認する。
    for y in top..bottom {
        for x in left..right {
            let color = original.sample(x / 2, y / 2).unwrap();
            let expected =
                std::array::from_fn(|channel| i64::from(color[channel]) + offset[channel]);
            assert_eq!(
                patch.sample_raw(
                    Coordinate::new(12 + 5 * (2 * u64::from(x) + 1), 84),
                    Coordinate::new(8 + 3 * (2 * u64::from(y) + 1), 36)
                ),
                expected
            );
        }
    }
}

/// {
///   責務: [all_half_pixel_crops_keep_source_boundaries_and_raw_colors: 全210切り抜きの元座標と未飽和色を検証する]
///   処理: [1: 各矩形を切り抜き整数の期待値と照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn all_half_pixel_crops_keep_source_boundaries_and_raw_colors() {
    // 負値・255超の差分を含め、切り抜きが色を飽和させないことを確認する。
    let offset = [-300, 400, -50, 250];
    let original = mapped_patch(offset);
    let snapshot = original.clone();
    let rectangles = rectangles();
    assert_eq!(rectangles.len(), 210);
    for rectangle in rectangles {
        let cropped = original.cropped(mapped_bounds(rectangle)).unwrap();
        assert_crop(&cropped, rectangle, offset);
    }
    assert_eq!(original, snapshot);
}

/// {
///   責務: [nested_crops_equal_direct_crops_for_all_contained_rectangles: 全4410組の連続切り抜きで座標のずれを検出する]
///   処理: [1: 包含関係にある各矩形で直接と連続の切り抜きを照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn nested_crops_equal_direct_crops_for_all_contained_rectangles() {
    // 1回目の切り抜きで原点が動いた後も、最初の元画像座標を維持する。
    let offset = [1000, -1000, 700, -700];
    let original = mapped_patch(offset);
    let rectangles = rectangles();
    let mut checked = 0;
    for outer in &rectangles {
        let first = original.cropped(mapped_bounds(*outer)).unwrap();
        let snapshot = first.clone();
        for inner in &rectangles {
            if inner[0] < outer[0]
                || inner[1] < outer[1]
                || inner[2] > outer[2]
                || inner[3] > outer[3]
            {
                continue;
            }
            let repeated = first.cropped(mapped_bounds(*inner)).unwrap();
            assert_eq!(repeated, original.cropped(mapped_bounds(*inner)).unwrap());
            assert_crop(&repeated, *inner, offset);
            checked += 1;
        }
        assert_eq!(first, snapshot);
    }
    assert_eq!(checked, 4410);
}

/// {
///   責務: [unchanged_source_support_reuses_the_same_raster: 必要な元画素が同じなら再確保しないことを検証する]
///   処理: [1: 表示範囲だけ変えて共有ラスタの同一性を照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn unchanged_source_support_reuses_the_same_raster() {
    // 原点が0でない切り抜き画像でも、同じ元画素の範囲ならArcを共有する。
    let original = mapped_patch([0; 4])
        .cropped(mapped_bounds([2, 0, 6, 4]))
        .unwrap();
    let cropped = original.cropped(mapped_bounds([3, 1, 6, 3])).unwrap();
    let (PatchSource::Raster { raster: before, .. }, PatchSource::Raster { raster: after, .. }) =
        (&original.source, &cropped.source)
    else {
        panic!("expected raster sources")
    };
    assert!(Arc::ptr_eq(before, after));
    assert_crop(&cropped, [3, 1, 6, 3], [0; 4]);
}

/// {
///   責務: [source_data_reconstruction_keeps_cropped_samples: 保存用元データからの復元で標本と追加切り抜きを維持する]
///   処理: [1: 切り抜いた各パッチを元データから復元して標本を照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn source_data_reconstruction_keeps_cropped_samples() {
    // JSON経路と同じ元範囲・未補正画素・差分の組から復元する。
    let offset = [-300, 400, -50, 250];
    let original = mapped_patch(offset);
    for rectangle in rectangles() {
        let cropped = original.cropped(mapped_bounds(rectangle)).unwrap();
        let (extent, raster, _) = cropped.source_data();
        let restored =
            FieldPatch::from_source(cropped.bounds, extent, raster.unwrap().clone(), offset);
        assert_crop(&restored, rectangle, offset);
        // 復元した局所画像をさらに左上の半画素へ絞り、新しい元座標系も確認する。
        let [left, top, _, _] = rectangle;
        let inner = [left, top, left + 1, top + 1];
        assert_crop(
            &restored.cropped(mapped_bounds(inner)).unwrap(),
            inner,
            offset,
        );
    }
}

/// {
///   責務: [solid_crops_keep_color_offset_and_one_pixel_budget: 単色切り抜きの色・差分・予算を維持する]
///   処理: [1: 全210矩形で単色の保存データと未飽和色を照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn solid_crops_keep_color_offset_and_one_pixel_budget() {
    // 透明画素の隠れたRGBと未飽和差分は、単色経路でも維持する。
    let color = [12, 34, 56, 0];
    let grid = Resolution::new(5, 3).unwrap();
    let mut original = FieldPatch::solid(mapped_bounds([0, 0, 6, 4]), grid, color);
    original.offset = [-20, 300, 1000, -400];
    for rectangle in rectangles() {
        let bounds = mapped_bounds(rectangle);
        let cropped = original.cropped(bounds).unwrap();
        assert_eq!(cropped.source_data(), (bounds, None, color));
        assert_eq!(cropped.stored_pixels(), 1);
        assert_eq!(cropped.grid, grid);
        assert_eq!(cropped.offset, original.offset);
        assert_eq!(
            cropped.sample_raw(bounds.left, bounds.top),
            [-8, 334, 1056, -400]
        );
    }
}

/// {
///   責務: [unit_source_crops_keep_exact_pixel_edges_and_leave_snapshot_unchanged: 単位領域の通常画像の切り抜きと元状態保護を検証する]
///   処理: [1: 端の画素を切り抜き元画像と保存範囲を照合する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn unit_source_crops_keep_exact_pixel_edges_and_leave_snapshot_unchanged() {
    // from_rasterの通常入口でも、最終行・最終列の原点と終端を確認する。
    let original = FieldPatch::from_raster(pattern());
    let snapshot = original.clone();
    let bounds = FieldBounds {
        left: Coordinate::new(2, 3),
        top: Coordinate::new(1, 2),
        right: Coordinate::new(1, 1),
        bottom: Coordinate::new(1, 1),
    };
    let cropped = original.cropped(bounds).unwrap();
    let (extent, raster, _) = cropped.source_data();
    assert_eq!(extent, bounds);
    assert_eq!(cropped.grid, Resolution::new(3, 2).unwrap());
    assert_eq!(cropped.stored_pixels(), 1);
    assert_eq!(raster.unwrap().sample(0, 0), pattern().sample(2, 1));
    assert_eq!(
        cropped.sample_raw(bounds.left, bounds.top),
        pattern().sample(2, 1).unwrap().map(i64::from)
    );
    assert_eq!(original, snapshot);
}
