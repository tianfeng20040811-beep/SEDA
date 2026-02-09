import os, uuid, json, sys, time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from audit_logger import AuditLogger

# Import optimizer modules
from optimizer.milp_pyomo import MILPOptimizer
from optimizer.fallback_rule import FallbackScheduler
from optimizer.kpi import KPICalculator
from optimizer.explain import DispatchExplainer

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Initialize components
milp_optimizer = MILPOptimizer(solver_name='cbc', timeout_seconds=3.0)
fallback_scheduler = FallbackScheduler()
kpi_calculator = KPICalculator()
explainer = DispatchExplainer()
audit_logger = AuditLogger(DATABASE_URL)

app = FastAPI(title="Dispatch Service - MILP Enhanced")


# ============================================================================
# Request Models
# ============================================================================

class BessParams(BaseModel):
    capacity_kwh: float = 100.0
    p_charge_max_kw: float = 50.0
    p_discharge_max_kw: float = 50.0
    soc0: float = 0.5
    soc_min: float = 0.2
    soc_max: float = 0.9
    eta_charge: float = 0.95
    eta_discharge: float = 0.95

class GridLimits(BaseModel):
    grid_import_max_kw: float = 200.0
    grid_export_max_kw: float = 200.0
    transformer_max_kw: float = 250.0

class Weights(BaseModel):
    cost: float = 1.0
    curtail: float = 0.2
    violation: float = 1000.0

class Tariff(BaseModel):
    buy: List[float]  # Array of N tariff values
    sell: List[float]  # Array of N tariff values

class RunReq(BaseModel):
    site_id: str
    start: Optional[str] = None  # ISO 8601, defaults to tomorrow
    end: Optional[str] = None
    resolution_minutes: int = 15
    forecast_quantile: float = 0.5  # Which forecast quantile to use
    load_kw: List[float]  # Load forecast array
    tariff: Tariff
    bess: Optional[BessParams] = None
    limits: Optional[GridLimits] = None
    weights: Optional[Weights] = None
    use_milp: bool = True  # Use MILP optimizer or fallback to rules


# ============================================================================
# Main Dispatch Endpoint
# ============================================================================

