use super::{
    Canvas, Coordinate, FieldBounds, FieldPatch, ProjectJsonError, Resolution, validate_partition,
};
use serde_json::{Value, json};

/// {
///   責務: [rectangle: 分数端点から被覆検証用の矩形を作る]
///   処理: [1: 左・上・右・下の分数を有理座標へ変換する]
///   引数: [edges: 各端点の分子・分母]
///   戻り値: [検証用の半開矩形]
/// }
fn rectangle(edges: [[u64; 2]; 4]) -> FieldBounds {
    // 期待値に製品の交差・切除処理を使わず、指定した境界だけを構成する。
    let [left, top, right, bottom] = edges.map(|[n, d]| Coordinate::new(n, d));
    FieldBounds {
        left,
        top,
        right,
        bottom,
    }
}

/// {
///   責務: [lattice_rectangles: 2×2格子の全9矩形を列挙する]
///   処理: [1: 正の幅と高さを持つ整数端点を列挙する]
///   引数: []
///   戻り値: [左・上・右・下の整数端点の列]
/// }
fn lattice_rectangles() -> Vec<[u32; 4]> {
    // 9矩形をそれぞれ0・1・2枚使うことで重複を含む全入力を有限に列挙する。
    let mut rectangles = Vec::new();
    for left in 0..2 {
        for right in left + 1..=2 {
            for top in 0..2 {
                for bottom in top + 1..=2 {
                    rectangles.push([left, top, right, bottom]);
                }
            }
        }
    }
    rectangles
}

/// {
///   責務: [transparent_patches: 矩形列を画像確保なしの単色パッチ列へ変換する]
///   処理: [1: 各矩形に透明色と固定解像度を設定する]
///   引数: [bounds: 正の面積を持つ矩形の列]
///   戻り値: [被覆検証用の単色パッチ列]
/// }
fn transparent_patches(bounds: &[FieldBounds]) -> Vec<FieldPatch> {
    // 被覆だけを調べるため、画像サイズや色の不一致で先に失敗させない。
    let grid = Resolution::new(1, 1).unwrap();
    bounds
        .iter()
        .map(|bounds| FieldPatch::solid(*bounds, grid, [0; 4]))
        .collect()
}

/// {
///   責務: [document: プレビューが透明な1×1のversion 2文書を作る]
///   処理: [1: 各矩形を同じ透明色の保持パッチとしてJSONへ格納する]
///   引数: [bounds: 保持パッチの表示範囲と元画像範囲]
///   戻り値: [公開読込APIへ渡す文書]
/// }
fn document(bounds: &[FieldBounds]) -> Value {
    // 画素中心に現れない隙間でも、プレビュー比較の前に被覆検証で拒否させる。
    let patches: Vec<_> = bounds
        .iter()
        .map(|bounds| {
            let edges =
                [bounds.left, bounds.top, bounds.right, bounds.bottom].map(Coordinate::fraction);
            json!({"clip": edges, "extent": edges, "resolution": [1, 1],
            "pixels": [[null]], "offset": [0, 0, 0, 0]})
        })
        .collect();
    json!({"version": 2, "canvas_size": 1, "resolution": [1, 1], "pixels": [[null]],
        "retained_field": patches, "retained_splits": []})
}

/// {
///   責務: [all_small_lattice_multisets_match_integer_coverage: 重複を含む全19683入力を整数の被覆数と照合する]
///   処理: [
///     1: 各矩形の枚数を3進数から復元する
///     2: 4セルの被覆数を整数で数える
///     3: 各セルが1枚の場合だけ受理されることを順序反転も含めて確認する
///   ]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn all_small_lattice_multisets_match_integer_coverage() {
    // 面積の合計では見逃す、同じ面積の重複と欠落も整数の被覆数で識別する。
    let rectangles = lattice_rectangles();
    assert_eq!(rectangles.len(), 9);
    let mut accepted = 0;
    for encoding in 0..19_683 {
        let mut remaining = encoding;
        let mut coverage = [0u32; 4];
        let mut bounds = Vec::new();
        for &[left, top, right, bottom] in &rectangles {
            let count = remaining % 3;
            remaining /= 3;
            for y in top..bottom {
                for x in left..right {
                    coverage[(2 * y + x) as usize] += count;
                }
            }
            let bounds_for_rectangle = rectangle([
                [u64::from(left), 2],
                [u64::from(top), 2],
                [u64::from(right), 2],
                [u64::from(bottom), 2],
            ]);
            for _ in 0..count {
                bounds.push(bounds_for_rectangle);
            }
        }
        let expected = coverage == [1; 4];
        let mut patches = transparent_patches(&bounds);
        assert_eq!(
            validate_partition(&patches).is_ok(),
            expected,
            "encoding={encoding}"
        );
        patches.reverse();
        assert_eq!(
            validate_partition(&patches).is_ok(),
            expected,
            "reversed={encoding}"
        );
        accepted += u32::from(expected);
    }
    assert!(accepted > 0 && accepted < 19_683);
}

