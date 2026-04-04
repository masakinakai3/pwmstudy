"""UI 非依存のシミュレーション統合処理.

Web API やデスクトップ UI の双方から再利用できるよう、
simulation 配下の pure function を束ねて構造化結果を返す。
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from simulation.carrier_generator import generate_carrier
from simulation.fft_analyzer import analyze_spectrum
from simulation.inverter_voltage import calc_inverter_voltage
from simulation.pwm_comparator import apply_deadtime, apply_sampling_mode, compare_pwm
from simulation.reference_generator import THIRD_HARMONIC_LIMIT, generate_reference
from simulation.rl_load_solver import solve_rl_load


POINTS_PER_CARRIER = 100
N_DISPLAY_CYCLES = 2
N_WARMUP_CYCLES_MIN = 5
NONIDEAL_CORRECTION_STEPS = 2
WEB_CARRIER_POINT_FACTOR = 4
SIMULATION_API_VERSION = "phase5-v1"

PWM_MODE_LABELS = {
    "natural": "Natural Sampling",
    "regular": "Regular Sampling",
    "third_harmonic": "Third Harmonic Injection",
}
FFT_TARGET_LABELS = {
    "voltage": "Line Voltage v_uv",
    "current": "Phase Current i_u",
}
FFT_WINDOW_LABELS = {
    "hann": "Hann",
    "rectangular": "Rectangular",
}


def _solve_nonideal_power_stage(
    leg_u: np.ndarray,
    leg_v: np.ndarray,
    leg_w: np.ndarray,
    V_dc: float,
    R: float,
    L: float,
    dt: float,
    V_on: float,
    v_uN_ideal: np.ndarray,
    v_vN_ideal: np.ndarray,
    v_wN_ideal: np.ndarray,
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
    """非理想インバータと RL 負荷を反復整合させる."""
    i_u, i_v, i_w = solve_rl_load(v_uN_ideal, v_vN_ideal, v_wN_ideal, R, L, dt)

    for _ in range(NONIDEAL_CORRECTION_STEPS):
        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
            leg_u,
            leg_v,
            leg_w,
            V_dc,
            i_u=i_u,
            i_v=i_v,
            i_w=i_w,
            V_on=V_on,
            inputs_are_leg_states=True,
        )
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)

    v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
        leg_u,
        leg_v,
        leg_w,
        V_dc,
        i_u=i_u,
        i_v=i_v,
        i_w=i_w,
        V_on=V_on,
        inputs_are_leg_states=True,
    )

    return v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w


def _select_downsample_indices(length: int, max_points: int) -> np.ndarray:
    """等間隔ダウンサンプリング用のインデックスを返す."""
    if max_points <= 0:
        raise ValueError("max_points must be positive.")
    if length <= max_points:
        return np.arange(length, dtype=np.int64)

    return np.linspace(0, length - 1, max_points, dtype=np.int64)


def _to_serializable_list(values: np.ndarray) -> list[float] | list[int]:
    """NumPy 配列を JSON 化しやすい Python の list へ変換する."""
    if np.issubdtype(values.dtype, np.integer):
        return values.astype(int).tolist()
    return values.astype(float).tolist()


def _build_web_fft_payload(
    spectrum: Mapping[str, object],
    max_points: int,
) -> dict[str, object]:
    """FFT 結果を web API 向けに整形する."""
    freq = np.asarray(spectrum["freq"])
    magnitude = np.asarray(spectrum["magnitude"])
    indices = _select_downsample_indices(len(freq), max_points)

    return {
        "freq": _to_serializable_list(freq[indices]),
        "magnitude": _to_serializable_list(magnitude[indices]),
        "fundamental_mag": float(spectrum["fundamental_mag"]),
        "fundamental_phase": float(spectrum["fundamental_phase"]),
        "fundamental_freq": float(spectrum["fundamental_freq"]),
        "fundamental_rms": float(spectrum["fundamental_rms"]),
        "rms_total": float(spectrum["rms_total"]),
        "thd": float(spectrum["thd"]),
        "dc_component": float(spectrum["dc_component"]),
    }


def run_simulation(params: Mapping[str, object]) -> dict[str, object]:
    """シミュレーションを実行し、UI 非依存の構造化結果辞書を返す.

    Args:
        params: SI 単位系のパラメータ辞書。
            V_dc [V], V_ll [V RMS], f [Hz], f_c [Hz], t_d [s], V_on [V],
            R [Ω], L [H], pwm_mode, fft_target, fft_window を含む。

    Returns:
        描画用途と web API 用途の双方で再利用できる結果辞書。
    """
    V_dc = float(params["V_dc"])
    V_ll = float(params["V_ll"])
    f = float(params["f"])
    f_c = float(params["f_c"])
    t_d = float(params["t_d"])
    V_on = float(params["V_on"])
    R = float(params["R"])
    L = float(params["L"])
    pwm_mode = str(params["pwm_mode"])
    fft_target = str(params["fft_target"])
    fft_window = str(params["fft_window"])

    tau = L / R
    T_cycle = 1.0 / f
    n_warmup = max(N_WARMUP_CYCLES_MIN, int(np.ceil(5.0 * tau / T_cycle)))

    n_total_cycles = n_warmup + N_DISPLAY_CYCLES
    T_sim = n_total_cycles / f
    dt = 1.0 / (f_c * POINTS_PER_CARRIER)
    n_points = int(round(T_sim / dt)) + 1
    t = np.linspace(0.0, T_sim, n_points)
    dt_actual = t[1] - t[0]

    reference_mode = "third_harmonic" if pwm_mode == "third_harmonic" else "sinusoidal"
    sampling_mode = "regular" if pwm_mode == "regular" else "natural"

    v_u_ref, v_v_ref, v_w_ref = generate_reference(V_ll, f, V_dc, t, mode=reference_mode)
    v_u_mod, v_v_mod, v_w_mod = apply_sampling_mode(
        v_u_ref,
        v_v_ref,
        v_w_ref,
        t,
        f_c,
        sampling_mode=sampling_mode,
    )
    v_carrier = generate_carrier(f_c, t)
    S_u, S_v, S_w = compare_pwm(v_u_mod, v_v_mod, v_w_mod, v_carrier)
    leg_u, leg_v, leg_w = apply_deadtime(S_u, S_v, S_w, t_d, dt_actual)

    _, _, _, v_uN_ideal, v_vN_ideal, v_wN_ideal = calc_inverter_voltage(S_u, S_v, S_w, V_dc)

    if t_d > 0.0 or V_on > 0.0:
        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w = _solve_nonideal_power_stage(
            leg_u,
            leg_v,
            leg_w,
            V_dc,
            R,
            L,
            dt_actual,
            V_on,
            v_uN_ideal,
            v_vN_ideal,
            v_wN_ideal,
        )
    else:
        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(S_u, S_v, S_w, V_dc)
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, dt_actual)

    S_u_plot = (leg_u == 1).astype(np.int32)
    S_v_plot = (leg_v == 1).astype(np.int32)
    S_w_plot = (leg_w == 1).astype(np.int32)

    T_display = N_DISPLAY_CYCLES / f
    n_display = int(round(T_display / dt_actual)) + 1
    sl = slice(-n_display, None)
    fft_slice = slice(-n_display, -1) if n_display > 1 else sl

    t_disp = t[sl] - t[-n_display]
    t_fft = t[fft_slice] - t[-n_display]

    fft_vuv = analyze_spectrum(v_uv[fft_slice], dt_actual, f, window_mode=fft_window)
    fft_vuN = analyze_spectrum(v_uN[fft_slice], dt_actual, f, window_mode=fft_window)
    fft_iu = analyze_spectrum(i_u[fft_slice], dt_actual, f, window_mode=fft_window)

    omega_voltage = 2.0 * np.pi * fft_vuN["fundamental_freq"]
    v_uv_fund = fft_vuv["fundamental_mag"] * np.cos(
        2.0 * np.pi * fft_vuv["fundamental_freq"] * t_disp + fft_vuv["fundamental_phase"]
    )
    v_uN_fund = fft_vuN["fundamental_mag"] * np.cos(
        omega_voltage * t_disp + fft_vuN["fundamental_phase"]
    )

    Z = np.sqrt(R**2 + (omega_voltage * L) ** 2)
    phi = np.arctan2(omega_voltage * L, R)
    V_uN_fund_mag = fft_vuN["fundamental_mag"]
    I_theory_peak = V_uN_fund_mag / Z
    i_u_theory = I_theory_peak * np.cos(
        omega_voltage * t_disp + fft_vuN["fundamental_phase"] - phi
    )
    I_measured = fft_iu["fundamental_mag"]
    phase_diff = fft_vuN["fundamental_phase"] - fft_iu["fundamental_phase"]
    phase_diff = np.arctan2(np.sin(phase_diff), np.cos(phase_diff))
    pf1_fft = np.cos(phase_diff)

    V_ph_peak = V_ll * np.sqrt(2.0) / np.sqrt(3.0)  # [V] V_ll は RMS
    m_a_raw = 2.0 * V_ph_peak / V_dc
    m_a_limit = THIRD_HARMONIC_LIMIT if pwm_mode == "third_harmonic" else 1.0
    m_a = min(m_a_raw, m_a_limit)

    result = {
        "meta": {
            "simulation_api_version": SIMULATION_API_VERSION,
            "pwm_mode": pwm_mode,
            "pwm_mode_label": PWM_MODE_LABELS[pwm_mode],
            "sampling_mode": sampling_mode,
            "fft_target": fft_target,
            "fft_target_label": FFT_TARGET_LABELS[fft_target],
            "fft_window": fft_window,
            "fft_window_label": FFT_WINDOW_LABELS[fft_window],
            "points_per_carrier": POINTS_PER_CARRIER,
            "n_display_cycles": N_DISPLAY_CYCLES,
            "n_warmup_cycles": n_warmup,
        },
        "time": {
            "display_s": t_disp,
            "fft_s": t_fft,
        },
        "reference": {
            "u": v_u_ref[sl],
            "v": v_v_ref[sl],
            "w": v_w_ref[sl],
        },
        "modulation": {
            "u": v_u_mod[sl],
            "v": v_v_mod[sl],
            "w": v_w_mod[sl],
        },
        "carrier": {
            "waveform": v_carrier[sl],
        },
        "switching": {
            "u": S_u_plot[sl],
            "v": S_v_plot[sl],
            "w": S_w_plot[sl],
        },
        "leg_states": {
            "u": leg_u[sl],
            "v": leg_v[sl],
            "w": leg_w[sl],
        },
        "voltages": {
            "v_uv": v_uv[sl],
            "v_vw": v_vw[sl],
            "v_wu": v_wu[sl],
            "v_uN": v_uN[sl],
            "v_vN": v_vN[sl],
            "v_wN": v_wN[sl],
            "v_uv_fund": v_uv_fund,
            "v_uN_fund": v_uN_fund,
        },
        "currents": {
            "i_u": i_u[sl],
            "i_v": i_v[sl],
            "i_w": i_w[sl],
            "i_u_theory": i_u_theory,
        },
        "spectra": {
            "v_uv": fft_vuv,
            "v_uN": fft_vuN,
            "i_u": fft_iu,
        },
        "metrics": {
            "V_dc": V_dc,
            "V_ll": V_ll,
            "V_ll_rms": V_ll,  # [V RMS] — V_ll はすでに RMS 値
            "f": f,
            "f_c": f_c,
            "t_d": t_d,
            "V_on": V_on,
            "R": R,
            "L": L,
            "dt_actual": dt_actual,
            "m_a": m_a,
            "m_a_raw": m_a_raw,
            "m_a_limit": m_a_limit,
            "m_f": f_c / f,
            "Z": Z,
            "phi": phi,
            "I_theory": I_theory_peak,
            "I_measured": I_measured,
            "pf1_fft": pf1_fft,
        },
        "t": t_disp,
        "t_fft": t_fft,
        "v_u": v_u_mod[sl],
        "v_v": v_v_mod[sl],
        "v_w": v_w_mod[sl],
        "v_carrier": v_carrier[sl],
        "S_u": S_u_plot[sl],
        "S_v": S_v_plot[sl],
        "S_w": S_w_plot[sl],
        "v_uv": v_uv[sl],
        "v_vw": v_vw[sl],
        "v_wu": v_wu[sl],
        "v_uN": v_uN[sl],
        "v_vN": v_vN[sl],
        "v_wN": v_wN[sl],
        "i_u": i_u[sl],
        "i_v": i_v[sl],
        "i_w": i_w[sl],
        "V_dc": V_dc,
        "V_ll": V_ll,
        "t_d": t_d,
        "V_on": V_on,
        "pwm_mode": pwm_mode,
        "pwm_mode_label": PWM_MODE_LABELS[pwm_mode],
        "sampling_mode": sampling_mode,
        "fft_target": fft_target,
        "fft_target_label": FFT_TARGET_LABELS[fft_target],
        "fft_window": fft_window,
        "fft_window_label": FFT_WINDOW_LABELS[fft_window],
        "m_a_limit": m_a_limit,
        "fft_vuv": fft_vuv,
        "fft_vuN": fft_vuN,
        "fft_iu": fft_iu,
        "f": f,
        "f_c": f_c,
        "v_uv_fund": v_uv_fund,
        "v_uN_fund": v_uN_fund,
        "i_u_theory": i_u_theory,
        "Z": Z,
        "phi": phi,
        "m_f": f_c / f,
        "I_theory": I_theory_peak,
        "I_measured": I_measured,
        "pf1_fft": pf1_fft,
    }

    return result


def build_web_response(results: Mapping[str, object], max_points: int = 1000) -> dict[str, object]:
    """構造化結果辞書を web API 応答向けに整形する.

    Args:
        results: run_simulation() の戻り値。
        max_points: 各配列に対する最大点数。

    Returns:
        JSON シリアライズ可能な web API 応答辞書。
    """
    display_time = np.asarray(results["time"]["display_s"])
    time_indices = _select_downsample_indices(len(display_time), max_points)
    carrier_max_points = min(len(display_time), max_points * WEB_CARRIER_POINT_FACTOR)
    carrier_indices = _select_downsample_indices(len(display_time), carrier_max_points)

    reference = results["reference"]
    modulation = results["modulation"]
    carrier = results["carrier"]
    switching = results["switching"]
    voltages = results["voltages"]
    currents = results["currents"]
    spectra = results["spectra"]
    metrics = results["metrics"]
    meta = results["meta"]

    response = {
        "meta": {
            "simulation_api_version": meta["simulation_api_version"],
            "pwm_mode": meta["pwm_mode"],
            "sampling_mode": meta["sampling_mode"],
            "fft_target": meta["fft_target"],
            "fft_window": meta["fft_window"],
            "points_per_carrier": int(meta["points_per_carrier"]),
            "n_display_cycles": int(meta["n_display_cycles"]),
            "n_warmup_cycles": int(meta["n_warmup_cycles"]),
        },
        "params": {
            "V_dc": float(metrics["V_dc"]),
            "V_ll_rms": float(metrics["V_ll_rms"]),
            "f": float(metrics["f"]),
            "f_c": float(metrics["f_c"]),
            "t_d": float(metrics["t_d"]),
            "V_on": float(metrics["V_on"]),
            "R": float(metrics["R"]),
            "L": float(metrics["L"]),
        },
        "time": _to_serializable_list(display_time[time_indices]),
        "reference": {
            "u": _to_serializable_list(np.asarray(reference["u"])[time_indices]),
            "v": _to_serializable_list(np.asarray(reference["v"])[time_indices]),
            "w": _to_serializable_list(np.asarray(reference["w"])[time_indices]),
        },
        "modulation": {
            "u": _to_serializable_list(np.asarray(modulation["u"])[time_indices]),
            "v": _to_serializable_list(np.asarray(modulation["v"])[time_indices]),
            "w": _to_serializable_list(np.asarray(modulation["w"])[time_indices]),
        },
        "carrier": _to_serializable_list(np.asarray(carrier["waveform"])[time_indices]),
        "carrier_plot": {
            "time": _to_serializable_list(display_time[carrier_indices]),
            "waveform": _to_serializable_list(np.asarray(carrier["waveform"])[carrier_indices]),
        },
        "switching": {
            "u": _to_serializable_list(np.asarray(switching["u"])[time_indices]),
            "v": _to_serializable_list(np.asarray(switching["v"])[time_indices]),
            "w": _to_serializable_list(np.asarray(switching["w"])[time_indices]),
        },
        "voltages": {
            "v_uv": _to_serializable_list(np.asarray(voltages["v_uv"])[time_indices]),
            "v_vw": _to_serializable_list(np.asarray(voltages["v_vw"])[time_indices]),
            "v_wu": _to_serializable_list(np.asarray(voltages["v_wu"])[time_indices]),
            "v_uN": _to_serializable_list(np.asarray(voltages["v_uN"])[time_indices]),
            "v_vN": _to_serializable_list(np.asarray(voltages["v_vN"])[time_indices]),
            "v_wN": _to_serializable_list(np.asarray(voltages["v_wN"])[time_indices]),
            "v_uv_fund": _to_serializable_list(np.asarray(voltages["v_uv_fund"])[time_indices]),
            "v_uN_fund": _to_serializable_list(np.asarray(voltages["v_uN_fund"])[time_indices]),
        },
        "currents": {
            "i_u": _to_serializable_list(np.asarray(currents["i_u"])[time_indices]),
            "i_v": _to_serializable_list(np.asarray(currents["i_v"])[time_indices]),
            "i_w": _to_serializable_list(np.asarray(currents["i_w"])[time_indices]),
            "i_u_theory": _to_serializable_list(np.asarray(currents["i_u_theory"])[time_indices]),
        },
        "fft": {
            "target": meta["fft_target"],
            "window": meta["fft_window"],
            "v_uv": _build_web_fft_payload(spectra["v_uv"], max_points),
            "v_uN": _build_web_fft_payload(spectra["v_uN"], max_points),
            "i_u": _build_web_fft_payload(spectra["i_u"], max_points),
        },
        "metrics": {
            "m_a": float(metrics["m_a"]),
            "m_a_raw": float(metrics["m_a_raw"]),
            "m_a_limit": float(metrics["m_a_limit"]),
            "m_f": float(metrics["m_f"]),
            "Z": float(metrics["Z"]),
            "phi": float(metrics["phi"]),
            "pf1_fft": float(metrics["pf1_fft"]),
            "I_theory": float(metrics["I_theory"]),
            "I_measured": float(metrics["I_measured"]),
            "V1_pk": float(spectra["v_uv"]["fundamental_mag"]),
            "V_rms": float(spectra["v_uv"]["rms_total"]),
            "V_LL_rms_out": float(spectra["v_uv"]["fundamental_rms"]),
            "V_LL_rms_total": float(spectra["v_uv"]["rms_total"]),
            "THD_V": float(spectra["v_uv"]["thd"]),
            "I1_pk": float(spectra["i_u"]["fundamental_mag"]),
            "I_rms": float(spectra["i_u"]["rms_total"]),
            "THD_I": float(spectra["i_u"]["thd"]),
        },
    }

    return response