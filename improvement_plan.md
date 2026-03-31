# 改善ロードマップ実行計画書

## 概要

三相PWMインバータ学習ソフトウェアの理論的正確性・学習効果を向上させるための改善計画。
優先度順に6項目を定義し、各項目の変更仕様・影響範囲・検証方法を記述する。

---

## 依存関係グラフ

```
IMPROVE-1 (dt不整合修正)
    ↓
IMPROVE-3 (定常状態表示) ←── 独立可 ── IMPROVE-2 (m_a表示)
    ↓
IMPROVE-4 (V_LL peak/RMS明示)  ← 独立
    ↓
IMPROVE-5 (FFT解析パネル) ← IMPROVE-3 が望ましい（定常波形でFFTすべき）
    ↓
IMPROVE-6 (RK4中間点電圧改善)  ← 独立
```

- IMPROVE-1 はバグ修正のため最優先で単独実施
- IMPROVE-2, IMPROVE-4 は独立して実施可能
- IMPROVE-5 は IMPROVE-3（助走区間）完了後が望ましい（定常状態のFFTが正しい結果を与えるため）

---

## IMPROVE-1: dt不整合の修正

### 問題

`ui/visualizer.py` L143-146 で計算上の `dt` と `np.linspace` が生成する実際の時間刻みが不一致になるケースが存在する。

```python
# 現状（問題あり）
dt = 1.0 / (f_c * POINTS_PER_CARRIER)   # 理想dt
n_points = int(T_sim / dt) + 1           # int()で切り捨て → 点数がずれる
t = np.linspace(0, T_sim, n_points)      # linspaceの実dtは T_sim/(n_points-1)
# → ソルバーに渡すdtと実際のdtが乖離
```

### 変更仕様

#### 対象ファイル: `ui/visualizer.py` — `_run_simulation()`

```python
# 修正後
dt = 1.0 / (f_c * POINTS_PER_CARRIER)  # [s] 基準時間刻み
n_points = int(round(T_sim / dt)) + 1   # round()で四捨五入
t = np.linspace(0, T_sim, n_points)     # [s]
dt_actual = t[1] - t[0]                 # [s] 実際の時間刻み（これをソルバーに渡す）
```

`solve_rl_load()` に渡す `dt` を `dt_actual` に変更する。

#### 対象ファイル: `tests/test_simulation.py` — 共通パラメータ

テストの共通パラメータ部分も同様に修正：

```python
N_POINTS = int(round(T_SIM / DT)) + 1
T = np.linspace(0, T_SIM, N_POINTS)
DT_ACTUAL = T[1] - T[0]  # ソルバーに渡す実際のdt
```

### 検証方法

1. 既存テスト13件が全てPASS
2. 追加テスト: `f=73, f_c=4700` 等の非整数比パラメータで、`dt_actual` と元の `dt` の乖離が解消されることを確認
3. 定常電流振幅テストが引き続き5%以内

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `ui/visualizer.py` | `_run_simulation()` のdt計算修正 |
| `tests/test_simulation.py` | 共通パラメータのdt修正 |

---

## IMPROVE-2: 変調率 m_a の表示 + クランプ通知

### 問題

- スライダで V_LL を V_dc まで上げられるが、線形変調上限 V_LL,max = √3·V_dc/2 を超えるとクランプされる
- 学習者はクランプ中であることもV_LL上限も把握できない

### 変更仕様

#### 対象ファイル: `ui/visualizer.py`

##### 2-1. 変調率テキスト表示の追加

`__init__()` にて、Figure上に `matplotlib.text.Text` オブジェクトを追加:

```python
self._ma_text = self._fig.text(
    0.02, 0.97, "", fontsize=10, verticalalignment="top",
    fontfamily="monospace"
)
```

##### 2-2. `_draw_waveforms()` でm_a計算・表示更新

```python
V_ph = results["V_ll"] / np.sqrt(3)
m_a_raw = 2.0 * V_ph / results["V_dc"]  # クランプ前の変調率
m_a = min(m_a_raw, 1.0)                  # クランプ後

if m_a_raw > 1.0:
    text = f"m_a = {m_a:.3f} (クランプ中: 指令値 {m_a_raw:.3f})"
    color = "red"
else:
    text = f"m_a = {m_a:.3f}"
    color = "black"

self._ma_text.set_text(text)
self._ma_text.set_color(color)
```

##### 2-3. results辞書にV_llを追加

`_run_simulation()` の返却辞書に `"V_ll": V_ll` を追加する。

### 検証方法

