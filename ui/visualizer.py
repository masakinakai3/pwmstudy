"""三相PWMインバータ 波形表示UIモジュール.

Matplotlib + widgets によるインタラクティブ波形表示を提供する。
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.widgets import RadioButtons, Slider

from simulation.reference_generator import THIRD_HARMONIC_LIMIT, generate_reference
from simulation.carrier_generator import generate_carrier
from simulation.pwm_comparator import apply_deadtime, apply_sampling_mode, compare_pwm
from simulation.inverter_voltage import calc_inverter_voltage
from simulation.rl_load_solver import solve_rl_load
from simulation.fft_analyzer import analyze_spectrum


# キャリア1周期あたりのサンプル数
POINTS_PER_CARRIER = 100
# 表示する出力波形の周期数
N_DISPLAY_CYCLES = 2
# 助走周期数の最小値（定常状態到達用）
N_WARMUP_CYCLES_MIN = 5
# 非理想モデルの電流-電圧整合反復回数
NONIDEAL_CORRECTION_STEPS = 2
PWM_MODE_LABELS = {
    "natural": "Natural Sampling",
    "regular": "Regular Sampling",
    "third_harmonic": "Third Harmonic Injection",
}
FFT_TARGET_LABELS = {
    "voltage": "Line Voltage v_uv",
    "current": "Phase Current i_u",
}
FFT_WINDOW_LABELS = {
    "hann": "Hann",
    "rectangular": "Rectangular",
}


def _select_ui_font_family() -> str:
    """日本語表示に使うフォントファミリを選択する."""
    candidates = [
        "Yu Gothic",
        "Meiryo",
        "MS Gothic",
        "Hiragino Sans",
        "Noto Sans CJK JP",
        "IPAexGothic",
        "IPAPGothic",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for family in candidates:
        if family in available:
            return family
    return "DejaVu Sans"


class InverterVisualizer:
    """三相PWMインバータのインタラクティブ波形表示クラス."""

    def __init__(self, default_params: dict) -> None:
        """ビジュアライザを初期化する.

        Args:
            default_params: デフォルトパラメータ辞書
                V_dc [V], V_ll [V], f [Hz], f_c [Hz],
                t_d [s], V_on [V], R [Ω], L [H]
        """
        self._params = dict(default_params)
        self._pwm_mode = self._params.get("pwm_mode", "natural")
        self._fft_target = self._params.get("fft_target", "voltage")
        self._fft_window = self._params.get("fft_window", "hann")
        plt.rcParams["font.family"] = _select_ui_font_family()
        # 上5段は時間軸共有、6段目（FFT）は独立
        self._fig = plt.figure(figsize=(14, 14.5))
        gs = self._fig.add_gridspec(6, 1, hspace=0.45, bottom=0.34)
        self._axes = [
            self._fig.add_subplot(gs[0]),
            self._fig.add_subplot(gs[1], sharex=self._fig.axes[0]),
            self._fig.add_subplot(gs[2], sharex=self._fig.axes[0]),
            self._fig.add_subplot(gs[3], sharex=self._fig.axes[0]),
            self._fig.add_subplot(gs[4], sharex=self._fig.axes[0]),
            self._fig.add_subplot(gs[5]),  # FFT: x軸独立
        ]
        self._fig.canvas.manager.set_window_title(
            "三相PWMインバータ シミュレータ"
        )

        self._lines: dict = {}
        self._sliders: dict = {}

        # パラメータ情報パネル（m_a, m_f, Z, φ, cosφ, I比較）
        self._info_text = self._fig.text(
            0.02, 0.99, "", fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow",
                      alpha=0.9, edgecolor="gray")
        )

        self._setup_sliders()
        self._setup_fft_controls()
        self._setup_mode_selector()
        self._init_plots()
        self._update(None)

    def _setup_sliders(self) -> None:
        """パラメータスライダーを配置する."""
        slider_defs = [
            ("V_dc", "V_dc [V]",    100, 600, self._params["V_dc"], 1),
            ("V_ll", "V_LL(rms) [V]",  0, 450, self._params["V_ll"], 1),
            ("f",    "f [Hz]",        1, 200, self._params["f"],    1),
            ("f_c",  "f_c [kHz]",     1,  20, self._params["f_c"] / 1000.0, 0.1),
            ("t_d",  "t_d [us]",      0,  10, self._params["t_d"] * 1.0e6, 0.1),
            ("V_on", "V_on [V]",      0,   5, self._params["V_on"], 0.05),
            ("R",    "R [Ω]",       0.1, 100, self._params["R"],   0.1),
            ("L",    "L [mH]",      0.1, 100, self._params["L"] * 1000.0, 0.1),
        ]

        for i, (key, label, vmin, vmax, vinit, vstep) in enumerate(slider_defs):
            ax = self._fig.add_axes([0.15, 0.27 - i * 0.027, 0.62, 0.018])
            slider = Slider(ax, label, vmin, vmax, valinit=vinit, valstep=vstep)
            slider.on_changed(self._update)
            self._sliders[key] = slider

    def _setup_mode_selector(self) -> None:
        """PWM 方式選択 UI を配置する."""
        ax = self._fig.add_axes([0.81, 0.04, 0.16, 0.15])
        ax.set_title("PWM Mode", fontsize=9)

        labels = list(PWM_MODE_LABELS.values())
        active = list(PWM_MODE_LABELS).index(self._pwm_mode)
        self._mode_buttons = RadioButtons(ax, labels, active=active)
        self._mode_label_to_key = {
            label: key for key, label in PWM_MODE_LABELS.items()
        }
        self._mode_buttons.on_clicked(self._update_mode)

    def _update_mode(self, label: str) -> None:
        """PWM 方式選択のコールバック."""
        self._pwm_mode = self._mode_label_to_key[label]
        self._update(None)

    def _setup_fft_controls(self) -> None:
        """FFT 表示対象と窓関数の選択 UI を配置する."""
        ax_target = self._fig.add_axes([0.81, 0.27, 0.16, 0.06])
        ax_target.set_title("FFT Signal", fontsize=9)
        target_labels = list(FFT_TARGET_LABELS.values())
        target_active = list(FFT_TARGET_LABELS).index(self._fft_target)
        self._fft_target_buttons = RadioButtons(
            ax_target,
            target_labels,
            active=target_active,
        )
        self._fft_target_label_to_key = {
            label: key for key, label in FFT_TARGET_LABELS.items()
        }
        self._fft_target_buttons.on_clicked(self._update_fft_target)

        ax_window = self._fig.add_axes([0.81, 0.20, 0.16, 0.06])
        ax_window.set_title("FFT Window", fontsize=9)
        window_labels = list(FFT_WINDOW_LABELS.values())
        window_active = list(FFT_WINDOW_LABELS).index(self._fft_window)
        self._fft_window_buttons = RadioButtons(
            ax_window,
            window_labels,
            active=window_active,
        )
        self._fft_window_label_to_key = {
            label: key for key, label in FFT_WINDOW_LABELS.items()
        }
        self._fft_window_buttons.on_clicked(self._update_fft_window)

    def _update_fft_target(self, label: str) -> None:
        """FFT 表示対象選択のコールバック."""
        self._fft_target = self._fft_target_label_to_key[label]
        self._update(None)

    def _update_fft_window(self, label: str) -> None:
        """FFT 窓関数選択のコールバック."""
        self._fft_window = self._fft_window_label_to_key[label]
        self._update(None)

    def _init_plots(self) -> None:
        """サブプロットの初期設定を行う."""
        ax_ref, ax_sw, ax_vlv, ax_phv, ax_cur, ax_fft = self._axes

        # サブプロット 1: 指令信号 + キャリア
        ax_ref.set_ylabel("変調信号")
        ax_ref.set_ylim(-1.3, 1.3)
        self._lines["v_u"], = ax_ref.plot([], [], "r-", linewidth=0.5, label="v_u*")
        self._lines["v_v"], = ax_ref.plot([], [], "b-", linewidth=0.5, label="v_v*")
        self._lines["v_w"], = ax_ref.plot([], [], "g-", linewidth=0.5, label="v_w*")
        self._lines["carrier"], = ax_ref.plot(
            [], [], color="gray", linewidth=0.5, alpha=0.7, label="carrier"
        )
        ax_ref.legend(loc="upper right", fontsize=7, ncol=4)

        # サブプロット 2: スイッチングパターン（オフセット表示）
        ax_sw.set_ylabel("SW信号")
        ax_sw.set_ylim(-0.5, 5.5)
        ax_sw.set_yticks([0.5, 2.5, 4.5])
        ax_sw.set_yticklabels(["S_w", "S_v", "S_u"])
        self._lines["S_u"], = ax_sw.plot([], [], "r-", linewidth=0.5)
        self._lines["S_v"], = ax_sw.plot([], [], "b-", linewidth=0.5)
        self._lines["S_w"], = ax_sw.plot([], [], "g-", linewidth=0.5)

        # サブプロット 3: 線間電圧 + 基本波オーバーレイ
        ax_vlv.set_ylabel("線間電圧 [V]")
        self._lines["v_uv"], = ax_vlv.plot(
            [], [], "r-", linewidth=0.5, alpha=0.5, label="v_uv"
        )
        self._lines["v_vw"], = ax_vlv.plot(
            [], [], "b-", linewidth=0.5, alpha=0.25, label="v_vw"
        )
        self._lines["v_wu"], = ax_vlv.plot(
            [], [], "g-", linewidth=0.5, alpha=0.25, label="v_wu"
        )
        self._lines["v_uv_fund"], = ax_vlv.plot(
            [], [], "r--", linewidth=2.0, alpha=0.9, label="基本波"
        )
        ax_vlv.legend(loc="upper right", fontsize=7, ncol=4)

        # サブプロット 4: 相電圧（負荷中性点基準）+ 基本波オーバーレイ
        ax_phv.set_ylabel("相電圧 [V]")
        self._lines["v_uN"], = ax_phv.plot(
            [], [], "r-", linewidth=0.5, alpha=0.5, label="v_uN"
        )
        self._lines["v_uN_fund"], = ax_phv.plot(
            [], [], "r--", linewidth=2.0, alpha=0.9, label="基本波"
        )
        ax_phv.legend(loc="upper right", fontsize=7, ncol=2)

        # サブプロット 5: 相電流 + 理論値オーバーレイ
        ax_cur.set_ylabel("電流 [A]")
        ax_cur.set_xlabel("時間 [ms]")
        self._lines["i_u"], = ax_cur.plot([], [], "r-", linewidth=0.5, label="i_u")
        self._lines["i_v"], = ax_cur.plot([], [], "b-", linewidth=0.5, label="i_v")
        self._lines["i_w"], = ax_cur.plot([], [], "g-", linewidth=0.5, label="i_w")
        self._lines["i_theory"], = ax_cur.plot(
            [], [], "k--", linewidth=2.0, alpha=0.8, label="i_u 理論値"
        )
        ax_cur.legend(loc="upper right", fontsize=7, ncol=4)

        # サブプロット 6: FFTスペクトル
        ax_fft.set_ylabel("振幅 [V]")
        ax_fft.set_xlabel("周波数 [kHz]")
        ax_fft.set_title("線間電圧 v_uv スペクトル", fontsize=9)
        self._fft_bars = None
        self._thd_text = ax_fft.text(
            0.98, 0.95, "", transform=ax_fft.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
        )

    def _read_params(self) -> dict:
        """スライダーから現在のパラメータ値を読み取る.

        Returns:
            パラメータ辞書（SI単位系）
        """
        return {
            "V_dc": self._sliders["V_dc"].val,           # [V]
            "V_ll": self._sliders["V_ll"].val * np.sqrt(2),  # [V] RMS→peak
            "f":    self._sliders["f"].val,                # [Hz]
            "f_c":  self._sliders["f_c"].val * 1000.0,    # [Hz] (kHz→Hz)
            "t_d":  self._sliders["t_d"].val * 1.0e-6,    # [s] (us→s)
            "V_on": self._sliders["V_on"].val,            # [V]
            "R":    self._sliders["R"].val,                # [Ω]
            "L":    self._sliders["L"].val / 1000.0,       # [H]  (mH→H)
            "pwm_mode": self._pwm_mode,
            "fft_target": self._fft_target,
            "fft_window": self._fft_window,
        }

    def _solve_nonideal_power_stage(
        self,
        leg_u: np.ndarray,
        leg_v: np.ndarray,
        leg_w: np.ndarray,
        V_dc: float,
        R: float,
        L: float,
        dt: float,
        V_on: float,
        v_uN_ideal: np.ndarray,
        v_vN_ideal: np.ndarray,
        v_wN_ideal: np.ndarray,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
    ]:
        """非理想インバータと RL 負荷を反復的に整合させる.

        デッドタイム中の極電圧は電流方向で決まるため、まず理想相電圧から
        電流を初期推定し、その後に電圧-電流の整合を固定回数で更新する。

        Args:
            leg_u: U相レグ状態 {-1, 0, +1}
            leg_v: V相レグ状態 {-1, 0, +1}
            leg_w: W相レグ状態 {-1, 0, +1}
            V_dc: 直流母線電圧 [V]
            R: 負荷抵抗 [Ω]
            L: 負荷インダクタンス [H]
            dt: 時間刻み [s]
            V_on: 導通経路の固定電圧降下 [V]
            v_uN_ideal: 理想U相電圧 [V]
            v_vN_ideal: 理想V相電圧 [V]
            v_wN_ideal: 理想W相電圧 [V]

        Returns:
            (v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w)
        """
        i_u, i_v, i_w = solve_rl_load(v_uN_ideal, v_vN_ideal, v_wN_ideal, R, L, dt)

        for _ in range(NONIDEAL_CORRECTION_STEPS):
            v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
                leg_u,
                leg_v,
                leg_w,
                V_dc,
                i_u=i_u,
                i_v=i_v,
                i_w=i_w,
                V_on=V_on,
                inputs_are_leg_states=True,
            )
            i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)

        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
            leg_u,
            leg_v,
            leg_w,
            V_dc,
            i_u=i_u,
            i_v=i_v,
            i_w=i_w,
            V_on=V_on,
            inputs_are_leg_states=True,
        )

        return v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w

    def _run_simulation(
        self, params: dict
    ) -> dict[str, object]:
        """シミュレーションを実行する.

        Args:
            params: パラメータ辞書（SI単位系）

        Returns:
            シミュレーション結果辞書
        """
        V_dc = params["V_dc"]  # [V]
        V_ll = params["V_ll"]  # [V]
        f = params["f"]        # [Hz]
        f_c = params["f_c"]    # [Hz]
        t_d = params["t_d"]    # [s]
        V_on = params["V_on"]  # [V]
        R = params["R"]        # [Ω]
        L = params["L"]        # [H]
        pwm_mode = params["pwm_mode"]
        fft_target = params["fft_target"]
        fft_window = params["fft_window"]

        # 助走周期数の動的計算（5τ以上を確保）
        tau = L / R  # [s] RL時定数
        T_cycle = 1.0 / f  # [s] 1周期
        n_warmup = max(N_WARMUP_CYCLES_MIN, int(np.ceil(5.0 * tau / T_cycle)))

        # 時間配列の生成（助走 + 表示区間）
        N_total = n_warmup + N_DISPLAY_CYCLES
        T_sim = N_total / f  # [s] 合計シミュレーション時間
        dt = 1.0 / (f_c * POINTS_PER_CARRIER)  # [s] 基準時間刻み
        n_points = int(round(T_sim / dt)) + 1
        t = np.linspace(0, T_sim, n_points)  # [s]
        dt_actual = t[1] - t[0]  # [s] 実際の時間刻み

        # シミュレーション実行
        reference_mode = "third_harmonic" if pwm_mode == "third_harmonic" else "sinusoidal"
        sampling_mode = "regular" if pwm_mode == "regular" else "natural"

        v_u_ref, v_v_ref, v_w_ref = generate_reference(
            V_ll,
            f,
            V_dc,
            t,
            mode=reference_mode,
        )
        v_u, v_v, v_w = apply_sampling_mode(
            v_u_ref,
            v_v_ref,
            v_w_ref,
            t,
            f_c,
            sampling_mode=sampling_mode,
        )
        v_carrier = generate_carrier(f_c, t)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        leg_u, leg_v, leg_w = apply_deadtime(S_u, S_v, S_w, t_d, dt_actual)

        _, _, _, v_uN_ideal, v_vN_ideal, v_wN_ideal = calc_inverter_voltage(
            S_u, S_v, S_w, V_dc
        )

        if t_d > 0.0 or V_on > 0.0:
            v_uv, v_vw, v_wu, v_uN, v_vN, v_wN, i_u, i_v, i_w = (
                self._solve_nonideal_power_stage(
                    leg_u,
                    leg_v,
                    leg_w,
                    V_dc,
                    R,
                    L,
                    dt_actual,
                    V_on,
                    v_uN_ideal,
                    v_vN_ideal,
                    v_wN_ideal,
                )
            )
        else:
            v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
                S_u, S_v, S_w, V_dc
            )
            i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, dt_actual)

        S_u_plot = (leg_u == 1).astype(np.int32)
        S_v_plot = (leg_v == 1).astype(np.int32)
        S_w_plot = (leg_w == 1).astype(np.int32)

        # 表示区間の抽出（最後の N_DISPLAY_CYCLES 周期のみ）
        T_display = N_DISPLAY_CYCLES / f  # [s]
        n_display = int(round(T_display / dt_actual)) + 1
        sl = slice(-n_display, None)
        fft_slice = slice(-n_display, -1) if n_display > 1 else sl

        t_disp = t[sl] - t[-n_display]  # [s] 0起点にオフセット
        t_fft = t[fft_slice] - t[-n_display]  # [s] FFT 用（終端重複点を除く）

        # FFT解析（定常状態スペクトル）
        fft_vuv = analyze_spectrum(
            v_uv[fft_slice],
            dt_actual,
            f,
            window_mode=fft_window,
        )
        fft_vuN = analyze_spectrum(
            v_uN[fft_slice],
            dt_actual,
            f,
            window_mode=fft_window,
        )
        fft_iu = analyze_spectrum(
            i_u[fft_slice],
            dt_actual,
            f,
            window_mode=fft_window,
        )

        # 基本波オーバーレイの再構成
        omega_voltage = 2.0 * np.pi * fft_vuN["fundamental_freq"]  # [rad/s]

        # 線間電圧 v_uv の基本波
        v_uv_fund = fft_vuv["fundamental_mag"] * np.cos(
            2.0 * np.pi * fft_vuv["fundamental_freq"] * t_disp
            + fft_vuv["fundamental_phase"]
        )

        # 相電圧 v_uN の基本波
        v_uN_fund = fft_vuN["fundamental_mag"] * np.cos(
            omega_voltage * t_disp + fft_vuN["fundamental_phase"]
        )

        # 理論値計算
        Z = np.sqrt(R**2 + (omega_voltage * L)**2)  # [Ω] インピーダンス
        phi = np.arctan2(omega_voltage * L, R)      # [rad] 位相角
        V_uN_fund_mag = fft_vuN["fundamental_mag"]  # [V] 基本波相電圧振幅
        I_theory_peak = V_uN_fund_mag / Z         # [A] 理論電流振幅

        # 理論電流波形（基本波相電圧を Z で除して φ だけ遅延）
        i_u_theory = I_theory_peak * np.cos(
            omega_voltage * t_disp + fft_vuN["fundamental_phase"] - phi
        )

        # 実測電流基本波振幅（理論値と同じ物理量で比較する）
        I_measured = fft_iu["fundamental_mag"]  # [A]
        phase_diff = fft_vuN["fundamental_phase"] - fft_iu["fundamental_phase"]
        phase_diff = np.arctan2(np.sin(phase_diff), np.cos(phase_diff))
        pf1_fft = np.cos(phase_diff)

        return {
            "t": t_disp,
            "t_fft": t_fft,
            "v_u": v_u[sl], "v_v": v_v[sl], "v_w": v_w[sl],
            "v_carrier": v_carrier[sl],
            "S_u": S_u_plot[sl], "S_v": S_v_plot[sl], "S_w": S_w_plot[sl],
            "v_uv": v_uv[sl], "v_vw": v_vw[sl], "v_wu": v_wu[sl],
            "v_uN": v_uN[sl],
            "i_u": i_u[sl], "i_v": i_v[sl], "i_w": i_w[sl],
            "V_dc": V_dc,
            "V_ll": V_ll,
            "t_d": t_d,
            "V_on": V_on,
            "pwm_mode": pwm_mode,
            "pwm_mode_label": PWM_MODE_LABELS[pwm_mode],
            "sampling_mode": sampling_mode,
            "fft_target": fft_target,
            "fft_target_label": FFT_TARGET_LABELS[fft_target],
            "fft_window": fft_window,
            "fft_window_label": FFT_WINDOW_LABELS[fft_window],
            "m_a_limit": THIRD_HARMONIC_LIMIT if pwm_mode == "third_harmonic" else 1.0,
            "fft_vuv": fft_vuv,
            "fft_vuN": fft_vuN,
            "fft_iu": fft_iu,
            "f": f,
            "f_c": f_c,
            "v_uv_fund": v_uv_fund,
            "v_uN_fund": v_uN_fund,
            "i_u_theory": i_u_theory,
            "Z": Z,
            "phi": phi,
            "m_f": f_c / f,
            "I_theory": I_theory_peak,
            "I_measured": I_measured,
            "pf1_fft": pf1_fft,
        }

    def _draw_waveforms(self, results: dict) -> None:
        """波形データをプロットに反映する.

        Args:
            results: シミュレーション結果辞書
        """
        t_ms = results["t"] * 1000.0  # [ms] 表示用

        # === 情報パネル: 導出量の表示 ===
        V_ph = results["V_ll"] / np.sqrt(3)  # [V]
        m_a_raw = 2.0 * V_ph / results["V_dc"]  # クランプ前の変調率
        m_a_limit = results["m_a_limit"]
        m_a = min(m_a_raw, m_a_limit)
        m_f = results["m_f"]
        t_d_us = results["t_d"] * 1.0e6         # [us]
        V_on = results["V_on"]                  # [V]
        Z = results["Z"]                         # [Ω]
        phi_deg = np.degrees(results["phi"])      # [deg]
        cos_phi = np.cos(results["phi"])
        I_theory = results["I_theory"]            # [A]
        I_measured = results["I_measured"]         # [A]
        fft_vuv = results["fft_vuv"]
        fft_iu = results["fft_iu"]
        pf1_fft = results["pf1_fft"]
        err_pct = (abs(I_measured - I_theory) / I_theory * 100.0
                   if I_theory > 1e-6 else 0.0)

        clamp_str = (
            f" (クランプ中: 上限 {m_a_limit:.3f})"
            if m_a_raw > m_a_limit else ""
        )
        info_lines = [
            f"方式 = {results['pwm_mode_label']}",
            f"m_a = {m_a:.3f}{clamp_str}    "
            f"m_f = f_c/f = {m_f:.1f}",
            f"t_d = {t_d_us:.2f} us    "
            f"V_on = {V_on:.2f} V",
            f"Z = {Z:.2f} Ω    "
            f"φ = {phi_deg:.1f}°    "
            f"cos(φ) = {cos_phi:.3f}    PF1(FFT) = {pf1_fft:.3f}",
            f"V1 = {fft_vuv['fundamental_mag']:.1f} Vpk  /  "
            f"Vrms = {fft_vuv['rms_total']:.1f} V  /  "
            f"THD_V = {fft_vuv['thd']:.1f}%",
            f"I1_peak: 理論 {I_theory:.2f} A  /  "
            f"FFT実測 {I_measured:.2f} A  "
            f"(誤差 {err_pct:.1f}%)",
            f"Irms = {fft_iu['rms_total']:.2f} A  /  "
            f"THD_I = {fft_iu['thd']:.1f}%  /  "
            f"FFT = {results['fft_target_label']} [{results['fft_window_label']}]",
        ]
        self._info_text.set_text("\n".join(info_lines))
        if m_a_raw > m_a_limit:
            self._info_text.get_bbox_patch().set_facecolor("lightsalmon")
        else:
            self._info_text.get_bbox_patch().set_facecolor("lightyellow")

        # === サブプロット 1: 指令信号 + キャリア ===
        self._lines["v_u"].set_data(t_ms, results["v_u"])
        self._lines["v_v"].set_data(t_ms, results["v_v"])
        self._lines["v_w"].set_data(t_ms, results["v_w"])
        self._lines["carrier"].set_data(t_ms, results["v_carrier"])
        drawstyle = "steps-post" if results["sampling_mode"] == "regular" else "default"
        self._lines["v_u"].set_drawstyle(drawstyle)
        self._lines["v_v"].set_drawstyle(drawstyle)
        self._lines["v_w"].set_drawstyle(drawstyle)

        # === サブプロット 2: スイッチングパターン（オフセット表示）===
        self._lines["S_u"].set_data(t_ms, results["S_u"] + 4)
        self._lines["S_v"].set_data(t_ms, results["S_v"] + 2)
        self._lines["S_w"].set_data(t_ms, results["S_w"])

        # === サブプロット 3: 線間電圧 + 基本波 ===
        self._lines["v_uv"].set_data(t_ms, results["v_uv"])
        self._lines["v_vw"].set_data(t_ms, results["v_vw"])
        self._lines["v_wu"].set_data(t_ms, results["v_wu"])
        self._lines["v_uv_fund"].set_data(t_ms, results["v_uv_fund"])
        V_dc = results["V_dc"]  # [V]
        self._axes[2].set_ylim(-V_dc * 1.2, V_dc * 1.2)

        # === サブプロット 4: 相電圧 + 基本波 ===
        self._lines["v_uN"].set_data(t_ms, results["v_uN"])
        self._lines["v_uN_fund"].set_data(t_ms, results["v_uN_fund"])
        self._axes[3].set_ylim(-V_dc * 0.8, V_dc * 0.8)

        # === サブプロット 5: 相電流 + 理論値 ===
        self._lines["i_u"].set_data(t_ms, results["i_u"])
        self._lines["i_v"].set_data(t_ms, results["i_v"])
        self._lines["i_w"].set_data(t_ms, results["i_w"])
        self._lines["i_theory"].set_data(t_ms, results["i_u_theory"])

        # X軸の範囲を更新（時間軸の5段のみ）
        t_max = t_ms[-1]
        for ax in self._axes[:5]:
            ax.set_xlim(0, t_max)

        # 電流のY軸を自動スケール
        all_currents = np.concatenate(
            [results["i_u"], results["i_v"], results["i_w"]]
        )
        if np.any(all_currents != 0):
            i_max = np.max(np.abs(all_currents)) * 1.2
            self._axes[4].set_ylim(-i_max, i_max)

        # === サブプロット 6: FFTスペクトル（拡張版）===
        ax_fft = self._axes[5]
        if results["fft_target"] == "current":
            fft_data = results["fft_iu"]
            magnitude_unit = "A"
            series_title = "相電流 i_u"
            fundamental_label = "I_1"
            thd_label = "THD_I"
        else:
            fft_data = results["fft_vuv"]
            magnitude_unit = "V"
            series_title = "線間電圧 v_uv"
            fundamental_label = "V_1"
            thd_label = "THD_V"

        freq_khz = fft_data["freq"] / 1000.0  # [kHz]
        magnitude = fft_data["magnitude"]

        # 表示範囲: DC〜キャリア周波数の3倍
        f_c = results["f_c"]  # [Hz]
        f_max_khz = 3.0 * f_c / 1000.0  # [kHz]
        mask = freq_khz <= f_max_khz

        # 棒グラフを再描画
        ax_fft.cla()
        ax_fft.set_ylabel(f"振幅 [{magnitude_unit}]")
        ax_fft.set_xlabel("周波数 [kHz]")
        ax_fft.set_title(
            f"{series_title} スペクトル ({results['pwm_mode_label']}, {results['fft_window_label']})",
            fontsize=9,
        )

        # 基本波とキャリア高調波で色分け
        f_fund = results["f"]  # [Hz]
        colors = []
        for fk in fft_data["freq"][mask]:
            if abs(fk - f_fund) < f_fund * 0.5:
                colors.append("blue")  # 基本波成分
            elif any(abs(fk - n * f_c) < f_c * 0.3 for n in range(1, 4)):
                colors.append("red")  # キャリア高調波
            else:
                colors.append("gray")

        bar_width = freq_khz[1] - freq_khz[0] if len(freq_khz) > 1 else 0.01
        ax_fft.bar(freq_khz[mask], magnitude[mask], width=bar_width,
                   color=colors, alpha=0.8)

        # キャリア高調波グループのマーカー線
        y_max = np.max(magnitude[mask]) if np.any(mask) else 1.0
        for n in range(1, 4):
            fc_n_khz = n * f_c / 1000.0
            if fc_n_khz <= f_max_khz:
                ax_fft.axvline(fc_n_khz, color="red", linestyle=":",
                               alpha=0.5, linewidth=1.0)
                ax_fft.text(fc_n_khz, y_max * 0.90, f"{n}×f_c",
                            fontsize=7, ha="center", color="red", alpha=0.8)

        ax_fft.set_xlim(0, f_max_khz)

        # THD + 基本波振幅の表示
        self._thd_text = ax_fft.text(
            0.98, 0.95,
            f"{thd_label} = {fft_data['thd']:.1f}%\n"
            f"{fundamental_label} = {fft_data['fundamental_mag']:.1f} {magnitude_unit}\n"
            f"RMS = {fft_data['rms_total']:.1f} {magnitude_unit}",
            transform=ax_fft.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.8)
        )

        self._fig.canvas.draw_idle()

    def _update(self, val: object) -> None:
        """スライダー変更時のコールバック.

        Args:
            val: スライダーの値（未使用、コールバックシグネチャ用）
        """
        params = self._read_params()
        results = self._run_simulation(params)
        self._draw_waveforms(results)

    def run(self) -> None:
        """メインループを開始する."""
        plt.show()
