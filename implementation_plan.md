# 三相PWMインバータ学習シミュレータ 実装計画書

## 1. 文書の位置づけ

この文書は、現行リポジトリの機能を再実装または保守拡張するための基準計画書である。初期構築の履歴ではなく、2026年4月時点の完成仕様をどう組み上げるかを工程単位で整理する。

## 2. 完成条件

以下をすべて満たした状態を完了とみなす。

- 6つの simulation モジュールが pure function として分離されている
- UI が V_dc, V_LL(rms), f, f_c, t_d, V_on, R, L の 8 パラメータと PWM 方式を操作できる
- UI が FFT 表示対象と FFT 窓関数を切り替えられる
- 6段の波形表示と情報パネルが動作する
- PWM 方式比較として Natural Sampling 固定の SPWM、Third Harmonic Injection、Min-Max Zero-Sequence を切り替えられる
- 定常区間のみを表示するための助走ロジックがある
- FFT により基本波振幅・位相・THD を算出できる
- 理論電流と FFT 実測電流基本波を同一物理量として比較できる
- tests/test_simulation.py の 34 件がすべて通る

## 3. 前提条件

### 3.1 実行環境

- Python 3.10 以上
- Windows を主要開発環境としつつ、macOS / Linux でも動作可能な実装を維持する

### 3.2 依存ライブラリ

| ライブラリ | 役割 | 備考 |
| --- | --- | --- |
| NumPy | 数値計算、配列演算、FFT | 必須 |
| Matplotlib | 描画、スライダー UI | 必須 |
| pytest | テスト実行 | 開発時必須 |
| SciPy | 現行コードでは必須ではない | requirements には存在するが未使用 |

### 3.3 守るべき実装ルール

- simulation 配下では Matplotlib を import しない
- 入出力は float と NumPy 配列に限定する
- 時間配列は np.linspace で生成する
- UI だけが単位変換を行う
- 物理量命名は v_, i_, S_, f, f_c, V_dc, V_ll に従う

## 4. 作業分解構成

| フェーズ | 目的 | 主対象 |
| --- | --- | --- |
| Phase 0 | 開発基盤と共通規約の固定 | requirements, パッケージ構成, main |
| Phase 1 | 三相変調信号とキャリア生成 | reference_generator, carrier_generator |
| Phase 2 | PWM 論理と電圧演算 | pwm_comparator, inverter_voltage |
| Phase 3 | 負荷電流計算とスペクトル解析 | rl_load_solver, fft_analyzer |
| Phase 4 | UI 骨格とパラメータ入力 | visualizer の基本構造 |
| Phase 5 | 教育用オーバーレイと情報表示 | 基本波重畳, 理論比較, FFT パネル |
| Phase 6 | テスト、ドキュメント、運用整備 | tests, README, docs, .github |

## 5. フェーズ詳細

### Phase 0: 開発基盤の固定

#### Phase 0 の対象ファイル

- requirements.txt
- simulation/__init__.py
- ui/__init__.py
- main.py

#### Phase 0 の作業内容

1. 最低限必要な依存ライブラリを揃える
2. simulation と ui を Python パッケージとして定義する
3. main.py にデフォルトパラメータを集約する
4. UI 起動入口を main() に一本化する

#### Phase 0 の受け入れ条件

- pip install -r requirements.txt が成功する
- python main.py で UI が起動する
- main.py が V_LL を RMS 値として保持し、UI 変換方針と矛盾しない

### Phase 1: 三相変調信号とキャリア生成

#### Phase 1 の対象ファイル

- simulation/reference_generator.py
- simulation/carrier_generator.py

#### Phase 1 の作業内容

1. V_LL(peak) と V_dc から m_a を計算する
2. 正弦波参照では m_a を 1.0 で、三次高調波注入では 2 / √3 でクランプする
3. 120 度位相差の三相正弦波指令を生成する
4. 三次高調波注入モードでは零相三次高調波を加える
5. 振幅 ±1 の対称三角波キャリアを生成する

#### Phase 1 の主要式

$$
V_{ph,peak} = \frac{V_{LL,peak}}{\sqrt{3}}
$$

