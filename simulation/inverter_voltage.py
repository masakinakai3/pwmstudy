"""インバータ電圧演算モジュール.

スイッチングパターンから線間電圧および相電圧（負荷中性点基準）を計算する。
"""

import numpy as np


def _normalize_leg_state(S_x: np.ndarray) -> np.ndarray:
    """入力配列をレグ状態 {-1, 0, +1} へ正規化する.

    Args:
        S_x: 上アームゲート信号 {0, 1} またはレグ状態 {-1, 0, +1}

    Returns:
        レグ状態 {-1, 0, +1}
    """
    if np.all(np.isin(S_x, [0, 1])):
        return np.where(S_x > 0, 1, -1).astype(np.int8)

    if np.all(np.isin(S_x, [-1, 0, 1])):
        return S_x.astype(np.int8)

    raise ValueError("Leg state must contain only {0, 1} or {-1, 0, 1}.")


def _require_leg_state(S_x: np.ndarray) -> np.ndarray:
    """レグ状態 {-1, 0, +1} を検証して返す."""
    if not np.all(np.isin(S_x, [-1, 0, 1])):
        raise ValueError("Leg state input must contain only {-1, 0, 1}.")
    return S_x.astype(np.int8)


def _calc_pole_voltage(
    leg_state: np.ndarray,               # レグ状態 {-1, 0, +1}
    i_phase: np.ndarray | None,          # [A] 相電流
    V_dc: float,                         # [V] 直流母線電圧
    V_on: float                          # [V] 導通経路の固定電圧降下
) -> np.ndarray:
    """各相の極電圧（負母線基準）を計算する.

    簡易非理想モデルとして、導通経路には固定電圧降下 V_on を与える。
    デッドタイム中（leg_state = 0）は相電流の向きで上下どちらのダイオードが
    導通するかを決める。

    Args:
        leg_state: レグ状態 {-1, 0, +1}
        i_phase: 相電流 [A]
        V_dc: 直流母線電圧 [V]
        V_on: 導通経路の固定電圧降下 [V]

    Returns:
        極電圧（負母線基準） [V]
    """
    if np.any(leg_state == 0):
        if i_phase is None:
            raise ValueError(
                "Phase current is required when deadtime leg states are present."
            )
        upper_path = (leg_state == 1) | ((leg_state == 0) & (i_phase < 0.0))
    else:
        upper_path = leg_state == 1

    lower_level = V_on
    upper_level = V_dc - V_on

    return np.where(upper_path, upper_level, lower_level)


def calc_inverter_voltage(
    S_u: np.ndarray,  # U相スイッチング信号 {0, 1}
    S_v: np.ndarray,  # V相スイッチング信号 {0, 1}
    S_w: np.ndarray,  # W相スイッチング信号 {0, 1}
    V_dc: float,      # [V] 直流母線電圧
    i_u: np.ndarray | None = None,  # [A] U相電流
    i_v: np.ndarray | None = None,  # [A] V相電流
    i_w: np.ndarray | None = None,  # [A] W相電流
    V_on: float = 0.0,              # [V] 導通経路の固定電圧降下
    inputs_are_leg_states: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray,
           np.ndarray, np.ndarray, np.ndarray]:
    """インバータ出力の線間電圧と相電圧を計算する.

    Args:
        S_u: U相上アームゲート信号 {0, 1} またはレグ状態 {-1, 0, +1}
        S_v: V相上アームゲート信号 {0, 1} またはレグ状態 {-1, 0, +1}
        S_w: W相上アームゲート信号 {0, 1} またはレグ状態 {-1, 0, +1}
        V_dc: 直流母線電圧 [V]
        i_u: U相電流 [A]。デッドタイム状態を含む場合に必要
        i_v: V相電流 [A]。デッドタイム状態を含む場合に必要
        i_w: W相電流 [A]。デッドタイム状態を含む場合に必要
        V_on: 導通経路の固定電圧降下 [V]
        inputs_are_leg_states: True のとき S_u, S_v, S_w を
            レグ状態 {-1, 0, +1} として解釈する

    Returns:
        (v_uv, v_vw, v_wu, v_uN, v_vN, v_wN):
            線間電圧3相 [V] と相電圧3相（負荷中性点基準）[V]
    """
    if V_on < 0.0:
        raise ValueError("V_on must be non-negative.")

    if inputs_are_leg_states:
        leg_u = _require_leg_state(S_u)
        leg_v = _require_leg_state(S_v)
        leg_w = _require_leg_state(S_w)
    else:
        leg_u = _normalize_leg_state(S_u)
        leg_v = _normalize_leg_state(S_v)
        leg_w = _normalize_leg_state(S_w)

    # 各相の極電圧（負母線基準）
    v_uO = _calc_pole_voltage(leg_u, i_u, V_dc, V_on)  # [V]
    v_vO = _calc_pole_voltage(leg_v, i_v, V_dc, V_on)  # [V]
    v_wO = _calc_pole_voltage(leg_w, i_w, V_dc, V_on)  # [V]

    # 線間電圧
    v_uv = v_uO - v_vO  # [V]
    v_vw = v_vO - v_wO  # [V]
    v_wu = v_wO - v_uO  # [V]

    # 相電圧（負荷中性点基準）
    v_nO = (v_uO + v_vO + v_wO) / 3.0  # [V] 負荷中性点の極電圧
    v_uN = v_uO - v_nO  # [V]
    v_vN = v_vO - v_nO  # [V]
    v_wN = v_wO - v_nO  # [V]

    return v_uv, v_vw, v_wu, v_uN, v_vN, v_wN
