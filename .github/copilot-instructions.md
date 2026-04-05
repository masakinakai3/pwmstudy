# Copilot 指示書 — 三相PWMインバータ学習シミュレータ

## プロジェクト概要

三相2レベルPWMインバータの原理を学習するためのシミュレータ。
desktop UI（Matplotlib）と web UI（FastAPI + Plotly）を並行維持し、共通の application 層と simulation 層を共有する。
現行状態は **STEP 1〜8 実装済み、IMPROVE-1〜12 適用済み、web 移行後の application/webapi/webui 構成を含む。**

## アーキテクチャ

- `simulation/` — 純粋関数ベースの数値計算層
  - `reference_generator.py` — `generate_reference(..., reference_mode, limit_linear, clamp_mode)`
  - `carrier_generator.py` — `generate_carrier(f_c, t)`
  - `pwm_comparator.py` — `apply_sampling_mode(...)`, `compare_pwm(...)`, `apply_deadtime(...)`
  - `inverter_voltage.py` — `calc_inverter_voltage(..., V_on=0.0, inputs_are_leg_states=False)`
  - `rl_load_solver.py` — `solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)`
  - `fft_analyzer.py` — `analyze_spectrum(signal, dt, f_fundamental, window_mode, enable_peak_interpolation)`
- `application/` — desktop/web 共有の非UI層
  - `modulation_config.py` — `modulation_mode` と内部3軸の対応
  - `simulation_runner.py` — シミュレーション統合、`run_simulation()`, `build_web_response()`
  - `simulation_service.py` — UI単位変換、エクスポート、ベースライン比較
  - `scenario_presets.py` — desktop/web 共有の学習シナリオ定義
- `ui/` — Matplotlib ベースの desktop UI
  - `visualizer.py` — `InverterVisualizer`（シナリオ、比較、エクスポート含む）
- `webapi/` — FastAPI
  - `app.py` — `/, /health, /scenarios, /simulate`
  - `schemas.py` — `SimulationRequest`
- `webui/` — 静的フロントエンド
  - `index.html`, `styles.css`, `app.js`
- `tests/test_simulation.py` — simulation/application/API/UI をまとめて検証する回帰テスト群

詳細は `architecture.md`、`implementation_plan.md`、`improvement_plan.md`、`docs/web_api_contract.md` を参照。

## 実行・テスト

```bash
python main.py
python -m uvicorn webapi.app:app --reload
python -m pytest tests -v
```

## コーディング規約

### 言語・スタイル
- Python 3.10 以上
- PEP 8 準拠（スペース4、最大行長100目安）
- Python 関数は型ヒント付き、docstring は Google スタイル
- JS/HTML/CSS は既存 webui の記法と UI トーンを維持する

### 命名規則
- 電圧: `v_`、電流: `i_`、スイッチング信号: `S_`、レグ状態: `leg_`
- 周波数: `f`, `f_c`、時間: `t`, `dt`
- 変調率: `m_a`、周波数変調率: `m_f`
- ユーザー向け方式選択は **`modulation_mode` 1本化**
  - `carrier`
  - `carrier_third_harmonic`
  - `carrier_two_phase`
  - `space_vector`
  - `space_vector_two_phase`

### 数値計算・物理ルール
- `simulation/` は純粋関数を維持し、UI 依存を持ち込まない
- 配列処理は NumPy ベクトル演算を優先
  - 例外: `rl_load_solver.py` の厳密離散時間更新
- 時間配列は `np.linspace` を使用し、実刻みは `dt_actual = t[1] - t[0]` を使う
- UI表示時のみ kHz, mH, us 等へ変換する
- 変数コメントや docstring では単位を明記する

## データフロー

### desktop
```
main.py
  → ui.visualizer.InverterVisualizer
    → application.normalize_ui_display_params()
    → application.run_simulation()
      → simulation.*
    → application.build_export_payload() / build_baseline_snapshot()
```

### web
```
webui/app.js
  → POST /simulate
    → webapi.schemas.SimulationRequest
    → application.run_simulation()
    → application.build_web_response()
  → GET /scenarios
    → application.SCENARIO_PRESETS
```

## テスト方針

テストは `tests/test_simulation.py` に集約し、以下を含む。

- simulation の物理妥当性
- FFT / 非理想モデル / 過変調の回帰
- `application.scenario_presets` とサービス層の契約
- `run_simulation()` / `build_web_response()` の応答整合
- FastAPI の `/health`, `/scenarios`, `/simulate`

## 禁止事項

- `simulation/` での `matplotlib` / `fastapi` / `plotly` 依存
- グローバル状態への依存
- `eval()` / `exec()` の使用
- 旧入力軸 `reference_mode` / `sampling_mode` / `clamp_mode` を新規UI/API仕様へ逆流させること
- 実装と無関係なドキュメントや指示書の件数表記を放置すること

## ドキュメント同期

以下の仕様を変更したら、関連ドキュメントも同期する。

- modulation mode / scenario schema
- `/simulate` / `/scenarios` の応答構造
- desktop/web のエクスポート仕様
- テスト構成の大きな変更
