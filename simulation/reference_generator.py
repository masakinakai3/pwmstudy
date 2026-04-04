"""三相指令信号生成モジュール.

線間電圧指令から三相の正規化変調信号を生成する。
"""

import numpy as np


THIRD_HARMONIC_LIMIT = 2.0 / np.sqrt(3.0)


def _validate_reference_mode(mode: str) -> None:
    """参照生成モード名を検証する."""
    valid_modes = {"sinusoidal", "third_harmonic"}
    if mode not in valid_modes:
        raise ValueError(f"Unsupported reference mode: {mode}")


def generate_reference(
    V_ll: float,  # [V] 線間電圧振幅
    f: float,     # [Hz] 出力周波数
    V_dc: float,  # [V] 直流母線電圧
    t: np.ndarray,  # [s] 時間配列
    mode: str = "sinusoidal"
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三相正弦波の正規化変調信号を生成する.

    Args:
        V_ll: 線間電圧振幅 [V]
        f: 出力周波数 [Hz]
        V_dc: 直流母線電圧 [V]
        t: 時間配列 [s]
        mode: 参照生成方式
            sinusoidal: 正弦波参照
            third_harmonic: 三次高調波注入参照

    Returns:
        (v_u, v_v, v_w): 各相の正規化変調信号、値域 [-1, 1]
    """
    _validate_reference_mode(mode)

    V_ph = V_ll / np.sqrt(3)  # [V] 相電圧振幅
    m_a = 2.0 * V_ph / V_dc   # 変調率
    m_a_limit = THIRD_HARMONIC_LIMIT if mode == "third_harmonic" else 1.0
    m_a = min(m_a, m_a_limit)  # 線形変調範囲でクランプ

    omega = 2.0 * np.pi * f   # [rad/s] 角周波数

    phase_u = np.sin(omega * t)                          # U相基本波
    phase_v = np.sin(omega * t - 2.0 * np.pi / 3.0)     # V相基本波
    phase_w = np.sin(omega * t + 2.0 * np.pi / 3.0)     # W相基本波

    if mode == "third_harmonic":
        zero_sequence = (m_a / 6.0) * np.sin(3.0 * omega * t)
        v_u = m_a * phase_u + zero_sequence
        v_v = m_a * phase_v + zero_sequence
        v_w = m_a * phase_w + zero_sequence
    else:
        v_u = m_a * phase_u
        v_v = m_a * phase_v
        v_w = m_a * phase_w

    return v_u, v_v, v_w
