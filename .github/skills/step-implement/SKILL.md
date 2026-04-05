---
name: step-implement
description: "Implement or extend a current feature in this repository. Use when modifying simulation modules, application/web API layers, desktop UI, or web UI while keeping implementation_plan.md and improvement_plan.md aligned."
argument-hint: "STEP number (e.g., 'STEP 2' or '2') or feature name (e.g., 'FFT analysis')"
---

# STEP 実装 / 機能拡張スキル

> **現在の状態**: STEP 1〜8 実装済み。IMPROVE-1〜12 と web/application 層拡張が適用済み。simulation / application / desktop UI / web UI / FastAPI を横断して変更が入る可能性がある。

## When to Use
- implementation_plan.md の特定 STEP を再実装・修正するとき
- 既存改善項目や web/app 機能を拡張するとき
- `/step-implement STEP 2` や `/step-implement FFT` のように呼び出す

## Procedure (Existing STEP Modification)

### Step 1: 現状の確認
対象モジュールの現在の実装を読み取る:
- 関数シグネチャ・アルゴリズム
- 依存するモジュール・呼び出し元
- 関連するテストケース

### Step 2: 変更の実装
`.github/copilot-instructions.md` の規約に従い変更:
- 型ヒント付き関数シグネチャ
- Google スタイル docstring（引数の単位を明記）
- NumPy ベクトル演算
- 変数コメントに単位を記載
- desktop/web 共有仕様は application 層に寄せる

### Step 3: 検証
変更後に全テストを実行:
- 既存テスト34件のリグレッション確認
- 必要に応じて新規テストを追加

## Procedure (New Feature Extension)

### Step 1: 計画の確認
`improvement_plan.md` の将来拡張候補を確認:

実装済み:
1. ~~FFT解析パネル追加~~ (IMPROVE-5)
2. ~~助走期間の導入~~ (IMPROVE-3)
3. ~~THD 表示~~ (IMPROVE-5)
4. ~~m_a表示 + クランプ通知~~ (IMPROVE-2)
5. ~~V_LL RMS入力~~ (IMPROVE-4)
6. ~~RK4 ZOH一貫性~~ (IMPROVE-6)
7. ~~非理想インバータモデル~~ (IMPROVE-8)
8. ~~RL ソルバの厳密離散化~~ (IMPROVE-9)
9. ~~PWM 方式比較モード~~ (IMPROVE-7)
10. ~~FFT 精度向上と電流スペクトル拡張~~ (IMPROVE-10)
11. ~~学習シナリオガイド~~ (IMPROVE-11)
12. ~~条件比較・エクスポート~~ (IMPROVE-12)

継続的な保守対象:
1. simulation / application / web の契約同期
2. シナリオ定義と UI 表示の整合
3. SVPWM / DPWM / Overmod View の説明・可視化改善

### Step 2: 影響範囲の調査
- `simulation/` に新モジュールが必要か、既存の拡張か
- `application/` と `webapi/` の契約変更が必要か
- `ui/visualizer.py` と `webui/` の両方へ表示追加が必要か
- `main.py` / README / docs の同期が必要か

### Step 3: 実装
- `simulation/` と `ui/` のモジュール分離を維持する
- 新パラメータのデフォルト値は `main.py` で一元管理する

### Step 4: テスト追加
- `tests/test_simulation.py` に新テストクラスを追加
- 物理妥当性テスト（三相対称性・値域・理論値）を含める
- application / API / scenario schema の契約テストも必要に応じて追加する

### Step 5: 報告
実装結果を以下の形式で報告:
- 変更・追加した関数一覧
- 既存テスト34件 PASS/FAIL
- 新規テストの検証結果

## References
- [implementation_plan.md](../../../implementation_plan.md) — STEP 詳細仕様
- [improvement_plan.md](../../../improvement_plan.md) — 改善計画書
- [architecture.md](../../../architecture.md) — モジュール間データフロー
- [docs/web_api_contract.md](../../../docs/web_api_contract.md) — application / API / web UI 契約
