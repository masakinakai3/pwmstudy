# CLAUDE.md — 三相PWMインバータ学習シミュレータ

## プロジェクト概要

三相2レベルPWMインバータの原理を学習するためのシミュレータ。
desktop UI（Matplotlib）と web UI（FastAPI + Plotly）を並行維持し、共通の application 層と simulation 層を共有する。

## アーキテクチャ

```
simulation/          純粋関数ベースの数値計算層（UI依存なし）
application/         desktop/web 共有の非UI層（統合・単位変換・エクスポート）
ui/                  Matplotlib ベースの desktop UI
webapi/              FastAPI（REST API）
webui/               静的フロントエンド（vanilla JS + Plotly）
tests/               pytest 回帰テスト群
docs/                ユーザーガイド、API契約、数学ガイド
```

### データフロー

**desktop:**
```
main.py → ui.visualizer → application.run_simulation() → simulation.*
```

**web:**
```
webui/app.js → POST /simulate → webapi → application.run_simulation() → simulation.*
```

## 実行・テスト

```bash
# desktop UI
python main.py

# web UI
python -m uvicorn webapi.app:app --reload

# テスト（74件）
python -m pytest tests -v

# 特定テストクラスのみ
python -m pytest tests -k "RlLoad"
```

## 言語・スタイル

- Python 3.10+, PEP 8 準拠, スペース4, 最大行長100（数式のみ120許容）
- 全関数に型ヒント、docstring は Google スタイル
- JS/HTML/CSS は既存 webui の記法とトーンを維持
- コミットメッセージ: `<type>: <概要>`（type: feat, fix, refactor, test, docs, style）

## 命名規則

| 物理量 | プレフィックス | 例 |
|---|---|---|
| 電圧 | `v_` | `v_uv`, `v_carrier`, `v_uN` |
| 電流 | `i_` | `i_u`, `i_v`, `i_w` |
| スイッチング信号 | `S_` | `S_u`, `S_v`, `S_w` |
| レグ状態 | `leg_` | `leg_u`, `leg_v`, `leg_w` |
| 周波数 | `f`, `f_c` | `f`, `f_c` |
| 時間 | `t`, `dt` | `t`, `dt_actual` |
| 変調率 | `m_a` | `m_a` |
| 直流母線電圧 | `V_dc` | `V_dc` |

- 関数: スネークケース、変数: スネークケース、定数: アッパースネークケース、クラス: パスカルケース
- 変数コメントに単位を記載: `R: float  # [Ω]`

## 単位系

- **内部計算: 全てSI単位系**（V, A, Ω, H, Hz, s）
- UI表示のみ補助単位（mH, kHz, us）— 変換は UI/application 層で行う
- `int(round(T_sim / dt)) + 1` で `n_points` を計算（`int()` 切り捨て禁止）
- ソルバーに渡す dt: `dt_actual = t[1] - t[0]`

## modulation_mode 契約

外部入力は `modulation_mode` 1本で統一:
- `carrier`
- `carrier_third_harmonic`
- `carrier_two_phase`
- `space_vector`
- `space_vector_two_phase`

内部では `reference_mode` / `sampling_mode` / `clamp_mode` へ写像する。
旧入力軸を新規 UI/API 仕様へ逆流させない。

## 数値計算ルール

- 配列処理は NumPy ベクトル演算を優先
  - 唯一の例外: `rl_load_solver.py` の厳密離散時間更新（ステップ間依存）
- 時間配列は `np.linspace`（`np.arange` 禁止 — 端点精度の問題）
- 浮動小数点比較: `np.allclose` / `np.isclose`

## 禁止事項

- `simulation/` での `matplotlib` / `fastapi` / `plotly` 依存
- グローバル状態への依存
- `eval()` / `exec()` の使用
- SI 以外の単位での内部計算
- `np.arange` での時間配列生成
- ハードコードされた物理パラメータ

## ドキュメント同期

以下を変更したら関連ドキュメントも同期する:
- modulation mode / scenario schema → `docs/user_guide.md`, `docs/web_api_contract.md`, `README.md`
- `/simulate` / `/scenarios` の応答構造 → `docs/web_api_contract.md`
- desktop/web のエクスポート仕様
- テスト構成の大きな変更

## 参照ドキュメント

- `architecture.md` — アーキテクチャ設計
- `implementation_plan.md` — 実装計画書
- `improvement_plan.md` — 改善計画書
- `docs/web_api_contract.md` — Web API 契約
- `docs/user_guide.md` — ユーザーガイド
- `docs/deep_math_guide.md` — 数学・物理詳細ガイド
