"""PWM比較器モジュール.

三相変調信号とキャリア信号を比較してスイッチングパターンを生成する。
"""

import numpy as np


def compare_pwm(
    v_u: np.ndarray,       # 正規化変調信号 U相
    v_v: np.ndarray,       # 正規化変調信号 V相
    v_w: np.ndarray,       # 正規化変調信号 W相
    v_carrier: np.ndarray  # キャリア信号
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PWM比較によりスイッチングパターンを生成する.

    各相について指令信号 > キャリアなら上アームON (1)、
    それ以外は下アームON (0)。

    Args:
        v_u: U相変調信号 [-1, 1]
        v_v: V相変調信号 [-1, 1]
        v_w: W相変調信号 [-1, 1]
        v_carrier: キャリア信号 [-1, 1]

    Returns:
        (S_u, S_v, S_w): スイッチング信号、値は 0 or 1 (int型)
    """
    S_u = (v_u > v_carrier).astype(np.int32)  # U相スイッチング
    S_v = (v_v > v_carrier).astype(np.int32)  # V相スイッチング
    S_w = (v_w > v_carrier).astype(np.int32)  # W相スイッチング

    return S_u, S_v, S_w
