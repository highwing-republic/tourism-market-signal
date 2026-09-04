# 観光株シグナル / Tourism Market Signal

観光・インバウンド関連50銘柄を毎営業日監視し、「今日、追加調査する価値が生まれた企業」を5社に絞るMVPです。株価予測や売買自動化を行うものではありません。

## MVPの機能

- yfinanceで国内50銘柄と市場・為替・原油・海外航空株を分離取得
- 一括取得で欠けた系列は個別に再取得し、`repair=True/False` を切り替えて再試行
- 騰落率、MA20/MA60、RSI、20日ボラティリティ、出来高比を計算
- `attention_score` と前回レポートとの差を表す `change_score` を分離
- TOP10入り、順位急変、MA20クロス、出来高2倍、連続上昇、20日高値を検知
- 上位候補だけをGeminiへ送り、Pydantic Structured Outputsで検証
- `data/latest.json` と `data/history/YYYY-MM-DD.json` を保存
- `docs/index.html` と銘柄詳細ページを直接生成（Hugo不使用）
- GitHub Actionsで日本時間の平日7:30に自動実行

DuckDB、観光統計、企業IR、バックテストはMVPの対象外です。

## スコア

`attention_score` は銘柄間の相対評価です。

| 要素 | 比率 |
|---|---:|
| 20日モメンタム | 30% |
| 5日モメンタム | 20% |
| MA20乖離 | 15% |
| MA60乖離 | 10% |
| 出来高比 | 10% |
| インバウンド関連度 | 15% |

RSIは点数へ混ぜず、「売られ過ぎ / 弱い / 中立 / 強い / 過熱」の状態として表示します。外部ドライバーも銘柄スコアとは分離します。

`change_score` は2回目以降、順位・注目度の変化、TOP10入り、MA20クロス、出来高急増、20日高値、連続上昇から0〜100で計算します。初回は0です。

## Windows 11でのセットアップ

PowerShellでリポジトリ直下を開きます。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` の `GEMINI_API_KEY` にGoogle AI StudioのAPIキーを設定します。未設定でも定量分析・JSON・HTML生成は動き、AI分析だけを省略します。

```powershell
python scripts\validate_universe.py
python -m pytest -q
python main.py
```

生成後は `docs/index.html` をブラウザで開いて確認できます。

## GitHub Pagesと自動実行

1. `Settings → Pages` でSourceを「Deploy from a branch」、Branchを `main`、Folderを `/docs` にします。
2. `Settings → Secrets and variables → Actions` に `GEMINI_API_KEY` をRepository secretとして登録します。
3. Actionsから `Daily tourism market signal` を手動実行し、初回レポートを確認します。

定期実行は `30 22 * * 0-4`（UTC）、日本時間では月曜〜金曜の7:30です。祝日判定はせず、休場日は直近取引日のファイルを更新します。

## 構成

```text
app/                    データ取得・指標・スコア・AI・保存・HTML生成
config/universe.csv     監視する50銘柄
config/drivers.yml      外部ドライバー
data/latest.json        最新スナップショット（初回実行で生成）
data/history/           日次JSON
docs/                   GitHub Pages公開領域
tests/                  指標・スコア・差分・HTML/JSONテスト
main.py                 日次処理の入口
```

## 注意事項

- 本プロジェクトは投資調査支援用で、投資助言・売買推奨ではありません。
- yfinanceは非公式ライブラリです。公開・商用利用ではデータ提供元の利用条件を確認してください。
- 取得不能な市場指標が残った場合はActionsログへ該当ティッカーを表示し、取得済みデータだけでレポートを継続します。
- AI出力は必ず一次情報で検証してください。
- 最初の3か月は仮想ポートフォリオなどでシグナル品質を検証することを推奨します。
