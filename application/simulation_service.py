"""シミュレーション利用時のアプリケーションサービス群."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import numpy as np


def normalize_ui_display_params(
    display_params: Mapping[str, float],
    pwm_mode: str,
    fft_target: str,
    fft_window: str,
    overmod_view: bool = False,
) -> dict[str, object]:
    """UI 表示単位のパラメータを SI 単位系へ変換する.

    Args:
        display_params: UI 表示単位のパラメータ辞書。
            V_dc [V], V_ll [V RMS], f [Hz], f_c [kHz], t_d [us],
            V_on [V], R [Ω], L [mH] を含む。
        pwm_mode: PWM 方式。
        fft_target: FFT 表示対象。
        fft_window: FFT 窓関数。
        overmod_view: True のとき線形変調クランプを無効化する。

    Returns:
        simulation runner へ渡す SI 単位系の辞書。
    """
    return {
        "V_dc": float(display_params["V_dc"]),
        "V_ll": float(display_params["V_ll"]),  # [V RMS] — 変換不要（generate_reference が内部でピーク換算）
        "f": float(display_params["f"]),
        "f_c": float(display_params["f_c"]) * 1000.0,
        "t_d": float(display_params["t_d"]) * 1.0e-6,
        "V_on": float(display_params["V_on"]),
        "R": float(display_params["R"]),
        "L": float(display_params["L"]) / 1000.0,
        "pwm_mode": pwm_mode,
        "overmod_view": bool(overmod_view),
        "fft_target": fft_target,
        "fft_window": fft_window,
    }


def build_export_payload(
    results: Mapping[str, object],
    display_params: Mapping[str, float],
    timestamp: datetime | None = None,
) -> dict[str, object]:
    """シミュレーション結果から JSON 保存用 payload を組み立てる.

    Args:
        results: run_simulation() の戻り値。
        display_params: UI 表示単位のパラメータ辞書。
        timestamp: 保存時刻。省略時は現在時刻。

    Returns:
        JSON シリアライズ可能な辞書。
    """
    if timestamp is None:
        timestamp = datetime.now()

    meta = results["meta"]
    metrics = results["metrics"]
    spectra = results["spectra"]

    return {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "params": {
            "V_dc_V": float(display_params["V_dc"]),
            "V_ll_rms_V": float(display_params["V_ll"]),
            "f_Hz": float(display_params["f"]),
            "f_c_kHz": float(display_params["f_c"]),
            "t_d_us": float(display_params["t_d"]),
            "V_on_V": float(display_params["V_on"]),
            "R_ohm": float(display_params["R"]),
            "L_mH": float(display_params["L"]),
            "pwm_mode": meta["pwm_mode"],
            "fft_target": meta["fft_target"],
            "fft_window": meta["fft_window"],
        },
        "metrics": {
            "m_a": round(float(metrics["m_a"]), 4),
            "m_f": round(float(metrics["m_f"]), 1),
            "V1_pk_V": round(float(spectra["v_uv"]["fundamental_mag"]), 3),
            "THD_V_pct": round(float(spectra["v_uv"]["thd"]), 2),
            "V_rms_V": round(float(spectra["v_uv"]["rms_total"]), 3),
            "I1_theory_pk_A": round(float(metrics["I_theory"]), 4),
            "I1_fft_pk_A": round(float(metrics["I_measured"]), 4),
            "THD_I_pct": round(float(spectra["i_u"]["thd"]), 2),
            "I_rms_A": round(float(spectra["i_u"]["rms_total"]), 4),
            "PF1_fft": round(float(metrics["pf1_fft"]), 4),
            "phi_deg": round(float(np.degrees(metrics["phi"])), 2),
            "Z_ohm": round(float(metrics["Z"]), 4),
        },
    }


def build_baseline_snapshot(results: Mapping[str, object]) -> dict[str, float]:
    """ベースライン比較に必要な指標を抽出する.

    Args:
        results: run_simulation() の戻り値。

    Returns:
        ベースライン比較用の簡潔な指標辞書。
    """
    metrics = results["metrics"]
    spectra = results["spectra"]

    return {
        "m_a": float(metrics["m_a"]),
        "V1": float(spectra["v_uv"]["fundamental_mag"]),
        "THD_V": float(spectra["v_uv"]["thd"]),
        "I_measured": float(metrics["I_measured"]),
        "THD_I": float(spectra["i_u"]["thd"]),
    }