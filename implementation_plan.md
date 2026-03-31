# 三相PWMインバータ学習ソフトウェア — 実装計画書

> 採用方針: **案A（Python + NumPy + Matplotlib + widgets）**

## 1. 前提条件

### 1.1 実行環境
- Python 3.10 以上
- OS: Windows（開発環境）、macOS / Linux でも動作可能

### 1.2 依存ライブラリ
| ライブラリ | バージョン | 用途 |
|---|---|---|
| numpy | >= 1.24 | 数値計算・配列演算 |
| matplotlib | >= 3.7 | 波形描画・UIウィジェット |
| scipy | >= 1.10 | FFT解析（将来拡張用、初期は任意） |

### 1.3 最終ファイル構成
```
3lvlpwm/
├── main.py                      # エントリポイント
├── simulation/
│   ├── __init__.py
│   ├── reference_generator.py   # STEP 2
│   ├── carrier_generator.py     # STEP 3
│   ├── pwm_comparator.py        # STEP 4
│   ├── inverter_voltage.py      # STEP 5
│   └── rl_load_solver.py        # STEP 6
├── ui/
│   ├── __init__.py
│   └── visualizer.py            # STEP 7
├── requirements.txt             # STEP 1
├── architecture.md
└── implementation_plan.md
```

---

## 2. 実装ステップ

### STEP 1: プロジェクト基盤構築

**対象ファイル**: `requirements.txt`, `simulation/__init__.py`, `ui/__init__.py`

**作業内容**:
- `requirements.txt` に依存ライブラリを記述
- パッケージ用の `__init__.py` を作成
- 仮想環境の構築手順を確認

**完了条件**: `pip install -r requirements.txt` でライブラリが正常にインストールできる

---

### STEP 2: 指令信号生成モジュール (`simulation/reference_generator.py`)

**実装する関数**:
```
generate_reference(V_ll, f, V_dc, t) -> (v_u, v_v, v_w)
```

**処理詳細**:
1. 線間→相電圧変換: `V_ph = V_ll / √3`
2. 変調率計算: `m_a = 2 * V_ph / V_dc`
3. `m_a > 1.0` の場合は 1.0 にクランプ（過変調防止）
4. 三相正弦波を生成（120°位相差）

**入出力仕様**:
- 入力: `V_ll`(float), `f`(float), `V_dc`(float), `t`(np.ndarray)
- 出力: 各相の正規化変調信号 (np.ndarray × 3)、値域 [-1, 1]

**検証方法**: 出力3相の総和が常に 0 であることを確認

---

### STEP 3: キャリア生成モジュール (`simulation/carrier_generator.py`)

**実装する関数**:
```
generate_carrier(f_c, t) -> v_carrier
```

**処理詳細**:
1. `scipy.signal.sawtooth` または NumPy 演算で対称三角波を生成
2. 振幅 ±1、周波数 f_c のキャリア信号を返す
3. ライブラリ非依存のため NumPy のみで実装する（`sawtooth` は使わない）

**アルゴリズム**:
```
phase = (t * f_c) % 1.0
v_carrier = where(phase < 0.5, 4*phase - 1, 3 - 4*phase)
```

**入出力仕様**:
- 入力: `f_c`(float), `t`(np.ndarray)
- 出力: 三角波信号 (np.ndarray)、値域 [-1, 1]

**検証方法**: 周期 1/f_c で振幅が ±1 に達することを目視確認

---

### STEP 4: PWM比較器モジュール (`simulation/pwm_comparator.py`)

**実装する関数**:
```
compare_pwm(v_u, v_v, v_w, v_carrier) -> (S_u, S_v, S_w)
```

**処理詳細**:
1. 各相について指令信号とキャリアを比較
2. `v_x > v_carrier` → `S_x = 1`（上アームON）
3. `v_x <= v_carrier` → `S_x = 0`（下アームON）

**入出力仕様**:
- 入力: 変調信号3相 + キャリア信号（各 np.ndarray）
- 出力: スイッチング信号 (np.ndarray × 3)、値は 0 or 1（int型）

**検証方法**: m_a = 0 のとき全相 S_x = 0、キャリアのゼロクロス付近で切り替わること

---

### STEP 5: インバータ電圧演算モジュール (`simulation/inverter_voltage.py`)

