---
description: "Use when editing application layer or FastAPI modules (modulation_config, simulation_runner, simulation_service, scenario_presets, webapi/app.py, webapi/schemas.py). Covers modulation_mode normalization, unit conversion, shared desktop/web behavior, and API contracts."
applyTo: "application/**/*.py,webapi/**/*.py"
---

# application / webapi 規約

## 役割分担
- `simulation/` は純粋計算のみを担当する
- `application/` は desktop/web 共通の統合・整形・単位変換・比較・エクスポートを担当する
- `webapi/` は FastAPI の入出力契約だけを担当し、物理計算を再実装しない

## modulation_mode 契約
- 外部入力は `modulation_mode` 1本化を維持する
- 有効値:
  - `carrier`
  - `carrier_third_harmonic`
  - `carrier_two_phase`
  - `space_vector`
  - `space_vector_two_phase`
- 内部では `reference_mode` / `sampling_mode` / `clamp_mode` へ写像する
- 旧入力軸 `reference_mode`, `sampling_mode`, `clamp_mode`, `pwm_mode`, `svpwm_mode` を web API スキーマへ戻さない

## simulation_runner の責務
- `run_simulation()` は simulation 層を束ね、desktop/web 双方で再利用できる構造化結果を返す
- `build_web_response()` は web UI 向け payload を生成する
- `overmod_view=True` は `limit_linear=False` に対応する
- `dt_actual = t[1] - t[0]` を用い、`np.linspace` の実刻みと整合させる

## simulation_service の責務
- `normalize_ui_display_params()` で UI 補助単位を SI 単位へ変換する
- `build_export_payload()` で JSON 保存用の構造を組み立てる
- `build_baseline_snapshot()` で比較表示用の最小情報を抽出する

## scenario_presets の規約
- desktop/web 共有定義として維持する
- 現行スキーマは少なくとも以下を含む
  - `label`, `hint`, `focus`
  - `learning_objective`
  - `prerequisites`
  - `procedure`
  - `expected_observation`
  - `uncertainty_notes`
  - `recommended_compare_modes`
  - `tags`
  - `sliders`
  - `modulation_mode`, `overmod_view`, `fft_target`, `fft_window`
- `expected_observation` は `text` を必須とし、必要に応じて `metric`, `comparison`, `value`, `min`, `max`, `tolerance` を持てる

## FastAPI 規約
- `app.py` は `/, /health, /scenarios, /simulate` を公開する
- `schemas.py` は `SimulationRequest` による範囲検証と unknown field rejection を担う
- 外部APIの `fft_target` は `v_uv` / `i_u`、内部では `voltage` / `current` に写像する

## 同期対象ドキュメント
- `docs/web_api_contract.md`
- `docs/user_guide.md`
- `README.md`

API や scenario schema を変えたら、少なくとも上記3ファイルとの整合を確認すること。