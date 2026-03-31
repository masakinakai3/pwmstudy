# コーディング規約 — 三相PWMインバータ学習ソフトウェア

## 1. 一般規則

### 1.1 Python バージョン
- Python 3.10 以上を対象とする

### 1.2 スタイル
- PEP 8 準拠
- インデント: スペース4つ
- 最大行長: 100文字（数式が長い場合は例外的に120文字まで許容）
- インポート順序: 標準ライブラリ → サードパーティ → プロジェクト内

### 1.3 型ヒント
- 全ての関数シグネチャに型ヒントを付与する
- NumPy 配列は `np.ndarray` を使用

```python
def generate_reference(
    V_ll: float,  # [V]
    f: float,     # [Hz]
    V_dc: float,  # [V]
    t: np.ndarray  # [s]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
```

### 1.4 docstring
- Google スタイルを採用
- 物理的な意味と単位を明記する

```python
def generate_reference(V_ll: float, f: float, V_dc: float, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三相正弦波指令信号を生成する。

    線間電圧指令から変調率を計算し、120°位相差の三相正弦波を返す。

    Args:
        V_ll: 線間電圧振幅 [V]
        f: 出力周波数 [Hz]
        V_dc: 直流母線電圧 [V]
        t: 時間配列 [s]

    Returns:
        (v_u, v_v, v_w): 各相の正規化変調信号、値域 [-1, 1]
    """
```

## 2. 命名規則

### 2.1 物理量

| 物理量 | プレフィックス | 例 | 単位 |
|---|---|---|---|
| 電圧 | `v_` | `v_uv`, `v_carrier`, `v_uN` | V |
| 電流 | `i_` | `i_u`, `i_v`, `i_w` | A |
| スイッチング信号 | `S_` | `S_u`, `S_v`, `S_w` | 無次元 (0/1) |
| 周波数 | `f` / `f_c` | `f`, `f_c` | Hz |
| 時間 | `t` / `dt` | `t`, `dt` | s |
| 抵抗 | `R` | `R` | Ω |
| インダクタンス | `L` | `L` | H |
| 変調率 | `m_a` | `m_a` | 無次元 |
| 直流母線電圧 | `V_dc` | `V_dc` | V |
| 線間電圧RMS値 | `V_ll` | `V_ll` | V |

### 2.2 一般的な名前

| 対象 | 規則 | 例 |
|---|---|---|
| 関数 | スネークケース | `generate_reference`, `solve_rl_load` |
| 変数 | スネークケース | `time_array`, `n_points` |
| 定数 | アッパースネークケース | `V_DC_DEFAULT`, `POINTS_PER_CARRIER`, `N_DISPLAY_CYCLES`, `N_WARMUP_CYCLES_MIN` |
| クラス | パスカルケース | `InverterVisualizer` |
| モジュール | スネークケース | `reference_generator.py` |

## 3. 単位系

### 3.1 コード内部
- **全てSI単位系**を使用する

| 量 | SI単位 | 注意 |
|---|---|---|
| 電圧 | V | |
| 電流 | A | |
| 抵抗 | Ω | |
| インダクタンス | **H** | mH ではなく H (例: 10mH → 0.01) |
| 周波数 | **Hz** | kHz ではなく Hz (例: 5kHz → 5000) |
| 時間 | s | |

### 3.2 UI表示
- スライダーラベル等ではユーザーフレンドリーな補助単位を使用可
- 例: `L = 10 mH`, `f_c = 5 kHz`
- 内部値との変換は UI レイヤーで行う

### 3.3 コメント記法
- 変数宣言時に `# [単位]` 形式で単位を記載する

```python
R: float = 10.0      # [Ω]
L: float = 0.01      # [H]
V_dc: float = 300.0  # [V]
f_c: float = 5000.0  # [Hz]
```

## 4. 数値計算規則

### 4.1 ベクトル演算
- NumPy のベクトル演算を最大限活用する
- Python の for ループによる要素ごとの演算は禁止

```python
# 良い例
v_u = m_a * np.sin(2 * np.pi * f * t)

# 悪い例
v_u = np.zeros_like(t)
for i in range(len(t)):
    v_u[i] = m_a * np.sin(2 * np.pi * f * t[i])
```

### 4.2 浮動小数点比較
- 等値比較には `np.allclose` または `np.isclose` を使用する

```python
# 良い例
assert np.allclose(v_u + v_v + v_w, 0, atol=1e-10)

# 悪い例
assert (v_u + v_v + v_w == 0).all()
```

### 4.3 時間配列の生成
- `np.linspace` を使用する（端点を正確に含めるため）
- `n_points` の計算には `int(round(...))` を使用する（`int()` の切り捨てによるdt不整合を防止）
- ソルバーに渡す `dt` は `t[1] - t[0]` から取得する（`np.linspace` の実際の刻みと一致させる）

```python
# 良い例
n_points = int(round(T_sim / dt)) + 1
t = np.linspace(0, T_sim, n_points)
dt_actual = t[1] - t[0]  # ソルバーにはこちらを渡す

# 悪い例
t = np.arange(0, T_sim, dt)  # 端点の精度が保証されない
```

### 4.4 RK4（唯一の例外: for ループの使用）
- RL負荷ソルバーの時間ステップ積分は for ループを許容する
- ステップ間に依存関係があるため、ベクトル化が困難
- ZOH（零次ホールド）仮定: PWM電圧は各ステップ内で一定、k1〜k4 すべて `v(t_n)` を使用する

## 5. モジュール設計規則

### 5.1 純粋関数
- `simulation/` 内の関数は純粋関数として実装する
- 入力: `float` と `np.ndarray` のみ
- 出力: `float` と `np.ndarray` のみ
- 副作用（グローバル状態変更、ファイルI/O）禁止

### 5.2 パッケージ分離
- `simulation/` パッケージ内で **matplotlib をインポートしない**
- 描画ロジックは全て `ui/` パッケージに集約する

### 5.3 パラメータ管理
- ハードコードされたパラメータ値は禁止
- デフォルト値は `main.py` で一元管理する

## 6. 禁止事項

| 禁止事項 | 理由 |
|---|---|
| `simulation/` での matplotlib インポート | モジュール分離の原則に違反 |
| グローバル変数 | 副作用を排除するため |
| `eval()` / `exec()` | セキュリティリスク |
| `np.arange` での時間配列生成 | 端点精度の問題 |
| ハードコードされた物理パラメータ | 保守性の低下 |
| SI以外の単位での内部計算 | 単位変換バグの原因 |
| `int()` による `n_points` 計算 | `int(round())` を使用（dt不整合防止） |
