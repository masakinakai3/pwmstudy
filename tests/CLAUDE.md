# tests/ — テスト規約

## フレームワーク

- `pytest` を使用
- テストは `test_simulation.py` に集約（モジュール単位のクラスで構成）

```bash
python -m pytest tests -v           # 全テスト
python -m pytest tests -k "RlLoad"  # 特定クラスのみ
```

## テストクラス構成

| テストクラス | 対象 |
| --- | --- |
| `TestReferenceGenerator` | `reference_generator.py` |
| `TestCarrierGenerator` | `carrier_generator.py` |
| `TestPwmComparator` | `pwm_comparator.py` |
| `TestInverterVoltage` | `inverter_voltage.py` |
| `TestRlLoadSolver` | `rl_load_solver.py` |
| `TestNonidealInverterModel` | 非理想統合挙動 |
| `TestFftAnalyzer` | `fft_analyzer.py` |
| `TestScenarioPresets` | `application/scenario_presets.py` |
| `TestSimulationRunnerContract` | `application/simulation_runner.py` |
| `TestApplicationServices` | `application/simulation_service.py` |
| `TestWebApi` | `webapi/app.py`, `webapi/schemas.py` |

## 共通テストパラメータ（ファイル先頭で定数定義済み）

```python
V_DC = 300.0       # [V]
V_LL = 150.0       # [V]  線間電圧指令RMS値
F = 50.0           # [Hz]
F_C = 5000.0       # [Hz]
R = 10.0           # [Ω]
L = 0.01           # [H]
POINTS_PER_CARRIER = 100
N_CYCLES = 5
T_DEAD = 4.0e-6    # [s]
V_ON = 1.0         # [V]
```

## 物理妥当性テスト（必須）

### 三相対称性

```python
assert np.allclose(v_u + v_v + v_w, 0, atol=1e-10)
assert np.allclose(i_u + i_v + i_w, 0, atol=1e-3)  # 過渡状態を除く
```

三次高調波注入では線間参照差の不変性で検証。

### 値域チェック

```python
assert np.all((-1 <= v_ref) & (v_ref <= 1))       # 変調信号
assert np.all(np.isin(S_u, [0, 1]))                # スイッチング
assert np.all(np.isin(v_uv / V_dc, [-1, 0, 1]))   # 線間電圧
```

### 定常状態理論値（誤差5%以内）

```python
Z = np.sqrt(R**2 + (2 * np.pi * f * L)**2)
I_theory = V_ph / Z
assert abs(I_measured - I_theory) / I_theory < 0.05
```

## テスト作成ガイドライン

- 新規テストは既存クラス構造に追加するか、新モジュール用に新クラスを作成
- `@pytest.mark.parametrize` で複数条件を網羅
- エッジケース: `m_a=0`, `m_a=1`, `f_c >> f`, `R→0`, `L→0`, Third Harmonic, SVPWM, DPWM, Overmod View, scenario schema, unknown-field 422 rejection
- simulation / application / API の既存テストが全て PASS することを確認
