//! Ordered layers with one document-wide undo/redo history.
//!
//! Every layer shares one logical resolution. Layer edits, visibility, order,
//! names and resolution changes are all recorded as whole-document snapshots,
//! so one undo step never leaves layers in different states.

use crate::canvas::Canvas;
use crate::layer_error::LayerError;
use crate::resolution::Resolution;

pub(crate) const HISTORY_LIMIT: usize = 50;
pub const MAX_LAYERS: usize = 256;
const BACKGROUND_NAME: &str = "背景";

/// {
///   責務: [MoveDirection: レイヤーを合成順で動かす向きを表す]
///   フィールド: [
///     Up: 上層側へ1段動かす
///     Down: 下層側へ1段動かす
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MoveDirection {
    Up,
    Down,
}

/// {
///   責務: [LayerEntry: 名前・画素・表示状態を持つ1枚のレイヤーを表す]
///   フィールド: [
///     name: 重複しない前後空白なしの名前
///     canvas: 作品履歴が所有する、Canvas内履歴を持たない画素状態
///     visible: 合成に含めるか
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LayerEntry {
    pub(crate) name: String,
    pub(crate) canvas: Canvas,
    pub(crate) visible: bool,
}

/// {
///   責務: [DocumentState: 全レイヤーと選択状態を1回分の履歴として保存する]
///   フィールド: [
///     layers: 下層から上層の順のレイヤー
///     active: 編集対象レイヤーの位置
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct DocumentState {
    layers: Vec<LayerEntry>,
    active: usize,
}

/// {
///   責務: [LayeredCanvas: 複数レイヤーの構成と作品単位のUndo/Redoを管理する]
///   フィールド: [
///     layers: 下層から上層の順に並ぶレイヤー。末尾が最上層
///     active: 編集対象レイヤーの位置
///     history: 最大50件の編集前の作品状態
///     future: Redo用の作品状態
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LayeredCanvas {
    pub(crate) layers: Vec<LayerEntry>,
    pub(crate) active: usize,
    history: Vec<DocumentState>,
    future: Vec<DocumentState>,
}

impl LayeredCanvas {
    /// {
    ///   責務: [new: 背景レイヤーだけを持つ空の作品を作る]
    ///   処理: [
    ///     1: 指定解像度の透明Canvasを背景として確保する
    ///     2: 背景を表示・選択状態にして履歴を空にする
    ///   ]
    ///   引数: [
    ///     resolution: 全レイヤーで共通にする論理解像度
    ///   ]
    ///   戻り値: [作品またはCanvas確保エラー]
    /// }
    pub fn new(resolution: Resolution) -> Result<Self, LayerError> {
        let background = LayerEntry {
            name: BACKGROUND_NAME.to_owned(),
            canvas: Canvas::new(resolution)?,
            visible: true,
        };
        Ok(Self {
            layers: vec![background],
            active: 0,
            history: Vec::new(),
            future: Vec::new(),
        })
    }

    /// {
    ///   責務: [resolution: 全レイヤーに共通する論理解像度を取得する]
    ///   処理: [
    ///     1: 選択中レイヤーの解像度を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [論理解像度]
    /// }
    pub fn resolution(&self) -> Resolution {
        self.layers[self.active].canvas.resolution()
    }

    /// {
    ///   責務: [layer_names: 下層から上層の順にレイヤー名を列挙する]
    ///   処理: [
    ///     1: 合成順のまま名前の参照を並べる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [レイヤー名の一覧]
    /// }
    pub fn layer_names(&self) -> Vec<&str> {
        self.layers
            .iter()
            .map(|entry| entry.name.as_str())
            .collect()
    }

    /// {
    ///   責務: [active_layer: 編集対象レイヤーの名前を取得する]
    ///   処理: [
    ///     1: 選択位置のレイヤー名を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [選択中のレイヤー名]
    /// }
    pub fn active_layer(&self) -> &str {
        &self.layers[self.active].name
    }

    /// {
    ///   責務: [active: 編集対象のCanvasを読み取り専用で取得する]
    ///   処理: [
    ///     1: 選択位置のCanvasを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [選択中のCanvas]
    /// }
    pub fn active(&self) -> &Canvas {
        &self.layers[self.active].canvas
    }

