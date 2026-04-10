# SPDX-License-Identifier: MIT
"""シミュレーションモジュールの物理妥当性テスト."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from application import (
    SCENARIO_PRESETS,
    SIMULATION_API_VERSION,
    build_baseline_snapshot,
    build_export_payload,
    build_web_response,
    normalize_ui_display_params,
    run_simulation,
)
from webapi.app import app
from simulation.reference_generator import THIRD_HARMONIC_LIMIT, generate_reference
from simulation.carrier_generator import generate_carrier
from simulation.pwm_comparator import apply_deadtime, apply_sampling_mode, compare_pwm
from simulation.inverter_voltage import calc_inverter_voltage
from simulation.rl_load_solver import solve_rl_load
from simulation.fft_analyzer import analyze_spectrum


# --- 共通パラメータ ---
V_DC = 300.0   # [V]
V_LL = 150.0   # [V]  線間電圧指令RMS値 (m_a ≈ 0.816, sinusoidal線形範囲内)
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


def _run_nonideal_power_stage(
    V_ll: float,
    t_dead: float,
    V_on: float,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """非理想インバータ + RL負荷の反復整合を行うテスト用ヘルパー."""
    v_u, v_v, v_w = generate_reference(V_ll, F, V_DC, T)
    v_carrier = generate_carrier(F_C, T)
    S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
    leg_u, leg_v, leg_w = apply_deadtime(S_u, S_v, S_w, t_dead, DT_ACTUAL)

    _, _, _, v_uN_ideal, v_vN_ideal, v_wN_ideal = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
    i_u, i_v, i_w = solve_rl_load(v_uN_ideal, v_vN_ideal, v_wN_ideal, R, L, DT_ACTUAL)

    for _ in range(2):
        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
            leg_u,
            leg_v,
            leg_w,
            V_DC,
            i_u=i_u,
            i_v=i_v,
            i_w=i_w,
            V_on=V_on,
            inputs_are_leg_states=True,
        )
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, DT_ACTUAL)

    v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
        leg_u,
        leg_v,
        leg_w,
        V_DC,
        i_u=i_u,
        i_v=i_v,
        i_w=i_w,
        V_on=V_on,
        inputs_are_leg_states=True,
    )

    return v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w


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

    def test_overmodulation_view_disables_linear_clamp(self) -> None:
        """limit_linear=False では参照が ±1 を超えた過変調を観察できる."""
        v_u, v_v, v_w = generate_reference(V_DC * 2, F, V_DC, T, limit_linear=False)
        max_abs = max(np.max(np.abs(v_u)), np.max(np.abs(v_v)), np.max(np.abs(v_w)))

        assert max_abs > 1.0

    def test_zero_voltage(self) -> None:
        """V_ll=0 のとき全相が0."""
        v_u, v_v, v_w = generate_reference(0.0, F, V_DC, T)
        assert np.allclose(v_u, 0, atol=1e-10)
        assert np.allclose(v_v, 0, atol=1e-10)
        assert np.allclose(v_w, 0, atol=1e-10)

    def test_third_harmonic_injection_adds_common_mode(self) -> None:
        """三次高調波注入では零相成分が加わるが線間指令は不変."""
        v_u_sin, v_v_sin, _ = generate_reference(V_LL, F, V_DC, T)
        v_u_thi, v_v_thi, v_w_thi = generate_reference(
            V_LL,
            F,
            V_DC,
            T,
            mode="third_harmonic",
        )

        common_mode = (v_u_thi + v_v_thi + v_w_thi) / 3.0

        assert np.max(np.abs(common_mode)) > 0.01
        assert np.allclose(v_u_thi - v_v_thi, v_u_sin - v_v_sin, atol=1e-10)

    def test_third_harmonic_extends_linear_modulation_range(self) -> None:
        """三次高調波注入では自然サンプリングより高い基本波を維持できる."""
        m_a_target = 1.10
        V_ll_target = m_a_target * V_DC * np.sqrt(3.0) / (2.0 * np.sqrt(2.0))

        v_u_sin, v_v_sin, v_w_sin = generate_reference(V_ll_target, F, V_DC, T)
        v_u_thi, v_v_thi, v_w_thi = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="third_harmonic",
        )

        fund_sin = analyze_spectrum(v_u_sin - v_v_sin, DT_ACTUAL, F)["fundamental_mag"]
        fund_thi = analyze_spectrum(v_u_thi - v_v_thi, DT_ACTUAL, F)["fundamental_mag"]

        assert np.max(np.abs(v_u_thi)) <= 1.0 + 1e-10
        assert np.max(np.abs(v_v_thi)) <= 1.0 + 1e-10
        assert np.max(np.abs(v_w_thi)) <= 1.0 + 1e-10
        assert THIRD_HARMONIC_LIMIT > 1.0
        assert fund_thi > fund_sin * 1.05

    def test_svpwm_adds_common_mode_within_linear_range(self) -> None:
        """SVPWM は零相注入を伴い、各相の振幅を線形範囲で抑える."""
        m_a_target = 1.05
        V_ll_target = m_a_target * V_DC * np.sqrt(3.0) / (2.0 * np.sqrt(2.0))

        v_u_sin, v_v_sin, _ = generate_reference(V_ll_target, F, V_DC, T)
        v_u_svpwm, v_v_svpwm, v_w_svpwm = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="svpwm",
        )
        common_mode = (v_u_svpwm + v_v_svpwm + v_w_svpwm) / 3.0
        fund_sin = analyze_spectrum(v_u_sin - v_v_sin, DT_ACTUAL, F)["fundamental_mag"]
        fund_svpwm = analyze_spectrum(v_u_svpwm - v_v_svpwm, DT_ACTUAL, F)["fundamental_mag"]

        assert np.max(np.abs(common_mode)) > 0.01
        assert np.max(np.abs(v_u_svpwm)) <= 1.0 + 1e-10
        assert np.max(np.abs(v_v_svpwm)) <= 1.0 + 1e-10
        assert np.max(np.abs(v_w_svpwm)) <= 1.0 + 1e-10
        assert fund_svpwm > fund_sin * 1.03

    def test_svpwm_dpwm1_clamps_one_leg_and_preserves_line_voltage(self) -> None:
        """SVPWM の DPWM1 では1相クランプが生じ、線間参照差は3相変調と一致する."""
        V_ll_target = 180.0
        v_u_3p, v_v_3p, v_w_3p = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="svpwm",
            svpwm_mode="three_phase",
        )
        v_u_2p, v_v_2p, v_w_2p = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="svpwm",
            svpwm_mode="dpwm1",
        )

        phase_stack_2p = np.vstack((v_u_2p, v_v_2p, v_w_2p))
        clamped_metric = np.max(np.abs(phase_stack_2p), axis=0)

        assert np.allclose(clamped_metric, 1.0, atol=1e-10)
        assert np.allclose(v_u_2p - v_v_2p, v_u_3p - v_v_3p, atol=1e-10)

    def test_carrier_based_dpwm1_uses_peak_centered_clamp(self) -> None:
        """三角波比較向け DPWM1 は山頂中心の60度クランプを作る."""
        V_ll_target = 170.0
        v_u_3p, v_v_3p, _ = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="three_phase",
        )
        v_u_2p, v_v_2p, v_w_2p = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="dpwm1",
        )
        phase_stack_2p = np.vstack((v_u_2p, v_v_2p, v_w_2p))
        clamped_metric = np.max(np.abs(phase_stack_2p), axis=0)
        t_cycle = np.linspace(0.0, 1.0 / F, 3601)
        angles_deg = t_cycle / t_cycle[-1] * 360.0
        v_u_cycle, _, _ = generate_reference(
            V_ll_target,
            F,
            V_DC,
            t_cycle,
            mode="sinusoidal",
            svpwm_mode="dpwm1",
        )
        idx_30 = np.argmin(np.abs(angles_deg - 30.0))
        idx_90 = np.argmin(np.abs(angles_deg - 90.0))
        idx_150 = np.argmin(np.abs(angles_deg - 150.0))

        assert np.allclose(v_u_2p - v_v_2p, v_u_3p - v_v_3p, atol=1e-10)
        assert np.mean(np.isclose(clamped_metric, 1.0, atol=1e-10)) > 0.9
        assert np.isclose(v_u_cycle[idx_90], 1.0, atol=1e-10)
        assert not np.isclose(v_u_cycle[idx_30], 1.0, atol=1e-10)
        assert not np.isclose(v_u_cycle[idx_150], 1.0, atol=1e-10)

    def test_carrier_based_dpwm3_keeps_peak_unclamped(self) -> None:
        """DPWM3 は山頂で張り付かず、両脇で休止する M 字型挙動を持つ."""
        V_ll_target = 170.0
        t_cycle = np.linspace(0.0, 1.0 / F, 3601)
        angles_deg = t_cycle / t_cycle[-1] * 360.0
        v_u_dpwm3, _, _ = generate_reference(
            V_ll_target,
            F,
            V_DC,
            t_cycle,
            mode="sinusoidal",
            svpwm_mode="dpwm3",
        )
        idx_30 = np.argmin(np.abs(angles_deg - 30.0))
        idx_90 = np.argmin(np.abs(angles_deg - 90.0))
        idx_150 = np.argmin(np.abs(angles_deg - 150.0))

        assert np.isclose(v_u_dpwm3[idx_30], 1.0, atol=1e-10)
        assert not np.isclose(v_u_dpwm3[idx_90], 1.0, atol=1e-10)
        assert np.isclose(v_u_dpwm3[idx_150], 1.0, atol=1e-10)

    def test_dpwm2_produces_distinct_waveform_from_dpwm1(self) -> None:
        """DPWM2 は DPWM1 と異なるクランプパターンを持つ."""
        V_ll_target = 170.0
        v_u_dpwm1, v_v_dpwm1, _ = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="dpwm1",
        )
        v_u_dpwm2, v_v_dpwm2, _ = generate_reference(
            V_ll_target,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="dpwm2",
        )

        assert not np.allclose(v_u_dpwm1, v_u_dpwm2, atol=1e-10)
        assert np.allclose(v_u_dpwm2 - v_v_dpwm2, v_u_dpwm1 - v_v_dpwm1, atol=1e-10)

    def test_two_phase_alias_maps_to_dpwm1(self) -> None:
        """旧 two_phase 指定は後方互換として DPWM1 と同値."""
        v_u_alias, v_v_alias, v_w_alias = generate_reference(
            V_LL,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="two_phase",
        )
        v_u_dpwm1, v_v_dpwm1, v_w_dpwm1 = generate_reference(
            V_LL,
            F,
            V_DC,
            T,
            mode="sinusoidal",
            svpwm_mode="dpwm1",
        )

        assert np.allclose(v_u_alias, v_u_dpwm1, atol=1e-10)
        assert np.allclose(v_v_alias, v_v_dpwm1, atol=1e-10)
        assert np.allclose(v_w_alias, v_w_dpwm1, atol=1e-10)


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

    def test_apply_deadtime_zero_returns_ideal_leg_state(self) -> None:
        """t_dead=0 では理想レグ状態に一致する."""
        S_x = np.array([0, 0, 1, 1, 0], dtype=np.int32)
        leg_u, _, _ = apply_deadtime(S_x, S_x, S_x, 0.0, 1.0e-6)
        expected = np.array([-1, -1, 1, 1, -1], dtype=np.int8)
        assert np.array_equal(leg_u, expected)

    def test_apply_deadtime_inserts_both_off_interval(self) -> None:
        """デッドタイム中はレグ状態が 0 になる."""
        S_x = np.array([0, 0, 1, 1, 1], dtype=np.int32)
        leg_u, _, _ = apply_deadtime(S_x, S_x, S_x, 2.0e-6, 1.0e-6)
        expected = np.array([-1, -1, 0, 0, 1], dtype=np.int8)
        assert np.array_equal(leg_u, expected)

    def test_unsupported_sampling_mode_raises(self) -> None:
        """削除済みのサンプリング方式は拒否される."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        with pytest.raises(ValueError, match="Unsupported sampling mode: regular"):
            apply_sampling_mode(v_u, v_v, v_w, T, F_C, "regular")


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

    def test_voltage_drop_reduces_line_voltage_amplitude(self) -> None:
        """固定電圧降下 V_on により線間電圧振幅が 2*V_on 減少する."""
        S_u = np.ones(4, dtype=np.int32)
        S_v = np.zeros(4, dtype=np.int32)
        S_w = np.zeros(4, dtype=np.int32)

        v_uv, _, _, _, _, _ = calc_inverter_voltage(S_u, S_v, S_w, V_DC, V_on=V_ON)

        assert np.allclose(v_uv, V_DC - 2.0 * V_ON, atol=1e-10)

    def test_deadtime_freewheel_path_depends_on_current_direction(self) -> None:
        """デッドタイム中の極電圧が電流方向で切り替わる."""
        leg_u = np.array([0], dtype=np.int8)
        leg_v = np.array([-1], dtype=np.int8)
        leg_w = np.array([-1], dtype=np.int8)
        zeros = np.zeros(1)

        v_uv_pos, _, _, _, _, _ = calc_inverter_voltage(
            leg_u,
            leg_v,
            leg_w,
            V_DC,
            i_u=np.array([5.0]),
            i_v=zeros,
            i_w=zeros,
            V_on=V_ON,
            inputs_are_leg_states=True,
        )
        v_uv_neg, _, _, _, _, _ = calc_inverter_voltage(
            leg_u,
            leg_v,
            leg_w,
            V_DC,
            i_u=np.array([-5.0]),
            i_v=zeros,
            i_w=zeros,
            V_on=V_ON,
            inputs_are_leg_states=True,
        )

        assert np.isclose(v_uv_pos[0], 0.0, atol=1e-10)
        assert np.isclose(v_uv_neg[0], V_DC - 2.0 * V_ON, atol=1e-10)


