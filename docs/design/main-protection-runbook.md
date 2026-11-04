# mainの保護設定と必須チェックの手順書

対象: [Issue #46](https://github.com/tomiya7688/dot_editor/issues/46)。必須にするチェックの意味は[Rust正本と必須ゲート](rust-canonical-and-gates.md)（#40）です。**この設定は所有者（リポジトリ管理者）が適用します。** 担当者は設定を無断で変更せず、迂回もしません（運用規則）。状態: 設計と手順の確定案。実際の設定は未適用です。

## 背景・目的

CIのジョブをワークフローに書いても、`main`への直接push、CIの無効化、チェックを通さないマージは防げません。保護設定を有効にして、必須のチェックを強制し、実際に阻止されることをテストPRで確かめます。

## 現状（2026-11-05にAPIで確認）

- `main`のブランチ保護: **なし**（`branches/main/protection`が404「Branch not protected」）。
- リポジトリのruleset: **なし**（`rulesets`が空の配列）。
- 以前は権限不足（403）で確認できませんでしたが、現在は確認できます。ただし、これは参照だけで、設定の変更を意味しません。

## 設定する内容

| 設定 | 値 | 理由 |
| --- | --- | --- |
| 対象 | 既定ブランチ（`main`） | |
| 削除の禁止 | 有効 | mainの消失を防ぐ |
| 強制pushの禁止（non-fast-forward） | 有効 | 履歴の書換えを防ぐ |
| プルリクエスト必須 | 有効 | 直接pushの禁止 |
| 必要な承認数 | **0**（現状） | 下の「承認」を参照 |
| 必須ステータスチェック | 下の表 | |
| マージ前にmain最新へ更新 | 有効（`strict`） | 古い基点での検査を信用しない |
| バイパス | なし。緊急時は所有者がrulesetを一時的に無効化し、記録を残す | |

### 必須チェック名（GitHubの画面に出る名前のとおり）

| チェック名 | 由来 |
| --- | --- |
| `Agent policy` | 担当者向け文書の制限、PR本文の様式 |
| `Declaration comments` | 宣言コメント、Pythonの整形 |
| `Rust Core` | Rustの整形・静的検査・テスト・ビルド・互換・E2E |
| `Python 3.10`、`Python 3.11`、`Python 3.12`、`Python 3.13`、`Python 3.14` | 各版のビルド・評価・回帰 |
| `windows-build` | Windows配布物の検査（ジョブ名を付けていないため、ジョブのIDがそのまま名前） |

後で追加する候補: `Rust release (windows-x86_64)`、`Rust release (linux-x86_64)`、`Rust release (macos-arm64)`（[配布の設計](release-distribution.md)、#38）。ジョブ名を変えると必須チェックが「見つからない」状態になり、PRが永久に待つか、検査が素通りします。**名前を変える変更は、保護設定の更新と同じPRで扱い、所有者が先に設定を直します。** CodeRabbitとSourceryは外部のbotで、必須にしません。

### 承認（Issueの「独立した人間の承認」について）

唯一のGitHubアカウントが作ったPRは、そのアカウント自身が承認できません。別の人間のアカウントを用意できるまでは、承認数は0にします（PRとCIの強制は有効）。これは「独立した承認を必須にした」とは表現しません。運用規則（実装担当が自己レビューして、CI成功後に自分でマージする）とも矛盾しません。別のアカウントが用意できたら、承認数を1にし、`CODEOWNERS`の指定も有効にします。

## 適用の手順

所有者がGitHubの設定画面（Settings → Rules → Rulesets）で作成するか、次のAPI呼び出しで作成します。

```bash
gh api repos/tomiya7688/dot_editor/rulesets -X POST --input ruleset.json
```

```json
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {"context": "Agent policy"}, {"context": "Declaration comments"},
        {"context": "Rust Core"}, {"context": "Python 3.10"},
        {"context": "Python 3.11"}, {"context": "Python 3.12"},
        {"context": "Python 3.13"}, {"context": "Python 3.14"},
        {"context": "windows-build"}]}}
  ]
}
```

適用前に、GitHub Actionsの直近の実行で上のチェック名がすべて表示されていること（`gh pr checks <番号>`）を確かめてください。

## 検証（テストPR）

設定後、次を確認し、結果を#46へ記録します。

| 確認 | 期待 |
| --- | --- |
| mainへ直接pushする | 拒否される（確認は作業用の空コミットで行い、成功したら取り消す） |
| 必須チェックを1つ失敗させたPR（例: 宣言コメントの欠落） | マージボタンが無効で、`gh pr merge`が失敗する |
| 全チェック成功のPR | マージできる |
| 古い基点のPR | 更新するまでマージできない |
| `ruleset`の画面とAPIの出力 | 設定のとおり（スクリーンショットまたはAPI出力を記録） |

## 戻し方と記録

問題があればrulesetを無効化（`enforcement: "disabled"`）してから原因を直します。変更のたびに、日付、変更者、変更前後の内容、検証の結果を#46に残します。設定が適用されていない間は、保護を有効化済みと表現しません。