**実装する関数**:
```
calc_inverter_voltage(S_u, S_v, S_w, V_dc) -> (v_uv, v_vw, v_wu, v_uN, v_vN, v_wN)
```

**処理詳細**:

1. **線間電圧**（3レベル: +V_dc, 0, -V_dc）:
   ```
   v_uv = (S_u - S_v) * V_dc
   v_vw = (S_v - S_w) * V_dc
   v_wu = (S_w - S_u) * V_dc
   ```

2. **相電圧（負荷中性点基準）**:
   ```
   v_uN = (V_dc / 3) * (2*S_u - S_v - S_w)
   v_vN = (V_dc / 3) * (2*S_v - S_w - S_u)
   v_wN = (V_dc / 3) * (2*S_w - S_u - S_v)
   ```

**入出力仕様**:
- 入力: スイッチング信号3相 (np.ndarray × 3), V_dc (float)
- 出力: 線間電圧3相 + 相電圧3相 (np.ndarray × 6)

**検証方法**: `v_uv + v_vw + v_wu = 0` が常に成立, `v_uN + v_vN + v_wN = 0` が常に成立

---

### STEP 6: RL負荷電流演算モジュール (`simulation/rl_load_solver.py`)

**実装する関数**:
```
solve_rl_load(v_uN, v_vN, v_wN, R, L, dt) -> (i_u, i_v, i_w)
```

**処理詳細**:
1. 各相独立に微分方程式を数値積分
2. 回路方程式: `v_xN(t) = R * i_x(t) + L * di_x(t)/dt`
3. **4次ルンゲ・クッタ法（RK4）** を採用（オイラー法より精度が高い）
4. 初期条件: `i_u(0) = i_v(0) = i_w(0) = 0`
5. 定常状態到達のため、出力周波数の数周期分をシミュレーション

**RK4 アルゴリズム（1ステップ）**:
```
f(i, v) = (v - R*i) / L

k1 = f(i_n, v_n)
k2 = f(i_n + dt/2 * k1, v_{n+0.5})    ※ v_{n+0.5} は v_n で近似
k3 = f(i_n + dt/2 * k2, v_{n+0.5})
k4 = f(i_n + dt * k3, v_{n+1})
i_{n+1} = i_n + (dt/6) * (k1 + 2*k2 + 2*k3 + k4)
```

**注意**: PWM電圧はステップ状のため、半ステップ点の電圧は直前のステップ値で近似する

**入出力仕様**:
- 入力: 相電圧3相 (np.ndarray × 3), R (float), L (float), dt (float)
- 出力: 相電流3相 (np.ndarray × 3)

**検証方法**:
- 定常状態で `i_u + i_v + i_w ≈ 0` であること
- 電流振幅が理論値 `V_ph / √(R² + (2πfL)²)` に概ね一致すること

---

### STEP 7: 波形表示UI (`ui/visualizer.py`)

**実装する関数・クラス**:
```
class InverterVisualizer:
    def __init__(self, default_params)
    def run(self)                      # メインループ
    def _update(self, val)             # スライダー変更時のコールバック
    def _run_simulation(self, params)  # シミュレーション実行
    def _draw_waveforms(self, results) # 波形描画
```

**画面レイアウト**:
```
┌─────────────────────────────────────────────┐
│  [subplot 1] 指令信号 + キャリア             │
│  [subplot 2] スイッチングパターン Su,Sv,Sw   │
│  [subplot 3] 線間電圧 Vuv, Vvw, Vwu         │
│  [subplot 4] 相電流 iu, iv, iw               │
├─────────────────────────────────────────────┤
│  [Slider] V_dc  ====●==========  300 V      │
│  [Slider] V_LL  ======●========  200 V      │
│  [Slider] f     ==●============   50 Hz     │
│  [Slider] f_c   ========●======  5000 Hz    │
│  [Slider] R     ===●===========   10 Ω      │
│  [Slider] L     ===●===========   10 mH     │
└─────────────────────────────────────────────┘
```

**UIコンポーネント**:
- `matplotlib.widgets.Slider` × 6本
- `matplotlib.pyplot.subplots` で4段サブプロット
- スライダー変更時に全シミュレーションを再実行して波形を再描画

