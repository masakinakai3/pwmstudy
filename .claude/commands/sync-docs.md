# /sync-docs — ドキュメント同期チェック

直近の変更内容（git diff）を確認し、以下のルールに従ってドキュメント同期が必要か判断して日本語で報告する。

## 同期ルール（CLAUDE.md より）

| 変更対象 | 同期すべきドキュメント |
|---|---|
| modulation mode 追加・変更 | docs/user_guide.md, docs/web_api_contract.md, README.md |
| scenario schema 変更 | docs/user_guide.md, docs/web_api_contract.md, README.md |
| `/simulate` / `/scenarios` 応答構造変更 | docs/web_api_contract.md |
| desktop/web エクスポート仕様変更 | 該当ドキュメント |
| テスト構成の大きな変更 | docs/user_guide.md |

## 手順

1. `git diff --name-only` でコード変更ファイルを列挙する
2. 上記ルールに照らして同期が必要なドキュメントを特定する
3. 対象ドキュメントの該当セクションを Read で確認する
4. 不整合があれば具体的な修正案を提示する（自動適用は確認を取ってから）

## 出力フォーマット

```
## ドキュメント同期チェック結果

### 変更検出
- ファイル: xxx.py → トリガー: modulation mode 変更

### 同期が必要
- [ ] docs/web_api_contract.md §X.X: 〇〇を追記
- [ ] docs/user_guide.md §Y.Y: 〇〇を更新

### 同期不要
- 該当なし
```

$ARGUMENTS
