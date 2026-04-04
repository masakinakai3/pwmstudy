# Web Phase 0-5 契約整理

## 目的

web 移行 Phase 0 では、Matplotlib UI に埋め込まれていた統合シミュレーション処理を UI 非依存の契約として切り出し、後続の FastAPI 実装でそのまま再利用できる状態を作る。

実装は [application/simulation_runner.py](../application/simulation_runner.py) に集約した。

## 実装範囲

1. run_simulation(params)
2. build_web_response(results, max_points=1000)
3. normalize_ui_display_params(display_params, pwm_mode, fft_target, fft_window, overmod_view=False, svpwm_mode="three_phase")
4. build_export_payload(results, display_params)
5. build_baseline_snapshot(results)
6. desktop UI からの service / runner 呼び出しへの切り替え
7. FastAPI の /simulate エンドポイント
8. Pydantic による入力バリデーション
9. 静的 Web UI の配信
10. FastAPI の /health と /scenarios エンドポイント
11. Dockerfile / docker-compose.yml / requirements-web.txt による web 配布

## 入力契約

run_simulation() は SI 単位系の辞書を受け取る。

| 項目 | 単位 | 備考 |
| --- | --- | --- |
| V_dc | V | 直流母線電圧 |
| V_ll | V RMS | 線間電圧指令の RMS 値 |
| f | Hz | 出力基本波周波数 |
| f_c | Hz | キャリア周波数 |
| t_d | s | デッドタイム |
| V_on | V | 固定導通電圧降下 |
| R | Ω | 負荷抵抗 |
| L | H | 負荷インダクタンス |
| pwm_mode | - | natural / regular / third_harmonic / svpwm |
| overmod_view | - | True で線形クランプ無効 |
| svpwm_mode | - | three_phase / two_phase |
| fft_target | - | voltage / current |
| fft_window | - | hann / rectangular |

desktop UI 側の補助単位は [application/simulation_service.py](../application/simulation_service.py) の normalize_ui_display_params() で SI 単位へ変換してから渡す。

## 結果契約

run_simulation() は次の top-level キーを返す。

| キー | 内容 |
| --- | --- |
| meta | モード、表示設定、バージョン、周期数 |
| time | display_s, fft_s |
| reference | 生成直後の三相参照波形 |
| modulation | サンプリング方式適用後の比較用波形 |
| carrier | キャリア波形 |
| switching | 描画用スイッチング信号 |
| leg_states | デッドタイム適用後のレグ状態 |
| voltages | 線間電圧、相電圧、基本波オーバーレイ |
| currents | 三相電流、理論電流 |
| spectra | v_uv, v_uN, i_u の FFT 結果 |
| metrics | m_a, m_f, Z, φ, PF1, 理論/実測基本波など |

既存 UI 互換のため、従来の flat キーも残している。

## Web 応答契約

build_web_response() は run_simulation() の結果を JSON シリアライズ可能な辞書へ変換する。

返却キーは以下とする。

| キー | 内容 |
| --- | --- |
| meta | simulation_api_version, pwm_mode, sampling_mode, overmod_view, svpwm_mode, fft_target, fft_window |
| params | V_dc, V_ll_rms, f, f_c, t_d, V_on, R, L, overmod_view, svpwm_mode |
| time | 表示用時間軸 |
| reference | 生の三相参照波形 |
| modulation | PWM 比較に使った三相波形 |
| carrier | キャリア波形 |
| carrier_plot | キャリア表示用の高密度時間軸と波形 |
| switching | スイッチングパターン |
| voltages | 線間電圧、相電圧、基本波オーバーレイ |
| currents | 三相電流、理論電流 |
| fft | v_uv, v_uN, i_u のスペクトル |
| metrics | m_a, m_f, THD, V_LL_rms_out, V_LL_rms_total, PF1, 理論/実測基本波 |

## Phase 2-4 の API エンドポイント

実装は [webapi/app.py](../webapi/app.py) にある。

### GET /health

稼働確認用の簡易エンドポイント。

```json
{
  "status": "ok",
  "simulation_api_version": "phase5-v1"
}
```

### GET /scenarios

学習シナリオプリセットを返すエンドポイント。desktop UI と web UI で共有する [application/scenario_presets.py](../application/scenario_presets.py) をそのまま返す。

### POST /simulate

入力は [webapi/schemas.py](../webapi/schemas.py) の SimulationRequest で検証する。

| 項目 | 単位 | 範囲 |
| --- | --- | --- |
| V_dc | V | 100–600 |
| V_ll_rms | V | 0–450 |
| f | Hz | 1–200 |
| f_c | Hz | 1000–20000 |
| t_d | s | 0–1.0e-5 |
| V_on | V | 0–5 |
| R | Ω | 0.1–100 |
| L | H | 0.1e-3–100e-3 |
| pwm_mode | - | natural / regular / third_harmonic / svpwm |
| overmod_view | - | true / false |
| svpwm_mode | - | three_phase / two_phase |
| fft_target | - | v_uv / i_u |
| fft_window | - | hann / rectangular |