    /// {
    ///   責務: [layer: 名前で指定したCanvasを読み取り専用で取得する]
    ///   処理: [
    ///     1: 名前から位置を探してCanvasを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 取得するレイヤー名
    ///   ]
    ///   戻り値: [Canvasまたは存在しない名前のエラー]
    /// }
    pub fn layer(&self, name: &str) -> Result<&Canvas, LayerError> {
        Ok(&self.layers[self.position_of(name)?].canvas)
    }

    /// {
    ///   責務: [is_layer_visible: レイヤーが合成に含まれるか調べる]
    ///   処理: [
    ///     1: 対象位置を解決して表示状態を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 対象名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [表示状態または存在しない名前のエラー]
    /// }
    pub fn is_layer_visible(&self, name: Option<&str>) -> Result<bool, LayerError> {
        Ok(self.layers[self.target_position(name)?].visible)
    }

    /// {
    ///   責務: [can_undo: 取り消せる作品編集があるか判定する]
    ///   処理: [
    ///     1: 作品のUndo履歴が空か確認する
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
    ///   責務: [can_redo: やり直せる作品編集があるか判定する]
    ///   処理: [
    ///     1: 作品のRedo履歴が空か確認する
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
    ///   責務: [add_layer: 空のレイヤーを最上層へ追加して選択する]
    ///   処理: [
    ///     1: 名前・重複・層数上限を検証する
    ///     2: 現在解像度の透明Canvasと履歴枠を先に確保する
    ///     3: 追加前の状態を記録して最上層を選択する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 前後の空白を除いて使う新しい名前
    ///   ]
    ///   戻り値: [成功時は単位値、検証や確保に失敗すれば状態を変えずエラー]
    /// }
    pub fn add_layer(&mut self, name: &str) -> Result<(), LayerError> {
        let clean = Self::clean_name(name)?;
        if self.layers.iter().any(|entry| entry.name == clean) {
            return Err(LayerError::DuplicateName(clean.to_owned()));
        }
        if self.layers.len() >= MAX_LAYERS {
            return Err(LayerError::TooManyLayers);
        }
        let canvas = Canvas::new(self.resolution())?;
        self.reserve_history_slot()?;
        let before = self.snapshot();
        self.layers.push(LayerEntry {
            name: clean.to_owned(),
            canvas,
            visible: true,
        });
        self.active = self.layers.len() - 1;
        self.record(before);
        Ok(())
    }

    /// {
    ///   責務: [select_layer: 既存レイヤーを編集対象にする]
    ///   処理: [
    ///     1: 名前から位置を探して選択位置だけを変える。履歴は記録しない
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 選択するレイヤー名
    ///   ]
    ///   戻り値: [成功時は単位値、存在しない名前ならエラー]
    /// }
    pub fn select_layer(&mut self, name: &str) -> Result<(), LayerError> {
        self.active = self.position_of(name)?;
        Ok(())
    }

    /// {
    ///   責務: [remove_layer: 1層以上を残して対象レイヤーを削除する]
    ///   処理: [
    ///     1: 対象と残存層数を検証し、履歴枠を確保する
    ///     2: 削除前の状態を記録してレイヤーを取り除く
    ///     3: 選択位置を、選択中の層なら最下層へ、それ以外は同じ層を指すよう補正する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 削除名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [成功時は単位値、検証や確保に失敗すれば状態を変えずエラー]
    /// }
    pub fn remove_layer(&mut self, name: Option<&str>) -> Result<(), LayerError> {
        let target = self.target_position(name)?;
        if self.layers.len() == 1 {
            return Err(LayerError::LastLayer);
        }
        self.reserve_history_slot()?;
        let before = self.snapshot();
        self.layers.remove(target);
        if target == self.active {
            self.active = 0;
        } else if target < self.active {
            self.active -= 1;
        }
        self.record(before);
        Ok(())
    }

