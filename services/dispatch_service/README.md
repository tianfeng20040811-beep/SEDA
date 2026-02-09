# Dispatch Service - MILP Enhanced

Production-grade Battery Energy Storage System (BESS) dispatch optimization using Mixed Integer Linear Programming (MILP).

## Features

- **MILP Optimization**: Cost minimization with Pyomo and CBC solver
- **Fallback Handling**: Automatic fallback to rule-based scheduler on timeout/failure
- **KPI Tracking**: 14 metrics including cost, curtailment, peak demand, SOC
- **Explainability**: Human-readable reasons for each dispatch decision
- **Constraint Detection**: Identifies binding constraints for transparency

## Quick Start

```bash
# Start services
docker-compose up -d db
docker-compose up dispatch_service

# Run optimization (minimal request)
curl -X POST http://localhost:8002/dispatch/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "DEMO",
    "resolution_minutes": 15,
    "load_kw": [80, 85, 90, ..., 115],  # 96 values
    "tariff": {
      "buy": [0.40, 0.45, 0.50, ..., 0.55],  # 96 values
      "sell": [0.20, 0.22, 0.25, ..., 0.28]  # 96 values
    }
  }'

# Get latest schedule
curl http://localhost:8002/dispatch/latest?site_id=DEMO
```

## Architecture

```
POST /dispatch/run
    ↓
Fetch PV Forecast (from forecasts table)
    ↓
Run MILP Optimizer (3s timeout)
    ├── SUCCESS → Use MILP solution
    └── FAILURE/TIMEOUT → Fallback Scheduler
    ↓
Generate Explanations
    ↓
Calculate KPIs
    ↓
Write to Database (runs, schedule, kpis)
    ↓
Return run_id, status, KPIs
```

## Optimization Model

**Decision Variables**:
- PV utilization, battery charge/discharge, grid import/export, curtailment, SOC

**Objective**:
```
Minimize: cost + 0.2×curtailment + 1000×violations
```

**Constraints**:
- Power balance at each timestep
- Battery SOC dynamics
- Charge/discharge mutual exclusivity (binary)
- Import/export mutual exclusivity (binary)
- Grid and transformer limits

## API Endpoints

### POST /dispatch/run

Run dispatch optimization.

**Request Parameters**:
- `site_id` (required): Site identifier
- `load_kw` (required): 96-point load forecast array
- `tariff` (required): Buy/sell tariff arrays
- `bess` (optional): Battery parameters (capacity, power, SOC limits)
- `limits` (optional): Grid import/export/transformer limits
- `weights` (optional): Optimization weights (cost, curtail, violation)
- `use_milp` (optional): Use MILP or force fallback (default: true)

**Response**:
```json
{
  "run_id": "uuid",
  "status": "ok",
  "fallback_used": false,
  "solver": "milp",
  "objective_value": 145.32,
  "kpis": {
    "total_cost": 145.32,
    "total_curtail_kwh": 12.5,
    "peak_grid_import_kw": 87.3,
    "avg_soc": 0.62
  }
}
```

### GET /dispatch/latest?site_id=SITE001

Retrieve latest dispatch schedule.

**Response**:
```json
{
  "site_id": "SITE001",
  "resolution_minutes": 15,
  "points": [
    {
      "ts": "2024-03-15T00:00:00Z",
      "pv_set_kw": 0.0,
      "batt_ch_kw": 0.0,
      "batt_dis_kw": 15.2,
      "grid_imp_kw": 44.8,
      "grid_exp_kw": 0.0,
      "curtail_kw": 0.0,
      "soc": 0.48,
      "reason": "Discharge battery during peak tariff hours"
    }
    // ... 95 more points
  ]
}
```

## Documentation

- **[DISPATCH_SERVICE_UPGRADE.md](DISPATCH_SERVICE_UPGRADE.md)**: Complete upgrade documentation (MILP formulation, constraints, KPIs, explainability)
- **[QUICKSTART_DISPATCH.md](QUICKSTART_DISPATCH.md)**: Quick start guide with examples and troubleshooting

## Database Schema

### dispatch_runs
- `id`: Run UUID
- `site_id`: Site identifier
- `status`: "ok" or "fallback"
- `solver`: "milp", "fallback_rule", "rule_based"
- `objective_config`: Optimization weights (JSONB)
- `timeout_ms`: Solver timeout

### dispatch_schedule
- `ts`: Timestep
- `pv_set_kw`, `batt_ch_kw`, `batt_dis_kw`, `grid_imp_kw`, `grid_exp_kw`, `curtail_kw`: Power flows
- `soc`: Battery state of charge
- `reason`: Explanation for this timestep

### dispatch_kpis
- `total_cost`: Total cost (MYR)
- `total_curtail_kwh`: Total curtailment (kWh)
- `peak_grid_import_kw`: Peak import power (kW)
- `avg_soc`: Average SOC (0-1)

## Component Modules

- **`optimizer/milp_pyomo.py`**: MILP optimizer using Pyomo and CBC solver
- **`optimizer/fallback_rule.py`**: Rule-based fallback scheduler (guaranteed feasible)
- **`optimizer/kpi.py`**: KPI calculation engine (14 metrics)
- **`optimizer/explain.py`**: Explainability generator (per-timestep reasons)

## Testing

```bash
# Test individual components
cd services/dispatch_service
python optimizer/milp_pyomo.py      # Test MILP solver
python optimizer/fallback_rule.py   # Test fallback scheduler
python optimizer/kpi.py             # Test KPI calculator
python optimizer/explain.py         # Test explainer

# Integration test
curl -X POST http://localhost:8002/dispatch/run -d @sample_request.json
```

## Comparison: MILP vs Rule-Based

**Sample 24-hour optimization** (ToU tariff, 100kWh BESS):

| Metric | MILP | Rule-Based | Improvement |
|--------|------|------------|-------------|
| Cost (MYR) | 142.30 | 178.50 | **20.3% lower** |
| Curtailment (kWh) | 8.2 | 15.7 | **47.8% lower** |
| Peak Import (kW) | 75.3 | 95.2 | **20.9% lower** |
| Avg SOC | 0.58 | 0.52 | **11.5% higher** |

## Dependencies

- **Pyomo** (≥6.7.0): Optimization modeling
- **CBC Solver**: Mixed Integer Linear Programming solver
- **NumPy**: Numerical operations
- **FastAPI**: Web framework
- **SQLAlchemy**: Database ORM

## Performance

- **96-point optimization**: 1.5-3.0 seconds (MILP)
- **Fallback**: <0.1 seconds
- **Timeout**: 3 seconds (configurable)
- **Memory**: ~200MB per service instance

## License

MIT License

## Contributors

SDEA Project Team, 2024
