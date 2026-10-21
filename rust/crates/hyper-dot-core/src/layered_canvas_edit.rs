//! Pixel edits on the selected layer, recorded in the document history.

use crate::canvas::{Canvas, CanvasError, ChildCoordinate};
use crate::layer_error::LayerError;
use crate::layered_canvas::LayeredCanvas;
use crate::raster::{Color, RasterError};
use crate::resolution::Resolution;
use crate::resolution_field::DetailPolicy;

impl LayeredCanvas {
    /// {
    ///   責務: [edit_active: 選択中レイヤーの編集を作品単位の履歴へ接続する]
    ///   処理: [
    ///     1: 履歴枠と編集前の作品状態を先に確保する
    ///     2: 選択中のCanvasへ編集を委譲し、Canvas内の履歴を破棄する
    ///     3: 失敗なら編集前の状態へ戻し、変更があった場合だけ作品履歴へ記録する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     edit: 選択中のCanvasへ行う編集
    ///     changed: 編集結果が画素や分割を変えたかの判定
    ///   ]
    ///   戻り値: [編集の戻り値、失敗なら状態を変えずエラー]
    /// }
    fn edit_active<T>(
        &mut self,
        edit: impl FnOnce(&mut Canvas) -> Result<T, CanvasError>,
        changed: impl FnOnce(&T) -> bool,
    ) -> Result<T, LayerError> {
        self.reserve_history_slot()?;
        let before = self.snapshot();
        let active = self.active;
        let outcome = edit(&mut self.layers[active].canvas);
        self.layers[active].canvas.clear_history();
        match outcome {
            Err(error) => {
                // Canvasの失敗は状態を保つ契約だが、作品全体の不変条件のため確実に戻す。
                self.restore(before);
                Err(error.into())
            }
            Ok(result) => {
                // 変更なしの操作は、作品履歴とRedoを維持するため記録しない。
                if changed(&result) {
                    self.record(before);
                }
                Ok(result)
            }
        }
    }

    /// {
    ///   責務: [paint: 選択中レイヤーの親画素を塗る]
    ///   処理: [
    ///     1: 座標・色・細部方針を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更の有無、失敗なら状態を変えずエラー]
    /// }
    pub fn paint(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, LayerError> {
        self.edit_active(
            |canvas| canvas.paint(x, y, color, policy),
            |changed| *changed,
        )
    }

    /// {
    ///   責務: [erase: 選択中レイヤーの親画素を透明にする]
    ///   処理: [
    ///     1: 透明色の描画として選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更の有無、失敗なら状態を変えずエラー]
    /// }
    pub fn erase(&mut self, x: u32, y: u32, policy: DetailPolicy) -> Result<bool, LayerError> {
        self.edit_active(|canvas| canvas.erase(x, y, policy), |changed| *changed)
    }

    /// {
    ///   責務: [paint_child: 選択中レイヤーの分割画素の子セルを塗る]
    ///   処理: [
    ///     1: 親座標・子座標・色・細部方針を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 親の横座標
    ///     y: 親の縦座標
    ///     child: 2×2内の子セル座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更の有無、失敗なら状態を変えずエラー]
    /// }
    pub fn paint_child(
        &mut self,
        x: u32,
        y: u32,
        child: ChildCoordinate,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, LayerError> {
        self.edit_active(
            |canvas| canvas.paint_child(x, y, child, color, policy),
            |changed| *changed,
        )
    }

    /// {
    ///   責務: [fill: 選択中レイヤーの同色の4近傍領域を塗りつぶす]
    ///   処理: [
    ///     1: 起点・色・細部方針を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 起点の横座標
    ///     y: 起点の縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [対象にしたセル数、失敗なら状態を変えずエラー]
    /// }
    pub fn fill(
        &mut self,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<usize, LayerError> {
        self.edit_active(
            |canvas| canvas.fill(x, y, color, policy),
            |count| *count > 0,
        )
    }

    /// {
    ///   責務: [split_cell: 選択中レイヤーの画素を4つの子セルへ分割する]
    ///   処理: [
    ///     1: 座標を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [分割状態が変わったか、失敗なら状態を変えずエラー]
    /// }
    pub fn split_cell(&mut self, x: u32, y: u32) -> Result<bool, LayerError> {
        self.edit_active(|canvas| canvas.split_cell(x, y), |changed| *changed)
    }

    /// {
    ///   責務: [split_region: 選択中レイヤーの長方形領域をまとめて分割する]
    ///   処理: [
    ///     1: 領域を選択中のCanvasへ委譲し、領域全体を作品の1回の履歴にする
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 左上の横座標
    ///     y: 左上の縦座標
    ///     width: 領域の幅
    ///     height: 領域の高さ
    ///   ]
    ///   戻り値: [新たに展開したセル数、失敗なら状態を変えずエラー]
    /// }
    pub fn split_region(
        &mut self,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<usize, LayerError> {
        self.edit_active(
            |canvas| canvas.split_region(x, y, width, height),
            |count| *count > 0,
        )
    }

    /// {
    ///   責務: [collapse_cell: 選択中レイヤーの展開済みセルを折りたたむ]
    ///   処理: [
    ///     1: 座標を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [状態が変わったか、失敗なら状態を変えずエラー]
    /// }
    pub fn collapse_cell(&mut self, x: u32, y: u32) -> Result<bool, LayerError> {
        self.edit_active(|canvas| canvas.collapse_cell(x, y), |changed| *changed)
    }

    /// {
    ///   責務: [discard_detail: 選択中レイヤーの1セルの保持細部を破棄する]
    ///   処理: [
    ///     1: 座標を選択中のCanvasへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [細部を破棄したか、失敗なら状態を変えずエラー]
    /// }
    pub fn discard_detail(&mut self, x: u32, y: u32) -> Result<bool, LayerError> {
        self.edit_active(|canvas| canvas.discard_detail(x, y), |changed| *changed)
    }

    /// {
    ///   責務: [sample: 選択中レイヤーの親画素の色を読む]
    ///   処理: [
    ///     1: 座標を選択中のCanvasへ渡す。履歴や状態は変えない
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [RGBA色または座標エラー]
    /// }
    pub fn sample(&self, x: u32, y: u32) -> Result<Color, RasterError> {
        self.active().sample(x, y)
    }

    /// {
    ///   責務: [set_resolution: 全レイヤーの論理解像度を一括で変更する]
    ///   処理: [
    ///     1: 変更不要なら何もせず終了し、履歴枠を確保する
    ///     2: 全レイヤーの複製へ解像度変更を行い、1つでも失敗すれば元の作品を残す
    ///     3: 全層が成功してから作品を置き換え、1回の履歴へ記録する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 新しい論理解像度
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更したらtrue、不要ならfalse、失敗なら状態を変えずエラー]
    /// }
    pub fn set_resolution(
        &mut self,
        resolution: Resolution,
        policy: DetailPolicy,
    ) -> Result<bool, LayerError> {
        if resolution == self.resolution() && policy == DetailPolicy::Preserve {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        // 一部の層だけ解像度が変わる状態を防ぐため、全層を複製上で先に変更する。
        let mut candidates = self.layers.clone();
        for entry in &mut candidates {
            entry.canvas.set_resolution(resolution, policy)?;
            entry.canvas.clear_history();
        }
        let before = self.snapshot();
        self.layers = candidates;
        self.record(before);
        Ok(true)
    }
}
