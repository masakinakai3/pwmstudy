# SPDX-License-Identifier: MIT
"""三相指令信号生成モジュール.

線間電圧指令から三相の正規化変調信号を生成する。
"""

import numpy as np


THIRD_HARMONIC_LIMIT = 2.0 / np.sqrt(3.0)


def _normalize_reference_mode(reference_mode: str) -> str:
    """旧 mode 名を含む参照生成方式名を正規化する."""
    if reference_mode == "svpwm":
        return "minmax"
    return reference_mode


def _normalize_clamp_mode(clamp_mode: str) -> str:
    """旧 mode 名を含むクランプ方式名を正規化する."""
    if clamp_mode == "three_phase":
        return "continuous"
    if clamp_mode == "two_phase":
        return "dpwm1"
    return clamp_mode


def _apply_discontinuous_offset(
    v_u: np.ndarray,
    v_v: np.ndarray,
    v_w: np.ndarray,
    theta: np.ndarray,
    clamp_mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """不連続 PWM の零相オフセットを加える."""
    phase_stack = np.vstack((v_u, v_v, v_w))
    v_max = np.max(phase_stack, axis=0)
    v_min = np.min(phase_stack, axis=0)

    if clamp_mode == "dpwm3":
        use_upper_clamp = (v_max + v_min) <= 0.0
    else:
        sector = np.floor(np.mod(theta, 2.0 * np.pi) / (np.pi / 3.0)).astype(int)
        use_upper_clamp = (sector % 2) == 1
        if clamp_mode == "dpwm2":
            use_upper_clamp = np.logical_not(use_upper_clamp)

    zero_sequence = np.where(use_upper_clamp, 1.0 - v_max, -1.0 - v_min)
    return v_u + zero_sequence, v_v + zero_sequence, v_w + zero_sequence


def _validate_reference_mode(mode: str) -> None:
    """参照生成モード名を検証する."""
    valid_modes = {"sinusoidal", "third_harmonic", "minmax", "svpwm"}
    if mode not in valid_modes:
        raise ValueError(f"Unsupported reference mode: {mode}")


def _validate_clamp_mode(clamp_mode: str) -> None:
    """クランプ方式名を検証する."""
    valid_clamp_modes = {"continuous", "dpwm1", "dpwm2", "dpwm3", "three_phase", "two_phase"}
    if clamp_mode not in valid_clamp_modes:
        raise ValueError(f"Unsupported clamp mode: {clamp_mode}")


def generate_reference(
    V_ll: float,  # [V] 線間電圧RMS値
    f: float,     # [Hz] 出力周波数
    V_dc: float,  # [V] 直流母線電圧
    t: np.ndarray,  # [s] 時間配列
    reference_mode: str = "sinusoidal",
    limit_linear: bool = True,
    clamp_mode: str = "continuous",
    mode: str | None = None,
    svpwm_mode: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三相正弦波の正規化変調信号を生成する.

    Args:
        V_ll: 線間電圧RMS値 [V]
        f: 出力周波数 [Hz]
        V_dc: 直流母線電圧 [V]
        t: 時間配列 [s]
        reference_mode: 参照生成方式
            sinusoidal: 正弦波参照
            third_harmonic: 三次高調波注入参照
            minmax: 空間ベクトルPWM相当の零相注入参照
        limit_linear: True の場合は線形変調上限でクランプする
        clamp_mode: クランプ方式
            continuous: 連続PWM
            dpwm1: 山頂/谷底中心の不連続PWM
            dpwm2: DPWM1 と相補の不連続PWM
            dpwm3: 山頂両脇で休止する不連続PWM
            two_phase: dpwm1 への後方互換エイリアス
        mode: 旧 reference_mode 引数名への後方互換エイリアス
        svpwm_mode: 旧 clamp_mode 引数名への後方互換エイリアス

    Returns:
        (v_u, v_v, v_w): 各相の正規化変調信号、値域 [-1, 1]
    """
    if mode is not None:
        reference_mode = mode
    if svpwm_mode is not None:
        clamp_mode = svpwm_mode

    _validate_reference_mode(reference_mode)
    _validate_clamp_mode(clamp_mode)
    reference_mode = _normalize_reference_mode(reference_mode)
    clamp_mode = _normalize_clamp_mode(clamp_mode)

    V_ph_peak = V_ll * np.sqrt(2.0) / np.sqrt(3.0)  # [V] 相電圧ピーク値 (V_ll は RMS)
    m_a = 2.0 * V_ph_peak / V_dc                      # 変調率
    if limit_linear:
        m_a_limit = THIRD_HARMONIC_LIMIT if reference_mode in {"third_harmonic", "minmax"} else 1.0
        m_a = min(m_a, m_a_limit)  # 線形変調範囲でクランプ

    omega = 2.0 * np.pi * f   # [rad/s] 角周波数

    phase_u = np.sin(omega * t)                          # U相基本波
    phase_v = np.sin(omega * t - 2.0 * np.pi / 3.0)     # V相基本波
    phase_w = np.sin(omega * t + 2.0 * np.pi / 3.0)     # W相基本波

    if reference_mode == "third_harmonic":
        zero_sequence = (m_a / 6.0) * np.sin(3.0 * omega * t)
        v_u = m_a * phase_u + zero_sequence
        v_v = m_a * phase_v + zero_sequence
        v_w = m_a * phase_w + zero_sequence
    elif reference_mode == "minmax":
        # 空間ベクトルPWMの等価零相注入。
        phase_stack = m_a * np.vstack((phase_u, phase_v, phase_w))
        v_max = np.max(phase_stack, axis=0)  # [p.u.]
        v_min = np.min(phase_stack, axis=0)  # [p.u.]
        zero_sequence = -0.5 * (v_max + v_min)
        v_u = phase_stack[0] + zero_sequence
        v_v = phase_stack[1] + zero_sequence
        v_w = phase_stack[2] + zero_sequence
    else:
        v_u = m_a * phase_u
        v_v = m_a * phase_v
        v_w = m_a * phase_w

    if clamp_mode != "continuous":
        v_u, v_v, v_w = _apply_discontinuous_offset(v_u, v_v, v_w, omega * t, clamp_mode)

    return v_u, v_v, v_w
