# Rust CLI 同時更新・保存安全性の詳細設計（一部実装）

対象: [Issue #63](https://github.com/tomiya7688/dot_editor/issues/63)。本書は実装のための契約案です。**実装済み**: `result.revision`、`--if-revision`（`revision_conflict`）、`--lock-timeout-ms`（`project_busy`）、sidecarロック、一意な一時ファイル、置換禁止の原子的な新規作成、同一ファイル判定による書き出し拒否。**未実装**: `unsafe_path`の網羅（symlink・hardlinkの書込経路の拒否）、`commit_uncertain`、OS別の耐久性（親フォルダ同期）と権限の検証、障害注入テスト、macOS/Windowsでの実機確認。外部CLIの既存契約は[CLI契約](../CLI契約.md)を正本とします。ここでは複数ゲーム開発ツールが同じJSON作品を操作するときの更新消失を防ぎます。

## 背景・入口・非対象

現行の`project_file.rs`は、作品を読み込んで編集した後、PID由来の一時名へ書き、`fs::rename`で置換します。`runner.rs`の読込→編集→保存には排他区間がなく、別プロセスが間に保存すると後勝ちになります。原子的な置換と、編集全体の競合検出は別の機能です。

入口は`pixel-cli --json -p art.json status`によるrevision取得と、`pixel-cli --json -p art.json --if-revision sha256:<64文字のhex> pixel paint ...`です。従来のコマンド、終了値0/1/2、JSON v2、Python参照実装との意味的互換性を維持します。

対象外: 協調しない外部アプリまで含むグローバルな直列化、ネットワークファイルシステムでの保証、永続Undo、作品のJSON形式へのrevisionフィールド追加、バッチ操作の実装（[#64](https://github.com/tomiya7688/dot_editor/issues/64)）。

## 正本・revisionの定義

- revisionは**現在のディスク上のJSONの生バイト列**のSHA-256で、表記は`sha256:` + 小文字16進64文字。JSONのキー順・空白が変わっても別revisionとなります。描画意味の同一性を表すIDではありません。
- `status`と`project info`の`result.revision`へ読み込んだスナップショットのrevisionを追加します。既存の`result`項目は削除しません。存在しない作品にrevisionはありません。
- 変更コマンドと`project new --force`は共通`--if-revision`を受け付けます。指定されたrevisionがロック取得後の生バイト列と違う場合、編集も保存も行わず`revision_conflict`（exit 1）を返します。存在しないファイルに既存revisionを要求した場合も競合です。形式が不正な引数は`usage`（exit 2）。
- 未指定の場合でも、**同じCLIの協調プロセス間**はロック下で再読込して編集を順次適用します。外部の非協調ライターがロックを無視して書き換えた場合の完全防止は主張しません。
- 一切変更しないコマンドでは旧バイト列・mtimeを維持し、`saved=false`にします。確定した保存後のrevisionは確定したバイト列から取得します。

## ロックの所有とパスの正規化

1. まず対象の親ディレクトリを正規化し、既存ファイルの実体と種類を確認します。相対/絶対パス・`.`/`..`・OSごとの大文字小文字・Unicode表記・別名の扱いを明示し、**異なる文字列で同じ作品が別ロックを取得できない**ことをテストします。
2. 協調するプロセスは正規化した同一作品キーのsidecar lockにOSの**自動解放されるファイルロック**を取得します。ロックファイルはプロセス終了のたびに削除しません（削除と再作成の競合を回避）。単なる存在チェックや古いロックファイルの削除をロック代わりにしません。
3. ファイル自身のsymlink・複数hardlinkなど、作品同一性を安全に判定できない書込経路は原則として拒否します。安全と実証したOS別の取り扱いのみ許容します。ディレクトリ・デバイスなど通常ファイル以外は拒否します。
4. ロックは**読込より前に取得し、保存確定/失敗処理が済むまで保持**します。取得タイムアウトの既定は5秒、`--lock-timeout-ms`は0〜60000の整数を提案します。取得できなければ`project_busy`（exit 1）。
5. 読取専用の`status`等は、atomic replaceされたファイルの完全なスナップショットを読みます。読取時点と後続編集時点の一致が必要な呼び出し側は`--if-revision`を使用します。
6. `--dry-run`は新しいlock sidecarや一時ファイルを作成せず、スナップショット上で同じ入力/操作検証を行います。結果は**予約された編集成功**ではありません。既存lockがある場合も含め、作品やlockの内容・mtimeを変えません。

## 保存トランザクション（協調プロセス）

```text
入力検証
 → パス同一性検証
 → lock取得（編集時）
 → ロック下でファイル再読込 + raw SHA-256
 → --if-revision検証
 → Rust Coreで編集・全不変条件検証
 → 変更なしなら書込なし
 → 同じ親ディレクトリへ衝突しないtmpを排他的に作成
 → 全バイト書込・flush・fsync
 → 既存ファイルの権限/ACL等の扱いを検証
 → OS別のatomic replaceまたはatomic no-clobber create
 → OSが対応する場合は親ディレクトリの同期
 → lock解放、JSON結果
```

- 一時名はPID単独で決めず、一意性を確保し`create_new`相当で原子的に作成します。既存のtmpやsymlinkを開いて切り詰めません。
- `project new`（`--force`なし）は**同一作品キーのロックに加えて、置換禁止の原子的作成**を使います。存在確認だけで後から`rename`する処理は禁止です。`--force`はロック下で存在・revisionを再検証します。
- POSIXとWindowsでは置換/ディレクトリ同期のAPIと保証が異なるため、実装候補のライブラリ・システム呼び出しは**各OSの実テストで決める**こととします。`std::fs::rename`を無条件のクロスOS耐久性保証と見なしません。
- 確定前の失敗では元ファイル不変を確認しtmpを掃除します。**rename/置換後に同期等が失敗した場合は、ファイルが既に変更された可能性があるため`commit_uncertain`とし、旧状態維持を約束しません。** 呼び出し側はrevisionを読み直してから再試行します。
- メタデータ（権限/ACL）、同じファイルを指す別名、親ディレクトリのアクセス権、クラッシュ後のtmp回収方針をOS別に検証します。保証できない環境は安全側に拒否し、契約上の制限を明示します。
- PNG exportは作品ファイルと書き出し先が実際に同一なら拒否します。symlink・hardlink・相対/絶対を含む同一性確認を、単なる`Path`文字列比較で済ませません。

## エラー契約（追加提案）

| 状態 | error | exit | 作品に対する保証 |
| --- | --- | --- | --- |
| 期待revisionの不一致 | `revision_conflict` | 1 | 保存なし |
| 取得期限までロックできない | `project_busy` | 1 | 保存なし |
| 危険なパス・同一性不明 | `unsafe_path` | 1 | 保存なし |
| 置換後の確定状態が不明 | `commit_uncertain` | 1 | 変更された可能性あり。再読込必須 |
| 一時ファイル生成/確定前I/O失敗 | `io_error` | 1 | 元ファイル不変 |
| 引数のrevision表記不正 | `usage` | 2 | 保存なし |

既存の`status/operation/project/result/dry_run/saved`とエラーの`status/operation/error/message`を維持し、追加フィールドは後方互換の形で入れます。

## 実装単位・検証計画

- **C1** `project_file.rs`の一意tmp、上書き禁止作成、パス同一性/OS別置換、障害注入を分割実装。ソース機能の変更とコメントを一致させる。
- **C2** `GlobalOptions`へ`--if-revision`とlock timeout、`report`へrevision/新エラーを追加。既存JSON成功/失敗スキーマの回帰テスト。
- **C3** `runner.rs`に編集時のロック所有者（guard）を導入し、読込から確定までの排他境界を単一経路へまとめる。
- **C4** 2つの実`pixel-cli`プロセスへバリアを挿入し、競合/revision・順次編集・同時新規作成・kill・disk full相当・失敗注入・`dry-run`・同一ファイル別名を検証する。
- **C5** Ubuntu/Windows/macOSで実ファイルを使って動作を確認。公開JSON v2をPythonで往復し、画素/レイヤー/保持細部/PNGが一致することを確認する。

完了条件はIssue #63。成功例だけでなく競合・失敗注入の根拠をPRへ記録してください。既存Python 3.10〜3.14とRustの必須CIは維持します。
