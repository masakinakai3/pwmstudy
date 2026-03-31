"""FFT解析モジュール.

時間領域信号のスペクトル解析とTHD計算を提供する。
"""

import numpy as np


def analyze_spectrum(
    signal: np.ndarray,     # 時間領域信号
    dt: float,              # [s] サンプリング間隔
    f_fundamental: float    # [Hz] 基本波周波数
) -> dict[str, np.ndarray | float]:
    """信号のFFTスペクトルとTHDを計算する.

    Args:
        signal: 時間領域信号
        dt: サンプリング間隔 [s]
        f_fundamental: 基本波周波数 [Hz]

    Returns:
        {
            "freq": 周波数軸 [Hz],
            "magnitude": スペクトル振幅（ピーク値）,
            "thd": THD [%],
            "fundamental_mag": 基本波振幅
        }
    """
    N = len(signal)  # サンプル数

    # 片側FFT
    spectrum = np.fft.rfft(signal)
    freq = np.fft.rfftfreq(N, d=dt)  # [Hz]

    # ピーク振幅に正規化（DC成分は1倍、それ以外は2倍）
    magnitude = np.abs(spectrum) * 2.0 / N
    magnitude[0] /= 2.0  # DC成分の補正

    # 基本波成分の検出（f_fundamental に最も近い周波数ビン）
    idx_fundamental = np.argmin(np.abs(freq - f_fundamental))
    fundamental_mag = magnitude[idx_fundamental]  # 基本波振幅
    fundamental_phase = np.angle(spectrum[idx_fundamental])  # [rad] 基本波位相

    # THD計算: sqrt(sum(V_n^2)) / V_1 * 100 [%]
    if fundamental_mag > 1e-10:
        # 基本波を除く全高調波のパワー
        harmonic_power = np.sum(magnitude[1:] ** 2) - fundamental_mag ** 2
        harmonic_power = max(harmonic_power, 0.0)  # 数値誤差対策
        thd = np.sqrt(harmonic_power) / fundamental_mag * 100.0  # [%]
    else:
        thd = 0.0

    return {
        "freq": freq,
        "magnitude": magnitude,
        "thd": thd,
        "fundamental_mag": fundamental_mag,
        "fundamental_phase": fundamental_phase,
    }
