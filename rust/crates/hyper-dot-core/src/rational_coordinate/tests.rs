use super::RationalCoordinate as Coordinate;

/// {
///   責務: [reduces_endpoints_and_equivalent_fractions: 単位区間の両端と同値な分数を正規化することを確認する]
///   処理: [最大分母の0・1と約分可能な分数の格納値を比較する]
///   引数: []
///   戻り値: [なし、約分や端点が不正ならテスト失敗]
/// }
#[test]
fn reduces_endpoints_and_equivalent_fractions() {
    // u64上限でも0と1を共通表現へ正規化する必要がある。
    assert_eq!(Coordinate::new(0, u64::MAX).fraction(), [0, 1]);
    assert_eq!(Coordinate::new(u64::MAX, u64::MAX).fraction(), [1, 1]);
    assert_eq!(Coordinate::new(4, 6), Coordinate::new(2, 3));
}

/// {
///   責務: [orders_near_unit_coordinates_without_overflow: 巨大分母で1に近い座標の大小を正しく比較することを確認する]
///   処理: [u64では交差積を保持できない2座標の大小と部分順序を比較する]
///   引数: []
///   戻り値: [なし、比較の桁あふれや順序の不一致があればテスト失敗]
/// }
#[test]
fn orders_near_unit_coordinates_without_overflow() {
    let lower = Coordinate::new(u64::MAX - 2, u64::MAX - 1);
    let upper = Coordinate::new(u64::MAX - 1, u64::MAX);
    // 分母が大きい方は1との差が小さい。浮動小数では両者を区別できない。
    assert!(lower < upper);
    assert_eq!(lower.partial_cmp(&upper), Some(std::cmp::Ordering::Less));
    assert_eq!(upper.cmp(&upper), std::cmp::Ordering::Equal);
}

/// {
///   責務: [centers_maximum_grid_without_u32_overflow: u32上限の格子でも画素中心を正確に計算することを確認する]
///   処理: [先頭・中央・末尾の画素中心を独立した分数値と比較する]
///   引数: []
///   戻り値: [なし、桁あふれや丸めで座標が変わればテスト失敗]
/// }
#[test]
fn centers_maximum_grid_without_u32_overflow() {
    // 座標計算だけを試し、巨大な画像バッファは確保しない。
    assert_eq!(
        Coordinate::center(0, u32::MAX).fraction(),
        [1, 8_589_934_590]
    );
    assert_eq!(
        Coordinate::center(u32::MAX / 2, u32::MAX).fraction(),
        [1, 2]
    );
    assert_eq!(
        Coordinate::center(u32::MAX - 1, u32::MAX).fraction(),
        [8_589_934_589, 8_589_934_590]
    );
}

/// {
///   責務: [rounds_relative_positions_inside_shifted_extent: 原点以外から始まる画像範囲でも上下の丸めを区別することを確認する]
///   処理: [端点・整数画素端・画素途中の位置を3画素の範囲へ対応させる]
///   引数: []
///   戻り値: [なし、切り下げ・切り上げが期待と異なればテスト失敗]
/// }
#[test]
fn rounds_relative_positions_inside_shifted_extent() {
    let start = Coordinate::new(1, 5);
    let end = Coordinate::new(4, 5);
    // 始点・終点を含む画素端では両方の丸めが一致する。
    for (point, floor, ceil) in [
        (start, 0, 0),
        (end, 3, 3),
        (Coordinate::new(2, 5), 1, 1),
        (Coordinate::new(1, 2), 1, 2),
        (Coordinate::new(1, 3), 0, 1),
    ] {
        assert_eq!(point.relative_floor(start, end, 3), floor);
        assert_eq!(point.relative_ceil(start, end, 3), ceil);
    }
}

/// {
///   責務: [interpolation_round_trips_every_pixel_edge: 補間した元画素端から同じ画素番号へ戻れることを確認する]
///   処理: [非整数原点の5分割範囲で全6端点を補間し、分数値と逆変換を比較する]
///   引数: []
///   戻り値: [なし、画素境界がずれればテスト失敗]
/// }
#[test]
fn interpolation_round_trips_every_pixel_edge() {
    let start = Coordinate::new(2, 7);
    let end = Coordinate::new(6, 7);
    for position in 0..=5 {
        let point = Coordinate::interpolate(start, end, position, 5);
        // 2/7 + (4/7)*(position/5) = (10 + 4*position)/35。
        assert_eq!(point, Coordinate::new(10 + 4 * u64::from(position), 35));
        assert_eq!(point.relative_floor(start, end, 5), position);
        assert_eq!(point.relative_ceil(start, end, 5), position);
    }
}

/// {
///   責務: [density_saturates_only_the_summary: 保持解像度の要約だけを飽和し正確な標本座標を維持することを確認する]
///   処理: [端数密度の切り上げとu32上限への飽和を確認し、微小領域の画素位置を照合する]
///   引数: []
///   戻り値: [なし、要約値の丸めや標本位置が不正ならテスト失敗]
/// }
#[test]
fn density_saturates_only_the_summary() {
    assert_eq!(
        Coordinate::density(Coordinate::new(1, 5), Coordinate::new(4, 5), 4),
        7
    );
    let start = Coordinate::new(0, 1);
    let end = Coordinate::new(1, 16_777_216);
    assert_eq!(Coordinate::density(start, end, 4096), u32::MAX);
    // 要約が飽和しても、元画像の中央は正確な2048画素目に対応する。
    let middle = Coordinate::new(1, 33_554_432);
    assert_eq!(middle.relative_floor(start, end, 4096), 2048);
    assert_eq!(middle.relative_ceil(start, end, 4096), 2048);
}

/// {
///   責務: [bounded_json_extents_keep_large_interpolated_fractions_exact: 保存可能な分母上限近くの元範囲でも補間を正確に保つことを確認する]
///   処理: [異なる巨大分母の範囲を補間し、独立した有理演算の期待値と逆変換を照合する]
///   引数: []
///   戻り値: [なし、約分・桁幅・逆変換の誤りがあればテスト失敗]
/// }
#[test]
fn bounded_json_extents_keep_large_interpolated_fractions_exact() {
    let start = Coordinate::new(1, 16_777_213);
    let end = Coordinate::new(16_777_212, 16_777_215);
    let point = Coordinate::interpolate(start, end, 2047, 4096);
    // Python Fractionで独立計算した値を固定し、実装と同じ式を期待値に流用しない。
    assert_eq!(
        point.fraction(),
        [192_059_690_434_174_289, 384_307_076_576_317_440]
    );
    assert_eq!(point.relative_floor(start, end, 4096), 2047);
    assert_eq!(point.relative_ceil(start, end, 4096), 2047);
}

/// {
///   責務: [interpolation_accepts_maximum_pixel_count_without_allocation: 最大画素数の端点を画像確保なしで補間できることを確認する]
///   処理: [単位区間の中央付近と終点をu32上限の画素数で補間して比較する]
///   引数: []
///   戻り値: [なし、桁あふれや端点の誤差があればテスト失敗]
/// }
#[test]
fn interpolation_accepts_maximum_pixel_count_without_allocation() {
    let start = Coordinate::new(0, 1);
    let end = Coordinate::new(1, 1);
    // 元範囲は単位区間に限定し、未検証の巨大分母同士の補間は要求しない。
    assert_eq!(Coordinate::interpolate(start, end, u32::MAX, u32::MAX), end);
    assert_eq!(
        Coordinate::interpolate(start, end, u32::MAX / 2, u32::MAX),
        Coordinate::new(2_147_483_647, 4_294_967_295)
    );
}
