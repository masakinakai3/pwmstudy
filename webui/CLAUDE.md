# webui/ — Web フロントエンド規約

FastAPI から静的配信される `index.html`, `styles.css`, `app.js` で構成される vanilla JS フロントエンド。

## 構成

- `index.html` — ページ構造
- `styles.css` — スタイル
- `app.js` — 全ロジック（約 2700 行）

## 表示セクション

1. 変調信号 + キャリア
2. スイッチングパターン
3. 線間電圧 / 相電圧
4. 相電流 / FFT

追加: Scenario Guide、理論比較、条件比較、JSON/PNG エクスポート

## API 連携

- `GET /scenarios` で `application.SCENARIO_PRESETS` を取得
- `POST /simulate` へ送る値は SI 単位へ変換:
  - `f_c`: kHz → Hz
  - `t_d`: us → s
  - `L`: mH → H
- `fftTarget` は `v_uv` / `i_u` を使用

## Plotly / 可視化

- 全体再描画: `Plotly.react()`、軽量更新: `Plotly.restyle()`
- スイッチングパターンと線間電圧は切替点保持圧縮系列を尊重
- SVPWM 系: `svpwm_observer` と `carrier_hold` を優先使用
- Section 1 / Section 2 の同期アニメーションを壊さない

## UI / UX

- 既存の配色・カード構造・タイポグラフィを維持
- ステータス文・ヒント文は教育用途に合わせて簡潔に
- パネル番号に依存した説明を避け、セクション名や物理量名で説明

## Scenario Guide 表示

表示項目: `label`, `focus`, `hint`, `learning_objective`, `prerequisites`, `procedure`, `expected_observation`, `uncertainty_notes`

`expected_observation` にメトリクス条件がある場合のみ達成/未達/未判定の判定を行う。

## エクスポート / 比較

- JSON: controls + current response + baseline を含む
- PNG: dashboard 合成画像の仕様を維持
- ベースライン比較: 線間電圧基本波と相電流のオーバーレイ

## 同期対象

- `docs/user_guide.md`
- `docs/web_api_contract.md`
- `application/scenario_presets.py`