**描画仕様**:
| サブプロット | 表示内容 | Y軸範囲 | 線色 |
|---|---|---|---|
| 1 | v_u*, v_v*, v_w* + carrier | [-1.2, 1.2] | 赤,青,緑 + 灰 |
| 2 | S_u, S_v, S_w（オフセット表示） | [-0.5, 5.5] | 赤,青,緑 |
| 3 | v_uv, v_vw, v_wu | [-V_dc*1.2, V_dc*1.2] | 赤,青,緑 |
| 4 | i_u, i_v, i_w | 自動スケール | 赤,青,緑 |

**X軸**: 全サブプロットで共有、表示範囲は出力周波数の2周期分

**性能考慮**:
- スライダー操作ごとに再計算が走るため、時間配列のサンプル数を制御
- デフォルト: キャリア1周期あたり100点 → f_c=5kHz, 表示2周期(40ms) で 20,000点

---

### STEP 8: エントリポイント (`main.py`)

**実装内容**:
1. デフォルトパラメータ辞書の定義
2. `InverterVisualizer` のインスタンス生成
3. `visualizer.run()` の呼び出し

**デフォルトパラメータ**:
```
params = {
    "V_dc": 300.0,   # [V]
    "V_ll": 200.0,   # [V]
    "f": 50.0,        # [Hz]
    "f_c": 5000.0,    # [Hz]
    "R": 10.0,        # [Ω]
    "L": 0.01,        # [H] (= 10 mH)
}
```

---

## 3. シミュレーション時間・時間刻みの設計

### 時間配列の生成方針

| パラメータ | 計算式 | デフォルト値 |
|---|---|---|
| 表示周期数 | `n_cycles = 2` | 出力波形2周期分 |
| シミュレーション時間 | `T_sim = n_cycles / f` | 40 ms (f=50Hz) |
| 時間分解能 | `dt = 1 / (f_c * points_per_carrier)` | 2 μs (f_c=5kHz, 100点/周期) |
| 総サンプル数 | `N = T_sim / dt` | 20,000 点 |

### 定常状態への対応
- 初期電流を0とするため、表示の最初の数周期は過渡状態を含む
- 将来的には「助走期間」（例: 5周期分）を加え、表示は後半2周期のみとすることを検討

---

## 4. 実装順序と依存関係

```
STEP 1: プロジェクト基盤
  │
  ├──→ STEP 2: 指令信号生成（独立）
  ├──→ STEP 3: キャリア生成（独立）
  │       │
  │       ▼
  ├──→ STEP 4: PWM比較器（STEP 2, 3 に依存）
  │       │
  │       ▼
  ├──→ STEP 5: 電圧演算（STEP 4 に依存）
  │       │
  │       ▼
  ├──→ STEP 6: RL負荷演算（STEP 5 に依存）
  │       │
  │       ▼
  ├──→ STEP 7: 波形表示UI（STEP 2–6 全てに依存）
  │       │
  │       ▼
  └──→ STEP 8: エントリポイント（STEP 7 に依存）
```

---

## 5. 各STEP完了時の動作確認方法

| STEP | 確認方法 |
|---|---|
| 1 | `pip install -r requirements.txt` が成功 |
| 2 | 単体テスト: 3相の和が0、振幅が m_a 以内 |
| 3 | 単体テスト: 三角波の周期・振幅が正しい |
| 4 | 単体テスト: m_a=0で全OFF、m_a=1付近でデューティ比が妥当 |
| 5 | 単体テスト: 線間・相電圧の和が0 |
| 6 | 単体テスト: 定常電流振幅が理論値と5%以内で一致 |
| 7 | 目視: 4段波形が正しく表示、スライダー操作で動的更新 |
| 8 | `python main.py` でウィンドウが起動し操作可能 |

---

## 6. 既知の制約・将来拡張

### 初期リリースでの制約
- 過変調（m_a > 1）は非対応（クランプ処理）
- デッドタイムは考慮しない
- 電流初期値は常に0（定常状態への収束は自然に待つ）

### 将来拡張候補（優先度順）
1. **FFT解析パネル追加** — 出力電圧・電流の周波数スペクトル表示
2. **助走期間の導入** — 定常状態のみを表示するオプション
3. **過変調モード** — m_a > 1 領域のシミュレーション
4. **デッドタイム模擬** — スイッチング遷移時の短絡防止期間
5. **THD（全高調波歪み率）表示** — 数値指標としてUI上に表示
