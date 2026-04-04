---
description: "Use when writing or editing tests for simulation modules. Covers physical validation, tolerance checks, and test structure."
applyTo: "tests/**/*.py"
---

# テスト規約

## テストフレームワーク
- `pytest` を使用
- テストは `tests/test_simulation.py` に集約（モジュール単位のクラスで構成）
- 実行: `python -m pytest tests/ -v`

## 既存テスト構成（34件、7クラス）

| テストクラス | テスト数 | 対象モジュール |
|---|---|---|
| `TestReferenceGenerator` | 6 | `reference_generator.py` |
| `TestCarrierGenerator` | 2 | `carrier_generator.py` |
| `TestPwmComparator` | 6 | `pwm_comparator.py` |
| `TestInverterVoltage` | 5 | `inverter_voltage.py` |
| `TestRlLoadSolver` | 4 | `rl_load_solver.py` |
| `TestNonidealInverterModel` | 1 | `pwm_comparator.py`, `inverter_voltage.py`, `rl_load_solver.py` |
| `TestFftAnalyzer` | 10 | `fft_analyzer.py` |

## 共通テストパラメータ（ファイル先頭で定数定義済み）
```python
V_DC = 300.0   # [V]
V_LL = 200.0   # [V]
F = 50.0        # [Hz]
F_C = 5000.0    # [Hz]
R = 10.0        # [Ω]
L = 0.01        # [H]
POINTS_PER_CARRIER = 100
N_CYCLES = 5    # 定常状態到達のため5周期

T_SIM = N_CYCLES / F
DT = 1.0 / (F_C * POINTS_PER_CARRIER)
N_POINTS = int(round(T_SIM / DT)) + 1
T = np.linspace(0, T_SIM, N_POINTS)
DT_ACTUAL = T[1] - T[0]  # [s] ソルバーに渡す実際の時間刻み
T_DEAD = 4.0e-6  # [s]
V_ON = 1.0       # [V]
```

## 物理妥当性テスト（必須）
各シミュレーションモジュールに対して以下を検証:

### 三相対称性
```python
assert np.allclose(v_u + v_v + v_w, 0, atol=1e-10)
assert np.allclose(i_u + i_v + i_w, 0, atol=1e-3)  # 過渡状態を除く
```

三次高調波注入では参照三相和が 0 にならないため、代わりに線間参照差の不変性を確認する。

### 値域チェック
```python
assert np.all((-1 <= v_ref) & (v_ref <= 1))          # 変調信号
assert np.all(np.isin(S_u, [0, 1]))                   # スイッチング
assert np.all(np.isin(v_uv / V_dc, [-1, 0, 1]))      # 線間電圧
```

### 定常状態理論値
```python
# 電流振幅の理論値との一致（誤差5%以内）
Z = np.sqrt(R**2 + (2 * np.pi * f * L)**2)
I_theory = V_ph / Z
assert abs(I_measured - I_theory) / I_theory < 0.05
```

## テスト構成
- 新規テストは既存のクラス構造に追加するか、新モジュール用に新クラスを作成する
- リグレッション: 変更後は既存34件が全て PASS することを確認する
- パラメータ化テスト `@pytest.mark.parametrize` で複数条件を網羅
- エッジケース: m_a = 0, m_a = 1, f_c >> f, R → 0, L → 0, Third Harmonic Injection, Regular Sampling