    /// {
    ///   責務: [set_layer_visibility: レイヤーの表示・非表示を切り替える]
    ///   処理: [
    ///     1: 対象を解決し、同じ状態なら何も記録しない
    ///     2: 変更前の状態を記録して表示状態を変える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     visible: 新しい表示状態
    ///     name: 対象名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [変更したらtrue、同じ状態ならfalse、失敗ならエラー]
    /// }
    pub fn set_layer_visibility(
        &mut self,
        visible: bool,
        name: Option<&str>,
    ) -> Result<bool, LayerError> {
        let target = self.target_position(name)?;
        if self.layers[target].visible == visible {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        let before = self.snapshot();
        self.layers[target].visible = visible;
        self.record(before);
        Ok(true)
    }

    /// {
    ///   責務: [rename_layer: 合成順と選択を保ってレイヤー名を変更する]
    ///   処理: [
    ///     1: 対象と新しい名前を検証し、同じ名前なら何も記録しない
    ///     2: 変更前の状態を記録して名前だけを置き換える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     new_name: 前後の空白を除いて使う変更後の名前
    ///     name: 対象名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [変更したらtrue、同じ名前ならfalse、失敗ならエラー]
    /// }
    pub fn rename_layer(&mut self, new_name: &str, name: Option<&str>) -> Result<bool, LayerError> {
        let target = self.target_position(name)?;
        let clean = Self::clean_name(new_name)?;
        if self.layers[target].name == clean {
            return Ok(false);
        }
        if self.layers.iter().any(|entry| entry.name == clean) {
            return Err(LayerError::DuplicateName(clean.to_owned()));
        }
        self.reserve_history_slot()?;
        let before = self.snapshot();
        self.layers[target].name = clean.to_owned();
        self.record(before);
        Ok(true)
    }

    /// {
    ///   責務: [move_layer: レイヤーを合成順で1段入れ替える]
    ///   処理: [
    ///     1: 対象と移動先が範囲内か確認する。端なら何も記録しない
    ///     2: 変更前の状態を記録して隣と入れ替える
    ///     3: 選択中のレイヤーが同じ層を指し続けるよう選択位置を補正する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     direction: 上層側か下層側か
    ///     name: 対象名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [移動したらtrue、端ならfalse、失敗ならエラー]
    /// }
    pub fn move_layer(
        &mut self,
        direction: MoveDirection,
        name: Option<&str>,
    ) -> Result<bool, LayerError> {
        let target = self.target_position(name)?;
        let destination = match direction {
            MoveDirection::Up => target + 1,
            MoveDirection::Down => match target.checked_sub(1) {
                Some(position) => position,
                None => return Ok(false),
            },
        };
        if destination >= self.layers.len() {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        let before = self.snapshot();
        self.layers.swap(target, destination);
        if self.active == target {
            self.active = destination;
        } else if self.active == destination {
            self.active = target;
        }
        self.record(before);
        Ok(true)
    }

    /// {
    ///   責務: [undo: 直前の作品編集前の状態へ戻す]
    ///   処理: [
    ///     1: Redo用の保存領域を確保する
    ///     2: 現在の作品状態をRedoへ積み、Undo状態を復元する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [復元したらtrue、履歴がなければfalse、確保失敗ならエラー]
    /// }
    pub fn undo(&mut self) -> Result<bool, LayerError> {
        if self.history.is_empty() {
            return Ok(false);
        }
        self.future
            .try_reserve(1)
            .map_err(|_| LayerError::HistoryAllocationFailed)?;
        let current = self.snapshot();
        self.future.push(current);
        let state = self.history.pop().expect("history was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    /// {
    ///   責務: [redo: Undoで戻した作品編集を再適用する]
    ///   処理: [
    ///     1: Undo履歴の保存領域を確保する
    ///     2: 現在の作品状態をUndoへ積み、Redo状態を復元する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [復元したらtrue、履歴がなければfalse、確保失敗ならエラー]
    /// }
    pub fn redo(&mut self) -> Result<bool, LayerError> {
        if self.future.is_empty() {
            return Ok(false);
        }
        self.reserve_history_slot()?;
        let current = self.snapshot();
        self.push_history(current);
        let state = self.future.pop().expect("future was checked as nonempty");
        self.restore(state);
        Ok(true)
    }

    /// {
    ///   責務: [clean_name: レイヤー名の前後の空白を除いて空名を拒否する]
    ///   処理: [
    ///     1: 前後の空白を除く
    ///     2: 空になった名前を拒否する
    ///   ]
    ///   引数: [
    ///     name: 入力されたレイヤー名
    ///   ]
    ///   戻り値: [使用する名前または空名エラー]
    /// }
    fn clean_name(name: &str) -> Result<&str, LayerError> {
        let clean = name.trim();
        if clean.is_empty() {
            return Err(LayerError::EmptyName);
        }
        Ok(clean)
    }

    /// {
    ///   責務: [position_of: レイヤー名から合成順の位置を探す]
    ///   処理: [
    ///     1: 名前が一致する最初のレイヤーを探す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 探すレイヤー名
    ///   ]
    ///   戻り値: [位置または存在しない名前のエラー]
    /// }
    fn position_of(&self, name: &str) -> Result<usize, LayerError> {
        self.layers
            .iter()
            .position(|entry| entry.name == name)
            .ok_or_else(|| LayerError::NoSuchLayer(name.to_owned()))
    }

    /// {
    ///   責務: [target_position: 省略可能な名前を操作対象の位置へ解決する]
    ///   処理: [
    ///     1: 名前があれば位置を探し、省略時は選択中の位置を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 対象名。Noneなら選択中のレイヤー
    ///   ]
    ///   戻り値: [位置または存在しない名前のエラー]
    /// }
    fn target_position(&self, name: Option<&str>) -> Result<usize, LayerError> {
        match name {
            Some(name) => self.position_of(name),
            None => Ok(self.active),
        }
    }

    /// {
    ///   責務: [snapshot: 現在の全レイヤーと選択を履歴用に保存する]
    ///   処理: [
    ///     1: 各Canvasが共有する保持データごとレイヤー一覧を複製する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [作品状態]
    /// }
    pub(crate) fn snapshot(&self) -> DocumentState {
        DocumentState {
            layers: self.layers.clone(),
            active: self.active,
        }
    }

    /// {
    ///   責務: [restore: 保存した作品状態を現在の状態へ戻す]
    ///   処理: [
    ///     1: レイヤー一覧と選択位置を取り替える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     state: 復元する作品状態
    ///   ]
    ///   戻り値: [なし]
    /// }
    pub(crate) fn restore(&mut self, state: DocumentState) {
        self.layers = state.layers;
        self.active = state.active;
    }

    /// {
    ///   責務: [reserve_history_slot: 状態変更前にUndo履歴の保存領域を確保する]
    ///   処理: [
    ///     1: 履歴が上限未満なら1件分の容量を確保する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [成功時は単位値、確保失敗なら履歴エラー]
    /// }
    pub(crate) fn reserve_history_slot(&mut self) -> Result<(), LayerError> {
        if self.history.len() < HISTORY_LIMIT {
            self.history
                .try_reserve(1)
                .map_err(|_| LayerError::HistoryAllocationFailed)?;
        }
        Ok(())
    }

    /// {
    ///   責務: [push_history: 上限を守って編集前の状態をUndo履歴へ積む]
    ///   処理: [
    ///     1: 上限に達していれば最も古い状態を捨てる
    ///     2: 状態を末尾へ追加する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     state: 積む作品状態
    ///   ]
    ///   戻り値: [なし]
    /// }
    fn push_history(&mut self, state: DocumentState) {
        if self.history.len() == HISTORY_LIMIT {
            self.history.remove(0);
        }
        self.history.push(state);
    }

    /// {
    ///   責務: [record: 確定した編集の編集前状態をUndo履歴へ記録する]
    ///   処理: [
    ///     1: 編集前の状態を履歴へ積む
    ///     2: Redo履歴を消す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     before: 編集前の作品状態
    ///   ]
    ///   戻り値: [なし]
    /// }
    pub(crate) fn record(&mut self, before: DocumentState) {
        self.push_history(before);
        self.future.clear();
    }
}
