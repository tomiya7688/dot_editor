# Pythonの信頼ストア更新（#54）と成果物の署名・出所の検証（#55）の設計

対象: [Issue #54](https://github.com/tomiya7688/dot_editor/issues/54)（証明書インシデント対応）、[Issue #55](https://github.com/tomiya7688/dot_editor/issues/55)（署名とArtifact Attestation）。利用者向けの検証手順は[成果物の検証](../成果物の検証.md)が正本です。Windowsの署名検査の入口は進行中の[PR #61](https://github.com/tomiya7688/dot_editor/pull/61)（ドラフト）で扱います。配布物の構成は[配布の設計](release-distribution.md)です。状態: #54は実装の大部分が済み、環境ごとの確認記録が残りです。#55はチェックサムと出所情報（attestation）が済み、コード署名と公開条件の仕組みが未実装です。

## 背景・目的

Pythonの周辺ツールが信頼する証明書の取り扱いに関するインシデントがあり、古い環境が問題のある信頼経路を残している可能性があります（#54）。また、配布する成果物は、誰がどの手順で作ったかを利用者が確かめられる必要があります（#55）。

## Part A: Pythonの信頼ストア（#54）

### 実装済み

- `scripts/python_trust.py`: 版の下限（pip 26.2.2、certifi 2026.10.19、uv 0.13.4、sigstore 4.5.1）の確認と更新、`certifi.where()`の実体とCA束の確認、対象のルート証明書（SHA-256 `86a1ecba…`）が信頼されないことの確認（`--check`）。
- `scripts/prepare_ci_ca.py`: GitHub提供のUbuntuランナー上だけで、対象のルートを無効化して再生成。ローカルPCやself-hostedでは実行しない。
- `scripts/prepare_ci_windows_ca.ps1`: Windowsランナー用。
- CIの各ジョブ（`Declaration comments`、`Rust Core`、`Python 3.10`〜`3.14`、`windows-build`）の初めに実行。テストは`tests/test_python_trust.py`、`test_prepare_ci_ca.py`、`test_windows_ci_ca.py`。

### 残りの確認（Issueの完了条件）

環境ごとに、次の項目を記録します。記録がない環境は「未確認」として扱い、確認済みと書きません。

| 環境 | 確認すること |
| --- | --- |
| ローカルの`.venv`、`.venv-atlas`（開発者のPC） | `python --version`、`python -m pip --version`、`certifi`の版と`certifi.where()`、対象ルートが信頼されない、uv/sigstoreの有無と版 |
| CIの各ランナー（毎回新しい環境） | 上の確認が`python scripts/python_trust.py --check`で通っていること（ログのURL） |
| 配布物に同梱のPython（`dist`の`_internal`内のcertifiなど） | 同梱のcertifiの版とCA束。PyInstallerでビルドした環境のpip/certifiが下限以上であること |
| uv / sigstore | 使っていなければ「未使用」と根拠を記録。使っていれば版 |

記録の様式（Issueのコメントに表で残す）: 日付、環境、Pythonの版、pip/certifi/uv/sigstoreの版、`certifi.where()`のパス、対象ルートが信頼されない確認の結果、確認者。古い束が残っていた環境は、更新して再構築した後で再確認し、その結果も記録します。依存の固定（`requirements-build.txt`、`pyproject.toml`）に下限を下回る固定がないことは、`python_trust.py`の下限（`MINIMUMS`）とテストで保ちます。

## Part B: 成果物の署名と出所（#55）

### 成果物の一覧と方式

| 成果物 | 現状 | 方式 | 状態 |
| --- | --- | --- | --- |
| `HyperDotEditor-windows-x64.zip`、wheel、sdist、`SHA256SUMS` | CIで作成。公開はしない | SHA-256、GitHub Artifact Attestation（OIDCのkeyless）をpushで作成・検証 | 実装済み |
| 上のZIP内のEXE/DLL/PYD | 未署名 | Authenticode署名＋RFC 3161タイムスタンプ、検査は`PR #61` | 検査は進行中、署名は未実装 |
| Rust CLIのアーカイブ（3 OS） | 未作成（[#38](release-distribution.md)） | SHA-256、attestation。Windowsは実行ファイルのAuthenticode | 未実装 |
| macOS向け成果物 | 未作成 | Developer ID署名＋公証 | 未実装。アカウントが必要 |
| Android・コンテナ・パッケージレジストリへの公開 | 対象の成果物なし | 該当したときに、Issueの該当節に従って追加 | 対象外 |

### 公開の関門（リリースゲート）

公開（GitHub Releaseへのアップロード、利用者への配布）の条件を、次のとおりに定めます。**どれかが満たせない成果物は公開しません。**

1. 成果物が`SHA256SUMS`に載り、`SHA256SUMS`自身のattestationが検証できる（`gh attestation verify --signer-workflow … --source-ref … --deny-self-hosted-runners`）。
2. 各成果物のattestationが検証できる。
3. Windowsの実行ファイルは、Authenticode署名とタイムスタンプが有効（`PR #61`の検査）。macOSは署名と公証が有効。
4. 鍵・証明書・パスワードがリポジトリ、ログ、成果物のいずれにも無い。

実装案: 検査をまとめた入口`scripts/verify_release_artifacts.py <フォルダ>`を作り、既存の`artifact_checksums.py`とPR #61の検査を呼びます。公開用のジョブ（タグが付いたときだけ動く）は、この入口が成功してからアップロードします。PRや通常のpushのジョブは、アップロードをしないままです（既存のテストが`actions/upload-artifact`を禁止しているため、公開用ジョブは別のワークフローに分け、その時点でテストの方針を更新します）。

### 秘密情報

- 署名用の鍵・PFX・keystoreをリポジトリへ置きません。署名の資格情報は、GitHubの暗号化された秘密と、必須の承認者を付けた保護された環境（environment）に置くか、クラウドの署名サービスにOIDCで接続します。
- フォークのPRには秘密を渡しません。署名ジョブはmainのタグからだけ動かします。
- ログに資格情報を出さない（マスクと、署名コマンドの出力確認）。

### 所有者の判断が必要なこと

次は費用・本人確認・契約を伴うため、実装担当が決めません。

1. Windowsのコード署名の方式（証明書の購入か、クラウドの署名サービスか）。署名が決まるまで、Windowsの実行ファイルは公開しません。
2. macOSのDeveloper ID（Appleの開発者プログラム）。署名が決まるまで、macOS向け成果物は公開しません。
3. 過去の成果物の扱い: GitHub Actionsのartifactが87件残っています（最新の確認は2026-11-05。いずれも署名・出所の検証が整う前に作られた、未署名のWindows配布物とCIの記録）。公開リリースとタグは**ありません**。削除は取り消せないため、削除するかどうか、保持期間を短縮するかを所有者が決めます。決まるまで、これらを「未署名・検証不可」として扱い、利用者へ案内しません。

### 完了条件との対応

| 条件 | 状態 |
| --- | --- |
| 生成・公開する成果物の種類を列挙 | 上の一覧 |
| 方式を実装 | 一部（チェックサムとattestation）。署名は未実装 |
| 最終成果物のSHA-256と真正性の検証 | Windows ZIP・wheel・sdist・`SHA256SUMS`は実装済み |
| CIで署名・attestationの検証 | attestationは実装済み。署名の検証はPR #61 |
| 秘密情報がリポジトリにない | 現状なし。署名導入時に保つ |
| 利用者向けの検証手順 | `docs/成果物の検証.md`に記載 |
| 現行の公開成果物の対応状況 | 公開リリースなし。Actions artifactの扱いは所有者の判断待ち |
