---
description: "Use when editing UI/visualization code (visualizer.py). Covers Matplotlib widgets, subplot layout, and display units."
applyTo: "ui/**/*.py"
---

# UI / 可視化モジュール規約

## 実装済みクラス: `InverterVisualizer`

### メソッド一覧
| メソッド | 用途 |
|---|---|
| `__init__(self, default_params: dict)` | 初期化（Figure/Axes/Slider/Line生成） |
| `run(self)` | `plt.show()` でメインループ開始 |
| `_setup_sliders(self)` | 8本のスライダーを配置 |
| `_setup_fft_controls(self)` | FFT表示対象と窓関数の選択を配置 |
| `_setup_mode_selector(self)` | PWM方式選択を配置 |
| `_init_plots(self)` | 6段サブプロットの初期設定 |
| `_read_params(self) -> dict` | スライダー値→SI単位系パラメータ辞書 |
| `_solve_nonideal_power_stage(self, ...)` | 非理想電圧-電流整合の反復計算 |
| `_run_simulation(self, params) -> dict` | シミュレーション実行（全6モジュール呼び出し） |
| `_draw_waveforms(self, results)` | Line2D の set_data で波形更新 |
| `_update(self, val)` | スライダー変更コールバック |
| `_update_fft_target(self, label)` | FFT表示対象変更コールバック |
| `_update_fft_window(self, label)` | FFT窓関数変更コールバック |
| `_update_mode(self, label)` | PWM方式変更コールバック |

### モジュール定数
- `POINTS_PER_CARRIER = 100` — キャリア1周期あたりのサンプル数
- `N_DISPLAY_CYCLES = 2` — 表示する出力波形の周期数
- `N_WARMUP_CYCLES_MIN = 5` — 助走周期数の最小値（定常状態到達用）
- `NONIDEAL_CORRECTION_STEPS = 2` — 非理想電圧-電流整合の反復回数

### 助走区間ロジック
- 動的計算: `n_warmup = max(N_WARMUP_CYCLES_MIN, ceil(5 * tau / T_cycle))`
- シミュレーションは `n_warmup + N_DISPLAY_CYCLES` 周期分実行
- 表示は最後の `N_DISPLAY_CYCLES` 周期のみ

### m_a 表示
- `fig.text()` で Figure 上部に変調率を表示
- クランプ上限は方式依存
  - Natural: 1.0
  - Third Harmonic Injection: `2 / sqrt(3)`

## Matplotlib 構成
- `matplotlib.widgets.Slider` でパラメータ操作
- `matplotlib.widgets.RadioButtons` で PWM 方式を選択
- `matplotlib.widgets.RadioButtons` で FFT 表示対象と窓関数を選択
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
- 時間軸: ms 表示（`t * 1000.0`）
- 軸ラベルに単位を必ず記載

## スライダーパラメータ（実装済み）
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
- `_update_fft_target(label)` で FFT 表示対象変更時に再描画する
- `_update_fft_window(label)` で FFT 窓関数変更時に再解析・再描画する
- `_update_mode(label)` で PWM 方式変更時に全シミュレーションを再実行
- `_run_simulation()` で `simulation/` パッケージの6関数を順次呼び出し、必要に応じて `_solve_nonideal_power_stage()` を用いる
- `_draw_waveforms()` で Line2D の `set_data` + FFT棒グラフ再描画 + 情報パネル更新 + `draw_idle()` で高速再描画
- UI コード内に物理演算ロジックを書かない
- V_ll スライダーは RMS 入力、`_read_params()` 内で `* np.sqrt(2)` でピーク値に変換
- t_d スライダーは us 入力、`_read_params()` 内で `* 1e-6` で秒に変換

## データフロー
```
_update(val)
  → _read_params() — スライダー値を SI 単位に変換（V_ll: RMS→peak, t_d: us→s）
  → _run_simulation(params)
      → generate_reference(mode=...) → apply_sampling_mode() → generate_carrier()
      → compare_pwm() → apply_deadtime()
      → calc_inverter_voltage() → solve_rl_load()
      → _solve_nonideal_power_stage()  # t_d > 0 または V_on > 0 のとき
      → analyze_spectrum(window_mode=...)
  → _draw_waveforms(results) — Line2D.set_data + FFT棒グラフ + draw_idle
```
