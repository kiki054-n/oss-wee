# Wall of Hands 仕様書 v0.1
### OSW（オッスウィー）相互信用台帳 — 波と粒のレジャー設計

> 測定するまで、答えは誰にも分からない。
> だからこそ、私たちは誰かと「対等に握手をする」とき、その不確定さのすべてを背負うという覚悟（責任）を同時に負うことになる。
> — 『オオカミたちの狼煙』第4章

---

## 0. 前提：この仕様書が解決したいこと

OSWの約束ごとは3つある。

1. 頂点を作らないこと
2. 源を独り占めしないこと
3. 情報を、ひとりで使わないこと

これを台帳（信用システム）として実装しようとした瞬間、既存の金融システムが持つ「発行体（中央銀行）」や「格付け機関（信用スコア企業）」という**頂点**を、どうしても呼び戻してしまいがちになる。

Wall of Handsは、この頂点を作らずに「誰が誰をどれだけ信用しているか」を記録するための構造である。核となる発想は、`オオカミたちの狼煙` で語られた量子論的信頼モデル——**信頼は測定される前は「波（可能性）」であり、測定された瞬間にのみ「粒（事実）」になる**——を、そのままデータモデルに落とし込むことである。

---

## 1. 用語定義

| 用語 | 定義 |
|---|---|
| **Hand（手）** | 台帳に参加する主体。個人・チーム・プロジェクトいずれも可。中央発行体ではなく、すべてのHandは対等（頂点なし）。 |
| **Reach（差し伸べ）** | あるHandが別のHandに対して信用枠（貸し・貢献・約束）を宣言する行為。この時点では**まだ何も確定していない＝波の状態**。 |
| **Grip（握手）** | ReachがWaveのまま放置されず、実際の取引・履行・不履行という具体的な出来事にぶつかった瞬間。**これが「測定」にあたる**。 |
| **Collapse（収縮）** | Gripの結果、ReachがBond（信頼の粒）かBreach（裏切りの粒）のどちらか一方に確定すること。一度Collapseした記録は不変（immutable）。 |
| **Witness（証人）** | Collapseの瞬間に居合わせ、それを記録に残す第三者以上のHand。「ひとりで使わない」原則を、測定行為そのものに適用したもの。 |
| **Wall（壁）** | すべてのHandのReach/Collapse履歴が並ぶ、追記専用（append-only）の公開台帳。 |

---

## 2. 状態遷移モデル

```
                 ┌─────────────┐
   Reach 宣言    │             │   Grip（測定イベント）が起きるまで
  ───────────▶   │  WAVE 状態   │   ずっとここに留まる。
                 │ （未確定信用） │   誰にも「正解」は分からない。
                 └──────┬──────┘
                        │
                Grip（履行 or 不履行という事実が発生）
                        │
                        ▼
              ┌─────────┴─────────┐
              │                   │
         BOND（粒）           BREACH（粒）
       ＝信頼が実証された    ＝裏切りが確定した
       ・不変（改ざん不可）   ・不変（改ざん不可）
       ・Wallに追記          ・Wallに追記
```

重要な設計原則：

- **WAVE状態のReachは、信用スコアの計算に使わない。** 「可能性」を「事実」として扱うことが、まさに既存の信用スコア産業が犯している誤りだから。
- **Collapseは一方向のみ。** BondからBreachへ、あるいはその逆への書き換えは存在しない（過去の測定結果は消えない＝歴史の否認を許さない）。ただし新しいReach→新しいGripは何度でも積み重ねられる。
- **Witnessが最低1人（本人たち以外）いないGripは、"仮収縮（Provisional Collapse）"として区別する。** 完全な収縮への昇格には、後から誰かがWitnessとして署名する猶予期間を設ける。

---

## 3. データモデル（最小実装案）

```json
// Hand — 参加者
{
  "hand_id": "hand:kiki054-n",
  "display_name": "キキ",
  "created_at": "2026-07-02T00:00:00Z"
}

// Reach — 波の状態の信用宣言
{
  "reach_id": "reach:0001",
  "from": "hand:kiki054-n",
  "to": "hand:someone",
  "declared_value": "3日分の翻訳作業を貸す",
  "declared_at": "2026-07-02T00:00:00Z",
  "state": "wave"
}

// Grip — 測定イベント（収縮のトリガー）
{
  "grip_id": "grip:0001",
  "reach_id": "reach:0001",
  "occurred_at": "2026-07-10T00:00:00Z",
  "outcome": "bond",          // "bond" | "breach"
  "evidence": "成果物URLまたは説明文",
  "witnesses": ["hand:third-party-1"],
  "provisional": false
}

// Wall entry — 台帳への追記（Grip確定後に自動生成、以後不変）
{
  "wall_id": "wall:0001",
  "grip_id": "grip:0001",
  "recorded_at": "2026-07-10T00:05:00Z",
  "immutable": true
}
```

