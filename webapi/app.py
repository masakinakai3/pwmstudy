# SPDX-License-Identifier: MIT
"""FastAPI ベースの Web API MVP."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from application import SCENARIO_PRESETS, SIMULATION_API_VERSION, build_web_response, run_simulation
from application.simulation_runner import run_sweep
from webapi.schemas import SimulationRequest, SweepRequest


WEBUI_DIR = Path(__file__).resolve().parent.parent / "webui"
LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Three-Phase Two-Level PWM Inverter Learning Simulator API",
    version=SIMULATION_API_VERSION,
    description="Three-phase two-level PWM inverter learning simulator web API.",
)

app.mount("/static", StaticFiles(directory=WEBUI_DIR), name="static")


def _to_public_fft_target(fft_target: object) -> str:
    if fft_target == "current":
        return "i_u"
    return "v_uv"


def _serialize_scenario_preset(preset: dict[str, object]) -> dict[str, object]:
    serialized = dict(preset)
    serialized["fft_target"] = _to_public_fft_target(preset.get("fft_target"))
    return serialized


@app.get("/")
def index() -> FileResponse:
    """Web UI のトップページを返す."""
    return FileResponse(WEBUI_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    """簡易ヘルスチェックを返す."""
    return {
        "status": "ok",
        "simulation_api_version": SIMULATION_API_VERSION,
    }


@app.get("/scenarios")
def scenarios() -> list[dict[str, object]]:
    """学習シナリオプリセットを返す."""
    return [_serialize_scenario_preset(preset) for preset in SCENARIO_PRESETS]


@app.post("/simulate")
def simulate(request: SimulationRequest) -> dict[str, object]:
    """シミュレーション結果を JSON で返す."""
    try:
        results = run_simulation(request.to_simulation_params())
    except Exception as exc:
        LOGGER.exception("Simulation failed")
        raise HTTPException(status_code=500, detail="シミュレーション実行エラー") from exc
    return build_web_response(results)


@app.post("/sweep")
def sweep(request: SweepRequest) -> dict[str, object]:
    """m_a スイープ結果を JSON で返す."""
    from application.modulation_config import normalize_modulation_mode

    try:
        result = run_sweep(
            V_dc=request.V_dc,
            f=request.f,
            f_c=request.f_c,
            R=request.R,
            L=request.L,
            modulation_mode=normalize_modulation_mode(request.modulation_mode),
            fft_window=request.fft_window,
            t_d=request.t_d,
            V_on=request.V_on,
            n_points=request.n_points,
            m_a_min=request.m_a_min,
            m_a_max=request.m_a_max,
        )
    except Exception as exc:
        LOGGER.exception("Sweep failed")
        raise HTTPException(
            status_code=500,
            detail="スイープ実行エラー",
        ) from exc
    return result