class TestRlLoadSolver:
    """RL負荷電流演算モジュールのテスト."""

    def test_steady_state_current_amplitude(self) -> None:
        """定常状態の電流基本波振幅が理論値と5%以内で一致."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        _, _, _, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, DT_ACTUAL)

        # 最後の2周期分のデータから基本波振幅を測定
        points_two_cycles = int(round(2.0 / (F * DT_ACTUAL))) + 1
        i_u_last = i_u[-points_two_cycles:]

        # 理論値
        V_ph_peak = V_LL * np.sqrt(2.0) / np.sqrt(3.0)  # [V] V_LL は RMS
        m_a = min(2.0 * V_ph_peak / V_DC, 1.0)
        V_ph_fund = m_a * V_DC / 2.0                  # [V] 基本波相電圧振幅
        Z = np.sqrt(R**2 + (2.0 * np.pi * F * L)**2)  # [Ω] インピーダンス
        I_theory = V_ph_fund / Z                       # [A] 理論電流振幅

        I_measured = analyze_spectrum(i_u_last, DT_ACTUAL, F)["fundamental_mag"]  # [A]

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

    def test_step_response_matches_analytic_solution(self) -> None:
        """定電圧入力に対して解析解と一致する."""
        t_test = np.linspace(0.0, 0.02, 2001)
        dt_test = t_test[1] - t_test[0]
        R_test = 5.0    # [Ω]
        L_test = 0.02   # [H]
        v_step = 120.0  # [V]

        v_uN = np.full_like(t_test, v_step)
        zeros = np.zeros_like(t_test)

        i_u, _, _ = solve_rl_load(v_uN, zeros, zeros, R_test, L_test, dt_test)
        expected = (v_step / R_test) * (1.0 - np.exp(-R_test * t_test / L_test))

        assert np.allclose(i_u, expected, atol=1e-10)

    def test_zero_resistance_matches_linear_ramp(self) -> None:
        """R=0 の極限で電流が線形ランプになる."""
        t_test = np.linspace(0.0, 0.01, 1001)
        dt_test = t_test[1] - t_test[0]
        L_test = 0.01   # [H]
        v_step = 30.0   # [V]

        v_uN = np.full_like(t_test, v_step)
        zeros = np.zeros_like(t_test)

        i_u, _, _ = solve_rl_load(v_uN, zeros, zeros, 0.0, L_test, dt_test)
        expected = (v_step / L_test) * t_test

        assert np.allclose(i_u, expected, atol=1e-10)


class TestNonidealInverterModel:
    """非理想インバータモデルのテスト."""

    def test_nonideal_model_reduces_fundamental_voltage(self) -> None:
        """デッドタイムと電圧降下により基本波振幅が低下する."""
        v_uv_ideal, _, _, _, _, _, _, _, _ = _run_nonideal_power_stage(40.0, 0.0, 0.0)
        v_uv_nonideal, _, _, _, _, _, _, _, _ = _run_nonideal_power_stage(40.0, T_DEAD, V_ON)

        fft_ideal = analyze_spectrum(v_uv_ideal, DT_ACTUAL, F)
        fft_nonideal = analyze_spectrum(v_uv_nonideal, DT_ACTUAL, F)

        assert fft_nonideal["fundamental_mag"] < fft_ideal["fundamental_mag"]


class TestFftAnalyzer:
    """FFT解析モジュールのテスト."""

    def test_pure_sine_thd_near_zero(self) -> None:
        """純正弦波のTHDが概ね0%."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.1 / dt_test)
        t_test = np.linspace(0, 0.1, n_samples, endpoint=False)
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

    def test_hann_window_recovers_peak_with_approximate_frequency_hint(self) -> None:
        """Hann 窓と補間で、近傍の基本波ピークを正しく捉えられる."""
        dt_test = 1e-3  # [s]
        duration = 2.0  # [s] 周波数分解能 0.5 Hz
        n_samples = int(duration / dt_test)
        t_test = np.linspace(0, duration, n_samples, endpoint=False)
        amplitude = 80.0  # [V]
        signal = amplitude * np.cos(2.0 * np.pi * 50.0 * t_test + 0.35)

        rectangular = analyze_spectrum(
            signal,
            dt_test,
            47.0,
            window_mode="rectangular",
            enable_peak_interpolation=False,
        )
        hann = analyze_spectrum(signal, dt_test, 47.0, window_mode="hann")

        rect_error = abs(rectangular["fundamental_mag"] - amplitude) / amplitude
        hann_error = abs(hann["fundamental_mag"] - amplitude) / amplitude

        assert hann_error < rect_error
        assert hann_error < 0.02

    def test_peak_interpolation_recovers_fundamental_frequency(self) -> None:
        """ピーク補間で非整数ビンの基本波周波数を推定できる."""
        dt_test = 1e-4  # [s]
        duration = 0.137  # [s]
        n_samples = int(duration / dt_test)
        t_test = np.linspace(0, duration, n_samples, endpoint=False)
        frequency = 53.3  # [Hz]
        phase = -0.4  # [rad]
        signal = 90.0 * np.cos(2.0 * np.pi * frequency * t_test + phase)

        result = analyze_spectrum(signal, dt_test, frequency, window_mode="hann")
        phase_error = np.arctan2(
            np.sin(result["fundamental_phase"] - phase),
            np.cos(result["fundamental_phase"] - phase),
        )

        assert abs(result["fundamental_freq"] - frequency) < 0.2
        assert abs(phase_error) < 0.1

    def test_known_harmonic_composite_thd_matches_theory(self) -> None:
        """既知高調波合成波の THD が理論値と一致する."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.2 / dt_test)
        t_test = np.linspace(0, 0.2, n_samples, endpoint=False)
        fundamental = 100.0  # [V]
        harmonic_5 = 30.0  # [V]
        harmonic_7 = 10.0  # [V]
        signal = (
            fundamental * np.cos(2.0 * np.pi * 50.0 * t_test)
            + harmonic_5 * np.cos(2.0 * np.pi * 250.0 * t_test + 0.2)
            + harmonic_7 * np.cos(2.0 * np.pi * 350.0 * t_test - 0.1)
        )

        result = analyze_spectrum(signal, dt_test, 50.0, window_mode="hann")
        expected_thd = np.sqrt(harmonic_5 ** 2 + harmonic_7 ** 2) / fundamental * 100.0

        assert abs(result["thd"] - expected_thd) < 1.0

    def test_rms_metrics_are_consistent(self) -> None:
        """RMS 指標が振幅と DC 成分から一貫して計算される."""
        dt_test = 1e-5  # [s]
        n_samples = int(0.1 / dt_test)
        t_test = np.linspace(0, 0.1, n_samples, endpoint=False)
        amplitude = 70.0  # [V]
        dc_component = 20.0  # [V]
        signal = dc_component + amplitude * np.cos(2.0 * np.pi * 50.0 * t_test)

        result = analyze_spectrum(signal, dt_test, 50.0, window_mode="hann")
        expected_rms_total = np.sqrt((amplitude / np.sqrt(2.0)) ** 2 + dc_component ** 2)

        assert abs(result["fundamental_rms"] - amplitude / np.sqrt(2.0)) < 0.2
        assert abs(result["rms_total"] - expected_rms_total) < 0.2
        assert abs(result["dc_component"] - dc_component) < 0.2

    def test_current_spectrum_has_lower_thd_than_voltage(self) -> None:
        """RL 負荷では相電流の THD が線間電圧より低い."""
        v_u, v_v, v_w = generate_reference(V_LL, F, V_DC, T)
        v_carrier = generate_carrier(F_C, T)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        v_uv, _, _, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_DC)
        i_u, _, _ = solve_rl_load(v_uN, v_vN, v_wN, R, L, DT_ACTUAL)

        fft_voltage = analyze_spectrum(v_uv[:-1], DT_ACTUAL, F, window_mode="hann")
        fft_current = analyze_spectrum(i_u[:-1], DT_ACTUAL, F, window_mode="hann")

        assert fft_current["thd"] < fft_voltage["thd"]


class TestScenarioPresets:
    """学習シナリオプリセットの構成・範囲検証（IMPROVE-11）."""

    def test_all_scenarios_have_required_keys(self) -> None:
        """全シナリオが必須キーを持つことを確認する."""
        from application.modulation_config import MODULATION_MODE_LABELS
        from ui.visualizer import (
            FFT_TARGET_LABELS,
            FFT_WINDOW_LABELS,
            SCENARIO_PRESETS,
        )

        required_slider_keys = {"V_dc", "V_ll", "f", "f_c", "t_d", "V_on", "R", "L"}
        for scenario in SCENARIO_PRESETS:
            assert "label" in scenario, "label キーがない"
            assert "hint" in scenario, "hint キーがない"
            assert "sliders" in scenario, "sliders キーがない"
            assert "modulation_mode" in scenario, "modulation_mode キーがない"
            assert "overmod_view" in scenario, "overmod_view キーがない"
            assert "fft_target" in scenario, "fft_target キーがない"
            assert "fft_window" in scenario, "fft_window キーがない"
            assert set(scenario["sliders"].keys()) == required_slider_keys, (
                f"シナリオ '{scenario['label']}' の sliders キーが不正"
            )
            assert scenario["modulation_mode"] in MODULATION_MODE_LABELS, (
                f"シナリオ '{scenario['label']}' の modulation_mode が無効"
            )
            assert scenario["fft_target"] in FFT_TARGET_LABELS, (
                f"シナリオ '{scenario['label']}' の fft_target が無効"
            )
            assert scenario["fft_window"] in FFT_WINDOW_LABELS, (
                f"シナリオ '{scenario['label']}' の fft_window が無効"
            )
            assert isinstance(scenario["overmod_view"], bool), (
                f"シナリオ '{scenario['label']}' の overmod_view が bool でない"
            )

    def test_scenario_slider_values_in_valid_range(self) -> None:
        """全シナリオのスライダー値が UI の有効範囲内に収まることを確認する."""
        from ui.visualizer import SCENARIO_PRESETS

        # UIスライダーの有効範囲（表示単位: f_c [kHz], t_d [us], L [mH]）
        ranges = {
            "V_dc": (100.0, 600.0),
            "V_ll": (0.0, 450.0),
            "f":    (1.0, 200.0),
            "f_c":  (1.0, 20.0),
            "t_d":  (0.0, 10.0),
            "V_on": (0.0, 5.0),
            "R":    (0.1, 100.0),
            "L":    (0.1, 100.0),
        }
        for scenario in SCENARIO_PRESETS:
            for key, val in scenario["sliders"].items():
                lo, hi = ranges[key]
                assert lo <= val <= hi, (
                    f"シナリオ '{scenario['label']}' の "
                    f"'{key}' = {val} が範囲 [{lo}, {hi}] 外"
                )

    def test_scenario_count(self) -> None:
        """シナリオ数が現行仕様の9件であることを確認する."""
        from ui.visualizer import SCENARIO_PRESETS

        assert len(SCENARIO_PRESETS) == 9


class TestSimulationRunnerContract:
    """web 移行 Phase 0 のシミュレーション契約テスト."""

    def test_run_simulation_returns_structured_sections(self) -> None:
        """runner が UI 非依存の構造化結果辞書を返す."""
        params = {
            "V_dc": 300.0,
            "V_ll": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "voltage",
            "fft_window": "hann",
        }

        results = run_simulation(params)

        assert results["meta"]["simulation_api_version"] == SIMULATION_API_VERSION
        assert results["meta"]["modulation_mode"] == "carrier"
        assert results["meta"]["reference_mode"] == "sinusoidal"
        assert results["meta"]["sampling_mode"] == "natural"
        assert results["meta"]["clamp_mode"] == "continuous"
        assert set(results.keys()) >= {
            "meta",
            "time",
            "reference",
            "modulation",
            "carrier",
            "switching",
            "leg_states",
            "voltages",
            "currents",
            "spectra",
            "metrics",
            "diagnostics",
        }
        assert set(results["voltages"].keys()) >= {
            "v_uv",
            "v_vw",
            "v_wu",
            "v_uN",
            "v_vN",
            "v_wN",
        }
        assert set(results["currents"].keys()) >= {"i_u", "i_v", "i_w", "i_u_theory"}

        n_display = len(results["time"]["display_s"])
        assert n_display > 100
        assert len(results["reference"]["u"]) == n_display
        assert len(results["modulation"]["u"]) == n_display
        assert len(results["carrier"]["waveform"]) == n_display
        assert len(results["voltages"]["v_wN"]) == n_display
        assert len(results["currents"]["i_w"]) == n_display
        assert results["diagnostics"]["ok_count"] + results["diagnostics"]["warn_count"] == 5
        assert len(results["diagnostics"]["items"]) == 5

    def test_build_web_response_limits_points_and_keeps_metrics(self) -> None:
        """web 応答が最大点数制限と主要メトリクスを満たす."""
        params = {
            "V_dc": 300.0,
            "V_ll": 220.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 4.0e-6,
            "V_on": 1.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier_third_harmonic",
            "fft_target": "current",
            "fft_window": "hann",
        }

        results = run_simulation(params)
        response = build_web_response(results, max_points=1000)

        assert response["meta"]["simulation_api_version"] == SIMULATION_API_VERSION
        assert response["meta"]["modulation_mode"] == "carrier_third_harmonic"
        assert response["meta"]["reference_mode"] == "third_harmonic"
        assert response["meta"]["sampling_mode"] == "natural"
        assert response["meta"]["clamp_mode"] == "continuous"
        assert response["meta"]["fft_target"] == "current"
        assert len(response["time"]) <= 1000
        assert len(response["reference"]["u"]) == len(response["time"])
        assert len(response["voltages"]["v_uv"]) == len(response["time"])
        assert len(response["currents"]["i_u_theory"]) == len(response["time"])
        assert len(response["carrier_plot"]["time"]) == len(response["carrier_plot"]["waveform"])
        assert len(response["carrier_plot"]["time"]) <= 1000
        assert len(response["line_voltage_plot"]["time"]) == len(response["line_voltage_plot"]["v_uv"])
        assert len(response["line_voltage_plot"]["time"]) <= 1000
        assert len(response["phase_voltage_plot"]["time"]) == len(response["phase_voltage_plot"]["v_uN"])
        assert len(response["phase_voltage_plot"]["time"]) <= 1000
        assert len(response["switching_plot"]["time"]) <= 1000
        assert len(response["fft"]["v_uv"]["freq"]) <= 1000
        assert response["metrics"]["THD_V"] >= 0.0
        assert response["metrics"]["THD_I"] >= 0.0
        assert response["metrics"]["m_a_limit"] > 1.0
        assert response["diagnostics"]["ok_count"] + response["diagnostics"]["warn_count"] == 5
        assert len(response["diagnostics"]["items"]) == 5

    def test_overmod_view_reports_unclamped_m_a(self) -> None:
        """overmod_view=True では m_a が線形上限でクランプされない."""
        params = {
            "V_dc": 300.0,
            "V_ll": 220.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "overmod_view": True,
            "fft_target": "voltage",
            "fft_window": "hann",
        }

        results = run_simulation(params)

        assert results["meta"]["modulation_mode"] == "carrier"
        assert results["meta"]["reference_mode"] == "sinusoidal"
        assert results["meta"]["sampling_mode"] == "natural"
        assert results["meta"]["clamp_mode"] == "continuous"
        assert results["meta"]["overmod_view"] is True
        assert results["metrics"]["limit_linear"] is False
        assert results["metrics"]["m_a"] > 1.0
        assert results["metrics"]["m_a"] == results["metrics"]["m_a_raw"]

    def test_modulation_mode_switch_is_reflected_in_meta(self) -> None:
        """単一の変調方式選択が内部3軸へ正しく写像される."""
        params_space_vector = {
            "V_dc": 300.0,
            "V_ll": 180.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "space_vector",
            "overmod_view": False,
            "fft_target": "voltage",
            "fft_window": "hann",
        }
        params_space_vector_2p = dict(params_space_vector)
        params_space_vector_2p["modulation_mode"] = "space_vector_two_phase"
        params_carrier_2p = dict(params_space_vector)
        params_carrier_2p["modulation_mode"] = "carrier_two_phase"

        result_space_vector = run_simulation(params_space_vector)
        result_space_vector_2p = run_simulation(params_space_vector_2p)
        result_carrier_2p = run_simulation(params_carrier_2p)

        assert result_space_vector["meta"]["modulation_mode"] == "space_vector"
        assert result_space_vector["meta"]["reference_mode"] == "minmax"
        assert result_space_vector["meta"]["sampling_mode"] == "natural"
        assert result_space_vector["meta"]["clamp_mode"] == "continuous"
        assert result_space_vector_2p["meta"]["modulation_mode"] == "space_vector_two_phase"
        assert result_space_vector_2p["meta"]["clamp_mode"] == "dpwm1"
        assert result_carrier_2p["meta"]["modulation_mode"] == "carrier_two_phase"
        assert result_carrier_2p["meta"]["reference_mode"] == "sinusoidal"
        assert result_space_vector["meta"]["modulation_mode_label"] == "空間ベクトル"
        assert result_space_vector_2p["meta"]["modulation_mode_label"] == "空間ベクトル(二相変調)"
        assert result_carrier_2p["meta"]["modulation_mode_label"] == "三角波比較(二相変調)"

    def test_run_simulation_defaults_to_carrier_modulation(self) -> None:
        """modulation_mode を省略した場合は carrier を既定値として扱う."""
        params = {
            "V_dc": 300.0,
            "V_ll": 170.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "overmod_view": False,
            "fft_target": "voltage",
            "fft_window": "hann",
        }

        result = run_simulation(params)

        assert result["meta"]["modulation_mode"] == "carrier"
        assert result["meta"]["reference_mode"] == "sinusoidal"
        assert result["meta"]["sampling_mode"] == "natural"
        assert result["meta"]["clamp_mode"] == "continuous"

    def test_run_simulation_produces_vector_states(self) -> None:
        """結果辞書に vector_states が含まれ、全エントリが 0-7 の範囲にある."""
        params = {
            "V_dc": V_DC, "V_ll": V_LL, "f": F, "f_c": F_C,
            "t_d": 0.0, "V_on": 0.0, "R": R, "L": L,
            "modulation_mode": "carrier", "overmod_view": False,
            "fft_target": "voltage", "fft_window": "hann",
        }
        result = run_simulation(params)

        assert "vector_states" in result
        indices = np.asarray(result["vector_states"]["indices"])
        assert np.all((indices >= 0) & (indices <= 7))
        usage = result["vector_states"]["usage_pct"]
        assert len(usage) == 8
        assert abs(sum(usage) - 100.0) < 0.01

    def test_run_simulation_produces_reference_decomposition(self) -> None:
        """三次高調波注入モードで零相成分が非ゼロとなる."""
        params = {
            "V_dc": V_DC, "V_ll": V_LL, "f": F, "f_c": F_C,
            "t_d": 0.0, "V_on": 0.0, "R": R, "L": L,
            "modulation_mode": "carrier_third_harmonic", "overmod_view": False,
            "fft_target": "voltage", "fft_window": "hann",
        }
        result = run_simulation(params)

        decomp = result["reference_decomposition"]
        assert decomp["peak_pure"] >= decomp["peak_combined"]
        zero_seq = np.asarray(decomp["zero_sequence"])
        assert np.max(np.abs(zero_seq)) > 0.01

    def test_run_simulation_pure_sine_has_zero_injection(self) -> None:
        """純正弦波モードで零相成分がほぼゼロとなる."""
        params = {
            "V_dc": V_DC, "V_ll": V_LL, "f": F, "f_c": F_C,
            "t_d": 0.0, "V_on": 0.0, "R": R, "L": L,
            "modulation_mode": "carrier", "overmod_view": False,
            "fft_target": "voltage", "fft_window": "hann",
        }
        result = run_simulation(params)

        zero_seq = np.asarray(result["reference_decomposition"]["zero_sequence"])
        assert np.max(np.abs(zero_seq)) < 1e-10

    def test_run_simulation_produces_duty_ratios(self) -> None:
        """デューティ比の実測と理論が近値を返す."""
        params = {
            "V_dc": V_DC, "V_ll": V_LL, "f": F, "f_c": F_C,
            "t_d": 0.0, "V_on": 0.0, "R": R, "L": L,
            "modulation_mode": "carrier", "overmod_view": False,
            "fft_target": "voltage", "fft_window": "hann",
        }
        result = run_simulation(params)

        dr = result["duty_ratios"]
        assert len(dr["time_centers"]) > 0
        u_actual = np.asarray(dr["u"])
        u_theory = np.asarray(dr["u_theory"])
        # 理想条件 (t_d=0, V_on=0) では実測と理論は ±5% 以内
        assert np.allclose(u_actual, u_theory, atol=0.05)

    def test_run_simulation_produces_deadtime_error(self) -> None:
        """デッドタイムあり条件でデッドタイム誤差が非ゼロとなる."""
        params = {
            "V_dc": V_DC, "V_ll": V_LL, "f": F, "f_c": F_C,
            "t_d": T_DEAD, "V_on": V_ON, "R": R, "L": L,
            "modulation_mode": "carrier", "overmod_view": False,
            "fft_target": "voltage", "fft_window": "hann",
        }
        result = run_simulation(params)

        error = np.asarray(result["deadtime_error"]["v_uN"])
        assert np.max(np.abs(error)) > 0.0
        assert result["metrics"]["delta_v_dt_theory"] > 0.0


class TestApplicationServices:
    """web 移行 Phase 1 の application サービス層テスト."""

    def test_normalize_ui_display_params_converts_display_units(self) -> None:
        """UI 表示単位が SI 単位へ正しく変換される."""
        params = normalize_ui_display_params(
            {
                "V_dc": 300.0,
                "V_ll": 141.0,
                "f": 50.0,
                "f_c": 5.0,
                "t_d": 4.0,
                "V_on": 1.0,
                "R": 10.0,
                "L": 10.0,
            },
            fft_target="current",
            fft_window="hann",
            overmod_view=True,
            modulation_mode="carrier_two_phase",
        )

        assert params["V_dc"] == 300.0
        assert params["V_ll"] == 141.0
        assert params["f_c"] == 5000.0
        assert params["t_d"] == 4.0e-6
        assert params["L"] == 0.01
        assert params["modulation_mode"] == "carrier_two_phase"
        assert params["overmod_view"] is True
        assert params["fft_target"] == "current"

    def test_normalize_ui_display_params_rejects_unsupported_modulation_mode(self) -> None:
        """未対応の modulation_mode は service 層で拒否される."""
        with pytest.raises(ValueError, match="Unsupported modulation mode: invalid_mode"):
            normalize_ui_display_params(
                {
                    "V_dc": 300.0,
                    "V_ll": 141.0,
                    "f": 50.0,
                    "f_c": 5.0,
                    "t_d": 4.0,
                    "V_on": 1.0,
                    "R": 10.0,
                    "L": 10.0,
                },
                modulation_mode="invalid_mode",
            )

    def test_build_export_payload_uses_structured_results(self) -> None:
        """JSON 保存 payload が application 層だけで組み立てられる."""
        display_params = {
            "V_dc": 300.0,
            "V_ll": 141.0,
            "f": 50.0,
            "f_c": 5.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 10.0,
        }
        results = run_simulation(
            normalize_ui_display_params(
                display_params,
                fft_target="voltage",
                fft_window="hann",
                modulation_mode="carrier",
            )
        )

        payload = build_export_payload(results, display_params)

        assert payload["params"]["V_ll_rms_V"] == 141.0
        assert payload["params"]["modulation_mode"] == "carrier"
        assert payload["params"]["reference_mode"] == "sinusoidal"
        assert payload["params"]["sampling_mode"] == "natural"
        assert payload["params"]["clamp_mode"] == "continuous"
        assert payload["metrics"]["m_a"] >= 0.0
        assert payload["metrics"]["THD_V_pct"] >= 0.0
        assert payload["metrics"]["THD_I_pct"] >= 0.0

    def test_build_baseline_snapshot_matches_runner_metrics(self) -> None:
        """ベースライン比較指標が runner の結果と整合する."""
        results = run_simulation(
            normalize_ui_display_params(
                {
                    "V_dc": 300.0,
                    "V_ll": 220.0,
                    "f": 50.0,
                    "f_c": 5.0,
                    "t_d": 4.0,
                    "V_on": 1.0,
                    "R": 10.0,
                    "L": 10.0,
                },
                fft_target="current",
                fft_window="hann",
                modulation_mode="carrier_third_harmonic",
            )
        )

        snapshot = build_baseline_snapshot(results)

        assert abs(snapshot["m_a"] - results["metrics"]["m_a"]) < 1.0e-12
        assert abs(snapshot["V1"] - results["spectra"]["v_uv"]["fundamental_mag"]) < 1.0e-12
        assert abs(snapshot["I_measured"] - results["metrics"]["I_measured"]) < 1.0e-12


class TestWebApi:
    """Web API MVP の疎通と入力検証テスト."""

    def test_health_endpoint_returns_version(self) -> None:
        """health エンドポイントが API バージョンを返す."""
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "simulation_api_version": SIMULATION_API_VERSION,
        }

    def test_scenarios_endpoint_returns_shared_presets(self) -> None:
        """シナリオ API が共有 preset を返す."""
        client = TestClient(app)

        response = client.get("/scenarios")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == len(SCENARIO_PRESETS)
        assert data[0]["label"] == SCENARIO_PRESETS[0]["label"]
        assert "focus" in data[0]
        assert "hint" in data[0]

    def test_root_serves_web_ui_html(self) -> None:
        """ルートで Web UI HTML を返す."""
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Web Learning Simulator" in response.text
        assert "referencePlot" in response.text
        assert "switchingPlot" in response.text
        assert "samplingMode" not in response.text
        assert "modulationMode" in response.text
        assert "referenceMode" not in response.text
        assert "clampMode" not in response.text
        assert "showLineVuv" in response.text
        assert "showLineVvw" in response.text
        assert "showLineVwu" in response.text
        assert "section1SvpwmInfo" in response.text
        assert "svpwmPatternPlot" in response.text
        assert "section1AnimSpeed" in response.text
        assert "section1AnimPlayPause" in response.text
        assert "scenarioButtons" in response.text
        assert "comparisonPanel" in response.text
        assert "exportJsonButton" in response.text

    def test_static_assets_are_served(self) -> None:
        """静的アセットが配信される."""
        client = TestClient(app)

        css_response = client.get("/static/styles.css")
        js_response = client.get("/static/app.js")

        assert css_response.status_code == 200
        assert "plot-card" in css_response.text
        assert "scenario-grid" in css_response.text
        assert "svpwm-chip" in css_response.text
        assert js_response.status_code == 200
        assert "runSimulation" in js_response.text
        assert "fetchScenarios" in js_response.text
        assert "switchingPlot" in js_response.text
        assert "computeSvpwmSnapshot" in js_response.text
        assert "startSvpwmVectorAnimation" in js_response.text
        assert "stepSvpwmAnimation" in js_response.text
        assert "setSvpwmAnimationPaused" in js_response.text
        assert "renderSvpwmPatternPlot" in js_response.text
        assert "section1SvpwmInfo" in js_response.text
        assert "svpwmPatternPlot" in js_response.text
        assert "exportDashboardPng" in js_response.text
        assert "v_uv fundamental" in js_response.text
        assert "baseline v_uN fundamental" in js_response.text
        assert "showLineVuv" in js_response.text
        assert "samplingMode" not in js_response.text
        assert "modulationMode" in js_response.text
        assert "referenceMode" not in js_response.text
        assert "clampMode" not in js_response.text

    def test_simulate_endpoint_returns_waveforms_and_metrics(self) -> None:
        """simulate エンドポイントが主要データを返す."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["simulation_api_version"] == SIMULATION_API_VERSION
        assert data["meta"]["modulation_mode"] == "carrier"
        assert data["meta"]["fft_target"] == "v_uv"
        assert len(data["time"]) <= 1000
        assert len(data["reference"]["u"]) == len(data["time"])
        assert len(data["switching"]["u"]) == len(data["time"])
        assert len(data["switching_plot"]["time"]) == len(data["switching_plot"]["u"])
        assert len(data["switching_plot"]["time"]) <= 1000
        assert len(data["line_voltage_plot"]["time"]) == len(data["line_voltage_plot"]["v_uv"])
        assert len(data["line_voltage_plot"]["time"]) <= 1000
        assert len(data["phase_voltage_plot"]["time"]) == len(data["phase_voltage_plot"]["v_uN"])
        assert len(data["phase_voltage_plot"]["time"]) <= 1000
        assert len(data["voltages"]["v_uv"]) == len(data["time"])
        assert len(data["currents"]["i_u"]) == len(data["time"])
        assert len(data["carrier_plot"]["time"]) == len(data["carrier_plot"]["waveform"])
        assert len(data["carrier_plot"]["time"]) <= 1000
        assert data["metrics"]["m_f"] == 100.0
        assert data["metrics"]["V_LL_rms_out"] == data["fft"]["v_uv"]["fundamental_rms"]
        assert data["metrics"]["V_LL_rms_total"] == data["fft"]["v_uv"]["rms_total"]
        assert data["metrics"]["V_LL_rms_total"] >= data["metrics"]["V_LL_rms_out"]
        assert data["metrics"]["THD_V"] >= 0.0
        assert data["metrics"]["THD_I"] >= 0.0

    def test_change_point_voltage_plot_beats_uniform_downsampling(self) -> None:
        """線間電圧の切替点保持圧縮は等間隔間引きより多くの遷移を残す."""
        params = {
            "V_dc": 300.0,
            "V_ll": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "voltage",
            "fft_window": "hann",
        }

        results = run_simulation(params)
        response = build_web_response(results, max_points=1000)
        full_signal = np.asarray(results["voltages"]["v_uv"])
        uniform_signal = np.asarray(response["voltages"]["v_uv"])
        compressed_signal = np.asarray(response["line_voltage_plot"]["v_uv"])

        full_transitions = int(np.count_nonzero(full_signal[1:] != full_signal[:-1]))
        uniform_transitions = int(np.count_nonzero(uniform_signal[1:] != uniform_signal[:-1]))
        compressed_transitions = int(np.count_nonzero(compressed_signal[1:] != compressed_signal[:-1]))

        assert full_transitions > 0
        assert compressed_transitions > uniform_transitions

    def test_change_point_switching_plot_beats_uniform_downsampling(self) -> None:
        """スイッチング補助系列は 3 相合成でも等間隔間引きより遷移を残す."""
        params = {
            "V_dc": 300.0,
            "V_ll": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "voltage",
            "fft_window": "hann",
        }

        results = run_simulation(params)
        response = build_web_response(results, max_points=1000)
        full_u = np.asarray(results["switching"]["u"])
        full_v = np.asarray(results["switching"]["v"])
        full_w = np.asarray(results["switching"]["w"])
        uniform_u = np.asarray(response["switching"]["u"])
        uniform_v = np.asarray(response["switching"]["v"])
        uniform_w = np.asarray(response["switching"]["w"])
        compressed_u = np.asarray(response["switching_plot"]["u"])
        compressed_v = np.asarray(response["switching_plot"]["v"])
        compressed_w = np.asarray(response["switching_plot"]["w"])

        full_transitions = int(
            np.count_nonzero(
                (full_u[1:] != full_u[:-1])
                | (full_v[1:] != full_v[:-1])
                | (full_w[1:] != full_w[:-1])
            )
        )
        uniform_transitions = int(
            np.count_nonzero(
                (uniform_u[1:] != uniform_u[:-1])
                | (uniform_v[1:] != uniform_v[:-1])
                | (uniform_w[1:] != uniform_w[:-1])
            )
        )
        compressed_transitions = int(
            np.count_nonzero(
                (compressed_u[1:] != compressed_u[:-1])
                | (compressed_v[1:] != compressed_v[:-1])
                | (compressed_w[1:] != compressed_w[:-1])
            )
        )

        assert full_transitions > 0
        assert compressed_transitions > uniform_transitions

    def test_simulate_endpoint_validates_range(self) -> None:
        """入力範囲外は 422 を返す."""
        client = TestClient(app)
        payload = {
            "V_dc": 50.0,
            "V_ll_rms": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 422

    def test_simulate_endpoint_supports_current_fft_target(self) -> None:
        """電流 FFT ターゲットが API 契約どおり扱われる."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 141.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 4.0e-6,
            "V_on": 1.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier_third_harmonic",
            "fft_target": "i_u",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["fft_target"] == "i_u"
        assert data["fft"]["target"] == "i_u"
        assert data["metrics"]["m_a_limit"] > 1.0

    def test_simulate_endpoint_exposes_svpwm_observer_series(self) -> None:
        """空間ベクトル方式では backend 生成の観察系列を返す."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 180.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "space_vector",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        observer = data["svpwm_observer"]
        assert observer["enabled"] is True
        assert observer["switching_period_s"] > 0.0
        assert len(observer["alpha"]) == len(data["time"])
        assert len(observer["beta"]) == len(data["time"])
        assert len(observer["carrier_hold"]["time"]) == len(observer["carrier_hold"]["u"])
        assert len(observer["carrier_hold"]["time"]) > 0
        assert len(observer["windows"]) > 0

        first_window = observer["windows"][0]
        assert 1 <= first_window["sector"] <= 6
        assert first_window["t1"] >= 0.0
        assert first_window["t2"] >= 0.0
        assert first_window["t0"] >= 0.0
        assert abs(
            (first_window["t1"] + first_window["t2"] + first_window["t0"])
            - observer["switching_period_s"]
        ) < 1.0e-9
        assert first_window["sequence"][0] == "V0"
        assert first_window["sequence"][-1] == "V0"
        assert "V7" in first_window["sequence"]
        assert len(first_window["event_times_rel_s"]) == 8
        assert first_window["event_times_rel_s"][0] == 0.0
        assert abs(
            first_window["event_times_rel_s"][-1] - observer["switching_period_s"]
        ) < 1.0e-12

    def test_simulate_endpoint_two_phase_observer_uses_single_zero_vector(self) -> None:
        """空間ベクトル(二相変調)ではゼロベクトルがV0またはV7の片側に固定される."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 180.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "space_vector_two_phase",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        observer = data["svpwm_observer"]
        assert observer["enabled"] is True
        assert len(observer["windows"]) > 0

        first_window = observer["windows"][0]
        zero_vectors = [label for label in first_window["sequence"] if label in {"V0", "V7"}]
        assert len(zero_vectors) > 0
        assert len(set(zero_vectors)) == 1

    def test_simulate_endpoint_rejects_legacy_mode_fields(self) -> None:
        """旧モード関連フィールドは API 契約から外し、422 で拒否する."""
        client = TestClient(app)
        base_payload = {
            "V_dc": 300.0,
            "V_ll_rms": 180.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "space_vector",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        for field_name, field_value in [
            ("pwm_mode", "third_harmonic"),
            ("svpwm_mode", "dpwm3"),
            ("reference_mode", "sinusoidal"),
            ("sampling_mode", "regular"),
            ("clamp_mode", "continuous"),
        ]:
            payload = dict(base_payload)
            payload[field_name] = field_value

            response = client.post("/simulate", json=payload)

            assert response.status_code == 422, field_name

    def test_simulate_endpoint_accepts_overmod_checkbox(self) -> None:
        """overmod_view=True を受理し、m_a が 1 を超えるケースを返す."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 220.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "overmod_view": True,
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["reference_mode"] == "sinusoidal"
        assert data["meta"]["sampling_mode"] == "natural"
        assert data["meta"]["clamp_mode"] == "continuous"
        assert data["meta"]["overmod_view"] is True
        assert data["metrics"]["m_a"] > 1.0

    def test_simulate_endpoint_returns_dwell_times_for_svpwm(self) -> None:
        """SVPWM モードで dwell_times が observer に含まれる."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 180.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "space_vector",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        observer = data["svpwm_observer"]
        assert observer["enabled"] is True
        dt = observer["dwell_times"]
        assert len(dt["t1_ratio"]) > 0
        # T1 + T2 + T0 ≈ 1.0 for each window
        for i in range(len(dt["t1_ratio"])):
            total = dt["t1_ratio"][i] + dt["t2_ratio"][i] + dt["t0_ratio"][i]
            assert abs(total - 1.0) < 0.02

    def test_simulate_endpoint_returns_reference_decomposition(self) -> None:
        """carrier_third_harmonic で reference_decomposition が返る."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 150.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier_third_harmonic",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        decomp = data["reference_decomposition"]
        assert decomp["peak_pure"] >= decomp["peak_combined"]
        assert len(decomp["zero_sequence"]) > 0

    def test_simulate_endpoint_returns_duty_ratios(self) -> None:
        """duty_ratios がレスポンスに含まれる."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "V_ll_rms": 150.0,
            "f": 50.0,
            "f_c": 5000.0,
            "t_d": 0.0,
            "V_on": 0.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "fft_target": "v_uv",
            "fft_window": "hann",
        }

        response = client.post("/simulate", json=payload)

        assert response.status_code == 200
        data = response.json()
        dr = data["duty_ratios"]
        assert len(dr["time_centers"]) > 0
        assert len(dr["u"]) == len(dr["u_theory"])

    def test_sweep_endpoint_returns_points(self) -> None:
        """sweep エンドポイントが m_a スイープ結果を返す."""
        client = TestClient(app)
        payload = {
            "V_dc": 300.0,
            "f": 50.0,
            "f_c": 5000.0,
            "R": 10.0,
            "L": 0.01,
            "modulation_mode": "carrier",
            "n_points": 5,
            "m_a_min": 0.5,
            "m_a_max": 1.2,
        }

        response = client.post("/sweep", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert len(data["points"]) == 5
        assert data["m_a_limit"] > 0.0
        # V1 should increase with m_a
        v1_values = [p["V1_pk"] for p in data["points"]]
        assert v1_values[-1] > v1_values[0]
