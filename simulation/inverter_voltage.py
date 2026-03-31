"""インバータ電圧演算モジュール.

スイッチングパターンから線間電圧および相電圧（負荷中性点基準）を計算する。
"""

import numpy as np


def calc_inverter_voltage(
    S_u: np.ndarray,  # U相スイッチング信号 {0, 1}
    S_v: np.ndarray,  # V相スイッチング信号 {0, 1}
    S_w: np.ndarray,  # W相スイッチング信号 {0, 1}
    V_dc: float       # [V] 直流母線電圧
) -> tuple[np.ndarray, np.ndarray, np.ndarray,
           np.ndarray, np.ndarray, np.ndarray]:
    """インバータ出力の線間電圧と相電圧を計算する.

    Args:
        S_u: U相スイッチング信号 {0, 1}
        S_v: V相スイッチング信号 {0, 1}
        S_w: W相スイッチング信号 {0, 1}
        V_dc: 直流母線電圧 [V]

    Returns:
        (v_uv, v_vw, v_wu, v_uN, v_vN, v_wN):
            線間電圧3相 [V] と相電圧3相（負荷中性点基準）[V]
    """
    # 線間電圧（3レベル: +V_dc, 0, -V_dc）
    v_uv = (S_u - S_v) * V_dc  # [V]
    v_vw = (S_v - S_w) * V_dc  # [V]
    v_wu = (S_w - S_u) * V_dc  # [V]

    # 相電圧（負荷中性点基準）
    v_uN = (V_dc / 3.0) * (2 * S_u - S_v - S_w)  # [V]
    v_vN = (V_dc / 3.0) * (2 * S_v - S_w - S_u)  # [V]
    v_wN = (V_dc / 3.0) * (2 * S_w - S_u - S_v)  # [V]

    return v_uv, v_vw, v_wu, v_uN, v_vN, v_wN
