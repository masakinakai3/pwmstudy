"""三角波キャリア生成モジュール.

PWM比較に使用する対称三角波キャリア信号を生成する。
"""

import numpy as np


def generate_carrier(
    f_c: float,    # [Hz] キャリア周波数
    t: np.ndarray  # [s] 時間配列
) -> np.ndarray:
    """対称三角波キャリア信号を生成する.

    Args:
        f_c: キャリア周波数 [Hz]
        t: 時間配列 [s]

    Returns:
        v_carrier: 三角波信号、値域 [-1, 1]
    """
    phase = (t * f_c) % 1.0  # キャリア1周期内の位相 [0, 1)
    v_carrier = np.where(phase < 0.5, 4.0 * phase - 1.0, 3.0 - 4.0 * phase)

    return v_carrier
