# webapi/ — FastAPI 規約

FastAPI の入出力契約のみを担当する。物理計算を再実装しない。

## エンドポイント

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/` | GET | ルート（静的ファイル配信） |
| `/health` | GET | ヘルスチェック |
| `/scenarios` | GET | `application.SCENARIO_PRESETS` を返す |
| `/simulate` | POST | シミュレーション実行、`application.run_simulation()` + `build_web_response()` |
| `/sweep` | POST | m_a スイープ実行、`application.simulation_runner.run_sweep()` |

## スキーマ

- `schemas.py` の `SimulationRequest` で範囲検証と unknown field rejection を行う
- `schemas.py` の `SweepRequest` で m_a スイープ入力を検証する
- 外部 API の `fft_target` は `v_uv` / `i_u`、内部では `voltage` / `current` に写像

## 規約

- `app.py` は API エンドポイント定義のみ — 物理計算ロジックを書かない
- `modulation_mode` 1本化を維持し、旧入力軸をスキーマに戻さない
- 全ての計算は `application/` 層へ委譲する

## 同期対象

- `docs/web_api_contract.md` — レスポンス構造が変わったら更新
