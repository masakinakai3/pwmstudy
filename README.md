# 三相2レベルPWMインバータ学習シミュレータ

三相2レベル電圧形PWMインバータの原理を対話的に学習するためのシミュレーションソフトウェアです。

> **プロジェクト名 `3lvlpwm` について**: 名称の「3lvl」は線間電圧が $\{-V_{dc}, 0, +V_{dc}\}$ の **3値** を取ることに由来します。インバータのトポロジは **2レベル** です（NPC等の3レベルインバータではありません）。
desktop UI は 6 段構成で指令信号・スイッチングパターン・線間電圧・相電圧・負荷電流・FFT を表示し、web UI は主要 4 セクションで指令信号・スイッチングパターン・電圧・電流・FFT を表示します。

## 特徴

- **Desktop 6段 / Web 4セクション**: desktop UI は 変調信号+キャリア / スイッチングパターン / 線間電圧 / 相電圧 / 相電流 / FFT、web UI は主要 4 セクションを表示
- **8パラメータスライダー + 変調選択**: 三角波比較 / 三角波比較(三倍高調波) / 三角波比較(二相変調) / 空間ベクトル / 空間ベクトル(二相変調) の 5 方式を切替可能。サンプリング方式は Natural 固定
- **FFT表示切替**: 線間電圧 v_uv と相電流 i_u を切替表示、Hann / Rectangular 窓も選択可能
- **Web UI**: ブラウザから 8 パラメータ、変調方式、Overmod View、FFT 表示対象を変更可能
- **FastAPI API**: `/health`, `/scenarios`, `/simulate`, `/sweep` を公開し、web UI と外部クライアントの双方から利用可能
- **FFT解析 + THD表示**: desktop UI は基本波とキャリア高調波を色分けし、desktop/web の双方で V1_LL,pk（v_uv 基本波ピーク）/ I1_u,pk（i_u 基本波ピーク）/ RMS / THD / 基本波力率を確認可能
- **変調率モニタ**: $m_a$ 値を常時表示、過変調時にはクランプ警告
- **理論比較表示**: 相電流の基本波振幅を理論値と FFT 実測値で比較
- **定常状態表示**: 助走区間（5τ以上）を自動計算し、定常波形のみを表示
- **厳密離散 RL ソルバ**: 区分定数の相電圧入力に対し、解析解ベースの離散時間更新で電流を計算
- **非理想インバータモデル**: デッドタイムと固定導通電圧降下を含む簡易実機近似を切り替え可能
- **標準方式比較**: 三角波比較、三角波比較(三倍高調波)、三角波比較(二相変調)、空間ベクトル、空間ベクトル(二相変調) を同一UIで比較可能

## 動作環境

- Python 3.10 以上
- OS: Windows / macOS / Linux

## セットアップ

```bash
pip install -r requirements.txt
```

依存ライブラリ: NumPy, Matplotlib, Pydantic, pytest, FastAPI, Uvicorn, httpx

## 実行

### desktop UI

```bash
python main.py
```

### web UI / API（直接起動）

```bash
python -m uvicorn webapi.app:app --reload
```

起動後は次を利用できます。

- web UI: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### web UI / API（Docker）

Docker がインストールされた環境では、1 コマンドで起動できます。事前に Python 環境や依存パッケージのインストールは不要です。

```bash
docker compose up --build
```

