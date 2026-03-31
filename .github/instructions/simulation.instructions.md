---
description: "Use when editing simulation engine modules (reference_generator, carrier_generator, pwm_comparator, inverter_voltage, rl_load_solver). Covers pure function design, NumPy vectorization, and physical quantity naming."
applyTo: "simulation/**/*.py"
---

# シミュレーションモジュール規約

## 実装済み関数一覧

| モジュール | 関数シグネチャ | 出力 |
|---|---|---|
| `reference_generator.py` | `generate_reference(V_ll, f, V_dc, t)` | `(v_u, v_v, v_w)` |
| `carrier_generator.py` | `generate_carrier(f_c, t)` | `v_carrier` |
| `pwm_comparator.py` | `compare_pwm(v_u, v_v, v_w, v_carrier)` | `(S_u, S_v, S_w)` |
| `inverter_voltage.py` | `calc_inverter_voltage(S_u, S_v, S_w, V_dc)` | `(v_uv, v_vw, v_wu, v_uN, v_vN, v_wN)` |
| `rl_load_solver.py` | `solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)` | `(i_u, i_v, i_w)` |
| `fft_analyzer.py` | `analyze_spectrum(signal, dt, f_fundamental)` | `{"freq", "magnitude", "thd", "fundamental_mag"}` |

## 純粋関数設計
- 各関数は副作用なし（グローバル状態の変更禁止）
- 入出力は `np.ndarray` と `float` のみ
- `matplotlib` のインポート禁止（`ui/` パッケージに限定）

## NumPy ベクトル演算
- Python の `for` ループで配列を処理しない — `np.where`, ブロードキャスト, ファンシーインデックスを使う
  - **唯一の例外**: `rl_load_solver.py` の RK4 時間ステップ積分（ステップ間依存）
  - RK4 は ZOH（零次ホールド）仮定: k1〜k4 すべて `v(t_n)` を使用する
- 浮動小数点比較には `np.allclose(a, b, atol=1e-10)` を使用
- 時間配列は `np.linspace` で生成（`np.arange` は端点精度の問題あり）

## 命名規則（物理量）
- 電圧: `v_` プレフィックス（例: `v_uv`, `v_carrier`, `v_uN`）
- 電流: `i_` プレフィックス（例: `i_u`, `i_v`, `i_w`）
- スイッチング信号: `S_` プレフィックス（例: `S_u`, `S_v`, `S_w`）
- 周波数: `f`, `f_c`（キャリア）
- 時間: `t`, 時間刻み: `dt`
- 変調率: `m_a`、直流母線電圧: `V_dc`、線間電圧RMS値: `V_ll`
- 変数コメントには必ず単位を記載: `R: float  # [Ω]`
- 時間配列の点数計算: `int(round(T_sim / dt)) + 1`（`int()` 切り捨て禁止）
- ソルバーに渡す dt: `dt_actual = t[1] - t[0]`（`np.linspace` の実際の刻み）

## 物理制約（検証観点）
- 三相対称量の和 = 0: `v_u + v_v + v_w ≈ 0`, `i_u + i_v + i_w ≈ 0`
- 変調信号の値域: `[-1, 1]`
- スイッチング信号の値域: `{0, 1}`（int 型）
- 線間電圧: `{-V_dc, 0, +V_dc}` の3レベル
