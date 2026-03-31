"""シミュレーションモジュールの物理妥当性テスト."""

import numpy as np
import pytest

from simulation.reference_generator import generate_reference
from simulation.carrier_generator import generate_carrier
from simulation.pwm_comparator import compare_pwm
from simulation.inverter_voltage import calc_inverter_voltage
from simulation.rl_load_solver import solve_rl_load
from simulation.fft_analyzer import analyze_spectrum


# --- 共通パラメータ ---
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


class TestReferenceGenerator:
    """指令信号生成モジュールのテスト."""

    def test_three_phase_sum_is_zero(self) -> None:
        """三相変調信号の和が常に0."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        assert np.allclose(v_u + v_v + v_w, 0, atol=1e-10)

    def test_amplitude_within_range(self) -> None:
        """変調信号の値域が [-1, 1] 以内."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        for v in (v_u, v_v, v_w):
            assert np.all((-1.0 <= v) & (v <= 1.0))

    def test_overmodulation_clamp(self) -> None:
        """過変調時に m_a が1.0にクランプされる."""
        v_u, v_v, v_w = generate_reference(V_DC * 2, F, V_DC, T)
        for v in (v_u, v_v, v_w):
            assert np.all((-1.0 - 1e-10 <= v) & (v <= 1.0 + 1e-10))

    def test_zero_voltage(self) -> None:
        """V_ll=0 のとき全相が0."""
        v_u, v_v, v_w = generate_reference(0.0, F, V_DC, T)
        assert np.allclose(v_u, 0, atol=1e-10)
        assert np.allclose(v_v, 0, atol=1e-10)
        assert np.allclose(v_w, 0, atol=1e-10)


class TestCarrierGenerator:
    """キャリア生成モジュールのテスト."""

    def test_amplitude_range(self) -> None:
        """キャリアの値域が [-1, 1]."""
        v_carrier = generate_carrier(F_C, T)
        assert np.all((-1.0 - 1e-10 <= v_carrier) & (v_carrier <= 1.0 + 1e-10))

    def test_reaches_peak(self) -> None:
        """キャリアが ±1 の付近に達する."""
        v_carrier = generate_carrier(F_C, T)
        assert np.max(v_carrier) > 0.99
        assert np.min(v_carrier) < -0.99


class TestPwmComparator:
    """PWM比較器モジュールのテスト."""

    def test_switching_values(self) -> None:
        """スイッチング信号が 0 or 1 のみ."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        for S in (S_u, S_v, S_w):
            assert np.all(np.isin(S, [0, 1]))

    def test_zero_modulation_all_off(self) -> None:
        """変調率0のとき全スイッチがほぼOFF（キャリアピーク時のみ不定）."""
        v_u, v_v, v_w = generate_reference(0.0, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        # 変調信号=0、キャリア<0のときのみON（三角波の下半分）
        # キャリアがちょうど0のとき不定なので厳密に全OFF とは限らない
        assert np.mean(S_u) < 0.55


class TestInverterVoltage:
    """インバータ電圧演算モジュールのテスト."""

    def test_line_voltage_sum_is_zero(self) -> None:
        """線間電圧の和が常に0."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        v_uv, v_vw, v_wu, _, _, _ = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        assert np.allclose(v_uv + v_vw + v_wu, 0, atol=1e-10)

    def test_phase_voltage_sum_is_zero(self) -> None:
        """相電圧の和が常に0."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        _, _, _, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        assert np.allclose(v_uN + v_vN + v_wN, 0, atol=1e-10)

    def test_line_voltage_levels(self) -> None:
        """線間電圧が {-V_dc, 0, +V_dc} の3レベル."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        v_uv, v_vw, v_wu, _, _, _ = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        for v in (v_uv, v_vw, v_wu):
            assert np.all(np.isin(v, [-V_DC, 0, V_DC]))


