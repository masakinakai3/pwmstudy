---
name: step-implement
description: "Implement a specific STEP from the implementation plan. Use when starting a new implementation step, coding a simulation module, or building the UI. Reads the plan, scaffolds the file, implements the algorithm, and runs verification."
argument-hint: "STEP number (e.g., 'STEP 2' or '2') or feature name (e.g., 'FFT analysis')"
---

# STEP 実装 / 機能拡張スキル

> **現在の状態**: STEP 1〜8 の初期実装＋改善 IMPROVE-1〜6 適用済み。テスト16件 ALL PASS。

## When to Use
- implementation_plan.md の特定 STEP を再実装・修正するとき
- 将来拡張候補（FFT解析、助走期間、過変調モード等）を実装するとき
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

### Step 3: 検証
変更後に全テストを実行:
- 既存テスト16件のリグレッション確認
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

未実装:
1. 過変調モード（m_a > 1）
2. デッドタイム模擬
3. 規則サンプリングPWMモード

### Step 2: 影響範囲の調査
- `simulation/` に新モジュールが必要か、既存の拡張か
- `ui/visualizer.py` への表示追加が必要か
- `main.py` にパラメータ追加が必要か

### Step 3: 実装
- `simulation/` と `ui/` のモジュール分離を維持する
- 新パラメータのデフォルト値は `main.py` で一元管理する

### Step 4: テスト追加
- `tests/test_simulation.py` に新テストクラスを追加
- 物理妥当性テスト（三相対称性・値域・理論値）を含める

### Step 5: 報告
実装結果を以下の形式で報告:
- 変更・追加した関数一覧
- 既存テスト16件 PASS/FAIL
- 新規テストの検証結果

## References
- [implementation_plan.md](../../implementation_plan.md) — STEP 詳細仕様
- [improvement_plan.md](../../improvement_plan.md) — 改善計画書（IMPROVE-1〜6）
- [architecture.md](../../architecture.md) — モジュール間データフロー
