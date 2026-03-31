"""三相指令信号生成モジュール.

線間電圧指令から三相の正規化変調信号を生成する。
"""

import numpy as np


def generate_reference(
    V_ll: float,  # [V] 線間電圧振幅
    f: float,     # [Hz] 出力周波数
    V_dc: float,  # [V] 直流母線電圧
    t: np.ndarray  # [s] 時間配列
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三相正弦波の正規化変調信号を生成する.

    Args:
        V_ll: 線間電圧振幅 [V]
        f: 出力周波数 [Hz]
        V_dc: 直流母線電圧 [V]
        t: 時間配列 [s]

    Returns:
        (v_u, v_v, v_w): 各相の正規化変調信号、値域 [-1, 1]
    """
    V_ph = V_ll / np.sqrt(3)  # [V] 相電圧振幅
    m_a = 2.0 * V_ph / V_dc   # 変調率
    m_a = min(m_a, 1.0)       # 過変調防止クランプ

    omega = 2.0 * np.pi * f   # [rad/s] 角周波数

    v_u = m_a * np.sin(omega * t)                          # U相
    v_v = m_a * np.sin(omega * t - 2.0 * np.pi / 3.0)     # V相
    v_w = m_a * np.sin(omega * t + 2.0 * np.pi / 3.0)     # W相

    return v_u, v_v, v_w
