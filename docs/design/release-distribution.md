# Rust CLIの単体実行ファイル配布（3 OS）の詳細設計（一部実装）

対象: [Issue #38](https://github.com/tomiya7688/dot_editor/issues/38)。先行する[#32/#33の設計](cli-alias-skill-e2e.md)（別名・SKILL.md・E2E）と、署名・出所の[供給網の設計](supply-chain-security.md)（#55）に依存します。状態: **一部実装。** CIに`Rust release (windows-x86_64 / linux-x86_64 / macos-arm64)`の3行があり、`scripts/package_rust_cli.py`が版の照合・アーカイブ作成・新しい空のフォルダへの展開・展開後のE2E・大きさとSHA-256の記録を行います。サイズ最適化は測定のうえ採用済みです（下記）。出所情報（attestation）は、pushのときに各アーカイブへ付与し、同じジョブで作成元・ソースSHA・refを検証します（PRでは権限が無いため作りません）。**未実装**: 署名（Authenticode・Developer ID）、公開（#55待ち。未署名の成果物はアップロードしません）。 現行の`windows-build`ジョブはPython製のGUI/CLI配布物（PyInstaller）で、Rust CLIの配布物ではありません。

## 背景・目的・入口

ゲームエンジンや自動化ツールは、Pythonを入れずに`pixel-cli`の実行ファイルを同梱し、プロセスとして起動します。この文書は、Windows x86_64・Linux x86_64・macOS arm64向けの配布物を、どう作り、何を検査し、何を記録するかを定めます。

利用者の入口: 配布物のアーカイブを展開し、`pixel-cli`（または`cli-anything-dot-editor`）を起動します。開発者の入口: CIの`Rust release`ジョブの結果と、ジョブの要約に出る版・target・サイズ・SHA-256です。

## 対象と配布物

| 対象 | Rustのtarget | 実行ファイル | アーカイブ |
| --- | --- | --- | --- |
| Windows x86_64 | `x86_64-pc-windows-msvc` | `pixel-cli.exe`、`cli-anything-dot-editor.exe` | `.zip` |
| Linux x86_64 | `x86_64-unknown-linux-musl` | `pixel-cli`、`cli-anything-dot-editor` | `.tar.gz` |
| macOS arm64 | `aarch64-apple-darwin` | `pixel-cli`、`cli-anything-dot-editor` | `.tar.gz` |

- Linuxはmuslの静的リンクにします。中核は外部のCライブラリに依存しない（依存はserde系のみ）ため、古いディストリビューションでも動き、glibcの版に縛られません。最初のジョブで、muslでも全テストとE2Eが通ることを確認してから採用します。通らなければgnuを使い、必要なglibcの版をアーカイブ名に記録します。
- 追加のtargetは別のIssueにします。

### アーカイブの中身と名前

名前: `hyper-dot-cli-<版>-<target>.zip`（Linux/macOSは`.tar.gz`）。展開すると、同名の1つのフォルダに次が入ります。

```text
pixel-cli[.exe]
cli-anything-dot-editor[.exe]      # pixel-cliと同じ内容の2つ目の実行ファイル（#32）
skills/cli-anything-dot-editor/SKILL.md
LICENSE
README-CLI.md                       # 配置・起動・JSON出力・終了コードの短い案内
```

コマンド表（#66）が実装されたら、同じフォルダに同梱します。tar.gzは実行権限を保持し、zipはWindows専用です。版は`rust/crates/hyper-dot-cli/Cargo.toml`の`version`、実行ファイルの`--version`と一致することを検査します。

## サイズ方針

最初は既定のreleaseの大きさ（現状、1つあたり約0.6 MB）を記録し、次の設定を1つずつ測ります: `lto`、`strip`、`codegen-units=1`、`opt-level`（`s`/`3`）、`panic="abort"`。採用の条件は(1)全テストとE2Eが通る、(2)大きさが10%以上小さくなる、(3)通しシナリオの実行時間が20%を超えて悪化しない、です。`panic="abort"`は、失敗時の巻き戻しの挙動に影響するため、保存の安全性のテストが通ることを確認します。設定は`[profile.release]`に置き、測定結果をPRに記録します。サイズのために正しさを下げません。

### 測定結果（2026-11-05、Windows x86_64 msvc、`pixel-cli.exe`）

大きさは1回のビルド結果、時間は6,000件の`pixel.paint`を`batch apply`で適用するプロセスのCPU時間（4回のうち最小。この機は他の処理で高負荷だったため、実時間ではなくCPU時間で比べました）です。

| 設定 | 大きさ（バイト） | 基準比 | CPU時間（ms） |
| --- | --- | --- | --- |
| 基準（既定のrelease） | 734,208 | — | 1,219 |
| `lto` のみ | 696,320 | −5% | — |
| `codegen-units=1` のみ | 681,472 | −7% | — |
| `opt-level="s"` のみ | 610,304 | −17% | — |
| `panic="abort"` のみ | 613,888 | −16% | — |
| `strip`のみ | 734,208 | 0%（msvcではシンボルが別ファイルのため効かない） | — |
| lto + cgu1 + strip | 668,672 | −9% | 766 |
| 上 + `opt-level="s"` | 531,968 | −27.5% | 1,172 |
| lto + cgu1 + strip + `panic="abort"`（opt-level 3） | 539,136 | −26.6% | 812 |
| 上 + `opt-level="s"` | 409,088 | −44% | 1,156 |

**採用**: `lto = true`、`codegen-units = 1`、`strip = true`、`panic = "abort"`（opt-levelは既定の3のまま）。採用条件の(2)大きさが10%以上小さい（−26.6%）、(3)通しシナリオが20%を超えて遅くならない（むしろ−33%）を満たします。`opt-level="s"`を足すと更に小さくなりますが、速度の利点を失うため採りません。`panic="abort"`は、パニックで巻き戻さず即座に終了します。このコードには`catch_unwind`がなく、保存は一時ファイルへの書き込み後の置換で、ロックはOSが自動解放するため、保存の安全性（元ファイルが壊れない）には影響しません。パニックし得る箇所（`unwrap`・`expect`・`panic!`）は、Coreの編集処理とコマンド表の生成にあり、保存処理（`project_file.rs`）と`runner.rs`には**ありません**。編集と直列化はメモリ上で保存の書き込みより前に終わるので、パニックが起きるのは常にファイルへ書き始める前で、元のファイルは巻き戻しの有無にかかわらず無傷です。パニックは不変条件の違反でだけ起き、その場合の終了値は以前も契約外（101）でした。Linux musl・macOSの大きさはCIの`Rust release`ジョブの要約に記録されます（この表はWindowsのみ）。

## CIの構成

新しいジョブ`Rust release`を、3 OSの行列として追加します（既存の`Rust Core`と`windows-build`は変えません）。

| 順 | 内容 | 失敗の意味 |
| --- | --- | --- |
| 1 | `cargo test --workspace --locked` | 製品の不具合 |
| 2 | `cargo build --release --workspace --locked` | ビルド不可 |
| 3 | 実行ファイルの煙試験: `--version`、`--help`、`project new`、`status`（`--json`） | 起動不可 |
| 4 | `scripts/e2e_rust_cli.py <ビルド出力フォルダ>` | 契約違反（別プロセスE2E） |
| 5 | アーカイブを作成し、**新しい空のフォルダへ展開して**同じE2Eを実行 | 配布物が動かない |
| 6 | 実行ファイルとアーカイブの大きさ、SHA-256をジョブの要約へ記録 | 記録漏れ |
| 7 | 出所情報（attestation）の作成と検証（pushのみ。既存の方式に合わせる） | 真正性を示せない |

- Pythonが入っていない環境での動作は、E2Eが子プロセスの環境変数を最小にして（`PATH`を空にして）実行することで確認します。検査の司令塔はPythonですが、検査対象の実行ファイルはPythonを使いません。
- アップロード: [供給網の設計](supply-chain-security.md)の公開条件（#55）が満たされるまで、`actions/upload-artifact`は使いません（既存のテストが禁止）。ビルド・検査・出所情報の作成までを行い、公開は条件が整った後に別のジョブで行います。
- 必須チェック名: 追加するジョブ名（例: `Rust release (windows-x86_64)`、`Rust release (linux-x86_64)`、`Rust release (macos-arm64)`）は、保護設定の必須チェックに加える候補として[保護設定の手順](main-protection-runbook.md)に載せます。名前は決めたら変えません。

## 利用者向けの案内

READMEには、配置・起動・JSON出力の取得・終了コードの確認の例が（#32で）入っています。配布物に同梱する`README-CLI.md`は同じ内容の短縮版です。UnityやGodot固有のコードはこのIssueの対象外です。

## 受け入れ条件（Issueの完了条件との対応）

| 条件 | 確認方法 |
| --- | --- |
| 3 OSのリリース配布物をCIで生成 | `Rust release`の3行がすべて成功 |
| Python未導入の環境で動く | 空の`PATH`でのE2E、展開後のE2E |
| 配布物そのもののE2E | 手順5 |
| 大きさをログへ記録 | 手順6 |
| #33のE2Eを配布物へ適用 | 手順5（同じスクリプト） |
| Rustのビルド・テストの必須チェックが成功 | 手順1・2 |

## 未決・リスク

- macOS用のDeveloper ID署名と公証は、アカウントの費用と本人確認が必要で、所有者の判断が要ります（供給網の設計）。署名が揃うまで、macOS配布物は「CIで生成・検査する」までで、公開しません。
- Windowsの実行ファイルは、コード署名がないとSmartScreenの警告が出ます。署名の方式は#55で決めます。
- macOSのランナーがarm64であること、Linuxのmusl静的リンクの確認は、最初のジョブの結果で確定します。
