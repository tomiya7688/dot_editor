//! Bounded, four-connected traversal of an immutable logical projection.

use crate::raster::{Raster, RasterError};

/// {
///   責務: [flood_region: 変更前ラスタの同色4近傍領域を列挙する]
///   処理: [
///     1: 種点の色を読み探索領域を確保する
///     2: 未訪問の上下左右を同色のときだけ探索する
///   ]
///   引数: [
///     view: 判定元の論理表示
///     x: 横座標
///     y: 縦座標
///   ]
///   戻り値: [同色領域の座標配列または確保・座標エラー]
/// }
pub(crate) fn flood_region(view: &Raster, x: u32, y: u32) -> Result<Vec<(u32, u32)>, RasterError> {
    let original = view.sample(x, y)?;
    let width = view.resolution().width();
    let height = view.resolution().height();
    // Raster construction has already checked both dimensions and pixel budget.
    let count = width as usize * height as usize;
    let mut visited = Vec::new();
    visited
        .try_reserve_exact(count)
        .map_err(|_| RasterError::AllocationFailed)?;
    visited.resize(count, false);
    let mut points = Vec::new();
    points
        .try_reserve_exact(count)
        .map_err(|_| RasterError::AllocationFailed)?;
    points.push((x, y));
    visited[(y * width + x) as usize] = true;
    let mut cursor = 0;
    while cursor < points.len() {
        let (px, py) = points[cursor];
        cursor += 1;
        for neighbor in [
            px.checked_sub(1).map(|nx| (nx, py)),
            (px + 1 < width).then_some((px + 1, py)),
            py.checked_sub(1).map(|ny| (px, ny)),
            (py + 1 < height).then_some((px, py + 1)),
        ]
        .into_iter()
        .flatten()
        {
            let (nx, ny) = neighbor;
            let index = (ny * width + nx) as usize;
            if !visited[index] {
                visited[index] = true;
                if view.sample(nx, ny)? == original {
                    points.push(neighbor);
                }
            }
        }
    }
    Ok(points)
}
