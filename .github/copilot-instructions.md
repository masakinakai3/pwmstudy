# Copilot 指示書 — 三相PWMインバータ学習ソフトウェア

## プロジェクト概要

三相PWMインバータの原理を学習するためのシミュレーションソフトウェア。
Python + NumPy + Matplotlib（widgets）構成。**STEP 1〜8 の初期実装＋改善 IMPROVE-1〜6 適用済み。**

## アーキテクチャ

- `simulation/` — シミュレーションエンジン（6モジュール、全て純粋関数）
  - `reference_generator.py` — `generate_reference(V_ll, f, V_dc, t)`
  - `carrier_generator.py` — `generate_carrier(f_c, t)`
  - `pwm_comparator.py` — `compare_pwm(v_u, v_v, v_w, v_carrier)`
  - `inverter_voltage.py` — `calc_inverter_voltage(S_u, S_v, S_w, V_dc)`
  - `rl_load_solver.py` — `solve_rl_load(v_uN, v_vN, v_wN, R, L, dt)`
  - `fft_analyzer.py` — `analyze_spectrum(signal, dt, f_fundamental)`
- `ui/` — Matplotlib ベースの波形表示UI
  - `visualizer.py` — `InverterVisualizer` クラス（5段サブプロット + 6スライダー + m_a表示）
- `main.py` — エントリポイント（デフォルトパラメータの一元管理、V_ll は RMS 値）
- `tests/test_simulation.py` — 物理妥当性テスト（16件）
- `docs/user_guide.md` — 利用手順書

詳細は `architecture.md`、`implementation_plan.md`、`improvement_plan.md` を参照。

## 実行・テスト

```bash
python main.py                    # GUI 起動
python -m pytest tests/ -v        # テスト実行（16件）
```

## コーディング規約

### 言語・スタイル
- Python 3.10 以上を対象
- PEP 8 準拠（インデント: スペース4つ、最大行長: 100文字）
- docstring は Google スタイル
- 型ヒントを関数シグネチャに付与すること

### 命名規則
- 物理量の変数名は電気工学の慣例に従う
  - 電圧: `v_` プレフィックス（例: `v_uv`, `v_carrier`, `v_uN`）
  - 電流: `i_` プレフィックス（例: `i_u`, `i_v`, `i_w`）
  - スイッチング信号: `S_` プレフィックス（例: `S_u`, `S_v`, `S_w`）
  - 周波数: `f` または `f_c`（キャリア）
  - 時間: `t`, 時間刻み: `dt`
  - 変調率: `m_a`、直流母線電圧: `V_dc`、線間電圧RMS値: `V_ll`
- 定数はアッパースネークケース（例: `V_DC_DEFAULT`, `POINTS_PER_CARRIER`, `N_WARMUP_CYCLES_MIN`）
- 関数名・変数名はスネークケース
- クラス名はパスカルケース（例: `InverterVisualizer`）

### 数値計算ルール
- 配列演算には NumPy のベクトル演算を使用し、Python の for ループは避ける
  - **例外**: `rl_load_solver.py` のRK4時間ステップ積分（ステップ間依存のため for ループ許容）
- 浮動小数点比較には許容誤差（`np.allclose`）を使用する
- 時間配列は `np.arange` ではなく `np.linspace` で生成する（端点精度の確保）

### 物理パラメータ
- SI単位系を使用（V, A, Ω, H, Hz, s）
- UI表示時のみ mH, kHz 等の補助単位を使用（`ui/visualizer.py` 内で変換）
- 変数のコメントに必ず単位を記載する（例: `R: float  # [Ω]`）

## モジュール間インターフェース

各シミュレーションモジュールは **純粋関数** として実装する:
- 副作用なし（グローバル状態の変更禁止）
- 入出力は NumPy 配列と float のみ
- matplotlib への依存は `ui/` パッケージ内に限定

### データフロー（実装済み）
```
main.py → InverterVisualizer._run_simulation()
  → generate_reference() → generate_carrier() → compare_pwm()
  → calc_inverter_voltage() → solve_rl_load()
  → analyze_spectrum()
  → _draw_waveforms()
```

## テスト方針

テストは `tests/test_simulation.py` に集約（pytest、クラス単位で構成）:

| テストクラス | 検証内容 |
|---|---|
| `TestReferenceGenerator` | 三相和=0、値域[-1,1]、過変調クランプ、零電圧 |
| `TestCarrierGenerator` | 値域[-1,1]、±1到達 |
| `TestPwmComparator` | スイッチング値{0,1}、零変調時の挙動 |
| `TestInverterVoltage` | 線間電圧和=0、相電圧和=0、3レベル確認 |
| `TestRlLoadSolver` | 定常電流振幅の理論値一致（5%以内）、三相電流和≈0 |
| `TestFftAnalyzer` | 純正弦波THD≈0、基本波振幅一致、PWMスペクトル検証 |

## 禁止事項

- `simulation/` パッケージ内での matplotlib インポート
- グローバル変数の使用
- `eval()` / `exec()` の使用
- ハードコードされたパラメータ値（デフォルト値は `main.py` で一元管理）
- `np.arange` での時間配列生成（端点精度の問題）
