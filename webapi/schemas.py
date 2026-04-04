"""Web API の入出力スキーマ."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from application.modulation_config import resolve_modulation_axes


PwmMode = Literal["natural", "regular", "third_harmonic", "svpwm", "natural_overmod"]
ReferenceMode = Literal["sinusoidal", "third_harmonic", "minmax", "svpwm"]
SamplingMode = Literal["natural", "regular"]
ClampMode = Literal["continuous", "dpwm1", "dpwm2", "dpwm3", "three_phase", "two_phase"]
ApiFftTarget = Literal["v_uv", "i_u"]
FftWindow = Literal["hann", "rectangular"]


class SimulationRequest(BaseModel):
    """simulate エンドポイントの入力スキーマ."""

    V_dc: float = Field(ge=100.0, le=600.0)
    V_ll_rms: float = Field(ge=0.0, le=450.0)
    f: float = Field(ge=1.0, le=200.0)
    f_c: float = Field(ge=1000.0, le=20000.0)
    t_d: float = Field(ge=0.0, le=1.0e-5)
    V_on: float = Field(ge=0.0, le=5.0)
    R: float = Field(ge=0.1, le=100.0)
    L: float = Field(ge=0.1e-3, le=100e-3)
    reference_mode: ReferenceMode | None = None
    sampling_mode: SamplingMode | None = None
    clamp_mode: ClampMode | None = None
    pwm_mode: PwmMode | None = None
    overmod_view: bool = False
    svpwm_mode: ClampMode | None = None
    fft_target: ApiFftTarget = "v_uv"
    fft_window: FftWindow = "hann"

    def to_simulation_params(self) -> dict[str, object]:
        """application runner が期待する内部パラメータへ変換する."""
        fft_target = "voltage" if self.fft_target == "v_uv" else "current"
        reference_mode, sampling_mode, clamp_mode = resolve_modulation_axes(
            reference_mode=self.reference_mode,
            sampling_mode=self.sampling_mode,
            clamp_mode=self.clamp_mode,
            pwm_mode=self.pwm_mode,
            svpwm_mode=self.svpwm_mode,
        )

        return {
            "V_dc": self.V_dc,
            "V_ll": self.V_ll_rms,  # [V RMS] — 変換不要（generate_reference が内部でピーク換算）
            "f": self.f,
            "f_c": self.f_c,
            "t_d": self.t_d,
            "V_on": self.V_on,
            "R": self.R,
            "L": self.L,
            "reference_mode": reference_mode,
            "sampling_mode": sampling_mode,
            "clamp_mode": clamp_mode,
            "overmod_view": self.overmod_view,
            "fft_target": fft_target,
            "fft_window": self.fft_window,
        }