各HandのReachとGripを辿ることで、「このHandは波をどれだけ粒に変えてきたか（Bond化率）」は導出できる。ただし——

> **この比率を単独のスコアとしてランキング化しないこと。**
> それをやった瞬間、Wall of Handsは頂点を持つ信用スコアシステムに逆戻りする。比率は「参考情報」であって「格付け」ではない。

---

## 4. ガバナンス：誰が「測定」を行うのか

これがこの仕様における最大の論点である。中央の格付け機関を置かない以上、「これはBondだ／Breachだ」という判定は誰が下すのか。

提案する原則は次の3層構造：

1. **第一層：当事者間の合意。** ReachのfromとtoのHandが両者ともに同じoutcomeを申告した場合、それをそのままGripとして確定する（最も軽い手続き）。
2. **第二層：Witness立会い。** 当事者間で見解が割れた場合、事前に指定されたWitness（または任意の第三者Hand）が事実（evidence）を確認し、Gripを記録する。
3. **第三層：仮収縮からの時効確定。** 誰もWitnessしないまま一定期間（例：30日）経過した場合、"provisional"のまま記録は残るが、Bond/Breachいずれの側の計算にもカウントしない。**「誰も見ていない出来事は、粒にならない」**——これは量子論的信頼モデルへの忠実さそのものである。

---

## 5. Witness UI：GitHub Issue/PRコメントの流用（実装済み）

新しいアプリやサーバーを作らず、GitHubそのものを「壁」として使う設計。

### 5.1 Gripの宣言＝Issueの作成

`.github/ISSUE_TEMPLATE/grip.yml` のIssue Formを使ってIssueを立てると、それがそのままGripの宣言になる。作成された時点では自動的に `provisional`（仮収縮）として扱われる。

フィールド：`Reach ID` / `From Hand ID` / `To Hand ID` / `Occurred At` / `Outcome` / `Evidence`

### 5.2 Witness署名＝コメント

当事者(from/to)以外のHandが、そのIssueに次の形式でコメントする。

```
/witness hand:xxxxxxxx
```

`.github/workflows/witness-sign.yml` が `issue_comment` イベントを検知し、`wall-of-hands/scripts/witness_bot.py` を実行する。このスクリプトは：

1. コメント投稿者の実際のGitHubアカウントを `wall-of-hands/hands-github-map.json` と突き合わせ、コメントで名乗ったHand IDとの一致を検証する（なりすまし防止）。
2. 当事者(from/to)自身によるWitness署名を拒否する。
3. 既に確定済み（`provisional: false`）のGripへの再署名を拒否する（不変性の担保）。
4. 有効なWitnessが1名以上そろった時点でGripを確定し、`wall-of-hands/data/wall.jsonl` に不変の1行として追記し、Issueをクローズする。

途中経過（未確定のGrip記録）は `wall-of-hands/data/grips/grip-issue-<番号>.json` に保存される。

### 5.3 新しいHandの参加方法

`wall-of-hands/hands-github-map.json` にPRで1行追加する。中央の承認者を置かないため、このPR自体もWall of Handsの外側にある通常のGitHubレビュープロセス（＝コミュニティの合意形成）に委ねられる。

---

## 6. 次のステップ（提案）

- [x] `oss-wee` リポジトリ内に `wall-of-hands/` ディレクトリを新設し、本仕様書を配置
- [x] 上記JSONスキーマをJSON Schema形式（`.schema.json`）として正式化
- [x] WAVE→GRIP→COLLAPSEの状態遷移を検証する最小限のPythonスクリプト（`validate_grip.py`）を試作
- [x] Witness機能の最小実装として、GitHub Issue/PRのコメント機能をWitness署名の代替UIとして流用
- [ ] `provisional` のまま30日経過したGripを自動的に失効させる定期実行ワークフロー（`schedule` トリガー）の追加
- [ ] 複数Witnessが必要な高額Reach（閾値は要議論）向けの、署名者数の可変しきい値対応

---

*本仕様書はv0.1（たたき台）。実装しながら、量子論的比喩と実際の運用のズレを継続的に埋めていくことを前提とする。*
