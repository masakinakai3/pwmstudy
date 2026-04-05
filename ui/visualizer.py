"""三相PWMインバータ 波形表示UIモジュール.

Matplotlib + widgets によるインタラクティブ波形表示を提供する。
"""

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider

from application import (
    SCENARIO_PRESETS,
    build_baseline_snapshot,
    build_export_payload,
    normalize_ui_display_params,
    run_simulation,
)
from application.modulation_config import (
    MODULATION_MODE_LABELS,
    normalize_modulation_mode,
)


# キャリア1周期あたりのサンプル数
POINTS_PER_CARRIER = 100
# 表示する出力波形の周期数
N_DISPLAY_CYCLES = 2
# 助走周期数の最小値（定常状態到達用）
N_WARMUP_CYCLES_MIN = 5
# 非理想モデルの電流-電圧整合反復回数
NONIDEAL_CORRECTION_STEPS = 2
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
        self._overmod_view = bool(self._params.get("overmod_view", False))
        self._modulation_mode = normalize_modulation_mode(self._params.get("modulation_mode"))
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
        self._last_results: dict = {}       # 最新シミュレーション結果（エクスポート/ベースライン用）
        self._baseline_results: dict | None = None  # ベースラインスナップショット
        self._applying_scenario: bool = False  # プリセット適用中フラグ（_update 抑制用）

        # パラメータ情報パネル（m_a, m_f, Z, φ, cosφ, I比較）
        self._info_text = self._fig.text(
            0.02, 0.99, "", fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow",
                      alpha=0.9, edgecolor="gray")
        )

        self._setup_sliders()
        self._setup_fft_controls()
        self._setup_mode_selector()
        self._setup_scenario_buttons()
        self._setup_export_buttons()
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
        """単一の変調方式選択 UI を配置する."""
        ax_mode = self._fig.add_axes([0.78, 0.11, 0.19, 0.18])
        ax_mode.set_title("変調方式", fontsize=9)
        modulation_labels = list(MODULATION_MODE_LABELS.values())
        modulation_active = list(MODULATION_MODE_LABELS).index(self._modulation_mode)
        self._modulation_buttons = RadioButtons(
            ax_mode,
            modulation_labels,
            active=modulation_active,
        )
        self._modulation_label_to_key = {
            label: key for key, label in MODULATION_MODE_LABELS.items()
        }
        self._modulation_buttons.on_clicked(self._update_modulation_mode)
        self._set_radio_label_fontsize(self._modulation_buttons, fontsize=7)

        ax_overmod = self._fig.add_axes([0.81, 0.06, 0.16, 0.035])
        ax_overmod.set_title("", fontsize=8)
        self._overmod_check = CheckButtons(ax_overmod, ["Overmod View"], [self._overmod_view])
        self._overmod_check.on_clicked(self._update_overmod_view)

    def _set_radio_label_fontsize(self, widget: RadioButtons, fontsize: int = 8) -> None:
        """RadioButtons ラベルのフォントサイズを揃える."""
        for text in widget.labels:
            text.set_fontsize(fontsize)

    def _update_modulation_mode(self, label: str) -> None:
        """変調方式選択のコールバック."""
        self._modulation_mode = self._modulation_label_to_key[label]
        self._update(None)

    def _update_overmod_view(self, label: str) -> None:
        """Overmod View 切替のコールバック."""
        self._overmod_view = bool(self._overmod_check.get_status()[0])
        self._update(None)

    def _setup_fft_controls(self) -> None:
        """FFT 表示対象と窓関数の選択 UI を配置する."""
        ax_target = self._fig.add_axes([0.64, 0.09, 0.12, 0.06])
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
        self._set_radio_label_fontsize(self._fft_target_buttons)

        ax_window = self._fig.add_axes([0.64, 0.02, 0.12, 0.06])
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
        self._set_radio_label_fontsize(self._fft_window_buttons)

    def _update_fft_target(self, label: str) -> None:
        """FFT 表示対象選択のコールバック."""
        self._fft_target = self._fft_target_label_to_key[label]
        self._update(None)

    def _update_fft_window(self, label: str) -> None:
        """FFT 窓関数選択のコールバック."""
        self._fft_window = self._fft_window_label_to_key[label]
        self._update(None)

    def _setup_scenario_buttons(self) -> None:
        """学習シナリオプリセットボタンを配置する（IMPROVE-11）."""
        # ヒントテキスト: シナリオボタンの直下に配置
        self._hint_text = self._fig.text(
            0.015, 0.031, "",
            fontsize=8, verticalalignment="top",
            color="steelblue", style="italic",
        )

        n = len(SCENARIO_PRESETS)
        max_cols = 5
        cols = max(1, min(max_cols, n))
        rows = int(np.ceil(n / cols)) if n > 0 else 1

        x_start = 0.015
        x_end = 0.763
        content_width = x_end - x_start
        col_gap = 0.008
        btn_width = (content_width - col_gap * (cols - 1)) / cols

        btn_height = 0.018
        row_gap = 0.004
        first_row_y = 0.060

        self._scenario_buttons: list = []
        for i, scenario in enumerate(SCENARIO_PRESETS):
            row = i // cols
            col = i % cols
            x = x_start + col * (btn_width + col_gap)
            y = first_row_y - row * (btn_height + row_gap)
            ax_btn = self._fig.add_axes([x, y, btn_width, btn_height])
            btn = Button(ax_btn, scenario["label"], color="lightcyan", hovercolor="lightblue")
            btn.label.set_fontsize(8)

            def _make_scenario_cb(idx: int):
                def _cb(event: object) -> None:
                    self._apply_scenario(idx)
                return _cb

            btn.on_clicked(_make_scenario_cb(i))
            self._scenario_buttons.append(btn)

    def _setup_export_buttons(self) -> None:
        """エクスポートボタンを配置する（IMPROVE-12）."""
        btn_height = 0.020
        btn_y = 0.006
        export_defs = [
            ("json_save",      "JSON保存",          0.015, 0.115, "lightyellow",  "lemonchiffon"),
            ("json_load",      "JSON読込",          0.135, 0.115, "lightyellow",  "lemonchiffon"),
            ("png_save",       "PNG保存",           0.255, 0.115, "lightyellow",  "lemonchiffon"),
            ("baseline_set",   "ベースライン設定",   0.375, 0.185, "lightgreen",   "palegreen"),
            ("baseline_clear", "ベースライン解除",   0.565, 0.185, "mistyrose",    "lightsalmon"),
        ]
        self._export_buttons: dict = {}
        for key, label, x, width, color, hcolor in export_defs:
            ax_btn = self._fig.add_axes([x, btn_y, width, btn_height])
            btn = Button(ax_btn, label, color=color, hovercolor=hcolor)
            btn.label.set_fontsize(8)
            self._export_buttons[key] = btn

        self._export_buttons["json_save"].on_clicked(self._save_json)
        self._export_buttons["json_load"].on_clicked(self._load_json)
        self._export_buttons["png_save"].on_clicked(self._save_png)
        self._export_buttons["baseline_set"].on_clicked(self._set_baseline)
        self._export_buttons["baseline_clear"].on_clicked(self._clear_baseline)

    def _apply_scenario(self, idx: int) -> None:
        """シナリオプリセットを適用する（IMPROVE-11）.

        Args:
            idx: SCENARIO_PRESETS のインデックス
        """
        scenario = SCENARIO_PRESETS[idx]
        # _applying_scenario フラグで _update の多重呼び出しを抑制する
        self._applying_scenario = True
        try:
            for key, val in scenario["sliders"].items():
                self._sliders[key].set_val(val)
            # set_active は内部で _update_* を呼ぶが、フラグにより
            # _update は実行されず、選択状態のみ更新される
            modulation_idx = list(MODULATION_MODE_LABELS).index(scenario["modulation_mode"])
            self._modulation_buttons.set_active(modulation_idx)
            scenario_overmod = bool(scenario.get("overmod_view", False))
            current_overmod = bool(self._overmod_check.get_status()[0])
            if scenario_overmod != current_overmod:
                self._overmod_check.set_active(0)
            fft_target_idx = list(FFT_TARGET_LABELS).index(scenario["fft_target"])
            self._fft_target_buttons.set_active(fft_target_idx)
            fft_window_idx = list(FFT_WINDOW_LABELS).index(scenario["fft_window"])
            self._fft_window_buttons.set_active(fft_window_idx)
        finally:
            self._applying_scenario = False
        self._hint_text.set_text(f"ヒント: {scenario['hint']}")
        self._update(None)

    def _save_json(self, event: object) -> None:
        """現在のパラメータと主要指標を JSON ファイルに保存する（IMPROVE-12）.

        Args:
            event: ボタンクリックイベント（未使用）
        """
        if not self._last_results:
            return
        now = datetime.now()
        data = build_export_payload(self._last_results, self._read_display_params(), now)
        fname = f"pwm_export_{now.strftime('%Y%m%d_%H%M%S')}.json"
        fpath = os.path.join(os.getcwd(), fname)
        with open(fpath, "w", encoding="utf-8") as f_out:
            json.dump(data, f_out, ensure_ascii=False, indent=2)
        self._hint_text.set_text(f"保存完了: {fname}")
        self._fig.canvas.draw_idle()

    def _save_png(self, event: object) -> None:
        """現在の波形を PNG ファイルに保存する（IMPROVE-12）.

        Args:
            event: ボタンクリックイベント（未使用）
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"pwm_export_{ts}.png"
        fpath = os.path.join(os.getcwd(), fname)
        self._fig.savefig(fpath, dpi=150, bbox_inches="tight")
        self._hint_text.set_text(f"保存完了: {fname}")
        self._fig.canvas.draw_idle()

    def _load_json(self, event: object) -> None:
        """保存済み JSON から条件を読み込み、UI へ適用する.

        Args:
            event: ボタンクリックイベント（未使用）
        """
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            file_path = filedialog.askopenfilename(
                title="読み込む JSON を選択",
                filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
                initialdir=str(Path.cwd()),
            )
            root.destroy()
        except Exception:
            self._hint_text.set_text("JSON読込に失敗: ファイル選択ダイアログを開けませんでした")
            self._fig.canvas.draw_idle()
            return

        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f_in:
                payload = json.load(f_in)
        except Exception:
            self._hint_text.set_text("JSON読込に失敗: ファイルを解析できませんでした")
            self._fig.canvas.draw_idle()
            return

        display_params: dict[str, float] | None = None
        modulation_mode = None
        overmod_view = None
        fft_target = None
        fft_window = None

        # desktop export payload
        if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
            p = payload["params"]
            if all(
                key in p for key in (
                    "V_dc_V", "V_ll_rms_V", "f_Hz", "f_c_kHz", "t_d_us", "V_on_V", "R_ohm", "L_mH"
                )
            ):
                display_params = {
                    "V_dc": float(p["V_dc_V"]),
                    "V_ll": float(p["V_ll_rms_V"]),
                    "f": float(p["f_Hz"]),
                    "f_c": float(p["f_c_kHz"]),
                    "t_d": float(p["t_d_us"]),
                    "V_on": float(p["V_on_V"]),
                    "R": float(p["R_ohm"]),
                    "L": float(p["L_mH"]),
                }
                modulation_mode = p.get("modulation_mode")
                fft_target = p.get("fft_target")
                fft_window = p.get("fft_window")

        # web export payload
        if display_params is None and isinstance(payload, dict) and isinstance(payload.get("controls"), dict):
            c = payload["controls"]
            if all(key in c for key in ("V_dc", "V_ll_rms", "f", "f_c", "t_d", "V_on", "R", "L")):
                display_params = {
                    "V_dc": float(c["V_dc"]),
                    "V_ll": float(c["V_ll_rms"]),
                    "f": float(c["f"]),
                    "f_c": float(c["f_c"]) / 1000.0,
                    "t_d": float(c["t_d"]) * 1.0e6,
                    "V_on": float(c["V_on"]),
                    "R": float(c["R"]),
                    "L": float(c["L"]) * 1000.0,
                }
                modulation_mode = c.get("modulation_mode")
                overmod_view = c.get("overmod_view")
                fft_target = "current" if c.get("fft_target") == "i_u" else "voltage"
                fft_window = c.get("fft_window")

        if display_params is None:
            self._hint_text.set_text("JSON読込に失敗: 対応フォーマットではありません")
            self._fig.canvas.draw_idle()
            return

        self._applying_scenario = True
        try:
            for key, val in display_params.items():
                if key in self._sliders:
                    self._sliders[key].set_val(val)

            if modulation_mode in MODULATION_MODE_LABELS:
                modulation_idx = list(MODULATION_MODE_LABELS).index(modulation_mode)
                self._modulation_buttons.set_active(modulation_idx)

            if isinstance(overmod_view, bool):
                current_overmod = bool(self._overmod_check.get_status()[0])
                if overmod_view != current_overmod:
                    self._overmod_check.set_active(0)

            if fft_target in FFT_TARGET_LABELS:
                fft_target_idx = list(FFT_TARGET_LABELS).index(fft_target)
                self._fft_target_buttons.set_active(fft_target_idx)

            if fft_window in FFT_WINDOW_LABELS:
                fft_window_idx = list(FFT_WINDOW_LABELS).index(fft_window)
                self._fft_window_buttons.set_active(fft_window_idx)
        finally:
            self._applying_scenario = False

        self._hint_text.set_text(f"読込完了: {Path(file_path).name}")
        self._update(None)

    def _set_baseline(self, event: object) -> None:
        """現在の波形をベースラインとして設定する（IMPROVE-12）.

        Args:
            event: ボタンクリックイベント（未使用）
        """
        if not self._last_results:
            return
        r = self._last_results
        t_ms = r["t"] * 1000.0
        # 線間電圧基本波と相電流をベースラインとしてオーバーレイ
        self._lines["v_uv_baseline"].set_data(t_ms, r["v_uv_fund"])
        self._lines["i_u_baseline"].set_data(t_ms, r["i_u"])
        self._baseline_results = build_baseline_snapshot(r)
        hint = (
            f"ベースライン設定済み: m_a={self._baseline_results['m_a']:.3f}, "
            f"V1={self._baseline_results['V1']:.1f}V, "
            f"THD_V={self._baseline_results['THD_V']:.1f}%"
        )
        self._hint_text.set_text(hint)
        self._fig.canvas.draw_idle()

    def _clear_baseline(self, event: object) -> None:
        """ベースラインオーバーレイをクリアする（IMPROVE-12）.

        Args:
            event: ボタンクリックイベント（未使用）
        """
        self._lines["v_uv_baseline"].set_data([], [])
        self._lines["i_u_baseline"].set_data([], [])
        self._baseline_results = None
        self._hint_text.set_text("ベースライン解除")
        self._fig.canvas.draw_idle()

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
        self._lines["v_uv_baseline"], = ax_vlv.plot(
            [], [], color="darkorange", linestyle=":", linewidth=2.0, alpha=0.7,
            label="ベースライン",
        )
        ax_vlv.legend(loc="upper right", fontsize=7, ncol=5)

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
        self._lines["i_u_baseline"], = ax_cur.plot(
            [], [], color="purple", linestyle=":", linewidth=2.0, alpha=0.7,
            label="ベースライン i_u",
        )
        ax_cur.legend(loc="upper right", fontsize=7, ncol=5)

        # サブプロット 6: FFTスペクトル
        ax_fft.set_ylabel("振幅 [V]")
        ax_fft.set_xlabel("周波数 [kHz]")
        ax_fft.set_title("線間電圧 v_uv スペクトル", fontsize=9)
        self._fft_bars = None
        self._thd_text = ax_fft.text(
            0.98, 0.95, "", transform=ax_fft.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
        )

    def _read_display_params(self) -> dict[str, float]:
        """スライダーから現在の表示単位パラメータを読み取る."""
        return {
            "V_dc": float(self._sliders["V_dc"].val),
            "V_ll": float(self._sliders["V_ll"].val),
            "f": float(self._sliders["f"].val),
            "f_c": float(self._sliders["f_c"].val),
            "t_d": float(self._sliders["t_d"].val),
            "V_on": float(self._sliders["V_on"].val),
            "R": float(self._sliders["R"].val),
            "L": float(self._sliders["L"].val),
        }

    def _read_params(self) -> dict:
        """スライダーから現在のパラメータ値を読み取る.

        Returns:
            パラメータ辞書（SI単位系）
        """
        return normalize_ui_display_params(
            self._read_display_params(),
            fft_target=self._fft_target,
            fft_window=self._fft_window,
            overmod_view=self._overmod_view,
            modulation_mode=self._modulation_mode,
        )

    def _run_simulation(
        self, params: dict
    ) -> dict[str, object]:
        """application 層の simulation runner を呼び出す.

        Args:
            params: パラメータ辞書（SI単位系）

        Returns:
            シミュレーション結果辞書
        """
        return run_simulation(params)

    def _draw_waveforms(self, results: dict) -> None:
        """波形データをプロットに反映する.

        Args:
            results: シミュレーション結果辞書
        """
        t_ms = results["t"] * 1000.0  # [ms] 表示用

        # === 情報パネル: 導出量の表示 ===
        V_ph_peak = results["V_ll"] * np.sqrt(2.0) / np.sqrt(3.0)  # [V] V_ll は RMS
        m_a_raw = 2.0 * V_ph_peak / results["V_dc"]  # クランプ前の変調率
        m_a_limit = results["m_a_limit"]
        limit_linear = bool(results.get("limit_linear", True))
        m_a = min(m_a_raw, m_a_limit) if limit_linear else m_a_raw
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
        diagnostics = results.get("diagnostics", {})
        err_pct = (abs(I_measured - I_theory) / I_theory * 100.0
                   if I_theory > 1e-6 else 0.0)

        clamp_str = ""
        if limit_linear and m_a_raw > m_a_limit:
            clamp_str = f" (クランプ中: 上限 {m_a_limit:.3f})"
        if not limit_linear and m_a_raw > m_a_limit:
            clamp_str = f" (過変調観察中: 線形上限 {m_a_limit:.3f} を超過)"
        info_lines = [
            f"変調構成 = {results['modulation_summary_label']}",
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
        if diagnostics:
            info_lines.append(
                "実務チェック = "
                f"OK {diagnostics.get('ok_count', 0)} / "
                f"Warn {diagnostics.get('warn_count', 0)}  "
                f"({diagnostics.get('summary', '')})"
            )
        # ベースライン比較情報（設定済みの場合に追記）
        if self._baseline_results:
            bl = self._baseline_results
            delta_V1 = fft_vuv["fundamental_mag"] - bl["V1"]
            delta_I1 = I_measured - bl["I_measured"]
            info_lines.append(
                f"[ベースライン比較] m_a={bl['m_a']:.3f}, "
                f"V1={bl['V1']:.1f}V (Δ{delta_V1:+.1f}V), "
                f"THD_V={bl['THD_V']:.1f}%, "
                f"I1={bl['I_measured']:.2f}A (Δ{delta_I1:+.2f}A)"
            )
        self._info_text.set_text("\n".join(info_lines))
        if limit_linear and m_a_raw > m_a_limit:
            self._info_text.get_bbox_patch().set_facecolor("lightsalmon")
        elif (not limit_linear) and m_a_raw > m_a_limit:
            self._info_text.get_bbox_patch().set_facecolor("moccasin")
        else:
            self._info_text.get_bbox_patch().set_facecolor("lightyellow")

        # === サブプロット 1: 指令信号 + キャリア ===
        self._lines["v_u"].set_data(t_ms, results["v_u"])
        self._lines["v_v"].set_data(t_ms, results["v_v"])
        self._lines["v_w"].set_data(t_ms, results["v_w"])
        self._lines["carrier"].set_data(t_ms, results["v_carrier"])
        self._lines["v_u"].set_drawstyle("default")
        self._lines["v_v"].set_drawstyle("default")
        self._lines["v_w"].set_drawstyle("default")

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
            f"{series_title} スペクトル ({results['modulation_summary_label']}, {results['fft_window_label']})",
            fontsize=8,
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
        if self._applying_scenario:
            return
        params = self._read_params()
        results = self._run_simulation(params)
        self._last_results = results
        self._draw_waveforms(results)

    def run(self) -> None:
        """メインループを開始する."""
        plt.show()
