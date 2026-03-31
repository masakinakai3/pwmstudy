"""三相PWMインバータ学習ソフトウェア — エントリポイント."""

from ui.visualizer import InverterVisualizer


def main() -> None:
    """デフォルトパラメータでビジュアライザを起動する."""
    default_params = {
        "V_dc": 300.0,    # [V]  直流母線電圧
        "V_ll": 141.0,    # [V]  線間電圧指令RMS値 (peak ≈ 200 V)
        "f":     50.0,    # [Hz] 出力周波数
        "f_c": 5000.0,    # [Hz] キャリア周波数
        "R":     10.0,    # [Ω]  負荷抵抗
        "L":      0.01,   # [H]  負荷インダクタンス (= 10 mH)
    }

    visualizer = InverterVisualizer(default_params)
    visualizer.run()


if __name__ == "__main__":
    main()
