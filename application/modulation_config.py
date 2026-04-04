"""変調方式の軸定義と正規化ヘルパー."""

from __future__ import annotations


REFERENCE_MODE_LABELS = {
    "sinusoidal": "Sinusoidal Reference",
    "third_harmonic": "Third Harmonic Injection",
    "minmax": "Min-Max Zero-Sequence (SVPWM Eq.)",
}
SAMPLING_MODE_LABELS = {
    "natural": "Natural Sampling",
    "regular": "Regular Sampling",
}
CLAMP_MODE_LABELS = {
    "continuous": "Continuous PWM",
    "dpwm1": "DPWM1",
    "dpwm2": "DPWM2",
    "dpwm3": "DPWM3",
}


def normalize_reference_mode(reference_mode: str | None) -> str:
    """参照生成方式を正規化する."""
    if reference_mode in {None, ""}:
        return "sinusoidal"
    if reference_mode == "svpwm":
        return "minmax"
    if reference_mode not in REFERENCE_MODE_LABELS:
        raise ValueError(f"Unsupported reference mode: {reference_mode}")
    return reference_mode


def normalize_sampling_mode(sampling_mode: str | None) -> str:
    """サンプリング方式を正規化する."""
    if sampling_mode in {None, ""}:
        return "natural"
    if sampling_mode not in SAMPLING_MODE_LABELS:
        raise ValueError(f"Unsupported sampling mode: {sampling_mode}")
    return sampling_mode


def normalize_clamp_mode(clamp_mode: str | None) -> str:
    """クランプ方式を正規化する."""
    if clamp_mode in {None, "", "three_phase"}:
        return "continuous"
    if clamp_mode == "two_phase":
        return "dpwm1"
    if clamp_mode not in CLAMP_MODE_LABELS:
        raise ValueError(f"Unsupported clamp mode: {clamp_mode}")
    return clamp_mode


def resolve_modulation_axes(
    reference_mode: str | None = None,
    sampling_mode: str | None = None,
    clamp_mode: str | None = None,
    pwm_mode: str | None = None,
    svpwm_mode: str | None = None,
) -> tuple[str, str, str]:
    """新旧入力を受けて変調軸を解決する."""
    if reference_mode is None and sampling_mode is None and pwm_mode is not None:
        legacy_pwm_mode = pwm_mode
        if legacy_pwm_mode == "natural_overmod":
            legacy_pwm_mode = "natural"
        if legacy_pwm_mode == "natural":
            reference_mode = "sinusoidal"
            sampling_mode = "natural"
        elif legacy_pwm_mode == "regular":
            reference_mode = "sinusoidal"
            sampling_mode = "regular"
        elif legacy_pwm_mode == "third_harmonic":
            reference_mode = "third_harmonic"
            sampling_mode = "natural"
        elif legacy_pwm_mode == "svpwm":
            reference_mode = "minmax"
            sampling_mode = "natural"
        else:
            raise ValueError(f"Unsupported pwm mode: {pwm_mode}")

    reference_mode = normalize_reference_mode(reference_mode)
    sampling_mode = normalize_sampling_mode(sampling_mode)
    clamp_mode = normalize_clamp_mode(clamp_mode if clamp_mode is not None else svpwm_mode)
    return reference_mode, sampling_mode, clamp_mode


def derive_legacy_pwm_mode(
    reference_mode: str,
    sampling_mode: str,
    clamp_mode: str,
) -> str:
    """互換表示用の旧 pwm_mode を導出する."""
    if clamp_mode != "continuous":
        return "custom"
    if reference_mode == "sinusoidal" and sampling_mode == "natural":
        return "natural"
    if reference_mode == "sinusoidal" and sampling_mode == "regular":
        return "regular"
    if reference_mode == "third_harmonic" and sampling_mode == "natural":
        return "third_harmonic"
    if reference_mode == "minmax" and sampling_mode == "natural":
        return "svpwm"
    return "custom"


def build_modulation_summary_label(
    reference_mode: str,
    sampling_mode: str,
    clamp_mode: str,
) -> str:
    """3軸の組み合わせを要約した表示ラベルを返す."""
    return (
        f"{REFERENCE_MODE_LABELS[reference_mode]} / "
        f"{SAMPLING_MODE_LABELS[sampling_mode]} / "
        f"{CLAMP_MODE_LABELS[clamp_mode]}"
    )