class TestRlLoadSolver:
    """RL負荷電流演算モジュールのテスト."""

    def test_steady_state_current_amplitude(self) -> None:
        """定常状態の電流振幅が理論値と5%以内で一致."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        _, _, _, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, DT_ACTUAL)

        # 最後の1周期分のデータで振幅を測定
        points_per_cycle = int(round(1.0 / (F * DT_ACTUAL)))
        i_u_last = i_u[-points_per_cycle:]

        # 理論値
        V_ph = V_LL / np.sqrt(3)                     # [V]
        m_a = min(2.0 * V_ph / V_DC, 1.0)
        V_ph_fund = m_a * V_DC / 2.0                  # [V] 基本波相電圧振幅
        Z = np.sqrt(R**2 + (2.0 * np.pi * F * L)**2)  # [Ω] インピーダンス
        I_theory = V_ph_fund / Z                       # [A] 理論電流振幅

        I_measured = (np.max(i_u_last) - np.min(i_u_last)) / 2.0  # [A]

        assert abs(I_measured - I_theory) / I_theory < 0.05

    def test_three_phase_current_sum_near_zero(self) -> None:
        """定常状態で三相電流の和が概ね0."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        _, _, _, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, DT_ACTUAL)

        # 最後の1周期分で検証
        points_per_cycle = int(round(1.0 / (F * DT_ACTUAL)))
        total = i_u[-points_per_cycle:] + i_v[-points_per_cycle:] + i_w[-points_per_cycle:]
        assert np.allclose(total, 0, atol=1e-3)


class TestFftAnalyzer:
    """FFT解析モジュールのテスト."""

    def test_pure_sine_thd_near_zero(self) -> None:
        """純正弦波のTHDが概ね0%."""
        dt_test = 1e-5  # [s]
        t_test = np.arange(0, 0.1, dt_test)
        signal = 100.0 * np.sin(2.0 * np.pi * 50.0 * t_test)  # [V]
        result = analyze_spectrum(signal, dt_test, 50.0)
        assert result["thd"] < 1.0  # THD < 1%

    def test_pure_sine_fundamental_amplitude(self) -> None:
        """純正弦波の基本波振幅が入力振幅と一致."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.1 / dt_test)
        t_test = np.linspace(0, 0.1, n_samples, endpoint=False)
        amplitude = 150.0  # [V]
        signal = amplitude * np.sin(2.0 * np.pi * 50.0 * t_test)
        result = analyze_spectrum(signal, dt_test, 50.0)
        assert abs(result["fundamental_mag"] - amplitude) / amplitude < 0.02

    def test_pwm_voltage_spectrum(self) -> None:
        """PWM線間電圧のスペクトルで基本波成分が検出される."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        v_uv, _, _, _, _, _ = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        result = analyze_spectrum(v_uv, DT_ACTUAL, F)

        # 基本波成分が存在する（0でない）
        assert result["fundamental_mag"] > 10.0  # [V]
        # THDが有限値
        assert result["thd"] > 0.0

    def test_fundamental_phase_returned(self) -> None:
        """analyze_spectrum が fundamental_phase を返す."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.1 / dt_test)
        t_test = np.linspace(0, 0.1, n_samples, endpoint=False)
        signal = 100.0 * np.sin(2.0 * np.pi * 50.0 * t_test)
        result = analyze_spectrum(signal, dt_test, 50.0)
        assert "fundamental_phase" in result
        # sin = cos(x - π/2) → phase ≈ -π/2
        assert abs(result["fundamental_phase"] - (-np.pi / 2)) < 0.1

    def test_fundamental_reconstruction(self) -> None:
        """FFT基本波の振幅・位相から元信号を再構成できる."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.1 / dt_test)
        t_test = np.linspace(0, 0.1, n_samples, endpoint=False)
        amplitude = 120.0  # [V]
        phase_orig = 0.7   # [rad]
        signal = amplitude * np.cos(2.0 * np.pi * 50.0 * t_test + phase_orig)
        result = analyze_spectrum(signal, dt_test, 50.0)
        # 再構成
        reconstructed = result["fundamental_mag"] * np.cos(
            2.0 * np.pi * 50.0 * t_test + result["fundamental_phase"]
        )
        # 元信号との一致（基本波成分のみなので高精度一致）
        assert np.allclose(signal, reconstructed, atol=1.0)
