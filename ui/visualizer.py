"""三相PWMインバータ 波形表示UIモジュール.

Matplotlib + widgets によるインタラクティブ波形表示を提供する。
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

from simulation.reference_generator import generate_reference
from simulation.carrier_generator import generate_carrier
from simulation.pwm_comparator import compare_pwm
from simulation.inverter_voltage import calc_inverter_voltage
from simulation.rl_load_solver import solve_rl_load
from simulation.fft_analyzer import analyze_spectrum


# キャリア1周期あたりのサンプル数
POINTS_PER_CARRIER = 100
# 表示する出力波形の周期数
N_DISPLAY_CYCLES = 2
# 助走周期数の最小値（定常状態到達用）
N_WARMUP_CYCLES_MIN = 5


class InverterVisualizer:
    """三相PWMインバータのインタラクティブ波形表示クラス."""

    def __init__(self, default_params: dict) -> None:
        """ビジュアライザを初期化する.

        Args:
            default_params: デフォルトパラメータ辞書
                V_dc [V], V_ll [V], f [Hz], f_c [Hz], R [Ω], L [H]
        """
        self._params = dict(default_params)
        # 上5段は時間軸共有、6段目（FFT）は独立
        self._fig = plt.figure(figsize=(14, 14))
        gs = self._fig.add_gridspec(6, 1, hspace=0.45, bottom=0.27)
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
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow",
                      alpha=0.9, edgecolor="gray")
        )

        self._setup_sliders()
        self._init_plots()
        self._update(None)

    def _setup_sliders(self) -> None:
        """パラメータスライダーを配置する."""
        slider_defs = [
            ("V_dc", "V_dc [V]",    100, 600, self._params["V_dc"], 1),
            ("V_ll", "V_LL(rms) [V]",  0, 450, self._params["V_ll"], 1),
            ("f",    "f [Hz]",        1, 200, self._params["f"],    1),
            ("f_c",  "f_c [kHz]",     1,  20, self._params["f_c"] / 1000.0, 0.1),
            ("R",    "R [Ω]",       0.1, 100, self._params["R"],   0.1),
            ("L",    "L [mH]",      0.1, 100, self._params["L"] * 1000.0, 0.1),
        ]

        for i, (key, label, vmin, vmax, vinit, vstep) in enumerate(slider_defs):
            ax = self._fig.add_axes([0.15, 0.20 - i * 0.030, 0.70, 0.018])
            slider = Slider(ax, label, vmin, vmax, valinit=vinit, valstep=vstep)
            slider.on_changed(self._update)
            self._sliders[key] = slider

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
            fontfamily="monospace"
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
            "R":    self._sliders["R"].val,                # [Ω]
            "L":    self._sliders["L"].val / 1000.0,       # [H]  (mH→H)
        }

    def _run_simulation(
        self, params: dict
    ) -> dict[str, np.ndarray]:
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
        R = params["R"]        # [Ω]
        L = params["L"]        # [H]

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
        v_u, v_v, v_w = generate_reference(V_ll, f, V_dc, t)
        v_carrier = generate_carrier(f_c, t)
        S_u, S_v, S_w = compare_pwm(v_u, v_v, v_w, v_carrier)
        v_uv, v_vw, v_wu, v_uN, v_vN, v_wN = calc_inverter_voltage(
            S_u, S_v, S_w, V_dc
        )
        i_u, i_v, i_w = solve_rl_load(v_uN, v_vN, v_wN, R, L, dt_actual)

        # 表示区間の抽出（最後の N_DISPLAY_CYCLES 周期のみ）
        T_display = N_DISPLAY_CYCLES / f  # [s]
        n_display = int(round(T_display / dt_actual)) + 1
        sl = slice(-n_display, None)

        t_disp = t[sl] - t[-n_display]  # [s] 0起点にオフセット

        # FFT解析（定常状態スペクトル）
        fft_vuv = analyze_spectrum(v_uv[sl], dt_actual, f)
        fft_vuN = analyze_spectrum(v_uN[sl], dt_actual, f)

        # 基本波オーバーレイの再構成
        omega = 2.0 * np.pi * f  # [rad/s]

        # 線間電圧 v_uv の基本波
        v_uv_fund = fft_vuv["fundamental_mag"] * np.cos(
            omega * t_disp + fft_vuv["fundamental_phase"]
        )

        # 相電圧 v_uN の基本波
        v_uN_fund = fft_vuN["fundamental_mag"] * np.cos(
            omega * t_disp + fft_vuN["fundamental_phase"]
        )

        # 理論値計算
        Z = np.sqrt(R**2 + (omega * L)**2)       # [Ω] インピーダンス
        phi = np.arctan2(omega * L, R)            # [rad] 位相角
        V_uN_fund_mag = fft_vuN["fundamental_mag"]  # [V] 基本波相電圧振幅
        I_theory_peak = V_uN_fund_mag / Z         # [A] 理論電流振幅

        # 理論電流波形（基本波相電圧を Z で除して φ だけ遅延）
        i_u_theory = I_theory_peak * np.cos(
            omega * t_disp + fft_vuN["fundamental_phase"] - phi
        )

        # 実測電流振幅
        I_measured = (np.max(i_u[sl]) - np.min(i_u[sl])) / 2.0  # [A]

        return {
            "t": t_disp,
            "v_u": v_u[sl], "v_v": v_v[sl], "v_w": v_w[sl],
            "v_carrier": v_carrier[sl],
            "S_u": S_u[sl], "S_v": S_v[sl], "S_w": S_w[sl],
            "v_uv": v_uv[sl], "v_vw": v_vw[sl], "v_wu": v_wu[sl],
            "v_uN": v_uN[sl],
            "i_u": i_u[sl], "i_v": i_v[sl], "i_w": i_w[sl],
            "V_dc": V_dc,
            "V_ll": V_ll,
            "fft": fft_vuv,
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
        m_a = min(m_a_raw, 1.0)
        m_f = results["m_f"]
        Z = results["Z"]                         # [Ω]
        phi_deg = np.degrees(results["phi"])      # [deg]
        cos_phi = np.cos(results["phi"])
        I_theory = results["I_theory"]            # [A]
        I_measured = results["I_measured"]         # [A]
        err_pct = (abs(I_measured - I_theory) / I_theory * 100.0
                   if I_theory > 1e-6 else 0.0)

        clamp_str = " (クランプ中)" if m_a_raw > 1.0 else ""
        info_lines = [
            f"m_a = {m_a:.3f}{clamp_str}    "
            f"m_f = f_c/f = {m_f:.0f}",
            f"Z = {Z:.2f} Ω    "
            f"φ = {phi_deg:.1f}°    "
            f"cos(φ) = {cos_phi:.3f}",
            f"I_peak:  理論 {I_theory:.2f} A  /  "
            f"実測 {I_measured:.2f} A  "
            f"(誤差 {err_pct:.1f}%)",
        ]
        self._info_text.set_text("\n".join(info_lines))
        if m_a_raw > 1.0:
            self._info_text.get_bbox_patch().set_facecolor("lightsalmon")
        else:
            self._info_text.get_bbox_patch().set_facecolor("lightyellow")

        # === サブプロット 1: 指令信号 + キャリア ===
        self._lines["v_u"].set_data(t_ms, results["v_u"])
        self._lines["v_v"].set_data(t_ms, results["v_v"])
        self._lines["v_w"].set_data(t_ms, results["v_w"])
        self._lines["carrier"].set_data(t_ms, results["v_carrier"])

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
        fft_data = results["fft"]
        freq_khz = fft_data["freq"] / 1000.0  # [kHz]
        magnitude = fft_data["magnitude"]

        # 表示範囲: DC〜キャリア周波数の3倍
        f_c = results["f_c"]  # [Hz]
        f_max_khz = 3.0 * f_c / 1000.0  # [kHz]
        mask = freq_khz <= f_max_khz

        # 棒グラフを再描画
        ax_fft.cla()
        ax_fft.set_ylabel("振幅 [V]")
        ax_fft.set_xlabel("周波数 [kHz]")
        ax_fft.set_title("線間電圧 v_uv スペクトル", fontsize=9)

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
            f"THD = {fft_data['thd']:.1f}%\n"
            f"V_1 = {fft_data['fundamental_mag']:.1f} V",
            transform=ax_fft.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
            fontfamily="monospace",
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