1. 既存テスト13件がPASS（表示のみの変更で計算ロジック変更なし）
2. 手動確認:
   - V_dc=300, V_ll=200 → `m_a = 0.770`（黒字）
   - V_dc=300, V_ll=300 → `m_a = 1.000 (クランプ中: 指令値 1.155)`（赤字）
   - V_dc=300, V_ll=260 → `m_a = 1.000 (クランプ中: 指令値 1.001)`（赤字の境界）

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `ui/visualizer.py` | テキスト要素追加、`_draw_waveforms()` 更新 |

---

## IMPROVE-3: 定常状態表示（助走区間の追加）

### 問題

- シミュレーション=表示=2周期のため、1周期目は過渡応答が支配的
- 学習者が定常状態の波形を正しく観察できない
- 特にL/Rが大きい（時定数が長い）パラメータで顕著

### 変更仕様

#### 対象ファイル: `ui/visualizer.py`

##### 3-1. 助走期間定数の追加

```python
# 既存
N_DISPLAY_CYCLES = 2

# 追加
N_WARMUP_CYCLES = 5  # 助走周期数（定常状態到達用）
```

##### 3-2. `_run_simulation()` の変更

```python
N_total = N_WARMUP_CYCLES + N_DISPLAY_CYCLES  # 合計シミュレーション周期数
T_sim = N_total / f                            # [s] 合計シミュレーション時間
dt = 1.0 / (f_c * POINTS_PER_CARRIER)         # [s]
n_points = int(round(T_sim / dt)) + 1
t = np.linspace(0, T_sim, n_points)
dt_actual = t[1] - t[0]

# ... シミュレーション実行（全区間）...

# 表示区間の抽出（最後のN_DISPLAY_CYCLES周期のみ）
T_display = N_DISPLAY_CYCLES / f
n_display = int(round(T_display / dt_actual)) + 1
```

返却辞書には **表示区間のみのデータ** を格納する。
時間軸は表示区間の開始を0にオフセットする。

```python
return {
    "t": t[-n_display:] - t[-n_display],  # 0起点にオフセット
    "v_u": v_u[-n_display:],
    # ... 他の信号も同様 ...
}
```

##### 3-3. 助走周期数の動的計算（オプション）

RL時定数 τ = L/R に基づき、助走周期数を自動調整する方式も検討可能:

```python
tau = L / R                            # [s] 時定数
T_cycle = 1.0 / f                      # [s] 1周期
n_warmup = max(5, int(np.ceil(5 * tau / T_cycle)))  # 5τ以上
```

ただし初期実装では固定値 `N_WARMUP_CYCLES = 5` で十分。
デフォルトパラメータ（L/R = 1ms, T_cycle = 20ms）では 5τ = 5ms = 0.25周期なので余裕がある。
L=100mH, R=0.1Ω（τ=1s）のような極端なケースで不足するが、スライダー範囲内の最悪ケース（L=100mH, R=0.1Ω）でも 5周期（100ms）は5τ=5sに対して不足。
→ **動的計算の採用を推奨**。

### 検証方法

1. 既存テスト13件がPASS（テスト側は独自に5周期シミュレーションしているため影響なし）
2. 追加テスト: 表示区間の初期値と定常振幅が近いことを確認
3. 手動確認: L=100mH, R=1Ω（τ=100ms）で表示波形に過渡応答が見えないこと

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `ui/visualizer.py` | 定数追加、`_run_simulation()` 大幅変更 |

### 性能への影響

シミュレーション点数が (5+2)/2 = 3.5倍に増加。デフォルト設定で約70,000点（現状20,001点）。
RK4のforループがボトルネックだが、70,000点程度は数百ms以内で完了する見込み。
スライダー操作時の応答性が劣化する場合は、`N_WARMUP_CYCLES` の動的削減やRK4のNumba JIT化を検討。

---

## IMPROVE-4: V_LL の peak/RMS 明示

### 問題

- 電力工学の慣習では線間電圧はRMS値で表記する（例: 三相200V = 200Vrms）
- 現在のコードではV_LLを振幅値（ピーク値）として扱っている
- 学習者が教科書の値を入力した場合に結果が乖離し混乱する

### 変更仕様

2つの選択肢が存在する:

#### 案A: UIラベル明示のみ（最小変更）

スライダーラベルを `V_LL [V]` → `V_LL(peak) [V]` に変更するのみ。
計算ロジックの変更なし。

#### 案B: RMS入力に変更（推奨）

スライダー入力をRMS値に変更し、内部でピーク値に変換する。

##### 対象ファイル: `ui/visualizer.py`

スライダー定義を変更:
```python
("V_ll", "V_LL(rms) [V]", 0, 450, V_ll_rms_default, 1),
```

`_read_params()` でRMS→peak変換:
```python
"V_ll": self._sliders["V_ll"].val * np.sqrt(2),  # [V] RMS → peak
```

##### 対象ファイル: `main.py`

デフォルト値をRMS基準に変更:
```python
"V_ll": 141.4,  # [V] 線間電圧指令RMS値 (≈ 200/√2)
```

