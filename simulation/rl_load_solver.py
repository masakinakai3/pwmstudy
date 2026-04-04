"""RL負荷電流演算モジュール.

相電圧を入力としてRL直列負荷の電流を厳密離散時間解で計算する。
"""

import numpy as np


def _calc_exact_update_coefficients(
    R: float,  # [Ω] 負荷抵抗
    L: float,  # [H] 負荷インダクタンス
    dt: float  # [s] 時間刻み
) -> tuple[float, float]:
    """RL 回路の厳密離散時間更新係数を返す.

    区分定数入力 v_n を仮定したとき、電流更新は

        i[n+1] = alpha * i[n] + beta * v[n]

    で表される。beta は expm1 を使って R*dt/L が極小の条件でも
    打ち消し誤差が出にくい形で計算する。

    Args:
        R: 負荷抵抗 [Ω]
        L: 負荷インダクタンス [H]
        dt: 時間刻み [s]

    Returns:
        (alpha, beta): 離散時間更新係数
    """
    x = R * dt / L
    alpha = np.exp(-x)

    if x == 0.0:
        beta = dt / L
    else:
        beta = (dt / L) * (-np.expm1(-x) / x)

    return float(alpha), float(beta)


def solve_rl_load(
    v_uN: np.ndarray,  # [V] U相電圧（負荷中性点基準）
    v_vN: np.ndarray,  # [V] V相電圧（負荷中性点基準）
    v_wN: np.ndarray,  # [V] W相電圧（負荷中性点基準）
    R: float,          # [Ω] 負荷抵抗
    L: float,          # [H] 負荷インダクタンス
    dt: float          # [s] 時間刻み
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RL負荷の三相電流を厳密離散時間解で計算する.

    回路方程式: v_xN(t) = R * i_x(t) + L * di_x(t)/dt
    初期条件: i_u(0) = i_v(0) = i_w(0) = 0

    PWM 電圧は各サンプル区間で区分定数とみなし、零次ホールド入力に対する
    RL 回路の解析解を 1 ステップ更新式へ落とし込む。

    Args:
        v_uN: U相電圧 [V]
        v_vN: V相電圧 [V]
        v_wN: W相電圧 [V]
        R: 負荷抵抗 [Ω]
        L: 負荷インダクタンス [H]
        dt: 時間刻み [s]

    Returns:
        (i_u, i_v, i_w): 三相電流 [A]
    """
    n_points = len(v_uN)
    voltages = np.vstack((v_uN, v_vN, v_wN))  # [V]
    currents = np.zeros((3, n_points), dtype=float)  # [A]
    alpha, beta = _calc_exact_update_coefficients(R, L, dt)

    for n in range(n_points - 1):
        currents[:, n + 1] = alpha * currents[:, n] + beta * voltages[:, n]

    return currents[0], currents[1], currents[2]
