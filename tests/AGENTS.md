# tests/AGENTS.md

This directory owns the regression and contract suite.
The main test file is intentionally broad and covers physics, orchestration, UI/API smoke,
and compatibility checks.

## Test Entry Points

```powershell
python -m pytest tests -v
python -m pytest tests -k "RlLoad" -v
python -m pytest tests -k "WebApi" -v
python -m pytest tests -k "SimulationRunnerContract" -v
```

## Coverage Areas

- reference generation
- carrier generation
- PWM comparison and dead time
- inverter voltage calculation
- RL load solving
- FFT metrics
- scenario preset schema
- application-layer contracts
- web API contracts
- web UI smoke and string-based regressions

## Constants And Conventions

Shared baseline parameters are defined at the top of `test_simulation.py`.
Keep new tests aligned with the existing SI-unit conventions.

## What To Test For

- three-phase symmetry
- waveform value ranges
- switching and leg-state discrete sets
- line-voltage level set
- theory agreement for RL steady state
- API validation and unknown-field rejection
- response payload compatibility
- frontend-visible strings and expected UI hooks when behavior depends on them

## Change Guidance

- extend existing test classes when possible
- add new classes only when a new subsystem or concern becomes large enough
- prefer precise assertions over broad snapshot-style checks
- if you change public payloads or scenario schema, add or update tests in the same pass