起動後は [http://localhost:8000/](http://localhost:8000/) を開くだけで利用できます。

| コマンド | 内容 |
| --- | --- |
| `docker compose up --build` | イメージビルドと起動 |
| `docker compose up -d` | バックグラウンド起動 |
| `docker compose down` | 停止 |
| `docker compose logs -f` | リアルタイムログ |

> **Web UI の外部依存**: 現在の web UI は Plotly を `cdn.plot.ly` から読み込みます。閉域環境や完全オフライン環境では、Plotly 資産を `webui/` 配下へ同梱する追加対応が必要です。
> **デスクトップ版の位置付け**: `python main.py` による desktop UI は並行維持されます。Docker コンテナには desktop UI は含まれません。

## テスト

```bash
python -m pytest tests/ -v
```

物理妥当性検証・application 層・API/UI 疎通のテストが実行されます。

## プロジェクト構成

```text
3lvlpwm/
├── main.py                      # エントリポイント（デフォルトパラメータ一元管理）
├── application/                 # UI/API 共有の application 層
│   ├── modulation_config.py     # 単一 modulation_mode と内部3軸の定義・正規化
│   ├── simulation_runner.py     # シミュレーション統合処理
│   ├── simulation_service.py    # 単位変換・export・baseline サービス
│   └── scenario_presets.py      # 学習シナリオ共有定義（desktop/web 共用）
├── simulation/                  # シミュレーションエンジン（純粋関数）
│   ├── reference_generator.py   # 三相指令信号生成
│   ├── carrier_generator.py     # 三角波キャリア生成
│   ├── pwm_comparator.py        # PWMスイッチングパターン生成
│   ├── inverter_voltage.py      # インバータ出力電圧演算
│   ├── rl_load_solver.py        # RL負荷電流演算（厳密離散時間解）
│   └── fft_analyzer.py          # FFTスペクトル解析 + RMS/THD計算
├── ui/
│   └── visualizer.py            # Matplotlib波形表示UI（6段+変調方式選択+FFT切替+理論比較）
├── webapi/
│   ├── app.py                   # FastAPI アプリ（/, /health, /scenarios, /simulate, /sweep）
│   └── schemas.py               # API 入力スキーマ
├── webui/
│   ├── index.html               # Web UI
│   ├── styles.css               # Web UI スタイル
│   └── app.js                   # Web UI ロジック
├── tests/
│   └── test_simulation.py       # 物理妥当性 + application/API/UI テスト
├── docs/
│   ├── deep_math_guide.md       # 数式詳解（ZOH 離散ソルバ・SVPWM・THD・Clarke/Park）
│   ├── user_guide.md            # 操作手順と学習のポイント
│   ├── web_api_contract.md      # API 契約（application 層・REST・Web UI 間）
│   └── assets/                  # SVG 図版（12 ファイル）
├── Dockerfile                   # Web API 単体コンテナ
├── docker-compose.yml           # Docker Compose 起動定義
├── architecture.md              # アーキテクチャ設計書
├── implementation_plan.md       # 実装計画書（STEP 1〜8）
├── improvement_plan.md          # 改善ロードマップ（完了項目の記録）
├── web_migration_plan.md        # Web ベース移行案
├── CHANGELOG.md                 # 変更履歴
├── LICENSE                      # MIT License
├── requirements.txt             # フル依存（desktop + web）
└── requirements-web.txt         # Web/Docker 専用軽量依存
```

## Web UI

現時点の web UI は次の構成です。

1. 8 パラメータ入力
2. 変調方式 / FFT 切替
3. 学習シナリオガイド
4. 理論比較パネル
5. ベースライン条件比較
6. 実務チェックパネル
7. 学習進捗トラッカー
8. JSON読込 / JSON保存 / PNG保存 / 共有URLコピー
9. 主要 4 セクション表示

主要 4 セクションは次のとおりです。

1. 変調信号 + キャリア
2. スイッチングパターン
3. 線間電圧 / 相電圧
4. 相電流 / FFT

学習シナリオは desktop UI と共有定義です。ベースライン設定後は相電圧基本波と相電流を点線で比較できます。Web UI では、Section 3 を「線間電圧の PWM ステップ観察」と「相電圧の基本波比較」に分け、線間電圧側は v_uv を既定表示、v_vw と v_wu はトグルで追加表示できるようにしました。スイッチングと線間電圧の急峻な遷移を見やすくするため切替点保持圧縮した補助系列を使って描画します。

### αβベクトル図の理論背景（空間ベクトル）

空間ベクトル表示では、三相指令 $(v_u, v_v, v_w)$ を Clarke 変換して
$\alpha$-$\beta$ 平面へ写像しています。

$$
v_\alpha = \frac{2}{3}\left(v_u - \frac{1}{2}v_v - \frac{1}{2}v_w\right),
\quad
v_\beta = \frac{2}{3}\left(\frac{\sqrt{3}}{2}(v_v - v_w)\right)
$$

平衡三相の正弦指令では、理想的に軌跡は円になります。
二相変調（DPWM）では零相オフセットを加えて一部区間をクランプしますが、
零相成分は三相に共通に加わるため、$\alpha$-$\beta$ の基本軌跡そのものは理論上同じです。

空間ベクトル図は参照波と同じ変調信号正規化で描画し、アクティブベクトル $V_1$〜$V_6$ は半径 $4/3$ の六角形として表示します。

過変調観察（Overmod View）では選択中方式の線形上限を超える領域まで確認できるように、
Web UI のベクトル図レンジを次のように切り替えています。

- Overmod View OFF: $\pm 1.5$
- Overmod View ON: $\pm 2.2$

これにより、線形変調範囲外でベクトルが外側へ広がる様子を同じ図上で観察できます。
また、軌跡が楕円に見えないよう、表示は等縮尺（aspect ratio 1:1）で描画しています。

## パラメータ一覧

| パラメータ | 記号 | デフォルト | 範囲 | 単位 |
| --- | --- | --- | --- | --- |
| 直流母線電圧 | $V_{dc}$ | 300 | 100–600 | V |
| 線間電圧指令（RMS） | $V_{LL}$ | 141 | 0–450 | V(rms) |
| 出力周波数 | $f$ | 50 | 1–200 | Hz |
| キャリア周波数 | $f_c$ | 5 | 1–20 | kHz |
| デッドタイム | $t_d$ | 0 | 0–10 | us |
| 導通電圧降下 | $V_{on}$ | 0 | 0–5 | V |
| 負荷抵抗 | $R$ | 10 | 0.1–100 | Ω |
| 負荷インダクタンス | $L$ | 10 | 0.1–100 | mH |

> **API の単位**: POST `/simulate` と `/sweep` の入力は SI 単位（Hz, s, H）です。UI 表示の kHz, us, mH とは異なるため、API を直接利用する場合は単位変換に注意してください。

## シミュレーション処理フロー

```text
変調方式選択 → 内部3軸解決 → サンプリング方式適用 → キャリア生成 → PWM比較 → デッドタイム適用 →
非理想電圧演算 → RL負荷演算 → FFT解析 → 波形/理論比較表示
```

## ドキュメント

- [利用手順書](docs/user_guide.md) — 操作方法と学習のポイント
- [数式詳解（発展学習）](docs/deep_math_guide.md) — 理論式、導出、FFT指標の詳細
- [Web API 契約](docs/web_api_contract.md) — application 層、API、web UI の契約整理
- [アーキテクチャ設計書](architecture.md)
- [実装計画書](implementation_plan.md)
- [改善ロードマップ](improvement_plan.md) — IMPROVE-11〜12 完了済み（記録）
- [Web ベース移行案](web_migration_plan.md) — Python デスクトップ版から段階的に web 化する提案

## ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照してください。
