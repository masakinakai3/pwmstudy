---
name: verify-simulation
description: "Verify current simulation behavior and shared application responses. Use when checking physical correctness, modulation-mode consistency, steady-state values, FFT metrics, or API-visible waveform payloads."
---

# シミュレーション検証スキル

## When to Use
- シミュレーションモジュール実装後の検証
- パラメータ変更後の妥当性確認
- バグ調査時の物理量チェック
- application.run_simulation() / build_web_response() の応答検証
- modulation_mode / Overmod View / scenario 適用後の確認

## Procedure

### Step 1: 三相対称性の検証
各時刻で三相の和がゼロであることを確認する。

```python
import numpy as np

from simulation.fft_analyzer import analyze_spectrum

# 電圧（変調信号）
assert np.allclose(v_u + v_v + v_w, 0, atol=1e-10), "変調信号の三相和 ≠ 0"

# 相電圧（インバータ出力）
assert np.allclose(v_uN + v_vN + v_wN, 0, atol=1e-10), "相電圧の三相和 ≠ 0"

# 線間電圧
assert np.allclose(v_uv + v_vw + v_wu, 0, atol=1e-10), "線間電圧の三相和 ≠ 0"

# 電流（定常状態のみ — 先頭の過渡応答を除外）
steady = slice(len(i_u) // 2, None)
assert np.allclose(i_u[steady] + i_v[steady] + i_w[steady], 0, atol=1e-3), "電流の三相和 ≠ 0"
```

### Step 2: 値域チェック
```python
# 変調信号: [-1, 1]
assert np.all((-1 - 1e-10 <= v_u) & (v_u <= 1 + 1e-10))

# キャリア: [-1, 1]
assert np.all((-1 - 1e-10 <= v_carrier) & (v_carrier <= 1 + 1e-10))

# スイッチング信号: {0, 1}
assert np.all(np.isin(S_u, [0, 1]))

# 線間電圧: {-V_dc, 0, +V_dc}
unique_levels = np.unique(np.round(v_uv, decimals=6))
assert set(unique_levels).issubset({-V_dc, 0, V_dc})
```

DPWM / SVPWM 系では、線間参照差の不変性とクランプ区間の存在を分けて確認する。

### Step 3: 定常状態の理論値比較
```python
# 基本波電流振幅の理論値
fft_v = analyze_spectrum(v_uN[steady], dt, f)
Z = np.sqrt(R**2 + (2 * np.pi * f * L)**2)
I_theory = fft_v["fundamental_mag"] / Z

# 定常状態の電流基本波振幅を測定
fft_i = analyze_spectrum(i_u[steady], dt, f)
I_measured = fft_i["fundamental_mag"]

# 5%以内の一致を確認
error = abs(I_measured - I_theory) / I_theory
assert error < 0.05, f"電流振幅誤差: {error*100:.1f}% (許容: 5%)"
```

### Step 4: 時間刻みの妥当性確認
```python
# キャリア1周期あたりの点数
points_per_carrier = 1 / (f_c * dt)
assert points_per_carrier >= 100, f"分解能不足: {points_per_carrier:.0f} points/carrier (要100以上)"

# dt_actual が np.linspace の実際の刻みと一致するか
dt_actual = t[1] - t[0]
assert abs(dt - dt_actual) / dt < 1e-6, "dt不整合: ソルバーのdtとnp.linspaceの刻みが不一致"
```

### Step 5: FFT / スペクトルの検証
```python
# 基本波が正しく検出されるか
result = analyze_spectrum(v_uv, dt, f)
assert result["fundamental_mag"] > 10.0, "基本波成分が検出されない"

# 純正弦波のTHDが低いことの確認
pure_sine = np.sin(2 * np.pi * f * t)
result_sine = analyze_spectrum(pure_sine, dt, f)
assert result_sine["thd"] < 1.0, f"純正弦波のTHD異常: {result_sine['thd']:.1f}%"

# THDが有限な正の値であること（PWM波形）
assert result["thd"] > 0.0, "PWM波形のTHDが0%は異常"
```

必要に応じて `PF1`, `phi`, `V1_pk`, `I1_pk`, `m_a`, `m_f` を application 層のメトリクスとして検証する。

### Step 6: 助走区間の検証
```python
# 助走周期数がRL時定数に対して十分か
tau = L / R  # [s]
T_cycle = 1.0 / f  # [s]
n_warmup = max(5, int(np.ceil(5.0 * tau / T_cycle)))
assert n_warmup * T_cycle >= 5 * tau, "助走期間が5τに不足"

# 表示区間が定常状態のみ含むか（最後のN_DISPLAY_CYCLES周期）
```

## References
- [architecture.md](../../architecture.md) — モジュール設計・データフロー
- [implementation_plan.md](../../implementation_plan.md) — 各STEP の検証方法
- [improvement_plan.md](../../improvement_plan.md) — 改善計画書
- [docs/web_api_contract.md](../../docs/web_api_contract.md) — API-visible payload の契約
