# 三相PWMインバータ学習シミュレータ アーキテクチャ設計書

## 1. 目的

本ソフトウェアは、三相2レベル電圧形インバータの PWM 動作を学習するための可視化シミュレータである。利用者は 8 つのパラメータを操作しながら、以下を同時に理解できることを目標とする。

- 三相正弦波指令と三角波キャリアの比較から PWM パルスが生成される過程
- スイッチング状態と線間電圧・相電圧の対応
- RL 負荷による電流平滑化と位相遅れ
- 基本波、キャリア高調波群、THD の関係
- 変調率 m_a と周波数変調率 m_f が波形品質に与える影響
- Natural Sampling、Regular Sampling、Third Harmonic Injection の差異

## 2. 設計方針

- シミュレーションコアは pure function で分離し、UI から独立させる
- 内部計算は SI 単位系で統一し、単位変換は UI 表示層に閉じ込める
- 配列処理は NumPy ベクトル演算を基本とし、時間積分だけ for ループを許容する
- 教育用表示と数値計算を分離し、検証しやすい構成にする
- 理論比較は可能な限り同一物理量同士で行い、見かけの一致で誤魔化さない

## 3. システム全体像

```text
┌────────────────────────────────────────────────────────────┐
│                         main.py                            │
│  デフォルトパラメータ定義 / InverterVisualizer 起動        │
└─────────────────────────────┬──────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                    ui/visualizer.py                        │
│  パラメータ読取 / 時間軸生成 / シミュレーション呼出 / 描画  │
│  6段波形表示 / 情報パネル / スライダーイベント             │
└───────────────┬────────────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────┐
│                    simulation/                            │
│  generate_reference()   generate_carrier()               │
│  compare_pwm()          calc_inverter_voltage()          │
│  solve_rl_load()        analyze_spectrum()               │
└───────────────┬────────────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────┐
│                      tests/                                │
│  34件の物理妥当性テスト                                    │
└────────────────────────────────────────────────────────────┘
```

## 4. データフロー

### 4.1 ユーザ入力から表示まで

1. UI スライダーから V_dc, V_LL(rms), f, f_c, t_d, V_on, R, L と PWM 方式を読み取る
2. UI 層で V_LL(rms) を V_LL(peak) に変換する
3. 時間配列 t を生成する
4. PWM 方式に応じて三相変調信号 v_u, v_v, v_w を生成する
5. 規則サンプリング選択時は、比較用変調信号へサンプルホールドを適用する
6. 三角波キャリア v_carrier を生成する
7. PWM 比較で理想ゲート信号 S_u, S_v, S_w を求める
8. デッドタイムを適用して各相のレグ状態 {-1, 0, +1} を生成する
9. 理想相電圧から電流を初期推定し、非理想電圧-電流整合を反復する
10. 非理想相電圧を RL 負荷へ入力して相電流を求める
11. 定常区間の v_uv, v_uN, i_u に対して FFT を行う
12. 基本波オーバーレイ、理論電流、m_a, m_f, Z, φ を派生計算する
13. 6段のサブプロットと情報パネルに反映する

### 4.2 実行シーケンス

```text
main.py
  -> InverterVisualizer._read_params()
  -> InverterVisualizer._run_simulation()
  -> generate_reference(V_ll_peak, f, V_dc, t, mode=...)
  -> apply_sampling_mode(v_u, v_v, v_w, t, f_c, sampling_mode=...)
       -> generate_carrier(f_c, t)
       -> compare_pwm(v_u, v_v, v_w, v_carrier)
      -> apply_deadtime(S_u, S_v, S_w, t_d, dt_actual)
      -> calc_inverter_voltage(..., V_on, inputs_are_leg_states=True)
       -> solve_rl_load(v_uN, v_vN, v_wN, R, L, dt_actual)
       -> analyze_spectrum(v_uv)
       -> analyze_spectrum(v_uN)
       -> analyze_spectrum(i_u)
  -> InverterVisualizer._draw_waveforms()
```

