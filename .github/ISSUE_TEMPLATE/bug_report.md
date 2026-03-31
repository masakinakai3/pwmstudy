---
name: バグ報告
about: シミュレーション結果の不正や動作不具合の報告
title: "[BUG] "
labels: bug
assignees: ''
---

## バグの概要

<!-- 何が起きているか簡潔に記述 -->

## 再現手順

1. `python main.py` を実行
2. スライダーで以下のパラメータを設定:
   - V_dc: 
   - V_LL(rms): 
   - f: 
   - f_c: 
   - R: 
   - L: 
3. 発生した現象を記述

## 期待される動作

<!-- 物理的に正しい挙動を含めて記述 -->

## 実際の動作

<!-- スクリーンショットやエラーメッセージを添付 -->

## 環境

- OS: 
- Python バージョン: 
- NumPy バージョン: 
- Matplotlib バージョン: 

## 関連モジュール

- [ ] `simulation/reference_generator.py`
- [ ] `simulation/carrier_generator.py`
- [ ] `simulation/pwm_comparator.py`
- [ ] `simulation/inverter_voltage.py`
- [ ] `simulation/rl_load_solver.py`
- [ ] `simulation/fft_analyzer.py`
- [ ] `ui/visualizer.py`
- [ ] `main.py`

## 補足情報

<!-- 理論値との比較、参考文献など -->
