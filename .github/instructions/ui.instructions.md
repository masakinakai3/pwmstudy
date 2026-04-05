---
description: "Use when editing desktop UI code in ui/visualizer.py. Covers Matplotlib widgets, application-layer delegation, scenario buttons, comparison/export actions, and display units."
applyTo: "ui/**/*.py"
---

# UI / 可視化モジュール規約

## 対象クラス: `InverterVisualizer`

### 主な責務
- 8パラメータスライダーと modulation mode の操作
- Overmod View, FFT target/window の切替
- 学習シナリオボタンの適用
- ベースライン比較と JSON/PNG エクスポート
- application 層の結果を 6段の Matplotlib 表示へ反映

### モジュール定数
- `POINTS_PER_CARRIER = 100` — キャリア1周期あたりのサンプル数
- `N_DISPLAY_CYCLES = 2` — 表示する出力波形の周期数
- `N_WARMUP_CYCLES_MIN = 5` — 助走周期数の最小値（定常状態到達用）

## application 層への委譲
- 単位変換は `normalize_ui_display_params()` を通す
- シミュレーション本体は `run_simulation()` へ委譲する
- エクスポートは `build_export_payload()` を使う
- ベースラインは `build_baseline_snapshot()` を使う
- desktop UI 側で simulation ロジックを再実装しない

## 現行コールバック群
- `_setup_sliders()`
- `_setup_mode_selector()`
- `_setup_fft_controls()`
- `_setup_scenario_buttons()`
- `_setup_export_buttons()`
- `_update_modulation_mode()`
- `_update_overmod_view()`
- `_update_fft_target()`
- `_update_fft_window()`
- `_apply_scenario()`
- `_set_baseline()` / `_clear_baseline()`
- `_save_json()` / `_save_png()`
- `_draw_waveforms()` / `_update()`

## Matplotlib 構成
- `matplotlib.widgets.Slider` でパラメータ操作
- `matplotlib.widgets.RadioButtons` で PWM 方式を選択
- `matplotlib.widgets.RadioButtons` で Overmod View / FFT 表示対象 / 窓関数を選択
- `matplotlib.widgets.Button` でシナリオ・比較・エクスポートを操作
- `fig.add_gridspec(6, 1)` で6段サブプロット
- `fig.subplots_adjust(bottom=0.35)` でスライダー領域を確保
- サブプロット構成（上5段はsharex=True、FFTはx軸独立）:
  1. 指令信号 + キャリア信号（重ね描き）
  2. スイッチングパターン S_u, S_v, S_w（オフセット表示: +4, +2, +0）
  3. 線間出力電圧 v_uv, v_vw, v_wu + 基本波
  4. 相電圧 v_uN + 基本波
  5. 相電流 i_u, i_v, i_w + 理論値
  6. FFTスペクトル（線間電圧 v_uv / 相電流 i_u を切替）+ THD/RMS表示

## 表示単位
- 内部計算は SI 単位系（V, A, Ω, H, Hz, s）
- UI 表示のみ補助単位を使用:
  - `f_c`: kHz 表示 → `val * 1000.0` で Hz に変換
  - `L`: mH 表示 → `val / 1000.0` で H に変換
  - `t_d`: us 表示 → `val * 1e-6` で s に変換
- 時間軸: ms 表示（`t * 1000.0`）
- 軸ラベルに単位を必ず記載

## スライダーパラメータ
| パラメータ | 記号 | デフォルト | 範囲 | 表示単位 | valstep |
|---|---|---|---|---|---|
| 直流母線電圧 | V_dc | 300 V | 100–600 | V | 1 |
| 線間電圧指令 | V_LL | 141 V | 0–450 | V (RMS) | 1 |
| 出力周波数 | f | 50 Hz | 1–200 | Hz | 1 |
| キャリア周波数 | f_c | 5 kHz | 1–20 | kHz | 0.1 |
| デッドタイム | t_d | 0 us | 0–10 | us | 0.1 |
| 導通電圧降下 | V_on | 0 V | 0–5 | V | 0.05 |
| 負荷抵抗 | R | 10 Ω | 0.1–100 | Ω | 0.1 |
| 負荷インダクタンス | L | 10 mH | 0.1–100 | mH | 0.1 |

## コールバック設計
- `_update(val)` でスライダー変更時に全シミュレーションを再実行
- `_update_fft_target(label)` / `_update_fft_window(label)` は再描画トリガー
- `_update_modulation_mode(label)` / `_update_overmod_view(label)` は simulation を再実行する
- `_apply_scenario(idx)` は `application.scenario_presets` の desktop/web 共通定義を適用する
- `_draw_waveforms()` は application 層の構造化結果をそのまま使う
- UI コード内に物理演算ロジックを書かない

## データフロー
```
_update(val)
  → _read_display_params()
  → normalize_ui_display_params()
  → _run_simulation(params)
      → application.run_simulation()
          → simulation.*
  → _draw_waveforms(results)
```
