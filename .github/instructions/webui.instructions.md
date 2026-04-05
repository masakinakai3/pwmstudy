---
description: "Use when editing web UI files (webui/app.js, webui/index.html, webui/styles.css). Covers Plotly dashboard behavior, display-unit conversion, Scenario Guide rendering, SVPWM interaction, and API integration with /simulate and /scenarios."
applyTo: "webui/**/*.js,webui/**/*.html,webui/**/*.css"
---

# web UI 規約

## 構成
- web UI は FastAPI から静的配信される `index.html`, `styles.css`, `app.js` で構成される
- 主要表示は 4 セクション
  1. 変調信号 + キャリア
  2. スイッチングパターン
  3. 線間電圧 / 相電圧
  4. 相電流 / FFT
- 追加で Scenario Guide、理論比較、条件比較、JSON/PNG エクスポートを持つ

## API 連携
- `GET /scenarios` で `application.SCENARIO_PRESETS` を取得する
- `POST /simulate` へ送る値は SI 単位へ変換する
  - `f_c`: kHz → Hz
  - `t_d`: us → s
  - `L`: mH → H
- UI の `fftTarget` は `v_uv` / `i_u` を使う

## Scenario Guide 表示
- Guide カードは少なくとも以下を表示する
  - `label`
  - `focus`
  - `hint`
  - `learning_objective`
  - `prerequisites`
  - `procedure`
  - `expected_observation`
  - `uncertainty_notes`
- `expected_observation` にメトリクス条件がある場合のみ、達成/未達/未判定の簡易判定を行う
- シナリオデータが古い場合でも、後方互換で壊れない描画にする

## Plotly / 可視化
- 全体再描画は `Plotly.react()`、軽量更新は `Plotly.restyle()` を優先する
- スイッチングパターンと線間電圧は切替点保持圧縮系列を尊重する
- SVPWM 系では `svpwm_observer` と `carrier_hold` を優先して使う
- Section 1 / Section 2 の同期アニメーションを壊さない

## UI / UX
- 既存の配色・カード構造・タイポグラフィを維持する
- ステータス文・ヒント文は教育用途に合わせて簡潔にする
- パネル番号に依存した説明は避け、セクション名や物理量名で説明する

## エクスポート / 比較
- JSON 保存は controls + current response + baseline を含む
- PNG 保存は dashboard 合成画像の仕様を維持する
- ベースライン比較は線間電圧基本波と相電流のオーバーレイを前提とする

## 同期対象
- `docs/user_guide.md`
- `docs/web_api_contract.md`
- `application/scenario_presets.py`

上記いずれかを変えたら、表示文言や前提条件がズレていないかを確認すること。