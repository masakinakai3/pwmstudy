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
| `_setup_sliders(self)` | 6本のスライダーを配置 |
| `_init_plots(self)` | 4段サブプロットの初期設定 |
| `_read_params(self) -> dict` | スライダー値→SI単位系パラメータ辞書 |
| `_run_simulation(self, params) -> dict` | シミュレーション実行（全5モジュール呼び出し） |
| `_draw_waveforms(self, results)` | Line2D の set_data で波形更新 |
| `_update(self, val)` | スライダー変更コールバック |

### モジュール定数
- `POINTS_PER_CARRIER = 100` — キャリア1周期あたりのサンプル数
- `N_DISPLAY_CYCLES = 2` — 表示する出力波形の周期数
- `N_WARMUP_CYCLES_MIN = 5` — 助走周期数の最小値（定常状態到達用）

### 助走区間ロジック
- 動的計算: `n_warmup = max(N_WARMUP_CYCLES_MIN, ceil(5 * tau / T_cycle))`
- シミュレーションは `n_warmup + N_DISPLAY_CYCLES` 周期分実行
- 表示は最後の `N_DISPLAY_CYCLES` 周期のみ

### m_a 表示
- `fig.text()` で Figure 上部に変調率を表示
- クランプ中（m_a > 1）は赤字で「クランプ中: 指令値 X.XXX」を通知

## Matplotlib 構成
- `matplotlib.widgets.Slider` でパラメータ操作
- `fig.add_gridspec(5, 1)` で5段サブプロット
- `fig.subplots_adjust(bottom=0.35)` でスライダー領域を確保
- サブプロット構成（上4段はsharex=True、FFTはx軸独立）:
  1. 指令信号 + キャリア信号（重ね描き）
  2. スイッチングパターン S_u, S_v, S_w（オフセット表示: +4, +2, +0）
  3. 線間出力電圧 v_uv, v_vw, v_wu
  4. 相電流 i_u, i_v, i_w
  5. FFTスペクトル（線間電圧 v_uv）+ THD表示

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
| 負荷抵抗 | R | 10 Ω | 0.1–100 | Ω | 0.1 |
| 負荷インダクタンス | L | 10 mH | 0.1–100 | mH | 0.1 |

## コールバック設計
- `_update(val)` でスライダー変更時に全シミュレーションを再実行
- `_run_simulation()` で `simulation/` パッケージの6関数を順次呼び出し
- `_draw_waveforms()` で Line2D の `set_data` + FFT棒グラフ再描画 + `draw_idle()` で高速再描画
- UI コード内に物理演算ロジックを書かない
- V_ll スライダーは RMS 入力、`_read_params()` 内で `* np.sqrt(2)` でピーク値に変換

## データフロー
```
_update(val)
  → _read_params() — スライダー値を SI 単位に変換（V_ll: RMS→peak）
  → _run_simulation(params)
      → generate_reference() → generate_carrier() → compare_pwm()
      → calc_inverter_voltage() → solve_rl_load()
      → analyze_spectrum()
  → _draw_waveforms(results) — Line2D.set_data + FFT棒グラフ + draw_idle
```
