# 三相PWMインバータ学習シミュレータ

三相PWMインバータの原理を対話的に学習するためのシミュレーションソフトウェアです。
パラメータをスライダーで操作し、指令信号・スイッチングパターン・線間電圧・相電圧・負荷電流・FFTスペクトルをリアルタイムに観察できます。

## 特徴

- **6段波形表示**: 変調信号+キャリア / スイッチングパターン / 線間電圧 / 相電圧 / 相電流 / FFTスペクトル
- **8パラメータスライダー + PWM方式選択**: 数値条件に加え、Natural / Regular / Third Harmonic Injection を切替可能
- **FFT表示切替**: 線間電圧 v_uv と相電流 i_u を切替表示、Hann / Rectangular 窓も選択可能
- **FFT解析 + THD表示**: 基本波・キャリア高調波の色分け表示、V1 / I1 / RMS / THD / 基本波力率を確認可能
- **変調率モニタ**: $m_a$ 値を常時表示、過変調時にはクランプ警告
- **理論比較表示**: 相電流の基本波振幅を理論値と FFT 実測値で比較
- **定常状態表示**: 助走区間（5τ以上）を自動計算し、定常波形のみを表示
- **厳密離散 RL ソルバ**: 区分定数の相電圧入力に対し、解析解ベースの離散時間更新で電流を計算
- **非理想インバータモデル**: デッドタイムと固定導通電圧降下を含む簡易実機近似を切り替え可能
- **PWM方式比較**: 規則サンプリングによる保持波形と、三次高調波注入による線形範囲拡張を観察可能

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

34件のテスト（物理妥当性検証）が実行されます。

## プロジェクト構成

```text
3lvlpwm/
├── main.py                      # エントリポイント（デフォルトパラメータ一元管理）
├── simulation/                  # シミュレーションエンジン（純粋関数）
│   ├── reference_generator.py   # 三相指令信号生成
│   ├── carrier_generator.py     # 三角波キャリア生成
│   ├── pwm_comparator.py        # PWMスイッチングパターン生成
│   ├── inverter_voltage.py      # インバータ出力電圧演算
│   ├── rl_load_solver.py        # RL負荷電流演算（厳密離散時間解）
│   └── fft_analyzer.py          # FFTスペクトル解析 + RMS/THD計算
├── ui/
│   └── visualizer.py            # Matplotlib波形表示UI（6段+スライダー+FFT切替+理論比較）
├── tests/
│   └── test_simulation.py       # 物理妥当性テスト（34件）
├── architecture.md              # アーキテクチャ設計書
├── implementation_plan.md       # 実装計画書（STEP 1〜8）
├── improvement_plan.md          # 改善ロードマップ（IMPROVE 1〜6）
└── requirements.txt
```

## パラメータ一覧

| パラメータ | 記号 | デフォルト | 範囲 | 単位 |
| --- | --- | --- | --- | --- |
| 直流母線電圧 | $V_{dc}$ | 300 | 100–600 | V |
| 線間電圧指令（RMS） | $V_{LL}$ | 141 | 0–450 | V |
| 出力周波数 | $f$ | 50 | 1–200 | Hz |
| キャリア周波数 | $f_c$ | 5 | 1–20 | kHz |
| デッドタイム | $t_d$ | 0 | 0–10 | us |
| 導通電圧降下 | $V_{on}$ | 0 | 0–5 | V |
| 負荷抵抗 | $R$ | 10 | 0.1–100 | Ω |
| 負荷インダクタンス | $L$ | 10 | 0.1–100 | mH |

## シミュレーション処理フロー

```text
PWM方式選択 → 指令信号生成 / サンプリング方式適用 → キャリア生成 → PWM比較 → デッドタイム適用 →
非理想電圧演算 → RL負荷演算 → FFT解析 → 波形/理論比較表示
```

## ドキュメント

- [利用手順書](docs/user_guide.md) — 操作方法と学習のポイント
- [アーキテクチャ設計書](architecture.md)
- [実装計画書](implementation_plan.md)
- [改善ロードマップ](improvement_plan.md) — 未実装改善のロードマップ

## ライセンス

未設定です。配布条件を明示する場合は LICENSE ファイルを追加してください。
