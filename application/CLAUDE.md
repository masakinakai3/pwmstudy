# application/ — desktop/web 共有層規約

desktop UI と web API の間で共有される統合・整形・単位変換・比較・エクスポートを担う層。

## モジュール構成

| モジュール | 責務 |
|---|---|
| `modulation_config.py` | `modulation_mode` → 内部3軸（`reference_mode`/`sampling_mode`/`clamp_mode`）の写像 |
| `simulation_runner.py` | simulation 層の統合。`run_simulation()`, `build_web_response()` |
| `simulation_service.py` | UI 単位変換、エクスポート、ベースライン比較 |
| `scenario_presets.py` | desktop/web 共有の学習シナリオ定義 |

## modulation_mode 契約

- 外部入力は `modulation_mode` 1本を維持
- 有効値: `carrier`, `carrier_third_harmonic`, `carrier_two_phase`, `space_vector`, `space_vector_two_phase`
- 旧入力軸（`reference_mode`, `sampling_mode`, `clamp_mode`, `pwm_mode`, `svpwm_mode`）を web API スキーマへ戻さない

## simulation_runner の責務

- `run_simulation()` は simulation 層を束ね、構造化結果を返す
- `build_web_response()` は web UI 向け payload を生成
- `overmod_view=True` は `limit_linear=False` に対応
- `dt_actual = t[1] - t[0]` で `np.linspace` の実刻みと整合させる

## simulation_service の責務

- `normalize_ui_display_params()` — UI 補助単位を SI 単位へ変換
- `build_export_payload()` — JSON 保存用構造を組み立て
- `build_baseline_snapshot()` — 比較表示用の最小情報を抽出

## scenario_presets の規約

- desktop/web 共有定義として維持
- 必須キー: `label`, `hint`, `focus`, `learning_objective`, `prerequisites`, `procedure`, `expected_observation`, `uncertainty_notes`, `recommended_compare_modes`, `tags`, `sliders`, `modulation_mode`, `overmod_view`, `fft_target`, `fft_window`
- `expected_observation` は `text` を必須、オプションで `metric`, `comparison`, `value`, `min`, `max`, `tolerance`

## 同期対象ドキュメント

API や scenario schema を変更したら以下を確認:
- `docs/web_api_contract.md`
- `docs/user_guide.md`
- `README.md`
