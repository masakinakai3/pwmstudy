# simulation/ — シミュレーションエンジン規約

このディレクトリは純粋関数ベースの数値計算層である。UI依存を一切持ち込まない。

## モジュール構成

| モジュール | 主要関数 | 出力 |
|---|---|---|
| `reference_generator.py` | `generate_reference(V_ll, f, V_dc, t, reference_mode, limit_linear, clamp_mode)` | `(v_u, v_v, v_w)` |
| `carrier_generator.py` | `generate_carrier(f_c, t)` | `v_carrier` |
| `pwm_comparator.py` | `apply_sampling_mode(...)`, `compare_pwm(...)`, `apply_deadtime(...)` | スイッチング/レグ状態 |
| `inverter_voltage.py` | `calc_inverter_voltage(..., V_on, inputs_are_leg_states)` | `(v_uv, v_vw, v_wu, v_uN, v_vN, v_wN)` |
| `rl_load_solver.py` | `solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)` | `(i_u, i_v, i_w)` |
| `fft_analyzer.py` | `analyze_spectrum(signal, dt, f_fundamental, window_mode, enable_peak_interpolation)` | dict（freq, magnitude, thd 等） |

## 純粋関数設計

- 入出力は `np.ndarray` と `float` のみ
- 副作用禁止（グローバル状態変更、ファイル I/O）
- **`matplotlib` / `fastapi` / `plotly` のインポート禁止**

## NumPy ベクトル演算

- Python の `for` ループで配列を処理しない — `np.where`, ブロードキャスト, ファンシーインデックスを使う
- **唯一の例外**: `rl_load_solver.py` の厳密離散時間更新（ステップ間依存、ZOH 仮定の解析解、`expm1` で極小抵抗安定化）
- 浮動小数点比較: `np.allclose(a, b, atol=1e-10)`
- 時間配列: `np.linspace`（`np.arange` 禁止）
- `n_points = int(round(T_sim / dt)) + 1`、`dt_actual = t[1] - t[0]`

## 命名規則（物理量）

- 電圧: `v_`、電流: `i_`、スイッチング: `S_`、レグ状態: `leg_`
- `reference_mode` / `sampling_mode` / `clamp_mode` は simulation 層の内部軸
- 変数コメントに単位を記載: `R: float  # [Ω]`

## 物理制約（検証観点）

- 正弦波参照の三相和 ≈ 0（三次高調波注入では線間参照差の不変性で検証）
- 変調信号の値域: `[-1, 1]`
- スイッチング信号: `{0, 1}`（int 型）
- レグ状態: `{-1, 0, +1}`
- 線間電圧（理想条件）: `{-V_dc, 0, +V_dc}`

## 現行方式の前提

- user-facing の変調選択は `modulation_mode` 1本化だが、simulation 層では `reference_mode` / `sampling_mode` / `clamp_mode` を使う
- sampling は現行 `natural` 固定
- `carrier_two_phase` / `space_vector_two_phase` は DPWM1 クランプに対応
- `limit_linear=False` は過変調観察用
