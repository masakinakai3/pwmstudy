# /review — コードレビュー

引数で指定したファイル（省略時は直近の変更ファイル）を、以下の観点でレビューして日本語で報告する。

## チェックリスト

### スタイル（CLAUDE.md 準拠）
- [ ] PEP 8・行長 100文字以内（数式のみ 120 許容）
- [ ] 全関数に型ヒントと Google スタイル docstring
- [ ] 命名規則準拠（関数/変数: snake_case, 定数: UPPER_SNAKE, クラス: PascalCase）
- [ ] 物理量プレフィックス（v_, i_, S_, leg_, f_c, V_dc など）
- [ ] 変数コメントに単位: `R: float  # [Ω]`

### 設計・安全性
- [ ] `simulation/` 層に matplotlib / fastapi / plotly 依存なし
- [ ] グローバル状態・`eval()`・`exec()` 不使用
- [ ] 内部計算は全て SI 単位（V, A, Ω, H, Hz, s）
- [ ] 時間配列は `np.linspace`（`np.arange` 禁止）
- [ ] `n_points = int(round(T_sim / dt)) + 1`（`int()` 切り捨て禁止）
- [ ] ハードコードされた物理パラメータなし

### テスト
- [ ] 新規関数に対応する回帰テストが tests/ にあるか

## 出力フォーマット

問題がある場合は以下の形式で報告する:
```
### [CRITICAL|WARNING|INFO] ファイル名:行番号
問題の説明
修正案
```

問題がなければ「レビュー完了: 問題なし」と報告する。

$ARGUMENTS