/// {
///   責務: [rational_t_junctions_load_in_every_patch_order: 有理数のT字境界を持つ文書を全順序で復元できることを検証する]
///   処理: [1: 3パッチの全6順序で読込・再保存・再読込と描画を確認する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn rational_t_junctions_load_in_every_patch_order() {
    // 同じxの終了と開始、異なるy分割が接する正しいT字境界を受理する。
    let mut bounds = [
        rectangle([[0, 1], [0, 1], [1, 3], [1, 1]]),
        rectangle([[1, 3], [0, 1], [1, 1], [2, 5]]),
        rectangle([[1, 3], [2, 5], [1, 1], [1, 1]]),
    ];
    for _ in 0..3 {
        for order in [bounds.to_vec(), bounds.iter().rev().copied().collect()] {
            let canvas = Canvas::from_json(&document(&order).to_string()).unwrap();
            let restored = Canvas::from_json(&canvas.to_json().unwrap()).unwrap();
            let rendered = restored.render_at(Resolution::new(7, 5).unwrap()).unwrap();
            for y in 0..5 {
                for x in 0..7 {
                    assert_eq!(rendered.sample(x, y).unwrap(), [0; 4]);
                }
            }
        }
        bounds.rotate_left(1);
    }
}

/// {
///   責務: [subpixel_gaps_and_overlaps_are_rejected_before_preview_sampling: 低解像度で見えない極小の隙間と重複を拒否する]
///   処理: [1: 両軸に分母上限幅の隙間と重複を作り公開APIで検証する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn subpixel_gaps_and_overlaps_are_rejected_before_preview_sampling() {
    // 1×1プレビューの中心から離れた場所にも、分母上限幅の不正領域を置く。
    let denominator = 16_777_216;
    for axis in 0..2 {
        for overlap in [false, true] {
            let mut first = [[0, 1], [0, 1], [1, 1], [1, 1]];
            let mut second = first;
            first[axis + 2] = [if overlap { 2 } else { 1 }, denominator];
            second[axis] = [if overlap { 1 } else { 2 }, denominator];
            let bounds = [rectangle(first), rectangle(second)];
            assert!(
                matches!(
                    Canvas::from_json(&document(&bounds).to_string()),
                    Err(ProjectJsonError::Invalid(_))
                ),
                "axis={axis}, overlap={overlap}"
            );
        }
    }
}

/// {
///   責務: [equal_total_area_does_not_hide_overlap_and_hole: 面積合計が1でも重複と欠落が相殺されないことを検証する]
///   処理: [1: 左半分を二重に覆い右半分を空にした文書を拒否する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn equal_total_area_does_not_hide_overlap_and_hole() {
    // 面積合計と透明プレビューだけでは識別できない入力を公開経路で拒否する。
    let half = rectangle([[0, 1], [0, 1], [1, 2], [1, 1]]);
    assert!(matches!(
        Canvas::from_json(&document(&[half, half]).to_string()),
        Err(ProjectJsonError::Invalid(_))
    ));
}

/// {
///   責務: [separated_active_intervals_must_not_leave_an_internal_hole: 有効区間の途中に残る隙間と異なる区間の重複を検証する]
///   処理: [1: 上下端は覆うが中央で隙間または重複のある配置を拒否する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn separated_active_intervals_must_not_leave_an_internal_hole() {
    // 同じ区間の重複検査だけでは検出できない、異なる縦区間も調べる。
    for bottom_start in [[2, 3], [1, 3]] {
        let bounds = [
            rectangle([[0, 1], [0, 1], [1, 1], [1, 2]]),
            rectangle([[0, 1], bottom_start, [1, 1], [1, 1]]),
        ];
        assert!(matches!(
            Canvas::from_json(&document(&bounds).to_string()),
            Err(ProjectJsonError::Invalid(_))
        ));
    }
}

/// {
///   責務: [maximum_patch_count_strips_remain_a_valid_partition: 4096帯の被覆を画像展開なしで検証する]
///   処理: [1: 縦帯と横帯をそれぞれ4096枚作り全体被覆を確認する]
///   引数: []
///   戻り値: [単位値。不一致ならテストを失敗させる]
/// }
#[test]
fn maximum_patch_count_strips_remain_a_valid_partition() {
    // JSONのパッチ数上限と同数の幾何配置だけを調べ、予算検査そのものとは分ける。
    for axis in 0..2 {
        let bounds: Vec<_> = (0..4096)
            .map(|index| {
                let mut edges = [[0, 1], [0, 1], [1, 1], [1, 1]];
                edges[axis] = [index, 4096];
                edges[axis + 2] = [index + 1, 4096];
                rectangle(edges)
            })
            .collect();
        assert!(validate_partition(&transparent_patches(&bounds)).is_ok());
    }
}