## 5. モジュール責務

| ファイル | 主要シンボル | 責務 | 主入力 | 主出力 |
| --- | --- | --- | --- | --- |
| simulation/reference_generator.py | generate_reference | 正弦波参照または三次高調波注入参照の生成、m_a クランプ | V_ll(peak), f, V_dc, t, mode | v_u, v_v, v_w |
| simulation/carrier_generator.py | generate_carrier | 対称三角波キャリア生成 | f_c, t | v_carrier |
| simulation/pwm_comparator.py | apply_sampling_mode, compare_pwm, apply_deadtime | 規則サンプリング前処理、理想ゲート信号生成、デッドタイム適用 | v_u, v_v, v_w, t, f_c, v_carrier, t_d, dt | v_u_cmp, v_v_cmp, v_w_cmp, S_u, S_v, S_w, leg_u, leg_v, leg_w |
| simulation/inverter_voltage.py | calc_inverter_voltage | 理想/非理想の線間電圧と負荷中性点基準相電圧の算出 | S_u, S_v, S_w, V_dc, i_u, i_v, i_w, V_on | v_uv, v_vw, v_wu, v_uN, v_vN, v_wN |
| simulation/rl_load_solver.py | solve_rl_load | RL 負荷の三相電流計算 | v_uN, v_vN, v_wN, R, L, dt | i_u, i_v, i_w |
| simulation/fft_analyzer.py | analyze_spectrum | FFT、基本波振幅、位相、THD、RMS 指標の計算 | signal, dt, f_fundamental, window_mode | freq, magnitude, thd, fundamental_mag, fundamental_phase, fundamental_rms, rms_total |
| ui/visualizer.py | InverterVisualizer | パラメータ管理、シミュレーション統合、波形描画 | default_params | Matplotlib UI |
| main.py | main | デフォルト条件定義と UI 起動 | なし | アプリ起動 |

## 6. 数値設計

### 6.1 時間離散化

- キャリア 1 周期あたりのサンプル数: 100 点
- 表示区間: 出力波形 2 周期
- 助走区間: max(5, ceil(5τ / T_cycle)) 周期
- 基準時間刻み:

$$
dt_{base} = \frac{1}{f_c \cdot N_{ppc}}
$$

- サンプル数:

$$
N = round\left(\frac{T_{sim}}{dt_{base}}\right) + 1
$$

- 実際にソルバへ渡す時間刻み:

$$
dt_{actual} = t[1] - t[0]
$$

この構成により、np.linspace 由来の刻み誤差とソルバ入力の不整合を防いでいる。

### 6.2 RL 負荷の時間積分

採用モデルは三相 Y 結線 RL 負荷、負荷中性点は外部に接続しない浮遊中性点である。各相は以下で記述する。

$$
v_{xN}(t) = R i_x(t) + L \frac{d i_x(t)}{dt}
$$

時間積分には、各サンプル区間で PWM 電圧を零次ホールド入力とみなした厳密離散時間解を使う。各相の更新式は

$$
i_{x,n+1} = \alpha i_{x,n} + \beta v_{xN,n}
$$

であり、

$$
\alpha = e^{-R dt / L}, \qquad
\beta = \frac{dt}{L} \cdot \frac{1 - e^{-x}}{x}, \qquad
x = \frac{R dt}{L}
$$

とする。実装では `expm1` を用いて $x \to 0$ での打ち消し誤差を避け、$R = 0$ では $\beta = dt / L$ を使う。

### 6.3 FFT 解析

- 片側 FFT を使用
- 振幅はピーク値基準に正規化
- 基本波は f_fundamental に最も近いビンを採用
- THD は基本波以外の全成分から算出

現行実装は窓関数や補間を使っていないため、周波数分解能は表示区間長に依存する。

## 7. UI アーキテクチャ

### 7.1 表示構成