@app.post("/dispatch/run")
def run_dispatch(req: RunReq):
    """
    Run dispatch optimization using MILP or fallback rules
    """
    start_time = time.time()
    run_id = str(uuid.uuid4())
    
    # Parse timestamps
    if req.start:
        start = datetime.fromisoformat(req.start.replace('Z', '+00:00'))
    else:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    if req.end:
        end = datetime.fromisoformat(req.end.replace('Z', '+00:00'))
    else:
        end = start + timedelta(hours=24)
    
    # Set defaults
    bess_params = req.bess.dict() if req.bess else BessParams().dict()
    limits = req.limits.dict() if req.limits else GridLimits().dict()
    weights = req.weights.dict() if req.weights else Weights().dict()
    
    # Fetch PV forecast
    with engine.connect() as conn:
        # Get latest forecast for the requested period
        pv_rows = conn.execute(text("""
            SELECT ts, p10, p50, p90
            FROM forecasts f
            JOIN forecast_runs r ON r.id = f.run_id
            WHERE f.site_id = :sid
              AND f.ts >= :start
              AND f.ts < :end
            ORDER BY r.created_at DESC, f.ts ASC
            LIMIT :limit
        """), {
            "sid": req.site_id,
            "start": start,
            "end": end,
            "limit": int((end - start).total_seconds() / (req.resolution_minutes * 60))
        }).fetchall()
    
    # Extract PV forecast based on quantile
    pv_forecast_kw = []
    if pv_rows:
        for row in pv_rows:
            if req.forecast_quantile <= 0.15:
                pv_forecast_kw.append(float(row[1]))  # p10
            elif req.forecast_quantile >= 0.85:
                pv_forecast_kw.append(float(row[3]))  # p90
            else:
                pv_forecast_kw.append(float(row[2]))  # p50 (default)
    else:
        # Fallback: generate mock PV forecast
        import math
        N = int((end - start).total_seconds() / (req.resolution_minutes * 60))
        for i in range(N):
            hour = start.hour + i * req.resolution_minutes / 60.0
            if 6 <= hour <= 18:
                pv_forecast_kw.append(200 * math.sin((hour - 6) / 12 * math.pi))
            else:
                pv_forecast_kw.append(0.0)
    
    # Validate array lengths
    N = len(req.load_kw)
    if not (len(pv_forecast_kw) == len(req.tariff.buy) == len(req.tariff.sell) == N):
        # Pad or truncate to match
        pv_forecast_kw = (pv_forecast_kw + [0.0] * N)[:N]
    
    # Run optimization
    fallback_used = False
    solver_used = "milp"
    error_message = None
    
    if req.use_milp:
        try:
            success, solution, error = milp_optimizer.optimize(
                pv_forecast_kw=pv_forecast_kw,
                load_kw=req.load_kw,
                tariff_buy=req.tariff.buy,
                tariff_sell=req.tariff.sell,
                bess_params=bess_params,
                limits=limits,
                weights=weights,
                resolution_minutes=req.resolution_minutes
            )
            
            if not success:
                print(f"MILP optimization failed: {error}, falling back to rules")
                fallback_used = True
                solver_used = "fallback_rule"
                error_message = error
        
        except Exception as e:
            print(f"MILP exception: {e}, falling back to rules")
            success = False
            fallback_used = True
            solver_used = "fallback_rule"
            error_message = str(e)
    else:
        success = False
        fallback_used = True
        solver_used = "rule_based"
    
    # Fallback if MILP failed
    if not success or fallback_used:
        solution = fallback_scheduler.schedule(
            pv_forecast_kw=pv_forecast_kw,
            load_kw=req.load_kw,
            tariff_buy=req.tariff.buy,
            tariff_sell=req.tariff.sell,
            bess_params=bess_params,
            limits=limits,
            resolution_minutes=req.resolution_minutes
        )
    
    # Get binding constraints (if MILP was used)
    binding_constraints = None
    if success and not fallback_used:
        binding_constraints = milp_optimizer.get_binding_constraints(
            solution, bess_params, limits
        )
    
    # Generate explanations
    reasons = explainer.explain_schedule(
        solution=solution,
        pv_forecast_kw=pv_forecast_kw,
        load_kw=req.load_kw,
        tariff_buy=req.tariff.buy,
        bess_params=bess_params,
        limits=limits,
        binding_constraints=binding_constraints
    )
    
    # Calculate KPIs
    kpis = kpi_calculator.calculate_kpis(
        solution=solution,
        tariff_buy=req.tariff.buy,
        tariff_sell=req.tariff.sell,
        resolution_minutes=req.resolution_minutes
    )
    
    # Save to database
    with engine.begin() as conn:
        # Insert dispatch run metadata
        conn.execute(text("""
            INSERT INTO dispatch_runs (id, site_id, status, solver, objective_config, timeout_ms)
            VALUES (:id, :sid, :status, :solver, :cfg::jsonb, :timeout)
        """), {
            "id": run_id,
            "sid": req.site_id,
            "status": "ok" if success else "fallback",
            "solver": solver_used,
            "cfg": json.dumps(weights),
            "timeout": int(milp_optimizer.timeout_seconds * 1000)
        })
        
        # Insert dispatch schedule
        t = start
        out_rows = []
        for i in range(N):
            out_rows.append({
                "ts": t,
                "sid": req.site_id,
                "rid": run_id,
                "pv_set_kw": solution['pv_set_kw'][i],
                "batt_ch_kw": solution['batt_ch_kw'][i],
                "batt_dis_kw": solution['batt_dis_kw'][i],
                "grid_imp_kw": solution['grid_imp_kw'][i],
                "grid_exp_kw": solution['grid_exp_kw'][i],
                "curtail_kw": solution['curtail_kw'][i],
                "soc": solution['soc'][i],
                "reason": reasons[i]
            })
            t += timedelta(minutes=req.resolution_minutes)
        
        conn.execute(text("""
            INSERT INTO dispatch_schedule (ts, site_id, run_id, pv_set_kw, batt_ch_kw, batt_dis_kw, 
                                          grid_imp_kw, grid_exp_kw, curtail_kw, soc, reason)
            VALUES (:ts, :sid, :rid, :pv_set_kw, :batt_ch_kw, :batt_dis_kw, 
                    :grid_imp_kw, :grid_exp_kw, :curtail_kw, :soc, :reason)
        """), out_rows)
        
        # Insert KPIs
        conn.execute(text("""
            INSERT INTO dispatch_kpis (run_id, site_id, total_cost, total_curtail_kwh, 
                                       peak_grid_import_kw, avg_soc)
            VALUES (:rid, :sid, :cost, :curtail, :peak, :soc)
        """), {
            "rid": run_id,
            "sid": req.site_id,
            "cost": kpis['total_cost'],
            "curtail": kpis['total_curtail_kwh'],
            "peak": kpis['peak_grid_import_kw'],
            "soc": kpis['avg_soc']
        })
    
    # Calculate runtime
    solver_time_ms = int((time.time() - start_time) * 1000)
    
    # Audit log
    audit_logger.log_dispatch_run(
        site_id=req.site_id,
        request_params={
            "forecast_quantile": req.forecast_quantile,
            "tariff": req.tariff.dict(),
            "bess": bess_params,
            "limits": limits,
            "weights": weights,
            "resolution_minutes": req.resolution_minutes
        },
        run_id=run_id,
        status="ok" if success else "fallback",
        solver=solver_used,
        solver_time_ms=solver_time_ms,
        fallback_used=fallback_used,
        objective_value=solution['objective_value'],
        kpis={
            "total_cost": kpis['total_cost'],
            "total_curtail_kwh": kpis['total_curtail_kwh'],
            "peak_grid_import_kw": kpis['peak_grid_import_kw'],
            "avg_soc": kpis['avg_soc']
        },
        error=error_message
    )
    
    return {
        "run_id": run_id,
        "status": "ok" if success else "fallback",
        "fallback_used": fallback_used,
        "solver": solver_used,
        "objective_value": solution['objective_value'],
        "kpis": {
            "total_cost": kpis['total_cost'],
            "total_curtail_kwh": kpis['total_curtail_kwh'],
            "peak_grid_import_kw": kpis['peak_grid_import_kw'],
            "avg_soc": kpis['avg_soc']
        },
        "error": error_message
    }


