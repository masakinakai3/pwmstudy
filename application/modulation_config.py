# SPDX-License-Identifier: MIT
"""変調方式の軸定義と正規化ヘルパー."""

from __future__ import annotations


REFERENCE_MODE_LABELS = {
    "sinusoidal": "Sinusoidal Reference",
    "third_harmonic": "Third Harmonic Injection",
    "minmax": "Min-Max Zero-Sequence (SVPWM Eq.)",
}
MODULATION_MODE_LABELS = {
    "carrier": "三角波比較",
    "carrier_third_harmonic": "三角波比較(三倍高調波)",
    "carrier_two_phase": "三角波比較(二相変調)",
    "space_vector": "空間ベクトル",
    "space_vector_two_phase": "空間ベクトル(二相変調)",
}
SAMPLING_MODE_LABELS = {
    "natural": "Natural Sampling",
}
CLAMP_MODE_LABELS = {
    "continuous": "Continuous PWM",
    "dpwm1": "DPWM1",
    "dpwm2": "DPWM2",
    "dpwm3": "DPWM3",
}

_MODULATION_MODE_AXES = {
    "carrier": ("sinusoidal", "natural", "continuous"),
    "carrier_third_harmonic": ("third_harmonic", "natural", "continuous"),
    "carrier_two_phase": ("sinusoidal", "natural", "dpwm1"),
    "space_vector": ("minmax", "natural", "continuous"),
    "space_vector_two_phase": ("minmax", "natural", "dpwm1"),
}
_AXES_TO_MODULATION_MODE = {
    axes: mode for mode, axes in _MODULATION_MODE_AXES.items()
}


def normalize_modulation_mode(modulation_mode: str | None) -> str:
    """単一の変調方式キーを正規化する."""
    if modulation_mode in {None, ""}:
        return "carrier"
    if modulation_mode not in MODULATION_MODE_LABELS:
        raise ValueError(f"Unsupported modulation mode: {modulation_mode}")
    return modulation_mode


def derive_modulation_mode(
    reference_mode: str,
    sampling_mode: str,
    clamp_mode: str,
) -> str | None:
    """内部3軸から単一の変調方式キーを逆引きする."""
    return _AXES_TO_MODULATION_MODE.get((reference_mode, sampling_mode, clamp_mode))


def resolve_modulation_axes(
    modulation_mode: str | None = None,
) -> tuple[str, str, str]:
    """modulation_mode から内部3軸を解決する."""
    normalized_modulation_mode = normalize_modulation_mode(modulation_mode)
    return _MODULATION_MODE_AXES[normalized_modulation_mode]


def build_modulation_summary_label(
    reference_mode: str,
    sampling_mode: str,
    clamp_mode: str,
) -> str:
    """3軸の組み合わせを要約した表示ラベルを返す."""
    modulation_mode = derive_modulation_mode(reference_mode, sampling_mode, clamp_mode)
    if modulation_mode is not None:
        return MODULATION_MODE_LABELS[modulation_mode]

    return (
        f"{REFERENCE_MODE_LABELS.get(reference_mode, reference_mode)} / "
        f"{SAMPLING_MODE_LABELS.get(sampling_mode, sampling_mode)} / "
        f"{CLAMP_MODE_LABELS.get(clamp_mode, clamp_mode)}"
    )