あるいはデフォルト値自体をRMS的に意味のある値に変更:
```python
"V_ll": 200.0,  # [V] 線間電圧指令RMS値 → peak = 200√2 ≈ 283V
```

##### 注意事項

- `simulation/reference_generator.py` は **変更不要**（内部は常にpeak値を受け取る）
- テストは内部的にpeak値を直接渡しているため **変更不要**
- V_LLスライダーの最大値をRMS基準に調整: V_dc/√2 程度

### 推奨

**案Bを推奨**。ただし既存テストとの整合性維持のため、`reference_generator.py` のインターフェースは変更せず、変換はUI層（`_read_params()`）で行う。

### 検証方法

1. 既存テスト13件がPASS（simulationモジュールは変更なし）
2. 手動確認: V_LL(rms)=200V入力時の変調率が m_a = 2·(200√2/√3) / 300 ≈ 1.089 → クランプ表示

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `ui/visualizer.py` | スライダーラベル、`_read_params()` 変換 |
| `main.py` | デフォルト値調整 |

---

## IMPROVE-5: FFT解析パネルの追加

### 問題

- PWM学習の核心であるキャリア周波数と高調波スペクトルの関係が観察できない
- THD定量評価ができない
- 周波数変調率 m_f = f_c/f と高調波次数の関係が確認できない

### 変更仕様

#### 対象ファイル: `simulation/fft_analyzer.py`（新規）

純粋関数として FFT 解析機能を提供する。

```python
def analyze_spectrum(
    signal: np.ndarray,   # 時間領域信号
    dt: float,            # [s] サンプリング間隔
    f_fundamental: float  # [Hz] 基本波周波数
) -> dict:
    """信号のFFTスペクトルとTHDを計算する.

    Returns:
        {
            "freq": np.ndarray,       # [Hz] 周波数軸
            "magnitude": np.ndarray,  # スペクトル振幅（ピーク値）
            "thd": float,             # THD [%]
            "fundamental_mag": float  # 基本波振幅
        }
    """
```

##### アルゴリズム

1. **窓関数**: 定常状態波形の整数周期分（IMPROVE-3の表示区間）を使用するため、矩形窓で十分。
   非整数周期分の場合はHanning窓を適用。
2. **FFT**: `np.fft.rfft()` で片側スペクトル計算
3. **振幅**: `2 * |X(k)| / N` でピーク振幅に正規化
4. **THD計算**:

$$\text{THD} = \frac{\sqrt{\sum_{n=2}^{N_{max}} V_n^2}}{V_1} \times 100 \quad [\%]$$

$V_1$: 基本波振幅、$V_n$: n次高調波振幅、$N_{max}$: ナイキスト周波数に対応する最大次数

5. **表示範囲**: DC〜キャリア周波数の3倍程度（主要な高調波成分をカバー）

#### 対象ファイル: `ui/visualizer.py` — レイアウト変更

##### サブプロット構成の変更

4段 → 5段に拡張:
1. 指令信号 + キャリア（既存）
2. スイッチングパターン（既存）
3. 線間電圧（既存）
4. 相電流（既存）
5. **FFTスペクトル（新規）** — 線間電圧 v_uv のスペクトル + THD値表示

```python
self._fig, self._axes = plt.subplots(5, 1, figsize=(12, 11), sharex=False)
# 注意: 5段目はx軸共有しない（時間軸 vs 周波数軸）
```

5段目で表示する内容:
- 棒グラフ（`ax.bar()`）でスペクトル振幅を表示
- 基本波成分をハイライト色（青）で表示
- キャリア周波数付近の高調波を別色（赤）で表示
- テキストで THD 値を表示
- X軸: 高調波次数（0〜50次程度）or 周波数 [kHz]

##### FFTの解析対象

**線間電圧 v_uv** をデフォルトの解析対象とする。理由:
- 線間電圧が負荷に印加される実際の電圧
- 3レベルPWM波形の高調波構造が明確
- 教科書の理論（ベッセル関数展開）と直接比較可能

将来的に相電流のスペクトルも切り替え表示できるとよい。

#### 対象ファイル: `simulation/__init__.py`

新モジュールのエクスポート追加。

### 検証方法

1. 既存テスト13件がPASS
2. 追加テスト（`tests/test_simulation.py` に `TestFftAnalyzer` クラス追加）:
   - 純正弦波を入力 → 基本波のみ検出、THD ≈ 0%
   - 既知のPWM波形 → THD が理論値（解析的に計算可能な範囲）と10%以内で一致
   - 基本波振幅が入力振幅と一致