$$
m_a = min\left(\frac{2V_{ph,peak}}{V_{dc}}, 1\right)
$$

#### Phase 1 の受け入れ条件

- 正弦波参照では v_u + v_v + v_w = 0 が成り立つ
- 三次高調波注入では共通モードが加わる一方、線間参照差は正弦波参照と一致する
- 変調信号の値域が [-1, 1] を超えない
- キャリアがほぼ ±1 に到達する

### Phase 2: PWM 論理と電圧演算

#### Phase 2 の対象ファイル

- simulation/pwm_comparator.py
- simulation/inverter_voltage.py

#### Phase 2 の作業内容

1. 必要に応じて規則サンプリングのサンプルホールドを適用する
2. 各相で v_x > v_carrier を比較し S_x を生成する
3. デッドタイムを適用してレグ状態 {-1, 0, +1} を生成する
4. 理想ゲート入力またはレグ状態入力から線間電圧を求める
5. 固定電圧降下 V_on と電流方向依存の自由循環経路を反映する
6. 負荷中性点基準の相電圧を求める

#### Phase 2 の主要式

$$
v_{uv} = (S_u - S_v)V_{dc}
$$

$$
v_{uN} = \frac{V_{dc}}{3}(2S_u - S_v - S_w)
$$

#### Phase 2 の受け入れ条件

- S_u, S_v, S_w が 0 または 1 のみで構成される
- 規則サンプリングでは各キャリア周期の変調信号が保持波形になる
- v_uv + v_vw + v_wu = 0 が成り立つ
- v_uN + v_vN + v_wN = 0 が成り立つ
- 線間電圧が {-V_dc, 0, +V_dc} の 3 レベルになる

### Phase 3: 負荷電流計算とスペクトル解析

#### Phase 3 の対象ファイル

- simulation/rl_load_solver.py
- simulation/fft_analyzer.py

#### Phase 3 の作業内容

1. RL 微分方程式を ZOH 入力に対する厳密離散時間解で更新する
2. `expm1` を使って極小抵抗条件でも安定に係数を計算する
3. 片側 FFT から基本波振幅、位相、THD、RMS 指標を求める
4. Hann / Rectangular 窓と基本波近傍補間を扱えるようにする
5. 後続 UI が使える形で辞書に整理して返す

#### Phase 3 の設計上の判断

- RL ソルバはイベント整列型ではなく固定刻み型を採用する
- 区分定数の PWM 入力に対しては解析解ベースの更新を優先する
- FFT は Hann / Rectangular を切り替えられるようにし、表示と推定精度の両立を図る

#### Phase 3 の受け入れ条件

- 三相電流和が定常区間で概ね 0 になる
- 電流基本波振幅が理論値と 5% 以内で一致する
- 純正弦波入力に対して THD がほぼ 0 になる
- 基本波位相で元波形を再構成できる

### Phase 4: UI 骨格とパラメータ入力

#### Phase 4 の対象ファイル

- ui/visualizer.py

#### Phase 4 の作業内容

1. Figure と 6 段のサブプロットを生成する
2. 8 本の Slider を配置する
3. PWM 方式選択 UI を配置する
4. FFT 表示対象と FFT 窓関数の選択 UI を配置する
5. UI で V_LL(rms), f_c[kHz], t_d[us], L[mH] を内部単位へ変換する
6. 助走周期数と表示周期数から時間配列を生成する
7. 非理想モデル有効時は理想電流を初期推定とし、電圧-電流整合を反復する
8. dt_actual を求め、ソルバへ渡す

#### Phase 4 の受け入れ条件

- スライダー変更時に例外なく再描画される
- PWM 方式切替時に例外なく再描画される
- 表示区間が常に 2 周期分に揃う
- L/R が大きい条件でも初期過渡が表示に残りにくい

### Phase 5: 教育用オーバーレイと情報表示

#### Phase 5 の対象ファイル

- ui/visualizer.py

#### Phase 5 の作業内容