@app.get("/dispatch/latest")
def latest(site_id: str):
    """Get latest dispatch schedule"""
    q = text("""
      SELECT s.ts, s.pv_set_kw, s.batt_ch_kw, s.batt_dis_kw, s.grid_imp_kw, s.grid_exp_kw, s.curtail_kw, s.soc, s.reason
      FROM dispatch_schedule s
      JOIN dispatch_runs r ON r.id=s.run_id
      WHERE s.site_id=:sid
      ORDER BY r.created_at DESC, s.ts ASC
      LIMIT 96
    """)
    with engine.connect() as conn:
        rows = conn.execute(q, {"sid": site_id}).all()

    points = [{
        "ts": r[0], "pv_set_kw": float(r[1]), "batt_ch_kw": float(r[2]), "batt_dis_kw": float(r[3]),
        "grid_imp_kw": float(r[4]), "grid_exp_kw": float(r[5]), "curtail_kw": float(r[6]), "soc": float(r[7]),
        "reason": r[8] if r[8] else "No reason provided"
    } for r in rows]
    return {"site_id": site_id, "resolution_minutes": 15, "unit": "kW", "soc_unit": "ratio", "points": points}


# ============================================================================
# CSV Report Export
# ============================================================================

@app.get("/reports/dispatch.csv")
def export_dispatch_csv(run_id: str):
    """
    Export dispatch schedule as CSV
    
    Columns: ts,pv_set_kw,batt_ch_kw,batt_dis_kw,grid_imp_kw,grid_exp_kw,curtail_kw,soc,reason
    """
    from fastapi.responses import Response
    
    q = text("""
      SELECT ts, pv_set_kw, batt_ch_kw, batt_dis_kw, grid_imp_kw, grid_exp_kw, curtail_kw, soc, reason
      FROM dispatch_schedule
      WHERE run_id=:rid
      ORDER BY ts ASC
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(q, {"rid": run_id}).all()
    
    if len(rows) == 0:
        raise HTTPException(status_code=404, detail="Run ID not found")
    
    # Build CSV content
    csv_lines = []
    csv_lines.append("ts,pv_set_kw,batt_ch_kw,batt_dis_kw,grid_imp_kw,grid_exp_kw,curtail_kw,soc,reason")
    
    for row in rows:
        ts = row[0].isoformat()
        pv_set = row[1]
        batt_ch = row[2]
        batt_dis = row[3]
        grid_imp = row[4]
        grid_exp = row[5]
        curtail = row[6]
        soc = row[7]
        reason = (row[8] or "").replace('"', '""')  # Escape double quotes
        
        csv_lines.append(f'{ts},{pv_set},{batt_ch},{batt_dis},{grid_imp},{grid_exp},{curtail},{soc},"{reason}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=dispatch_{run_id}.csv"
        }
    )


@app.get("/reports/forecast.csv")
def export_forecast_csv(run_id: str):
    """
    Export forecast as CSV
    
    Columns: ts,p10,p50,p90
    """
    from fastapi.responses import Response
    from sqlalchemy import create_engine, text
    
    # Need to access forecast_service database
    # For simplicity, assume same database
    q = text("""
      SELECT ts, p10, p50, p90
      FROM forecasts
      WHERE run_id=:rid
      ORDER BY ts ASC
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(q, {"rid": run_id}).all()
    
    if len(rows) == 0:
        raise HTTPException(status_code=404, detail="Run ID not found")
    
    # Build CSV content
    csv_lines = []
    csv_lines.append("ts,p10,p50,p90")
    
    for row in rows:
        ts = row[0].isoformat()
        p10 = row[1]
        p50 = row[2]
        p90 = row[3]
        
        csv_lines.append(f"{ts},{p10},{p50},{p90}")
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=forecast_{run_id}.csv"
        }
    )