fft_target は外部 API では v_uv / i_u を受けるが、内部では application runner の都合に合わせて voltage / current へ写像する。

## Phase 3-4 の Web UI

静的 UI は [webui/index.html](../webui/index.html)、[webui/styles.css](../webui/styles.css)、[webui/app.js](../webui/app.js) にある。FastAPI は [webapi/app.py](../webapi/app.py) から次を配信する。

1. GET / で Web UI HTML
2. GET /static/... で CSS / JavaScript
3. GET /scenarios で学習シナリオ
4. POST /simulate でシミュレーション結果 JSON

### Web UI の構成

1. 8 パラメータ入力
2. PWM 方式選択 + 2相/3相変調選択
3. FFT 表示対象と窓関数の切替
4. 学習シナリオガイド
5. 理論比較パネル
6. ベースライン条件比較
7. JSON / PNG エクスポート
8. 主要 3 セクションの表示

主要 3 セクションは次の構成とした。

1. 変調信号 + キャリア
2. 線間電圧 / 相電圧
3. 相電流 / FFT

### Phase 4 の追加機能

1. 学習シナリオは application.scenario_presets の共有定義を使い、desktop UI と web UI で共通化した。
2. ベースライン設定後は、線間電圧基本波と相電流を点線オーバーレイし、V1 / I1 / THD の差分を比較できる。
3. JSON エクスポートは現在の control 値、API 応答、ベースライン情報をまとめて保存する。
4. PNG エクスポートは Plotly の各チャート画像をクライアント側 canvas へ合成して保存する。
5. 理論比較パネルでは I_theory, I_measured, 誤差, cos(phi), PF1, phi を表示する。

フロントエンドは desktop UI と同じ表示単位を採用し、API 呼び出し前に次の変換を行う。

1. V_ll_rms はそのまま API へ渡す
2. f_c [kHz] は Hz へ変換する
3. t_d [us] は s へ変換する
4. L [mH] は H へ変換する

高頻度変更は 300 ms デバウンスで /simulate を呼ぶ。

参照波形・電圧・電流などの表示系列は `max_points` に従って間引くが、キャリア三角波は折返し点の視認性を確保するため `carrier_plot` としてより高密度の配列を別途返す。

## Phase 1 のサービス層責務

Phase 1 では、visualizer に残っていた非描画ロジックを application 層へさらに移した。

| 関数 | 役割 |
| --- | --- |
| normalize_ui_display_params | UI 表示単位を SI 単位へ変換 |
| build_export_payload | JSON 保存用 payload の生成 |
| build_baseline_snapshot | ベースライン比較指標の抽出 |

この結果、[ui/visualizer.py](../ui/visualizer.py) は widget 値の取得、描画、ファイル保存トリガーに集中し、シミュレーション利用ロジックは application 配下へ集約された。

## Phase 0 時点の制約

1. build_web_response() は各配列を等間隔ダウンサンプリングで max_points 以下に制限する。
2. PWM の急峻なエッジに対する min/max ペア圧縮は未実装で、後続 Phase で最適化する。
3. 現時点の API テストは TestClient による単体疎通であり、ASGI サーバ起動やブラウザ接続までは含まない。

## 後続 Phase への接続

1. Phase 4 で学習シナリオガイド、条件比較、エクスポート、理論比較パネルを再実装する。→ 完了。
2. エクスポート専用の元データ API や比較 API は必要に応じて分離する。
3. 高頻度操作の最適化として、後続でデバウンス、キャッシュ、圧縮方式の改善を行う。

## Phase 5 の配布インフラ

Phase 5 では Docker 配布を標準化した。

| 成果物 | 内容 |
| --- | --- |
| `Dockerfile` | python:3.12-slim マルチステージビルド、非 root ユーザ実行 |
| `docker-compose.yml` | `docker compose up --build` 1 コマンド起動、ヘルスチェック付き |
| `.dockerignore` | `ui/`・`tests/`・`__pycache__` 等を除外しイメージ軽量化 |
| `requirements-web.txt` | numpy + pydantic + fastapi + uvicorn（matplotlib/scipy 除外） |

なお、web UI は現在 [webui/index.html](../webui/index.html) で Plotly CDN を参照しているため、完全オフライン環境では別途フロント資産の同梱が必要である。

**起動コマンド:**

```bash
docker compose up --build
# 起動後は http://localhost:8000/ を開く
```

**デスクトップ版の位置付け:** `python main.py` による Matplotlib desktop UI は並行維持される。Docker コンテナには desktop UI は含まれない。

**SIMULATION_API_VERSION:** `"phase5-v1"` 。バージョン文字列は `application/simulation_runner.py` の `SIMULATION_API_VERSION` 定数で管理する。フェーズや API 仕様変更時に更新すること。
