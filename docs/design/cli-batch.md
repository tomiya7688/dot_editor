# Rust CLI 原子的バッチ編集APIの詳細設計（実装済み）

対象: [Issue #64](https://github.com/tomiya7688/dot_editor/issues/64)。**実装済み（B1〜B4）**。#63の第1段階（revision・ロック）の上に載っています。速度とメモリの測定（B5）は未実施で、改善率は主張しません。 現行CLIの契約は[CLI契約](../CLI契約.md)が正本です。本書はv1既存コマンドを置換するものではありません。

## 背景・操作の入口

`pixel-cli`の1プロセス/1論理操作を維持しつつ、複数の既存編集を**1つの論理トランザクション**として実行する操作を追加します。GUI/daemon、stdinの暗黙待機、作品のJSON v2変更は不要です。

```bash
pixel-cli --json -p art.json batch apply --file operations.json
pixel-cli --json --dry-run -p art.json batch apply --file operations.json
pixel-cli --json -p art.json --if-revision sha256:<64文字のhex> batch apply --file operations.json
```

入力ファイルはリポジトリの作業場所ではなく呼び出し元の任意パスで指定します。外部ツールが引用符付きパスを正しく渡せることを受け入れ試験に含めます。`--file -`によるstdinストリームは初期版では非対応です。

## JSON schema（batchのversionは作品のversionと別）

```json
{
  "version": 1,
  "operations": [
    {"op": "pixel.paint", "x": 3, "y": 4, "color": "#FF8800FF"},
    {"op": "detail.split", "x": 3, "y": 4},
    {"op": "pixel.paint", "x": 3, "y": 4, "child": [1, 0], "color": "#0000FFFF"}
  ]
}
```

- UTF-8 JSONオブジェクトだけを受け付けます。`version`は整数1、`operations`は0〜10,000件の配列、入力ファイル上限は**8MiB（初期提案）**です。値はメモリ・実行時間・境界テストで確認してから実装の契約として固定します。
- 重複キー、未知トップレベルフィールド、未知`op`、未知操作フィールド、NaN/Infinity、負数/小数の座標、不正な色、過剰なネスト、余分な型変換を拒否します。上限に達する前に全体を無制限に確保しません。
- `op`には既存CLIの`operation`値を使用します。コマンド名との関係を独立したテストで固定します。既存の`--discard-detail`はJSONでは`"discard_detail": true`と表現し、省略時はfalseです。
- バッチファイルとプロジェクトファイルが同一実体だった場合は、誤った上書きを防ぐため拒否します。

## 初期対応する操作とフィールド

| op | 必須フィールド | 任意フィールド | 作用 |
| --- | --- | --- | --- |
| `canvas.resolution.set` | `width,height` | `discard_detail` | 全レイヤーの解像度変更 |
| `pixel.paint` | `x,y,color` | `child:[cx,cy]`, `discard_detail` | 親/子セル描画 |
| `pixel.erase` | `x,y` | `child`, `discard_detail` | 透明化 |
| `pixel.fill` | `x,y,color` | `discard_detail` | 4近傍塗りつぶし |
| `detail.split` | `x,y` | なし | 2×2分割 |
| `detail.split-region` | `x,y,width,height` | なし | 領域分割 |
| `detail.discard` | `x,y` | なし | 対象の細部破棄 |
| `layer.add` | `name` | なし | レイヤー追加と選択 |
| `layer.remove` | なし | `layer` | 指定/アクティブ層削除 |
| `layer.select` | `name` | なし | 編集対象を切替 |
| `layer.rename` | `new_name` | `layer` | レイヤー改名 |
| `layer.move` | `direction:up/down` | `layer` | 合成順を1段移動 |
| `layer.visibility` | `visible:boolean` | `layer` | 表示状態の切替 |

親・子セル座標は0始まりで、子セルは[0,0]〜[1,1]です。操作が依存するアクティブレイヤーは**先行操作適用後の状態**です。現在の`command_table.rs` / Rust Coreの検証・命名規則・細部保持/破棄を再利用し、描画アルゴリズムをバッチ専用に複製しません。

対象外: `project.new`、読み取り系、`export.render`、入れ子batch、複数作品にまたがるトランザクション、プロセス間Undo/Redo、任意スクリプト実行。

## 実行順・原子性

```text
--fileを読取 → 全体構文/型/上限を検証 → 型付きOperation配列へ変換
 → #63の編集ロック取得 → ロック下で作品を再読込・revision検証
 → 0番目から同一LayeredCanvasへ順序付き適用
 → 全件成功かつ変更ありの場合のみ1回の保存を確定
 → 結果JSONを出してexit 0
```

1. 1件でも失敗したら、**ディスクへ保存しない**。実行途中のメモリ内状態は捨て、既存作品の全情報を維持します。保存後のOS障害は#63の`commit_uncertain`に従い、ロールバック成功とは呼びません。
2. 0件/全件no-opなら成功して`saved=false`。すべて有効でも`--dry-run`なら保存なし。dry-runは後で同じrevisionでコミットできることを予約しません。
3. 1バッチに対する保存は高々1回で、Core内で作成されるセッション履歴はJSONへ書きません。バッチ1件を別プロセスでUndoできると宣言しません。
4. `--if-revision`がある場合、全操作の前にロック下で検証し、競合は`revision_conflict`。未指定でも協調CLIの一括編集は#63のロックで直列化します。
5. 入力ファイル、プロジェクトファイル、一時ファイルのパス同一性とsymlink/hardlinkの規則は#63へ合わせます。既存の`--json`と終了値0/1/2を変更しません。

## JSONの成功・失敗例（未実装）

成功時は既存応答の`status/operation/project/result/dry_run/saved`を維持します。

```json
{
  "status": "ok",
  "operation": "batch.apply",
  "project": "art.json",
  "result": {
    "operation_count": 3,
    "changed": true,
    "revision_before": "sha256:...",
    "revision_after": "sha256:..."
  },
  "dry_run": false,
  "saved": true
}
```

`revision_after`は**実際に保存が確定した場合だけ**返します。dry-runでは確定revisionを返さず、変更予定の有無だけ報告します。

失敗時は既存の`error`コード（例:`out_of_bounds`）を維持し、互換性を壊さない追加フィールド`details.failed_index`（0始まり）・`details.op`を返します。トップレベルのバッチ構文が不正なら`invalid_batch`（exit 1）、CLI引数の欠落/不正なら`usage`（exit 2）とします。

```json
{
  "status": "error",
  "operation": "batch.apply",
  "error": "out_of_bounds",
  "message": "cell is outside the canvas",
  "details": {"failed_index": 1, "op": "pixel.paint"}
}
```

## 実装分割と検証

- **B1 Parser:** 厳密なJSONパーサー、型付きoperationと入力上限、未知フィールド拒否。各`op`の正常/異常テスト。
- **B2 Adapter:** `command_spec`/既存ハンドラを共有して、単一CLIとbatchで同じ操作意味を再利用。定義漏れ・型の曖昧な変換を拒否する表検証。
- **B3 Transaction:** `runner`で#63の排他下に作業用`LayeredCanvas`を一度だけ読み込み、順次適用、失敗なら破棄、成功なら一度だけ保存。
- **B4 E2E:** Rust release binaryを別プロセスから起動し、逐次1操作とbatchで**保存JSONの意味とPNGの画素/alpha**を比較。保存途中失敗、途中操作失敗、同時編集、dry-run、0件、10,000件近傍、8MiB境界を確認。
- **B5 互換・速度:** Python 3.10〜3.14 wheel/sdist/install/test、Rust fmt/clippy/test/release、Python↔Rust JSON互換、Windows配布検証を維持。逐次呼び出しとの時間・メモリ・保存回数の比較は同条件で測定し、測定前に改善率を主張しません。

完了判断はIssue #64のチェックリストに従います。これは実装済みの機能説明でも、新しい利用者向けREADMEでもありません。
