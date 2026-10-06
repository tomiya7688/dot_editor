//! GUI-independent logical canvas with retained samples and bounded history.

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::flood_region::flood_region;
use crate::raster::{Color, MAX_DIMENSION, MAX_PIXELS, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;
use crate::resolution_field::{DetailPolicy, ResolutionField, ResolutionFieldError};
use crate::split_cell::SplitCell;

const HISTORY_LIMIT: usize = 50;
const MAX_SPLIT_CELLS: usize = 4096;

pub type ChildCoordinate = (u8, u8);

/// {
///   責務: [CanvasState: 編集をUndo/Redoで復元するための保存状態]
///   フィールド: [
///     resolution: 保存時の論理解像度
///     field: 共有する保持フィールド
///     splits: 共有する分割記録
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
struct CanvasState {
    resolution: Resolution,
    field: ResolutionField,
    splits: Arc<Vec<SplitCell>>,
}

/// {
///   責務: [Canvas: 論理表示・保持細部・分割と編集履歴を管理する]
///   フィールド: [
///     resolution: 論理解像度
///     field: 保持色と細部
///     splits: 解像度別の親色・展開記録
///     history: 最大50件のUndo状態
///     future: Redo状態
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Canvas {
    resolution: Resolution,
    pub(crate) field: ResolutionField,
    pub(crate) splits: Arc<Vec<SplitCell>>,
    history: Vec<CanvasState>,
    future: Vec<CanvasState>,
}

/// {
///   責務: [CanvasError: Canvas編集で検出した失敗を分類する]
///   フィールド: [
///     Raster: 描画・座標エラー
///     Field: 保持フィールドのエラー
///     AllocationFailed: 分割記録の確保失敗
///     HistoryAllocationFailed: 履歴の確保失敗
///     SplitLimitExceeded: 分割数上限
///     SplitResolutionOverflow: 子解像度の桁あふれ
///     InvalidRegionSize: 幅または高さがゼロ
///     RegionOutOfBounds: 範囲外のx・y・width・height
///     ChildCoordinateOutOfBounds: 範囲外の子x・y
///     CellNotSplit: 分割記録のないx・y
///     CellNotExpanded: 折りたたみ中のx・y
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanvasError {
    Raster(RasterError),
    Field(ResolutionFieldError),
    AllocationFailed,
    HistoryAllocationFailed,
    SplitLimitExceeded,
    SplitResolutionOverflow,
    InvalidRegionSize,
    RegionOutOfBounds {
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    },
    ChildCoordinateOutOfBounds {
        x: u8,
        y: u8,
    },
    CellNotSplit {
        x: u32,
        y: u32,
    },
    CellNotExpanded {
        x: u32,
        y: u32,
    },
}

impl Canvas {
    /// {
    ///   責務: [from_parts: 検証済みの保持状態から履歴のないCanvasを組み立てる]
    ///   処理: [
    ///     1: 論理解像度・保持フィールド・分割記録を格納する
    ///     2: UndoとRedoを空にする
    ///   ]
    ///   引数: [
    ///     resolution: 対象の解像度
    ///     field: 保持フィールド
    ///     splits: 分割親色と展開状態の記録
    ///   ]
    ///   戻り値: [新しいCanvas]
    /// }
    pub(crate) fn from_parts(
        resolution: Resolution,
        field: ResolutionField,
        splits: Vec<SplitCell>,
    ) -> Self {
        Self {
            resolution,
            field,
            splits: Arc::new(splits),
            history: Vec::new(),
            future: Vec::new(),
        }
    }

    /// {
    ///   責務: [new: 予算内の透明Canvasを作る]
    ///   処理: [
    ///     1: 解像度に応じた透明ラスタを確保する
    ///     2: 保持フィールドとしてCanvasへ格納する
    ///   ]
    ///   引数: [
    ///     resolution: 対象の解像度
    ///   ]
    ///   戻り値: [Canvasまたはラスタ確保エラー]
    /// }
    pub fn new(resolution: Resolution) -> Result<Self, CanvasError> {
        Ok(Self::from_raster(Raster::new(resolution)?))
    }

    /// {
    ///   責務: [from_raster: 入力ラスタを保持するCanvasを作る]
    ///   処理: [
    ///     1: ラスタの解像度を取得する
    ///     2: 保持フィールドを作り分割記録と履歴を空にする
    ///   ]
    ///   引数: [
    ///     raster: 元となるRGBAラスタ
    ///   ]
    ///   戻り値: [新しいCanvas]
    /// }
    pub fn from_raster(raster: Raster) -> Self {
        let resolution = raster.resolution();
        Self {
            resolution,
            field: ResolutionField::from_raster(raster),
            splits: Arc::new(Vec::new()),
            history: Vec::new(),
            future: Vec::new(),
        }
    }

    /// {
    ///   責務: [resolution: 現在の論理解像度を取得する]
    ///   処理: [
    ///     1: 保持している論理解像度を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [論理解像度]
    /// }
    pub const fn resolution(&self) -> Resolution {
        self.resolution
    }

    /// {
    ///   責務: [retained_resolution: 保持中の細部を表す最大解像度を取得する]
    ///   処理: [
    ///     1: 保持フィールドの解像度要約を取得する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [保持解像度の要約]
    /// }
    pub fn retained_resolution(&self) -> Resolution {
        self.field.retained_resolution()
    }

    /// {
    ///   責務: [can_undo: 取り消せる編集があるか判定する]
    ///   処理: [
    ///     1: Undo履歴が空か確認する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [取り消し可能ならtrue]
    /// }
    pub fn can_undo(&self) -> bool {
        !self.history.is_empty()
    }

    /// {
    ///   責務: [can_redo: やり直せる編集があるか判定する]
    ///   処理: [
    ///     1: Redo履歴が空か確認する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [やり直し可能ならtrue]
    /// }
    pub fn can_redo(&self) -> bool {
        !self.future.is_empty()
    }

    /// {
    ///   責務: [sample: 論理セルの保存済み親色または保持色を読む]
    ///   処理: [
    ///     1: 同じ解像度の分割記録を探す
    ///     2: 親色がなければ保持フィールドをサンプリングする
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [RGBA色または座標範囲エラー]
    /// }
    pub fn sample(&self, x: u32, y: u32) -> Result<Color, RasterError> {
        if x < self.resolution.width() && y < self.resolution.height() {
            if let Some(split) = self
                .splits
                .iter()
                .find(|split| split.matches(self.resolution, x, y))
            {
                return Ok(split.base);
            }
        }
        self.field.sample(self.resolution, x, y)
    }

    /// {
    ///   責務: [sample_child: 保存された分割セルの子色を読む]
    ///   処理: [
    ///     1: 親座標・子座標と分割記録を検証する
    ///     2: 確保不要の子解像度を計算して保持色を読む
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     child: 2×2内の子セル座標
    ///   ]
    ///   戻り値: [RGBA色または座標・分割状態のエラー]
    /// }
    pub fn sample_child(
        &self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
    ) -> Result<Color, CanvasError> {
        self.validate_parent(x, y)?;
        Self::validate_child(child)?;
        if !self
            .splits
            .iter()
            .any(|split| split.matches(self.resolution, x, y))
        {
            return Err(CanvasError::CellNotSplit { x, y });
        }
        // Sampling a collapsed child does not allocate a doubled raster.
        let grid = self.child_sampling_resolution()?;
        Ok(self
            .field
            .sample(grid, 2 * x + u32::from(child.0), 2 * y + u32::from(child.1))?)
    }

    /// {
    ///   責務: [render: 現在の論理表示を描画する]
    ///   処理: [
    ///     1: 現在の解像度で保持色と分割親色を投影する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [新しいラスタまたは描画予算エラー]
    /// }
    pub fn render(&self) -> Result<Raster, RasterError> {
        self.projection(self.resolution)
    }

    /// {
    ///   責務: [render_at: 指定解像度で保持中の細部を直接描画する]
    ///   処理: [
    ///     1: 保持フィールドを指定解像度へ投影する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///   ]
    ///   戻り値: [新しいラスタまたは描画予算エラー]
    /// }
    pub fn render_at(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        self.field.render(resolution)
    }

    /// {
    ///   責務: [native_resolution: 展開状態に応じた描画解像度を求める]
    ///   処理: [
    ///     1: 現在の解像度の展開セルを探す
    ///     2: 展開があれば予算検査済みの2倍解像度を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [描画解像度または子解像度エラー]
    /// }
    pub fn native_resolution(&self) -> Result<Resolution, CanvasError> {
        if self
            .splits
            .iter()
            .any(|split| split.resolution == self.resolution && split.expanded)
        {
            self.child_resolution()
        } else {
            Ok(self.resolution)
        }
    }

    /// {
    ///   責務: [render_native: 展開セルの子色を含む描画を作る]
    ///   処理: [
    ///     1: 描画解像度を決めて論理表示を複製する
    ///     2: 展開セルだけ子色で置き換える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [描画ラスタまたは描画・分割エラー]
    /// }
    pub fn render_native(&self) -> Result<Raster, CanvasError> {
        let target = self.native_resolution()?;
        if target == self.resolution {
            return Ok(self.render()?);
        }
        let source = self.render()?;
        let mut output = Raster::new(target)?;
        for y in 0..self.resolution.height() {
            for x in 0..self.resolution.width() {
                let color = source.sample(x, y)?;
                for child_y in 0..2 {
                    for child_x in 0..2 {
                        output.paint(2 * x + child_x, 2 * y + child_y, color);
                    }
                }
            }
        }
        for split in self
            .splits
            .iter()
            .copied()
            .filter(|split| split.resolution == self.resolution && split.expanded)
        {
            for child_y in 0..2u8 {
                for child_x in 0..2u8 {
                    let color = self.sample_child(split.x, split.y, (child_x, child_y))?;
                    output.paint(
                        2 * split.x + u32::from(child_x),
                        2 * split.y + u32::from(child_y),
                        color,
                    );
                }
            }
        }
        Ok(output)
    }

    /// {
    ///   責務: [has_detail_at: セル領域に細部や分割情報が残っているか判定する]
    ///   処理: [
    ///     1: 保持フィールドの細部を調べる
    ///     2: 交差する分割領域と中心位置の親色を調べる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [細部があればtrue、範囲外ならエラー]
    /// }
    pub fn has_detail_at(&self, x: u32, y: u32) -> Result<bool, RasterError> {
        if self.field.has_detail_at(self.resolution, x, y)? {
            return Ok(true);
        }
        let bounds = FieldBounds::cell(self.resolution, x, y);
        for split in self.splits.iter().copied() {
            let split_bounds = split.bounds();
            if let Some(overlap) = split_bounds.intersection(bounds) {
                if overlap == split_bounds {
                    return Ok(true);
                }
                let center_x = Coordinate::center(split.x, split.resolution.width());
                let center_y = Coordinate::center(split.y, split.resolution.height());
                if bounds.contains(center_x, center_y)
                    && split.base != self.field.sample(split.resolution, split.x, split.y)?
                {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    /// {
    ///   責務: [is_split: 現在の解像度でセルが展開中か判定する]
    ///   処理: [
    ///     1: 解像度と座標が一致する展開記録を探す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [展開中ならtrue]
    /// }
    pub fn is_split(&self, x: u32, y: u32) -> bool {
        self.splits
            .iter()
            .any(|split| split.matches(self.resolution, x, y) && split.expanded)
    }

    /// {
    ///   責務: [split_cell: 1セルを子セルへ展開する]
    ///   処理: [
    ///     1: 範囲外と展開済みを変更なしとして扱う
    ///     2: 1セルの領域分割へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [変更有無または分割予算エラー]
    /// }
    pub fn split_cell(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() || self.is_split(x, y) {
            return Ok(false);
        }
        Ok(self.split_region(x, y, 1, 1)? != 0)
    }

    /// Expands every cell in a positive, fully contained rectangle. Returns the
    /// number newly expanded, including previously collapsed cells. Existing
    /// parent overrides and children survive re-expansion. The whole operation
    /// is one undo step; invalid bounds or budgets leave state/history intact.
    /// {
    ///   責務: [split_region: 長方形内のセルを一括展開する]
    ///   処理: [
    ///     1: 範囲・子解像度・追加記録数を事前検証する
    ///     2: 親色と既存子色を保持して展開する
    ///     3: 1回の編集として確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     width: 対象領域の幅
    ///     height: 対象領域の高さ
    ///   ]
    ///   戻り値: [新たに展開したセル数または検証・確保エラー]
    /// }
    pub fn split_region(
        &mut self,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<usize, CanvasError> {
        if width == 0 || height == 0 {
            return Err(CanvasError::InvalidRegionSize);
        }
        let end_x = x.checked_add(width);
        let end_y = y.checked_add(height);
        let (Some(end_x), Some(end_y)) = (end_x, end_y) else {
            return Err(CanvasError::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            });
        };
        if end_x > self.resolution.width() || end_y > self.resolution.height() {
            return Err(CanvasError::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            });
        }
        self.child_resolution()?;
        let area = u64::from(width) * u64::from(height);
        let mut retained = 0;
        let mut expanded = 0;
        for split in self.splits.iter().filter(|split| {
            split.resolution == self.resolution
                && (x..end_x).contains(&split.x)
                && (y..end_y).contains(&split.y)
        }) {
            retained += 1;
            expanded += u64::from(split.expanded);
        }
        let additional = area - retained;
        if additional > (MAX_SPLIT_CELLS - self.splits.len()) as u64 {
            return Err(CanvasError::SplitLimitExceeded);
        }
        let changed = area - expanded;
        if changed == 0 {
            return Ok(0);
        }
        // The budget check bounds both conversions and iteration to 4096 cells.
        let mut splits = self.copy_splits(additional as usize)?;
        for py in y..end_y {
            for px in x..end_x {
                if let Some(split) = splits
                    .iter_mut()
                    .find(|split| split.matches(self.resolution, px, py))
                {
                    split.expanded = true;
                } else {
                    splits.push(SplitCell {
                        resolution: self.resolution,
                        x: px,
                        y: py,
                        base: self.field.sample(self.resolution, px, py)?,
                        expanded: true,
                    });
                }
            }
        }
        self.commit(self.resolution, self.field.clone(), Arc::new(splits))?;
        Ok(changed as usize)
    }

    /// {
    ///   責務: [collapse_cell: 子色を残してセル表示を親へ折りたたむ]
    ///   処理: [
    ///     1: 対象の展開記録を探す
    ///     2: 展開状態だけを変更して履歴へ確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [変更有無または履歴確保エラー]
    /// }
    pub fn collapse_cell(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        let Some(index) = self
            .splits
            .iter()
            .position(|split| split.matches(self.resolution, x, y) && split.expanded)
        else {
            return Ok(false);
        };
        let mut splits = self.copy_splits(0)?;
        splits[index].expanded = false;
        self.commit(self.resolution, self.field.clone(), Arc::new(splits))?;
        Ok(true)
    }

    /// {
    ///   責務: [paint_child: 独立した親色を保持して指定の子セルを描く]
    ///   処理: [
    ///     1: 座標・展開状態と変更の必要性を検証する
    ///     2: 保持色と対象外の親記録を更新する
    ///     3: 編集を履歴へ確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     child: 2×2内の子セル座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または座標・保持予算・履歴エラー]
    /// }
    pub fn paint_child(
        &mut self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        Self::validate_child(child)?;
        if !self.is_split(x, y) {
            return Err(CanvasError::CellNotExpanded { x, y });
        }
        let grid = self.child_resolution()?;
        let child_x = 2 * x + u32::from(child.0);
        let child_y = 2 * y + u32::from(child.1);
        let has_detail = self.field.has_detail_at(grid, child_x, child_y)?;
        let current = self.field.sample(grid, child_x, child_y)?;
        if current == color && !(policy == DetailPolicy::Discard && has_detail) {
            return Ok(false);
        }
        let raw = self.field.sample_raw_cell(grid, child_x, child_y)?;
        let delta = std::array::from_fn(|i| i64::from(color[i]) - raw[i]);
        let mut field = self.field.clone();
        let field_changed = field.paint(grid, child_x, child_y, color, policy)?;
        let mut splits = self.copy_splits(0)?;
        let metadata_changed = Self::update_splits(
            &mut splits,
            FieldBounds::cell(grid, child_x, child_y),
            policy,
            color,
            delta,
            Some((self.resolution, x, y)),
        );
        if !field_changed && !metadata_changed {
            return Ok(false);
        }
        self.commit(self.resolution, field, Arc::new(splits))?;
        Ok(true)
    }

    /// {
    ///   責務: [erase_child: 指定の子セルを透明にする]
    ///   処理: [
    ///     1: 透明RGBAを使って子セル描画へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     child: 2×2内の子セル座標
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または子セル描画エラー]
    /// }
    pub fn erase_child(
        &mut self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        self.paint_child(x, y, child, [0; 4], policy)
    }

    /// {
    ///   責務: [set_resolution: 細部方針に従って論理解像度を変更する]
    ///   処理: [
    ///     1: 保持なら既存状態を共有し、破棄なら対象表示を焼き込む
    ///     2: 解像度と分割記録を履歴へ確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または描画・履歴エラー]
    /// }
    pub fn set_resolution(
        &mut self,
        resolution: Resolution,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if resolution == self.resolution && policy == DetailPolicy::Preserve {
            return Ok(false);
        }
        let field = match policy {
            DetailPolicy::Preserve => self.field.clone(),
            DetailPolicy::Discard => ResolutionField::from_raster(self.projection(resolution)?),
        };
        let splits = match policy {
            DetailPolicy::Preserve => self.splits.clone(),
            DetailPolicy::Discard => Arc::new(Vec::new()),
        };
        self.commit(resolution, field, splits)?;
        Ok(true)
    }

    /// {
    ///   責務: [paint: 指定セルの親色または保持領域を描く]
    ///   処理: [
    ///     1: 範囲と同色時の細部破棄を判定する
    ///     2: 複製した保持状態へ局所編集する
    ///     3: 変更があれば履歴へ確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または保持予算・履歴エラー]
    /// }
    pub fn paint(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(false);
        }
        let has_detail = self.has_detail_at(x, y)?;
        let current = self.sample(x, y)?;
        if current == color && !(policy == DetailPolicy::Discard && has_detail) {
            return Ok(false);
        }
        let mut splits = self.copy_splits(0)?;
        let mut field = self.field.clone();
        if !Self::edit_cell(
            self.resolution,
            &mut field,
            &mut splits,
            (x, y),
            color,
            policy,
        )? {
            return Ok(false);
        }
        self.commit(self.resolution, field, Arc::new(splits))?;
        Ok(true)
    }

    /// Fills a four-connected region of equal logical RGBA samples. Returns the
    /// number of targeted cells; same-color discard targets only detailed cells.
    /// All edits form one undo step. Any error leaves state and history intact.
    /// {
    ///   責務: [fill: 論理RGBAが同じ4近傍領域を一括で塗る]
    ///   処理: [
    ///     1: 変更前表示から領域と細部対象を調べる
    ///     2: 全面単色化または局所編集を準備する
    ///     3: 全編集を1回の履歴へ確定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [対象セル数または描画・保持予算・履歴エラー]
    /// }
    pub fn fill(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<usize, CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Ok(0);
        }
        let original = self.sample(x, y)?;
        if original == color && policy == DetailPolicy::Preserve {
            return Ok(0);
        }
        let view = self.render()?;
        let mut points = flood_region(&view, x, y)?;
        let pixel_count = self.resolution.width() as usize * self.resolution.height() as usize;
        let mut has_detail = !self.splits.is_empty();
        let mut count = 0;
        for index in 0..points.len() {
            let (px, py) = points[index];
            let detail = self.has_detail_at(px, py)?;
            has_detail |= detail;
            if original != color || detail {
                points[count] = (px, py);
                count += 1;
            }
        }
        points.truncate(count);
        if count == 0 {
            return Ok(0);
        }
        // Avoid one patch per pixel for a uniform whole-canvas replacement.
        // Preserve must never flatten fine samples or saved split metadata.
        if count == pixel_count && (policy == DetailPolicy::Discard || !has_detail) {
            let mut solid = Raster::new(Resolution::new(1, 1).expect("positive resolution"))?;
            solid.paint(0, 0, color);
            self.commit(
                self.resolution,
                ResolutionField::from_raster(solid),
                Arc::new(Vec::new()),
            )?;
        } else {
            let mut field = self.field.clone();
            let mut splits = self.copy_splits(0)?;
            for point in points {
                Self::edit_cell(
                    self.resolution,
                    &mut field,
                    &mut splits,
                    point,
                    color,
                    policy,
                )?;
            }
            self.commit(self.resolution, field, Arc::new(splits))?;
        }
        Ok(count)
    }

    /// {
    ///   責務: [edit_cell: 履歴を確定せず候補状態の1セルを編集する]
    ///   処理: [
    ///     1: 保持時は同一セルの親色上書きを優先する
    ///     2: 保持フィールドと交差する分割記録を更新する
    ///   ]
    ///   引数: [
    ///     grid: 座標を解釈するグリッド
    ///     field: 保持フィールド
    ///     splits: 分割親色と展開状態の記録
    ///     (x, y): 対象セルの横・縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [候補状態の変更有無または保持編集エラー]
    /// }
    fn edit_cell(
        grid: Resolution,
        field: &mut ResolutionField,
        splits: &mut Vec<SplitCell>,
        (x, y): (u32, u32),
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, CanvasError> {
        if policy == DetailPolicy::Preserve {
            if let Some(split) = splits.iter_mut().find(|split| split.matches(grid, x, y)) {
                let changed = split.base != color;
                split.base = color;
                return Ok(changed);
            }
        }
        let raw = field.sample_raw_cell(grid, x, y)?;
        let delta = std::array::from_fn(|i| i64::from(color[i]) - raw[i]);
        let field_changed = field.paint(grid, x, y, color, policy)?;
        let metadata_changed = Self::update_splits(
            splits,
            FieldBounds::cell(grid, x, y),
            policy,
            color,
            delta,
            None,
        );
        Ok(field_changed || metadata_changed)
    }

    /// {
    ///   責務: [erase: 指定セルを透明にする]
    ///   処理: [
    ///     1: 透明RGBAを使って親セル描画へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または描画エラー]
    /// }
    pub fn erase(&mut self, x: u32, y: u32, policy: DetailPolicy) -> Result<bool, CanvasError> {
        self.paint(x, y, [0; 4], policy)
    }

    /// {
    ///   責務: [discard_detail: 表示色を維持して指定セルの細部を破棄する]
    ///   処理: [
    ///     1: 細部の有無を調べて現在色を取得する
    ///     2: 破棄方針で親セルを描く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [変更有無または座標・編集エラー]
    /// }
    pub fn discard_detail(&mut self, x: u32, y: u32) -> Result<bool, CanvasError> {
        if !self.has_detail_at(x, y)? {
            return Ok(false);
        }
        let color = self.sample(x, y)?;
        self.paint(x, y, color, DetailPolicy::Discard)
    }

    /// {
    ///   責務: [undo: 最後の編集前状態へ戻す]
    ///   処理: [
    ///     1: Redo保存領域を確保する
    ///     2: 現在状態を保存しUndo状態を復元する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [復元有無または履歴確保エラー]
    /// }
    pub fn undo(&mut self) -> Result<bool, CanvasError> {
        if self.history.is_empty() {
            return Ok(false);
        }
        self.future
            .try_reserve(1)
            .map_err(|_| CanvasError::HistoryAllocationFailed)?;
        self.future.push(self.snapshot());
        let state = self.history.pop().expect("history was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    /// {
    ///   責務: [redo: 取り消した編集後状態へ進む]
    ///   処理: [
    ///     1: Undo保存領域を確保する
    ///     2: 現在状態を保存しRedo状態を復元する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [復元有無または履歴確保エラー]
    /// }
    pub fn redo(&mut self) -> Result<bool, CanvasError> {
        if self.future.is_empty() {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(self.snapshot());
        let state = self.future.pop().expect("future was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    /// {
    ///   責務: [commit: 準備済み編集状態を1回の履歴として確定する]
    ///   処理: [
    ///     1: 履歴の確保と最大50操作の制限を処理する
    ///     2: 現在状態をUndoへ保存しRedoを消す
    ///     3: 準備した解像度・保持色・分割記録を採用する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     field: 保持フィールド
    ///     splits: 分割親色と展開状態の記録
    ///   ]
    ///   戻り値: [成功時は単位値、履歴確保に失敗した場合はエラー]
    /// }
    fn commit(
        &mut self,
        resolution: Resolution,
        field: ResolutionField,
        splits: Arc<Vec<SplitCell>>,
    ) -> Result<(), CanvasError> {
        self.reserve_history_slot()?;
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(self.snapshot());
        self.future.clear();
        self.resolution = resolution;
        self.field = field;
        self.splits = splits;
        Ok(())
    }

    /// {
    ///   責務: [reserve_history_slot: 状態変更前にUndo履歴の保存領域を確保する]
    ///   処理: [
    ///     1: 履歴が上限未満なら1件分の容量を確保する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [成功時は単位値、確保失敗時は履歴エラー]
    /// }
    fn reserve_history_slot(&mut self) -> Result<(), CanvasError> {
        if self.history.len() < HISTORY_LIMIT {
            self.history
                .try_reserve(1)
                .map_err(|_| CanvasError::HistoryAllocationFailed)?;
        }
        Ok(())
    }

    /// {
    ///   責務: [snapshot: 現在の編集状態を共有可能なスナップショットにする]
    ///   処理: [
    ///     1: 解像度と共有保持データ・分割記録を複製する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [CanvasState]
    /// }
    fn snapshot(&self) -> CanvasState {
        CanvasState {
            resolution: self.resolution,
            field: self.field.clone(),
            splits: self.splits.clone(),
        }
    }

    /// {
    ///   責務: [restore: 保存状態を現在の編集状態へ戻す]
    ///   処理: [
    ///     1: 解像度・保持フィールド・分割記録を取り替える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     state: 復元する保存状態
    ///   ]
    ///   戻り値: [なし]
    /// }
    fn restore(&mut self, state: CanvasState) {
        self.resolution = state.resolution;
        self.field = state.field;
        self.splits = state.splits;
    }

    /// {
    ///   責務: [copy_splits: 追加容量を備えた独立した分割記録を作る]
    ///   処理: [
    ///     1: 追加容量を検証して確保する
    ///     2: 既存記録を複製する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     additional: 追加する分割記録の容量
    ///   ]
    ///   戻り値: [分割記録の配列または確保エラー]
    /// }
    fn copy_splits(&self, additional: usize) -> Result<Vec<SplitCell>, CanvasError> {
        let capacity = self
            .splits
            .len()
            .checked_add(additional)
            .ok_or(CanvasError::SplitLimitExceeded)?;
        let mut splits = Vec::new();
        splits
            .try_reserve_exact(capacity)
            .map_err(|_| CanvasError::AllocationFailed)?;
        splits.extend(self.splits.iter().copied());
        Ok(splits)
    }

    /// {
    ///   責務: [child_resolution: 子セル描画用解像度の安全性を検証する]
    ///   処理: [
    ///     1: 2倍の解像度を計算する
    ///     2: 辺長と画素数の描画予算を検査する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [子解像度または描画予算エラー]
    /// }
    fn child_resolution(&self) -> Result<Resolution, CanvasError> {
        let resolution = self.child_sampling_resolution()?;
        let width = resolution.width();
        let height = resolution.height();
        if width > MAX_DIMENSION || height > MAX_DIMENSION {
            return Err(CanvasError::Raster(RasterError::DimensionLimitExceeded {
                width,
                height,
            }));
        }
        if u64::from(width) * u64::from(height) > MAX_PIXELS as u64 {
            return Err(CanvasError::Raster(RasterError::PixelBudgetExceeded));
        }
        Ok(resolution)
    }

    /// {
    ///   責務: [child_sampling_resolution: バッファ確保なしで子セルの座標系を求める]
    ///   処理: [
    ///     1: 縦横の2倍計算でオーバーフローを検査する
    ///     2: 正の子解像度を構成する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [子解像度または整数範囲エラー]
    /// }
    fn child_sampling_resolution(&self) -> Result<Resolution, CanvasError> {
        let width = self
            .resolution
            .width()
            .checked_mul(2)
            .ok_or(CanvasError::SplitResolutionOverflow)?;
        let height = self
            .resolution
            .height()
            .checked_mul(2)
            .ok_or(CanvasError::SplitResolutionOverflow)?;
        Resolution::new(width, height).map_err(|_| CanvasError::SplitResolutionOverflow)
    }

    /// {
    ///   責務: [validate_parent: 親セル座標がCanvas内にあるか検査する]
    ///   処理: [
    ///     1: 縦横の論理範囲と座標を比較する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [成功時は単位値、範囲外なら座標エラー]
    /// }
    fn validate_parent(&self, x: u32, y: u32) -> Result<(), CanvasError> {
        if x >= self.resolution.width() || y >= self.resolution.height() {
            return Err(CanvasError::Raster(RasterError::CoordinateOutOfBounds {
                x,
                y,
            }));
        }
        Ok(())
    }

    /// {
    ///   責務: [validate_child: 子座標が2×2内にあるか検査する]
    ///   処理: [
    ///     1: 各成分が0または1であることを確認する
    ///   ]
    ///   引数: [
    ///     child: 2×2内の子セル座標
    ///   ]
    ///   戻り値: [成功時は単位値、範囲外なら子座標エラー]
    /// }
    fn validate_child(child: ChildCoordinate) -> Result<(), CanvasError> {
        if child.0 > 1 || child.1 > 1 {
            return Err(CanvasError::ChildCoordinateOutOfBounds {
                x: child.0,
                y: child.1,
            });
        }
        Ok(())
    }

    /// {
    ///   責務: [projection: 保持色に対象解像度の親色上書きを重ねる]
    ///   処理: [
    ///     1: 保持フィールドを描画する
    ///     2: 同じ解像度の保存親色を上書きする
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///   ]
    ///   戻り値: [投影ラスタまたは描画エラー]
    /// }
    fn projection(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        let mut raster = self.field.render(resolution)?;
        for split in self
            .splits
            .iter()
            .filter(|split| split.resolution == resolution)
        {
            raster.paint(split.x, split.y, split.base);
        }
        Ok(raster)
    }

    /// {
    ///   責務: [update_splits: 局所編集に交差する保存親色と分割記録を更新する]
    ///   処理: [
    ///     1: 除外する親記録を飛ばして領域交差を求める
    ///     2: 保持では中心を含む親色へ色差分を足す
    ///     3: 破棄では内包記録を削除し部分交差の親色を更新する
    ///   ]
    ///   引数: [
    ///     splits: 分割親色と展開状態の記録
    ///     target: 局所編集の対象範囲
    ///     policy: 細部を保持または破棄する方針
    ///     replacement: 置換するRGBA色
    ///     delta: RGBA成分ごとの色差分
    ///     skip: 更新から除外する分割記録
    ///   ]
    ///   戻り値: [分割記録を変更した場合true]
    /// }
    fn update_splits(
        splits: &mut Vec<SplitCell>,
        target: FieldBounds,
        policy: DetailPolicy,
        replacement: Color,
        delta: [i64; 4],
        skip: Option<(Resolution, u32, u32)>,
    ) -> bool {
        let mut changed = false;
        splits.retain_mut(|split| {
            if skip.is_some_and(|(resolution, x, y)| split.matches(resolution, x, y)) {
                return true;
            }
            let bounds = split.bounds();
            let Some(overlap) = bounds.intersection(target) else {
                return true;
            };
            let center_x = Coordinate::center(split.x, split.resolution.width());
            let center_y = Coordinate::center(split.y, split.resolution.height());
            match policy {
                DetailPolicy::Preserve => {
                    if target.contains(center_x, center_y) {
                        let updated = std::array::from_fn(|channel| {
                            (i64::from(split.base[channel]) + delta[channel]).clamp(0, 255) as u8
                        });
                        if updated != split.base {
                            split.base = updated;
                            changed = true;
                        }
                    }
                    true
                }
                DetailPolicy::Discard => {
                    if overlap == bounds {
                        changed = true;
                        false
                    } else {
                        if target.contains(center_x, center_y) && split.base != replacement {
                            split.base = replacement;
                            changed = true;
                        }
                        true
                    }
                }
            }
        });
        changed
    }
}

impl From<RasterError> for CanvasError {
    /// {
    ///   責務: [from: 元のエラーをこの型の対応する種別へ変換する]
    ///   処理: [
    ///     1: 入力エラーを対応する列挙値に包む
    ///   ]
    ///   引数: [
    ///     error: 変換する元エラー
    ///   ]
    ///   戻り値: [変換後のエラー]
    /// }
    fn from(error: RasterError) -> Self {
        Self::Raster(error)
    }
}

impl From<ResolutionFieldError> for CanvasError {
    /// {
    ///   責務: [from: 元のエラーをこの型の対応する種別へ変換する]
    ///   処理: [
    ///     1: 入力エラーを対応する列挙値に包む
    ///   ]
    ///   引数: [
    ///     error: 変換する元エラー
    ///   ]
    ///   戻り値: [変換後のエラー]
    /// }
    fn from(error: ResolutionFieldError) -> Self {
        Self::Field(error)
    }
}

impl Display for CanvasError {
    /// {
    ///   責務: [fmt: エラー種別に対応する診断文を出力する]
    ///   処理: [
    ///     1: 種別を判定し内部エラーまたは説明文をformatterへ書く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     formatter: 診断文の出力先
    ///   ]
    ///   戻り値: [書き込み結果、出力に失敗するとfmt::Error]
    /// }
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Raster(error) => Display::fmt(error, formatter),
            Self::Field(error) => Display::fmt(error, formatter),
            Self::AllocationFailed => formatter.write_str("unable to allocate canvas state"),
            Self::HistoryAllocationFailed => {
                formatter.write_str("unable to allocate canvas history")
            }
            Self::SplitLimitExceeded => formatter.write_str("canvas exceeds its split-cell limit"),
            Self::SplitResolutionOverflow => {
                formatter.write_str("split resolution exceeds the integer range")
            }
            Self::InvalidRegionSize => formatter.write_str("region dimensions must be positive"),
            Self::RegionOutOfBounds {
                x,
                y,
                width,
                height,
            } => {
                write!(
                    formatter,
                    "region ({x}, {y}, {width}, {height}) is outside the canvas"
                )
            }
            Self::ChildCoordinateOutOfBounds { x, y } => {
                write!(formatter, "child coordinate ({x}, {y}) is out of bounds")
            }
            Self::CellNotSplit { x, y } => write!(formatter, "cell ({x}, {y}) is not split"),
            Self::CellNotExpanded { x, y } => {
                write!(formatter, "cell ({x}, {y}) is not expanded")
            }
        }
    }
}

impl Error for CanvasError {
    /// {
    ///   責務: [source: 連鎖する内部エラーを取得する]
    ///   処理: [
    ///     1: 内部エラーを持つ種別なら参照を返し、それ以外はNoneを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [内部エラーの参照またはNone]
    /// }
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            Self::Field(error) => Some(error),
            Self::AllocationFailed
            | Self::HistoryAllocationFailed
            | Self::SplitLimitExceeded
            | Self::SplitResolutionOverflow
            | Self::InvalidRegionSize
            | Self::RegionOutOfBounds { .. }
            | Self::ChildCoordinateOutOfBounds { .. }
            | Self::CellNotSplit { .. }
            | Self::CellNotExpanded { .. } => None,
        }
    }
}
