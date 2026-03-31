"""RL負荷電流演算モジュール.

相電圧を入力としてRL直列負荷の電流を4次ルンゲ・クッタ法で計算する。
"""

import numpy as np


def solve_rl_load(
    v_uN: np.ndarray,  # [V] U相電圧（負荷中性点基準）
    v_vN: np.ndarray,  # [V] V相電圧（負荷中性点基準）
    v_wN: np.ndarray,  # [V] W相電圧（負荷中性点基準）
    R: float,          # [Ω] 負荷抵抗
    L: float,          # [H] 負荷インダクタンス
    dt: float          # [s] 時間刻み
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RL負荷の三相電流を4次ルンゲ・クッタ法で計算する.

    回路方程式: v_xN(t) = R * i_x(t) + L * di_x(t)/dt
    初期条件: i_u(0) = i_v(0) = i_w(0) = 0

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

    i_u = np.zeros(n_points)  # [A]
    i_v = np.zeros(n_points)  # [A]
    i_w = np.zeros(n_points)  # [A]

    def _f(i: float, v: float) -> float:
        """微分方程式の右辺: di/dt = (v - R*i) / L."""
        return (v - R * i) / L

    for n in range(n_points - 1):
        # ZOH（零次ホールド）仮定: PWM電圧は各時間ステップ区間内で一定
        # k1〜k4 すべて同じ電圧 v(t_n) を使用する
        v_u_n = v_uN[n]       # [V]
        v_v_n = v_vN[n]       # [V]
        v_w_n = v_wN[n]       # [V]

        # U相 RK4
        k1_u = _f(i_u[n], v_u_n)
        k2_u = _f(i_u[n] + dt / 2.0 * k1_u, v_u_n)
        k3_u = _f(i_u[n] + dt / 2.0 * k2_u, v_u_n)
        k4_u = _f(i_u[n] + dt * k3_u, v_u_n)
        i_u[n + 1] = i_u[n] + (dt / 6.0) * (k1_u + 2.0 * k2_u + 2.0 * k3_u + k4_u)

        # V相 RK4
        k1_v = _f(i_v[n], v_v_n)
        k2_v = _f(i_v[n] + dt / 2.0 * k1_v, v_v_n)
        k3_v = _f(i_v[n] + dt / 2.0 * k2_v, v_v_n)
        k4_v = _f(i_v[n] + dt * k3_v, v_v_n)
        i_v[n + 1] = i_v[n] + (dt / 6.0) * (k1_v + 2.0 * k2_v + 2.0 * k3_v + k4_v)

        # W相 RK4
        k1_w = _f(i_w[n], v_w_n)
        k2_w = _f(i_w[n] + dt / 2.0 * k1_w, v_w_n)
        k3_w = _f(i_w[n] + dt / 2.0 * k2_w, v_w_n)
        k4_w = _f(i_w[n] + dt * k3_w, v_w_n)
        i_w[n + 1] = i_w[n] + (dt / 6.0) * (k1_w + 2.0 * k2_w + 2.0 * k3_w + k4_w)

    return i_u, i_v, i_w
