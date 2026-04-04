"""FFT解析モジュール.

時間領域信号のスペクトル解析とTHD計算を提供する。
"""

import numpy as np


WINDOW_MODES = {"rectangular", "hann"}
_EPSILON = 1.0e-12


def _validate_window_mode(window_mode: str) -> None:
    """窓関数モード名を検証する."""
    if window_mode not in WINDOW_MODES:
        raise ValueError(f"Unsupported window mode: {window_mode}")


def _build_window(
    n_samples: int,       # サンプル数
    window_mode: str      # 窓関数モード
) -> np.ndarray:
    """窓関数を返す."""
    if window_mode == "hann" and n_samples > 1:
        return np.hanning(n_samples)
    return np.ones(n_samples)


def _calc_one_sided_magnitude(
    spectrum: np.ndarray,   # FFT 複素スペクトル
    n_samples: int,         # サンプル数
    coherent_gain: float    # 窓関数の coherent gain
) -> np.ndarray:
    """片側スペクトルのピーク振幅を計算する."""
    magnitude = np.abs(spectrum) / (n_samples * coherent_gain)

    if magnitude.size > 1:
        if n_samples % 2 == 0 and magnitude.size > 2:
            magnitude[1:-1] *= 2.0
        else:
            magnitude[1:] *= 2.0

    return magnitude


def _find_fundamental_peak_index(
    freq: np.ndarray,           # [Hz] 周波数軸
    magnitude: np.ndarray,      # スペクトル振幅
    f_fundamental: float        # [Hz] 期待基本波周波数
) -> int:
    """基本波近傍のピークビンを返す."""
    if freq.size < 2:
        return 0

    df = freq[1] - freq[0]
    lower = max(f_fundamental * 0.5, df)
    upper = max(f_fundamental * 1.5, lower)
    mask = (freq >= lower) & (freq <= upper)

    if not np.any(mask):
        return int(np.argmin(np.abs(freq - f_fundamental)))

    indices = np.flatnonzero(mask)
    return int(indices[np.argmax(magnitude[mask])])


def _parabolic_peak_interpolation(
    magnitude: np.ndarray,   # スペクトル振幅
    peak_index: int          # ピークビン番号
) -> tuple[float, float]:
    """3点放物線補間でピーク位置とピーク振幅を推定する."""
    if peak_index <= 0 or peak_index >= len(magnitude) - 1:
        return float(peak_index), float(magnitude[peak_index])

    y_left = magnitude[peak_index - 1]
    y_center = magnitude[peak_index]
    y_right = magnitude[peak_index + 1]
    denominator = y_left - 2.0 * y_center + y_right

    if abs(denominator) < _EPSILON:
        return float(peak_index), float(y_center)

    delta = 0.5 * (y_left - y_right) / denominator
    delta = float(np.clip(delta, -1.0, 1.0))
    peak_magnitude = y_center - 0.25 * (y_left - y_right) * delta

    return peak_index + delta, float(peak_magnitude)


def _fit_fundamental_component(
    signal: np.ndarray,          # 時間領域信号
    dt: float,                   # [s] サンプリング間隔
    fundamental_freq: float      # [Hz] 基本波周波数
) -> tuple[float, float, float]:
    """最小二乗法で基本波成分の振幅・位相・DC成分を推定する."""
    t = np.arange(signal.size, dtype=float) * dt  # [s]
    omega = 2.0 * np.pi * fundamental_freq  # [rad/s]

    design = np.column_stack(
        (
            np.cos(omega * t),
            np.sin(omega * t),
            np.ones_like(t),
        )
    )
    coefficients, _, _, _ = np.linalg.lstsq(design, signal, rcond=None)
    coef_cos, coef_sin, dc_component = coefficients

    fundamental_mag = float(np.hypot(coef_cos, coef_sin))
    fundamental_phase = float(np.arctan2(-coef_sin, coef_cos))

    return fundamental_mag, fundamental_phase, float(dc_component)


def analyze_spectrum(
    signal: np.ndarray,              # 時間領域信号
    dt: float,                       # [s] サンプリング間隔
    f_fundamental: float,            # [Hz] 基本波周波数
    window_mode: str = "rectangular",
    enable_peak_interpolation: bool = True,
) -> dict[str, np.ndarray | float | str]:
    """信号のFFTスペクトルとTHDを計算する.

    Args:
        signal: 時間領域信号
        dt: サンプリング間隔 [s]
        f_fundamental: 基本波周波数 [Hz]
        window_mode: 窓関数モード
            rectangular: 矩形窓
            hann: Hann 窓
        enable_peak_interpolation: 基本波周辺の3点補間を有効にするか

    Returns:
        {
            "freq": 周波数軸 [Hz],
            "magnitude": スペクトル振幅（ピーク値）, 
            "thd": THD [%],
            "fundamental_mag": 基本波振幅 [peak],
            "fundamental_phase": 基本波位相 [rad],
            "fundamental_freq": 基本波周波数 [Hz],
            "fundamental_rms": 基本波実効値,
            "rms_total": 全実効値,
            "harmonic_rms": 高調波合成実効値,
            "dc_component": DC 成分,
            "window_mode": 使用した窓関数名
        }
    """
    if dt <= 0.0:
        raise ValueError("dt must be positive.")
    if f_fundamental <= 0.0:
        raise ValueError("f_fundamental must be positive.")

    _validate_window_mode(window_mode)

    signal = np.asarray(signal, dtype=float)
    n_samples = signal.size
    if n_samples < 2:
        raise ValueError("signal must contain at least 2 samples.")

    window = _build_window(n_samples, window_mode)
    coherent_gain = float(np.mean(window))
    windowed_signal = signal * window

    spectrum = np.fft.rfft(windowed_signal)
    freq = np.fft.rfftfreq(n_samples, d=dt)  # [Hz]
    magnitude = _calc_one_sided_magnitude(spectrum, n_samples, coherent_gain)

    peak_index = _find_fundamental_peak_index(freq, magnitude, f_fundamental)
    fundamental_freq = float(f_fundamental)
    if enable_peak_interpolation and freq.size >= 3:
        interpolated_bin, _ = _parabolic_peak_interpolation(magnitude, peak_index)
        df = freq[1] - freq[0]
        interpolated_freq = float(max(df, interpolated_bin * df))
        if abs(interpolated_freq - f_fundamental) > df:
            fundamental_freq = interpolated_freq

    fundamental_mag, fundamental_phase, dc_component = _fit_fundamental_component(
        signal,
        dt,
        fundamental_freq,
    )
    fundamental_rms = fundamental_mag / np.sqrt(2.0)
    rms_total = float(np.sqrt(np.mean(signal ** 2)))
    harmonic_rms = float(
        np.sqrt(
            max(
                rms_total ** 2 - dc_component ** 2 - fundamental_rms ** 2,
                0.0,
            )
        )
    )

    if fundamental_rms > _EPSILON:
        thd = harmonic_rms / fundamental_rms * 100.0
    else:
        thd = 0.0

    return {
        "freq": freq,
        "magnitude": magnitude,
        "thd": float(thd),
        "fundamental_mag": float(fundamental_mag),
        "fundamental_phase": float(fundamental_phase),
        "fundamental_freq": float(fundamental_freq),
        "fundamental_rms": float(fundamental_rms),
        "rms_total": float(rms_total),
        "harmonic_rms": float(harmonic_rms),
        "dc_component": float(dc_component),
        "window_mode": window_mode,
    }
