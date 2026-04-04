"""PWM比較器モジュール.

三相変調信号とキャリア信号を比較してスイッチングパターンを生成する。
"""

import numpy as np


def _validate_sampling_mode(mode: str) -> None:
    """サンプリングモード名を検証する."""
    valid_modes = {"natural", "regular"}
    if mode not in valid_modes:
        raise ValueError(f"Unsupported sampling mode: {mode}")


def _apply_regular_sampling_single_phase(
    v_x: np.ndarray,  # 正規化変調信号
    f_c: float,       # [Hz] キャリア周波数
    t: np.ndarray     # [s] 時間配列
) -> np.ndarray:
    """単相変調信号へ規則サンプリングを適用する.

    各キャリア周期の中点で変調信号をサンプルし、次周期境界まで保持する。

    Args:
        v_x: 正規化変調信号 [-1, 1]
        f_c: キャリア周波数 [Hz]
        t: 時間配列 [s]

    Returns:
        規則サンプリング後の保持波形
    """
    if f_c <= 0.0:
        raise ValueError("f_c must be positive for regular sampling.")

    carrier_index = np.floor((t - t[0]) * f_c - 1.0e-12).astype(np.int64)
    carrier_index = np.maximum(carrier_index, 0)

    _, start_indices, counts = np.unique(
        carrier_index,
        return_index=True,
        return_counts=True,
    )
    sample_indices = start_indices + counts // 2
    sampled_values = v_x[sample_indices]

    return np.repeat(sampled_values, counts)[: len(v_x)]


def apply_sampling_mode(
    v_u: np.ndarray,   # 正規化変調信号 U相
    v_v: np.ndarray,   # 正規化変調信号 V相
    v_w: np.ndarray,   # 正規化変調信号 W相
    t: np.ndarray,     # [s] 時間配列
    f_c: float,        # [Hz] キャリア周波数
    sampling_mode: str = "natural"
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PWM 比較前の変調信号へサンプリング方式を適用する.

    Args:
        v_u: U相変調信号 [-1, 1]
        v_v: V相変調信号 [-1, 1]
        v_w: W相変調信号 [-1, 1]
        t: 時間配列 [s]
        f_c: キャリア周波数 [Hz]
        sampling_mode: サンプリング方式
            natural: 連続比較
            regular: キャリア周期ごとの中点サンプル値を保持

    Returns:
        PWM 比較に使う変調信号 3相
    """
    _validate_sampling_mode(sampling_mode)

    if sampling_mode == "regular":
        return (
            _apply_regular_sampling_single_phase(v_u, f_c, t),
            _apply_regular_sampling_single_phase(v_v, f_c, t),
            _apply_regular_sampling_single_phase(v_w, f_c, t),
        )

    return v_u, v_v, v_w


def _upper_gate_to_leg_state(S_x: np.ndarray) -> np.ndarray:
    """上アームゲート信号をレグ状態へ変換する.

    Args:
        S_x: 上アームゲート信号 {0, 1}

    Returns:
        レグ状態 {+1, -1}
            +1: 上アームON
            -1: 下アームON
    """
    return np.where(S_x > 0, 1, -1).astype(np.int8)


def _apply_deadtime_single_phase(
    S_x: np.ndarray,       # 上アームゲート信号 {0, 1}
    n_dead_samples: int   # [sample] デッドタイム長
) -> np.ndarray:
    """単相分のデッドタイムを適用したレグ状態を返す.

    レグ状態は以下で表す:
    - +1: 上アームON
    -  0: デッドタイム中（上下アームともOFF）
    - -1: 下アームON

    Args:
        S_x: 上アームゲート信号 {0, 1}
        n_dead_samples: デッドタイム長 [sample]

    Returns:
        デッドタイム適用後のレグ状態 {-1, 0, +1}
    """
    leg_state = _upper_gate_to_leg_state(S_x)

    if n_dead_samples <= 0:
        return leg_state

    leg_state_with_deadtime = leg_state.copy()
    transition_indices = np.flatnonzero(leg_state[1:] != leg_state[:-1]) + 1

    for index in transition_indices:
        end_index = min(index + n_dead_samples, len(leg_state_with_deadtime))
        leg_state_with_deadtime[index:end_index] = 0

    return leg_state_with_deadtime


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


def apply_deadtime(
    S_u: np.ndarray,  # U相上アームゲート信号 {0, 1}
    S_v: np.ndarray,  # V相上アームゲート信号 {0, 1}
    S_w: np.ndarray,  # W相上アームゲート信号 {0, 1}
    t_dead: float,    # [s] デッドタイム
    dt: float         # [s] サンプル時間
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """各相のゲート信号へデッドタイムを適用する.

    デッドタイム中は上下アームともOFFとし、レグ状態 0 で表す。

    Args:
        S_u: U相上アームゲート信号 {0, 1}
        S_v: V相上アームゲート信号 {0, 1}
        S_w: W相上アームゲート信号 {0, 1}
        t_dead: デッドタイム [s]
        dt: サンプル時間 [s]

    Returns:
        (leg_u, leg_v, leg_w): デッドタイム適用後のレグ状態 {-1, 0, +1}
    """
    if t_dead < 0.0:
        raise ValueError("t_dead must be non-negative.")
    if dt <= 0.0:
        raise ValueError("dt must be positive.")

    n_dead_samples = int(round(t_dead / dt))

    return (
        _apply_deadtime_single_phase(S_u, n_dead_samples),
        _apply_deadtime_single_phase(S_v, n_dead_samples),
        _apply_deadtime_single_phase(S_w, n_dead_samples),
    )
