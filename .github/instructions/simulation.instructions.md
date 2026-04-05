---
description: "Use when editing simulation engine modules in simulation/. Covers pure function design, modulation reference generation, NumPy vectorization, and physical quantity naming."
applyTo: "simulation/**/*.py"
---

# シミュレーションモジュール規約

## 現行モジュール

| モジュール | 関数シグネチャ | 出力 |
|---|---|---|
| `reference_generator.py` | `generate_reference(V_ll, f, V_dc, t, reference_mode="sinusoidal", limit_linear=True, clamp_mode="continuous", mode=None, svpwm_mode=None)` | `(v_u, v_v, v_w)` |
| `carrier_generator.py` | `generate_carrier(f_c, t)` | `v_carrier` |
| `pwm_comparator.py` | `apply_sampling_mode(...)`, `compare_pwm(...)`, `apply_deadtime(...)` | `(v_u_cmp, v_v_cmp, v_w_cmp)`, `(S_u, S_v, S_w)`, `(leg_u, leg_v, leg_w)` |
| `inverter_voltage.py` | `calc_inverter_voltage(..., V_on=0.0, inputs_are_leg_states=False)` | `(v_uv, v_vw, v_wu, v_uN, v_vN, v_wN)` |
| `rl_load_solver.py` | `solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)` | `(i_u, i_v, i_w)` |
| `fft_analyzer.py` | `analyze_spectrum(signal, dt, f_fundamental, window_mode="rectangular", enable_peak_interpolation=True)` | `{"freq", "magnitude", "thd", "fundamental_mag", "fundamental_phase", "fundamental_freq", "fundamental_rms", "rms_total", ...}` |

## 純粋関数設計
- 各関数は副作用なし（グローバル状態の変更禁止）
- 入出力は `np.ndarray` と `float` のみ
- `matplotlib` / `fastapi` / `plotly` のインポート禁止

## NumPy ベクトル演算
- Python の `for` ループで配列を処理しない — `np.where`, ブロードキャスト, ファンシーインデックスを使う
  - **唯一の例外**: `rl_load_solver.py` の厳密離散時間更新（ステップ間依存）
  - RL ソルバは ZOH（零次ホールド）仮定の解析解を使い、`expm1` で極小抵抗条件を安定化する
- 浮動小数点比較には `np.allclose(a, b, atol=1e-10)` を使用
- 時間配列は `np.linspace` で生成（`np.arange` は端点精度の問題あり）

## 命名規則（物理量）
- 電圧: `v_` プレフィックス（例: `v_uv`, `v_carrier`, `v_uN`）
- 電流: `i_` プレフィックス（例: `i_u`, `i_v`, `i_w`）
- スイッチング信号: `S_` プレフィックス（例: `S_u`, `S_v`, `S_w`）
- レグ状態: `leg_` プレフィックス（例: `leg_u`, `leg_v`, `leg_w`）
- 参照生成方式: `reference_mode`、サンプリング方式: `sampling_mode`、クランプ方式: `clamp_mode`
- 周波数: `f`, `f_c`（キャリア）
- 時間: `t`, 時間刻み: `dt`
- 変調率: `m_a`、直流母線電圧: `V_dc`、線間電圧RMS値: `V_ll`、デッドタイム: `t_d`、固定電圧降下: `V_on`
- 変数コメントには必ず単位を記載: `R: float  # [Ω]`
- 時間配列の点数計算: `int(round(T_sim / dt)) + 1`（`int()` 切り捨て禁止）
- ソルバーに渡す dt: `dt_actual = t[1] - t[0]`（`np.linspace` の実際の刻み）

## 物理制約（検証観点）
- 三相対称量の和 = 0: 正弦波参照では `v_u + v_v + v_w ≈ 0`、電流では `i_u + i_v + i_w ≈ 0`
- 三次高調波注入 / min-max 零相注入では零相成分を許容し、線間参照差の不変性を検証する
- 変調信号の値域: `[-1, 1]`
- スイッチング信号の値域: `{0, 1}`（int 型）
- レグ状態の値域: `{-1, 0, +1}`
- 線間電圧: 理想条件では `{-V_dc, 0, +V_dc}` の3レベル

## 現行方式の前提
- user-facing の変調選択は `modulation_mode` 1本化されているが、simulation 層では `reference_mode` / `sampling_mode` / `clamp_mode` を使う
- sampling は現行仕様では `natural` 固定
- `carrier_two_phase` と `space_vector_two_phase` は DPWM1 クランプに対応する
- `limit_linear=False` は Overmod View 用で、過変調観察のために線形クランプを外す
