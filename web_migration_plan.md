# Web ベース移行案

## 1. 目的

現行の Python + Matplotlib ベース学習ソフトウェアを、ブラウザから利用できる web ベース構成へ段階的に移行するための方針を定義する。

本移行では、既存の教育価値と数値計算の妥当性を維持したまま、次を実現することを目標とする。

- インストール不要で利用できる学習環境
- 授業や自己学習で共有しやすい配布形態
- 既存の pure function ベース設計を活かした再利用
- 既存テスト資産を活かした段階移行

## 2. 現行構成の整理

現行構成は次の 3 層に分かれている。

1. `simulation/`
   - NumPy ベースの pure function 群
   - 参照信号生成、PWM 比較、インバータ電圧、RL 負荷、FFT を担当
2. `ui/visualizer.py`
   - Matplotlib widgets によるデスクトップ UI
   - スライダー、モード選択、描画、単位変換を担当
3. `tests/test_simulation.py`
   - 物理妥当性を検証する自動テスト群

この分離は web 化に有利である。特に `simulation/` は UI 非依存であるため、web API 化またはブラウザ実行向け変換の土台として再利用しやすい。

## 3. 推奨ターゲットアーキテクチャ

### 3.1 推奨案

最初の移行先として、**Python バックエンド + TypeScript フロントエンド** を推奨する。

```text
┌───────────────────────────────┐
│ Browser                       │
│  React / TypeScript           │
│  - Slider / Mode selector     │
│  - Waveform / FFT charts      │
│  - Scenario guide             │
└──────────────┬────────────────┘
               │ HTTPS / JSON
┌──────────────▼────────────────┐
│ Web API                       │
│  FastAPI                      │
│  - Parameter validation       │
│  - Simulation orchestration   │
│  - Result serialization       │
└──────────────┬────────────────┘
               │ Python call
┌──────────────▼────────────────┐
│ Simulation Core               │
│  existing simulation/*.py     │
│  - pure functions             │
│  - SI unit based calculation  │
└───────────────────────────────┘
```

### 3.2 推奨理由

- 既存の Python シミュレーション資産をほぼそのまま再利用できる
- 数値計算ロジックをフロントエンドへ移植せずに済む
- 既存 pytest を継続利用しやすい
- 将来、API の上にデスクトップ UI と web UI を共存させやすい

## 4. 代替案比較

| 案 | 概要 | 利点 | 注意点 |
| --- | --- | --- | --- |
| A. Python API + Web UI | FastAPI + React 等 | 最小リスク、既存コード再利用が容易 | サーバ運用が必要 |
| B. Pyodide/WASM でブラウザ実行 | Python をブラウザで動かす | サーバ負荷が小さい | NumPy/描画のビルド・配布構成が複雑 |
| C. 計算ロジックを TypeScript へ全面移植 | フロントのみで完結 | 配布は単純 | 数値検証の再実装コストが高い |

現時点では **A 案を第一候補** とし、B 案は将来のオフライン配布手段として検討対象に留める。

## 5. 移行時に維持すべき原則

- `simulation/` の pure function 設計を維持する
- 内部計算は SI 単位系のままとする
- UI 層のみで表示用単位変換を行う
- 既存の物理妥当性テストを回帰試験として維持する
- UI と数値計算を分離し、教育用表示を API 契約に依存させすぎない

## 6. 段階移行プラン

### Phase 0: 契約整理

- `InverterVisualizer._run_simulation()` の入出力を整理し、UI 依存のない結果辞書仕様を明文化する
- web API へ返す項目を定義する
  - 時間軸
  - 指令波形
  - スイッチングパターン
  - 線間電圧・相電圧・相電流
  - FFT 結果
  - 派生指標（`m_a`, `m_f`, THD, RMS など）

### Phase 1: アプリケーション層の切り出し

- `ui/visualizer.py` からシミュレーション統合処理を分離し、再利用可能なサービス層を追加する
- 例: `simulation_runner.py` あるいは `application/` パッケージを新設
- 目的は「Matplotlib を使わずに同一結果を返せる」状態を作ること

### Phase 2: Web API MVP

- FastAPI で `/simulate` エンドポイントを作成する
- 入力パラメータのバリデーションを追加する
- JSON で結果を返す
- pytest に API レベルの疎通テストを追加する

### Phase 3: Web UI MVP

- Web UI で次を再現する
  - 8 パラメータ入力
  - PWM 方式選択
  - 波形表示
  - FFT 表示切替
- 最初は Matplotlib 相当の全機能を一度に移植せず、主要 3 画面から着手する
  - 変調信号 + キャリア
  - 線間電圧 / 相電圧
  - 相電流 / FFT

