# コントリビューションガイド

三相PWMインバータ学習ソフトウェアへの貢献ありがとうございます。

> **現在の状態**: STEP 1〜8 の初期実装＋改善 IMPROVE-1〜6 適用済み。テスト16件 ALL PASS。
> 今後は機能拡張・改善フェーズです。

## 開発環境のセットアップ

### 前提条件
- Python 3.10 以上
- Git

### 手順

```bash
git clone <repository-url>
cd 3lvlpwm
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

### 動作確認

```bash
python main.py                    # GUI 起動
python -m pytest tests/ -v        # テスト実行（16件）
```

## プロジェクト構成

```
3lvlpwm/
├── main.py                      # エントリポイント（デフォルトパラメータ一元管理、V_llはRMS値）
├── simulation/
│   ├── __init__.py
│   ├── reference_generator.py   # 三相指令信号生成
│   ├── carrier_generator.py     # 三角波キャリア生成
│   ├── pwm_comparator.py        # PWMスイッチングパターン
│   ├── inverter_voltage.py      # 線間・相電圧演算
│   ├── rl_load_solver.py        # RL負荷電流演算（RK4法、ZOH一貫性）
│   └── fft_analyzer.py          # FFTスペクトル解析・THD計算
├── ui/
│   ├── __init__.py
│   └── visualizer.py            # 5段波形表示 + 6スライダー + m_a表示
├── tests/
│   └── test_simulation.py       # 物理妥当性テスト（16件、6クラス）
├── docs/
│   └── user_guide.md            # 利用手順書
├── requirements.txt
├── architecture.md
├── implementation_plan.md
└── improvement_plan.md
```

## ブランチ戦略

```
main          ← 安定版（常に動作する状態を維持）
├── feature/* ← 新機能（例: feature/fft-analysis）
├── fix/*     ← バグ修正（例: fix/carrier-phase-offset）
└── refactor/*← リファクタリング
```

- `main` への直接コミットは禁止
- PR ベースでマージする

## コミットメッセージ規約

```
<type>: <概要>

<本文（任意）>
```

### type 一覧

| type | 用途 |
|---|---|
| `feat` | 新機能追加 |
| `fix` | バグ修正 |
| `refactor` | コードの内部改善（動作変更なし） |
| `test` | テストの追加・修正 |
| `docs` | ドキュメントのみの変更 |
| `style` | フォーマット変更（動作に影響しないもの） |

### 例

```
feat: RL負荷電流演算モジュールを実装

RK4法による数値積分を採用。
各相独立に微分方程式を解く。
```

## 実装時の注意事項

### モジュール分離の原則

- `simulation/` パッケージ内では **matplotlib をインポートしない**
- シミュレーション関数は **純粋関数** として実装する（副作用なし）
- グローバル変数は使用しない

### 物理量の命名規則

| 物理量 | プレフィックス | 例 |
|---|---|---|
| 電圧 | `v_` | `v_uv`, `v_carrier` |
| 電流 | `i_` | `i_u`, `i_v`, `i_w` |
| スイッチング | `S_` | `S_u`, `S_v`, `S_w` |
| 周波数 | `f` / `f_c` | `f`, `f_c` |
| 時間 | `t` / `dt` | `t`, `dt` |

### 単位

- コード内部は **SI単位系** を使用（V, A, Ω, H, Hz, s）
- UI表示でのみ補助単位（mH, kHz 等）に変換
- 変数コメントに必ず単位を記載する: `R: float  # [Ω]`

### 数値計算

- NumPy のベクトル演算を使用（Python の for ループは避ける）
- 浮動小数点比較には `np.allclose` を使用
- 時間配列は `np.linspace` で生成（`np.arange` は端点精度の問題あり）

## テスト

### テストの実行

```bash
python -m pytest tests/ -v        # 全テスト（16件）
python -m pytest tests/ -k "RlLoad"  # 特定クラスのみ
```

### テストファイル構成

テストは `tests/test_simulation.py` に集約（クラス単位で構成）:

| テストクラス | テスト数 | 検証内容 |
|---|---|---|
| `TestReferenceGenerator` | 4 | 三相和=0、値域[-1,1]、過変調クランプ、零電圧 |
| `TestCarrierGenerator` | 2 | 値域[-1,1]、±1到達 |
| `TestPwmComparator` | 2 | スイッチング値{0,1}、零変調時OFF |
| `TestInverterVoltage` | 3 | 線間電圧和=0、相電圧和=0、3レベル |
| `TestRlLoadSolver` | 2 | 定常電流振幅理論値一致、三相電流和≈0 |
| `TestFftAnalyzer` | 3 | 純正弦波THD≈0、基本波振幅一致、PWMスペクトル検証 |

### テスト作成の指針

各モジュールで以下を検証すること:

| 検証項目 | 方法 |
|---|---|
| 三相の和 = 0 | `np.allclose(v_u + v_v + v_w, 0)` |
| 出力値の範囲 | 変調信号: [-1, 1]、スイッチング: {0, 1} |
| 理論値との一致 | 定常状態で誤差 5%以内 |

## Pull Request の手順

1. Issue を確認（または新規作成）
2. feature ブランチを作成
3. 機能拡張の場合は `improvement_plan.md` の将来拡張候補を参照
4. テストを追加・通過させる（`python -m pytest tests/ -v`）
5. PR テンプレートに従って記述
6. レビューを依頼

## 参照ドキュメント

- [architecture.md](../architecture.md) — アーキテクチャ設計
- [implementation_plan.md](../implementation_plan.md) — 実装計画書
- [improvement_plan.md](../improvement_plan.md) — 改善計画書（IMPROVE-1〜6）
- [CODING_STANDARDS.md](CODING_STANDARDS.md) — コーディング規約詳細
