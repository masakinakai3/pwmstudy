# SPDX-License-Identifier: MIT
"""FastAPI ベースの Web API MVP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from application import SCENARIO_PRESETS, SIMULATION_API_VERSION, build_web_response, run_simulation
from application.simulation_runner import run_sweep
from webapi.schemas import SimulationRequest, SweepRequest


WEBUI_DIR = Path(__file__).resolve().parent.parent / "webui"

app = FastAPI(
    title="Three-Phase Two-Level PWM Inverter Learning Simulator API",
    version=SIMULATION_API_VERSION,
    description="Three-phase two-level PWM inverter learning simulator web API.",
)

app.mount("/static", StaticFiles(directory=WEBUI_DIR), name="static")


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
    return SCENARIO_PRESETS


@app.post("/simulate")
def simulate(request: SimulationRequest) -> dict[str, object]:
    """シミュレーション結果を JSON で返す."""
    try:
        results = run_simulation(request.to_simulation_params())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"シミュレーション実行エラー: {type(exc).__name__}: {exc}") from exc
    response = build_web_response(results)
    # build_web_response は内部表現 ("voltage"/"current") で fft.target を書くが、
    # API 公開表現は "v_uv"/"i_u" であるため上書きする。
    # TODO: この変換は build_web_response または to_simulation_params 内で完結させることが望ましい。
    response["meta"]["fft_target"] = request.fft_target
    response["fft"]["target"] = request.fft_target

    return response


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
        raise HTTPException(
            status_code=500,
            detail=f"スイープ実行エラー: {type(exc).__name__}: {exc}",
        ) from exc
    return result