3. 手動確認:
   - m_f = f_c/f = 100 のとき、高調波が m_f ± 2, 2·m_f ± 1 等の理論的位置に出現
   - f_c を変更した際にスペクトルパターンが妥当に変化

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `simulation/fft_analyzer.py` | **新規作成** |
| `simulation/__init__.py` | エクスポート追加 |
| `ui/visualizer.py` | 5段目サブプロット追加、`_run_simulation()` にFFT呼出追加 |
| `tests/test_simulation.py` | `TestFftAnalyzer` クラス追加 |

### 性能への影響

FFT計算自体は O(N log N) で高速（70,000点で < 1ms）。描画コストの増加がスライダー応答性に影響する可能性があるが、棒グラフの更新は軽量。

---

## IMPROVE-6: RK4中間点電圧の改善

### 問題

PWM電圧はステップ状の不連続関数。現在の実装では RK4 の k2, k3 評価（t + dt/2）における電圧を t_n の値で近似しており、スイッチング遷移が dt 区間内に生じた場合に精度が1次に劣化する。

### 変更仕様

2つの選択肢:

#### 案A: 区間内一定電圧の仮定を明示化（最小変更）

現在のPWM比較器は離散時刻でのみ評価しており、dt区間内ではPWM電圧は前方ステップ（前値保持: zero-order hold）と見なせる。この仮定のもとでは、中間点の電圧は v(t_n) が正しい値であり、k4 のみ v(t_{n+1}) を使うのは不整合。

修正:
```python
# k4 も v(t_n) を使用（ZOH仮定の一貫性）
k4_u = _f(i_u[n] + dt * k3_u, v_u_n)  # v_u_n1 → v_u_n
```

これにより区間内一定電圧の仮定が一貫し、RK4が正しく4次精度となる。

#### 案B: 暗黙的台形法への変更（理論的に最適）

RL回路の時間定数を活用した解析的積分:

$$i(t_{n+1}) = i(t_n) \cdot e^{-R\Delta t/L} + \frac{v_n}{R}(1 - e^{-R\Delta t/L})$$

ZOH仮定の区間内で解析解が得られるため、数値誤差がゼロ。

```python
def solve_rl_load_analytical(...):
    alpha = np.exp(-R * dt / L)
    for n in range(n_points - 1):
        i_u[n + 1] = i_u[n] * alpha + (v_uN[n] / R) * (1.0 - alpha)
        # V, W 相同様
```

##### 案Bの利点
- 任意の dt で無条件安定（implicit method）
- ZOH仮定と完全に整合する解析解
- ループ内の計算がRK4（12回の `_f()` 呼出）→ 3回の乗算・加算に削減
- 性能が約4倍向上（IMPROVE-3の助走区間増加を相殺）

##### 案Bの欠点
- RK4を学習者に見せたい場合に目的と乖離
- 将来的に非線形負荷（例: 誘導電動機モデル）に拡張しにくい

### 推奨

**案A（ZOH一貫性修正）を初期実装**、性能問題が発生した場合に案Bへ移行。

学習目的でRK4を残しつつ、コメントで ZOH仮定を明記する。

### 検証方法

1. 既存テスト13件がPASS
2. 定常電流振幅テストの精度が向上することを確認（5% → 3% 以内を目標）
3. 三相電流和のドリフトが改善されることを確認

### 影響範囲

| ファイル | 変更内容 |
|---|---|
| `simulation/rl_load_solver.py` | RK4のk4電圧値修正 + ZOHコメント追記 |

---

## 実行スケジュール

| 順序 | 項目 | 前提 | 変更ファイル数 | 新規テスト |
|---|---|---|---|---|
| 1 | IMPROVE-1: dt不整合修正 | なし | 2 | 1 |
| 2 | IMPROVE-2: m_a表示 | なし | 1 | 0（手動確認） |
| 3 | IMPROVE-3: 定常状態表示 | IMPROVE-1 | 1 | 1 |
| 4 | IMPROVE-4: V_LL明示 | なし | 2 | 0（手動確認） |
| 5 | IMPROVE-5: FFTパネル | IMPROVE-3推奨 | 4（1新規） | 3 |
| 6 | IMPROVE-6: RK4改善 | なし | 1 | 0（既存で検証） |

### テスト合計

- 既存: 13件
- 追加予定: 約5件
- 最終合計: 約18件

---

## リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| IMPROVE-3 で計算量3.5倍 → スライダー応答遅延 | UX劣化 | IMPROVE-6 案B（解析解）への切替で4倍高速化 |
| IMPROVE-5 のFFTパネル追加で画面が狭くなる | 視認性低下 | figsize拡大、またはタブ切替UIに変更 |
| IMPROVE-4 で既存ユーザのパラメータ感覚が変わる | 混乱 | デフォルト値を実用的な値に設定（例: 200Vrms） |
| IMPROVE-6 案Aで理論精度改善が限定的 | 期待外れ | 案B（解析解）への段階的移行パスを確保 |
