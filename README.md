# 三相PWMインバータ学習シミュレータ

三相PWMインバータの原理を対話的に学習するためのシミュレーションソフトウェアです。  
パラメータをスライダーで操作し、指令信号・スイッチングパターン・出力電圧・負荷電流・FFTスペクトルをリアルタイムに観察できます。

## 特徴

- **5段波形表示**: 変調信号+キャリア / スイッチングパターン / 線間電圧 / 相電流 / FFTスペクトル
- **6パラメータスライダー**: $V_{dc}$, $V_{LL}$(rms), $f$, $f_c$, $R$, $L$ をリアルタイム変更
- **FFT解析 + THD表示**: 基本波（青）/ キャリア高調波（赤）の色分け表示
- **変調率モニタ**: $m_a$ 値を常時表示、過変調時にはクランプ警告
- **定常状態表示**: 助走区間（5τ以上）を自動計算し、定常波形のみを表示

## 動作環境

- Python 3.10 以上
- OS: Windows / macOS / Linux

## セットアップ

```bash
pip install -r requirements.txt
```

依存ライブラリ: NumPy, Matplotlib, SciPy, pytest

## 実行

```bash
python main.py
```

## テスト

```bash
python -m pytest tests/ -v
```

16件のテスト（物理妥当性検証）が実行されます。

## プロジェクト構成

```
3lvlpwm/
├── main.py                      # エントリポイント（デフォルトパラメータ一元管理）
├── simulation/                  # シミュレーションエンジン（純粋関数）
│   ├── reference_generator.py   # 三相指令信号生成
│   ├── carrier_generator.py     # 三角波キャリア生成
│   ├── pwm_comparator.py        # PWMスイッチングパターン生成
│   ├── inverter_voltage.py      # インバータ出力電圧演算
│   ├── rl_load_solver.py        # RL負荷電流演算（RK4法）
│   └── fft_analyzer.py          # FFTスペクトル解析 + THD計算
├── ui/
│   └── visualizer.py            # Matplotlib波形表示UI（5段+スライダー）
├── tests/
│   └── test_simulation.py       # 物理妥当性テスト（16件）
├── architecture.md              # アーキテクチャ設計書
├── implementation_plan.md       # 実装計画書（STEP 1〜8）
├── improvement_plan.md          # 改善ロードマップ（IMPROVE 1〜6）
└── requirements.txt
```

## パラメータ一覧

| パラメータ | 記号 | デフォルト | 範囲 | 単位 |
|---|---|---|---|---|
| 直流母線電圧 | $V_{dc}$ | 300 | 100–600 | V |
| 線間電圧指令（RMS） | $V_{LL}$ | 141 | 0–450 | V |
| 出力周波数 | $f$ | 50 | 1–200 | Hz |
| キャリア周波数 | $f_c$ | 5 | 1–20 | kHz |
| 負荷抵抗 | $R$ | 10 | 0.1–100 | Ω |
| 負荷インダクタンス | $L$ | 10 | 0.1–100 | mH |

## シミュレーション処理フロー

```
指令信号生成 → キャリア生成 → PWM比較 → 電圧演算 → RL負荷演算 → FFT解析 → 波形表示
```

## ドキュメント

- [利用手順書](docs/user_guide.md) — 操作方法と学習のポイント
- [アーキテクチャ設計書](architecture.md)
- [実装計画書](implementation_plan.md)
- [改善ロードマップ](improvement_plan.md)

## ライセンス

MIT License