### Phase 4: 教育機能の再実装

- 学習シナリオガイド
- 条件比較
- エクスポート
- 理論値比較パネル

この段階で `improvement_plan.md` の IMPROVE-11, 12 と統合して進める。

### Phase 5: 配布・運用整理

- 単体サーバ配布、Docker 配布、学内サーバ配布のどれを標準にするか決める
- デスクトップ版の扱いを決める
  - 並行維持
  - 保守モード化
  - web 版へ一本化

## 7. API 初期案

### 7.1 リクエスト例

```json
{
  "V_dc": 300.0,
  "V_ll_rms": 141.0,
  "f": 50.0,
  "f_c": 5000.0,
  "t_d": 0.0,
  "V_on": 0.0,
  "R": 10.0,
  "L": 0.01,
  "pwm_mode": "natural",
  "fft_target": "v_uv",
  "fft_window": "hann"
}
```

`pwm_mode` は既存 UI と同じく `natural` / `regular` / `third_harmonic` を使う。内部では現行実装に合わせて、

- `natural` → `reference_mode="sinusoidal"` + `sampling_mode="natural"`
- `regular` → `reference_mode="sinusoidal"` + `sampling_mode="regular"`
- `third_harmonic` → `reference_mode="third_harmonic"` + `sampling_mode="natural"`

へ写像する。

### 7.2 レスポンス例

```json
{
  "time": [...],
  "reference": {"u": [...], "v": [...], "w": [...]},
  "switching": {"u": [...], "v": [...], "w": [...]},
  "voltages": {"v_uv": [...], "v_vw": [...], "v_wu": [...], "v_uN": [...]},
  "currents": {"i_u": [...], "i_v": [...], "i_w": [...]},
  "fft": {"freq": [...], "magnitude": [...], "thd": 0.0},
  "metrics": {"m_a": 0.77, "m_f": 100.0, "rms_total": 0.0}
}
```

配列長が大きいため、MVP の時点で次を前提とする。

- API は表示用レスポンスを **最大 1000 点/信号** に間引いて返す
- 元データが必要なエクスポート系機能は後続 Phase 4 で分離する
- レスポンス生成時は等間隔ダウンサンプリングを基本とし、ピーク保持が必要なら min/max ペア圧縮を検討する

1000 点は、一般的なノート PC 画面幅とブラウザ描画負荷を踏まえ、1 波形を視認可能な密度で表示しつつ JSON サイズを抑えるための初期値である。将来は UI 実測を見て調整する。

## 8. 主なリスクと対策

| リスク | 内容 | 対策 |
| --- | --- | --- |
| 応答遅延 | スライダー変更ごとに全波形再計算が走る | UI で 300 ms デバウンス、表示用は 1 信号 1000 点上限、バックエンドはパラメータハッシュをキーにした LRU キャッシュを使う |
| JSON サイズ肥大 | 時系列配列が長い | MVP では表示用データのみ返し、1 信号あたり最大 1000 点へダウンサンプリングする |
| UI 仕様のずれ | Matplotlib と web 表示で見え方が変わる | 表示優先順位を決めて MVP を段階化 |
| テスト不足 | API 層と UI 層で回帰が漏れる | 既存 pytest 維持 + API テスト追加 |
| 運用負荷 | サーバ管理が新たに必要 | Docker 化、単一コンテナ配布 |

300 ms のデバウンス値は、スライダーをドラッグ中に過剰な再計算を避けつつ、体感上はほぼ即時に再描画される範囲を狙った初期値である。バックエンド応答時間の実測に応じて 200〜500 ms で再調整する。

## 9. 推奨技術スタック

- バックエンド: FastAPI
- スキーマ定義: Pydantic
- フロントエンド: React + TypeScript
- グラフ描画: Plotly または ECharts
- 配布: Docker Compose または単体コンテナ
- CI: 既存 pytest を継続しつつ、将来 web 側 lint/test を追加

## 10. 受け入れ条件案

web 移行の最初の完了条件は次とする。

1. ブラウザから主要パラメータを変更できる
2. 既存 desktop 版と同等の主要波形を表示できる
3. 既存の simulation テストが継続して通る
4. API 経由でも FFT 指標と主要メトリクスを取得できる
5. README と利用手順が web 版に対応する

## 11. 結論

本プロジェクトは、すでに simulation と UI が分離されているため、全面作り直しではなく**段階移行**が適している。

最も現実的な進め方は、まず Python シミュレーション資産を FastAPI で公開し、その上に web UI を構築する方式である。これにより、既存コードと既存テストを活かしながら、低リスクで web ベース学習ソフトウェアへ移行できる。