1. v_uv と v_uN の基本波を FFT から再構成し重畳表示する
2. 相電圧基本波から理論電流波形を算出して i_u に重ねる
3. m_a, m_f, Z, φ, cosφ, I1_peak を情報パネルに表示する
4. 過変調クランプ時はパネル色を変える
5. FFT で基本波とキャリア高調波群を色分けする
6. FFT パネルで電圧 / 電流スペクトルを切り替え表示できるようにする
7. Hann / Rectangular 窓の違いを UI 上で比較できるようにする
8. PWM 方式名を情報パネルと FFT タイトルへ反映する

#### Phase 5 の重要な整合条件

- 理論電流と比較する実測値は、波形ピークではなく電流基本波振幅とする
- V_LL の表示は RMS、内部計算は peak に統一する

#### Phase 5 の受け入れ条件

- 線間電圧・相電圧パネルに基本波が重畳される
- 相電流パネルに理論電流が重畳される
- 情報パネルが物理量として矛盾しない
- FFT パネルで f, f_c, 2f_c, 3f_c 近傍が識別できる

### Phase 6: テスト、文書、運用整備

#### Phase 6 の対象ファイル

- tests/test_simulation.py
- README.md
- docs/user_guide.md
- architecture.md
- implementation_plan.md
- improvement_plan.md
- .github 配下の指示書群

#### Phase 6 の作業内容

1. テストケースを実装仕様に追従させる
2. README と利用手順書を UI 現状へ同期する
3. 設計文書と .github 指示書の更新漏れを防ぐ
4. 物理量の定義と表示単位の食い違いを解消する

#### Phase 6 の受け入れ条件

- pytest が 34 件すべて成功する
- README、利用手順書、.github 指示書の件数や UI 段数が実装と一致する
- README、利用手順書、.github 指示書の PWM 方式説明が実装と一致する
- 現行仕様書として一貫して読める内容になる

## 6. 依存関係

```text
Phase 0
  ├─ Phase 1
  ├─ Phase 2 (Phase 1 の出力を利用)
  ├─ Phase 3 (Phase 2 の出力を利用)
  ├─ Phase 4 (Phase 1-3 の統合)
  ├─ Phase 5 (Phase 3, 4 の上に追加)
  └─ Phase 6 (Phase 1-5 の結果を文書とテストへ反映)
```

## 7. 検証計画

### 7.1 自動検証

- python -m pytest tests -v

### 7.2 手動検証

1. python main.py でウィンドウが開く
2. V_LL(rms) を増減させると m_a が追従する
3. 約 184 Vrms を超えるとクランプ表示へ切り替わる
4. f_c を変えると FFT の赤いピーク群が移動する
5. L を増やすと電流リプルが減少し位相遅れが増える

### 7.3 レビュー観点

- 理論比較が同一物理量同士か
- UI の説明単位と内部計算単位が混同されていないか
- テスト件数や文書の UI 段数が実装と一致しているか

## 8. 主なリスクと対策

| リスク | 内容 | 対策 |
| --- | --- | --- |
| 時間刻み不整合 | np.linspace の実刻みとソルバ入力がずれる | dt_actual を使う |
| 学習者の誤解 | RMS と peak の混同 | UI だけ RMS、内部は peak に固定 |
| 理論比較の誤表示 | 生波形ピークと基本波理論値を混同 | FFT 抽出した基本波振幅で比較 |
| 文書の陳腐化 | UI やテスト件数が更新漏れになる | Phase 6 を実装完了条件に含める |
| 高負荷計算 | L/R が大きい条件で助走期間が増える | 動的助走周期数 + 表示は 2 周期固定 |

## 9. 完了後の保守指針

- simulation 配下の関数シグネチャ変更時は tests と docs を同時更新する
- UI に教育的オーバーレイを足す場合、元の物理量計算ロジックを汚染しない
- 新しい改善項目は improvement_plan.md に登録し、完了したら基準文書へ取り込む

## 10. 現在の実装との対応

2026年4月時点で、現行リポジトリは本計画の Phase 0 から Phase 6 を概ね満たしている。以後の変更では、この計画を完成済み仕様の再現・保守基準として扱う。
