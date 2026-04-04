"""FastAPI ベースの Web API MVP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from application import SCENARIO_PRESETS, SIMULATION_API_VERSION, build_web_response, run_simulation
from webapi.schemas import SimulationRequest


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
    results = run_simulation(request.to_simulation_params())
    response = build_web_response(results)
    response["meta"]["fft_target"] = request.fft_target
    response["fft"]["target"] = request.fft_target

    return response