1. 変調信号 + キャリア
2. スイッチングパターン
3. 線間電圧 + 基本波オーバーレイ
4. 相電圧 + 基本波オーバーレイ
5. 相電流 + 理論電流オーバーレイ
6. 線間電圧 FFT スペクトル

加えて、図の左上に以下を表示する情報パネルを持つ。

- m_a
- PWM 方式
- m_f = f_c / f
- t_d
- V_on
- インピーダンス Z
- 位相角 φ
- 力率 cos φ
- 電流基本波振幅の理論値と FFT 実測値

### 7.2 単位変換の責務分離

- UI 入力: V_LL は RMS、f_c は kHz、t_d は us、L は mH、FFT Signal と FFT Window は離散選択
- シミュレーション入力: V_LL は peak、f_c は Hz、t_d は s、L は H
- 表示軸: 時間は ms、FFT は kHz

この変換を ui/visualizer.py に閉じ込めることで、simulation 配下の pure function は SI 単位前提で単純化している。

## 8. 物理モデルの前提と制約

### 8.1 採用している前提

- 三相 2 レベル電圧形インバータ
- 直流母線電圧は一定
- PWM 方式は Natural Sampling、Regular Sampling、Third Harmonic Injection から選択する
- スイッチ素子は簡易非理想モデルで表現する
- デッドタイムをレグ状態 0（上下アームとも OFF）で表現する
- 導通経路には固定電圧降下 V_on を与える
- 負荷は各相同一の線形 RL 直列回路
- 磁気飽和、寄生要素、相間不平衡は考慮しない

### 8.2 現時点で扱わない項目

- 空間ベクトル PWM
- デッドタイム補償
- 導通電圧降下の電流・温度依存モデル
- DC リンクリプル
- モータ等価回路や逆起電力

## 9. 品質保証アーキテクチャ

tests/test_simulation.py に 34 件のテストを集約し、以下を検証する。

- 三相変調信号の総和が 0
- 変調信号とキャリアの値域が正しい
- スイッチング信号が 0/1 のみ
- 線間電圧と相電圧の和が 0
- 線間電圧が 3 レベルである
- デッドタイムが正しく挿入される
- 規則サンプリングで変調信号がキャリア周期ごとに保持される
- 三次高調波注入で共通モードが加わり、線間基本波の線形範囲が拡張される
- 固定電圧降下で線間電圧振幅が低下する
- デッドタイム中の導通経路が電流方向で切り替わる
- RL 電流基本波振幅が理論値と 5% 以内で一致
- 三相電流和が概ね 0
- FFT の基本波振幅、位相、再構成が妥当
- Hann 窓と基本波近傍補間で、非整数周期でも安定した振幅推定ができる
- 既知高調波合成波の THD と RMS 指標が理論値と一致する
- RL 負荷により電流 THD が電圧 THD より低くなる

## 10. ディレクトリ構成

```text
3lvlpwm/
├── main.py
├── simulation/
│   ├── __init__.py
│   ├── reference_generator.py
│   ├── carrier_generator.py
│   ├── pwm_comparator.py
│   ├── inverter_voltage.py
│   ├── rl_load_solver.py
│   └── fft_analyzer.py
├── ui/
│   ├── __init__.py
│   └── visualizer.py
├── tests/
│   └── test_simulation.py
├── docs/
│   └── user_guide.md
├── README.md
├── architecture.md
├── implementation_plan.md
└── improvement_plan.md
```

## 11. 将来拡張の入り口

今後の拡張は、以下の方針を維持する。

- 新しい物理モデルは simulation 配下の pure function として追加する
- UI は既存の _run_simulation と _draw_waveforms の責務境界を崩さない
- 教育用注釈や比較表示は、元の波形計算ロジックを汚染しない形で派生量として追加する
- 精度向上は、まず物理量定義の整合、その後に数値積分・FFT 手法を改善する

詳細な今後の拡張候補は improvement_plan.md にまとめる。
