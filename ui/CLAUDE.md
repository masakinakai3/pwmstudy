# ui/ — Matplotlib desktop UI 規約

desktop 向け 6 段波形表示 UI。application 層へ委譲し、UI 内で物理演算を再実装しない。

## 対象クラス: `InverterVisualizer`

### 主な責務

- 8 パラメータスライダーと modulation_mode の操作
- Overmod View, FFT target/window の切替
- 学習シナリオボタンの適用
- ベースライン比較と JSON/PNG エクスポート
- application 層の結果を 6 段 Matplotlib 表示へ反映

### application 層への委譲

- 単位変換: `normalize_ui_display_params()`
- シミュレーション: `run_simulation()`
- エクスポート: `build_export_payload()`
- ベースライン: `build_baseline_snapshot()`
- **desktop UI 側で simulation ロジックを再実装しない**

## データフロー

```
_update(val)
  → _read_display_params()
  → normalize_ui_display_params()
  → application.run_simulation() → simulation.*
  → _draw_waveforms(results)
```

## サブプロット構成（6段）

1. 指令信号 + キャリア信号（重ね描き）
2. スイッチングパターン S_u, S_v, S_w（オフセット表示: +4, +2, +0）
3. 線間出力電圧 v_uv, v_vw, v_wu + 基本波
4. 相電圧 v_uN + 基本波
5. 相電流 i_u, i_v, i_w + 理論値
6. FFT スペクトル + THD/RMS 表示

上 5 段は `sharex=True`、FFT は x 軸独立。

## 表示単位

内部は SI — UI 表示のみ補助単位:
- `f_c`: kHz 表示 → `val * 1000.0` で Hz に変換
- `L`: mH 表示 → `val / 1000.0` で H に変換
- `t_d`: us 表示 → `val * 1e-6` で s に変換
- 時間軸: ms 表示（`t * 1000.0`）

## スライダーパラメータ

| パラメータ | デフォルト | 範囲 | 表示単位 |
|---|---|---|---|
| V_dc | 300 V | 100–600 | V |
| V_LL | 141 V | 0–450 | V (RMS) |
| f | 50 Hz | 1–200 | Hz |
| f_c | 5 kHz | 1–20 | kHz |
| t_d | 0 us | 0–10 | us |
| V_on | 0 V | 0–5 | V |
| R | 10 Ω | 0.1–100 | Ω |
| L | 10 mH | 0.1–100 | mH |
