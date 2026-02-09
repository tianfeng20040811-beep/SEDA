import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import httpx

DATABASE_URL = os.getenv("DATABASE_URL")
FORECAST_SERVICE_URL = os.getenv("FORECAST_SERVICE_URL", "http://forecast:8001")
DISPATCH_SERVICE_URL = os.getenv("DISPATCH_SERVICE_URL", "http://dispatch:8002")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(title="SEDAI Solar2Grid API Gateway")

# Add CORS middleware to allow Flutter web app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SeriesPoint(BaseModel):
    ts: datetime
    value: float

class TelemetryResponse(BaseModel):
    site_id: str
    metric: str
    unit: str
    series: list[SeriesPoint]

class ForecastPoint(BaseModel):
    ts: datetime
    p10: float
    p50: float
    p90: float

class ForecastLatestResponse(BaseModel):
    site_id: str
    horizon: str
    resolution_minutes: int
    unit: str
    points: list[ForecastPoint]

class DispatchPoint(BaseModel):
    ts: datetime
    pv_set_kw: float
    batt_ch_kw: float
    batt_dis_kw: float
    grid_imp_kw: float
    grid_exp_kw: float
    curtail_kw: float
    soc: float
    reason: str

class DispatchLatestResponse(BaseModel):
    site_id: str
    resolution_minutes: int
    unit: str
    soc_unit: str
    points: list[DispatchPoint]

class ValidateRunReq(BaseModel):
    site_id: str
    horizon: str = "day_ahead"
    metric: str = "pv_power_kw"
    start: datetime
    end: datetime
    resolution_minutes: int = 15

class ValidateLatestResponse(BaseModel):
    validation_id: str
    site_id: str
    horizon: str
    metric: str
    mae: float
    nrmse: float
    bias: float
    start_ts: datetime
    end_ts: datetime
    created_at: datetime
    
    def get_status(self) -> str:
        """返回健康状态：GREEN < 15%, AMBER < 25%, RED >= 25%"""
        if self.nrmse < 0.15:
            return "GREEN"
        elif self.nrmse < 0.25:
            return "AMBER"
        else:
            return "RED"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/sites")
def list_sites():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, timezone, lat, lon, capacity_kw FROM sites ORDER BY created_at DESC")).mappings().all()
    return {"sites": [dict(r) for r in rows]}

@app.get("/telemetry/query", response_model=TelemetryResponse)
def telemetry_query(
    site_id: str,
    metric: str,
    start: datetime,
    end: datetime,
    step_minutes: int = Query(15, ge=1, le=60),
):
    # If table empty, return mock sinusoid-like curve
    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM telemetry WHERE site_id=:sid AND metric=:m AND ts>=:s AND ts<=:e"),
                           {"sid": site_id, "m": metric, "s": start, "e": end}).scalar_one()
    points = []
    if cnt == 0:
        t = start
        while t <= end:
            # simple mock
            val = 200.0 if 8 <= t.hour <= 17 else 10.0
            points.append({"ts": t, "value": float(val)})
            t += timedelta(minutes=step_minutes)
    else:
        q = text("""
        SELECT time_bucket((CAST(:step AS TEXT) || ' minutes')::interval, ts) AS b, AVG(value) AS v
        FROM telemetry
        WHERE site_id=:sid AND metric=:m AND ts>=:s AND ts<=:e
        GROUP BY b ORDER BY b
        """)
        with engine.connect() as conn:
            rows = conn.execute(q, {"step": step_minutes, "sid": site_id, "m": metric, "s": start, "e": end}).all()
        points = [{"ts": r[0], "value": float(r[1])} for r in rows]

    return {"site_id": site_id, "metric": metric, "unit": "kW", "series": points}

class ForecastRunRequest(BaseModel):
    site_id: str
    horizon: str = "day_ahead"
    start: datetime
    end: datetime
    resolution_minutes: int = 15
    quantiles: list[float] = [0.1, 0.5, 0.9]
    weather_source: str = "telemetry_or_mock"

@app.post("/forecast/run")
async def forecast_run(req: ForecastRunRequest):
    """触发预测运行，生成光伏功率预测。符合统一接口契约：POST用JSON body。"""
    # Generate run_id
    run_id = str(uuid.uuid4())
    
    # Call downstream forecast service (simplified for now, only pass essential params)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{FORECAST_SERVICE_URL}/forecast/run", json={
            "site_id": req.site_id,
            "horizon": req.horizon,
            "resolution_minutes": req.resolution_minutes
            # Note: start, end, quantiles, weather_source will be used in future iterations
        })
        r.raise_for_status()
        result = r.json()
        
        # Write audit log with full request details
        with engine.begin() as conn:
            payload_data = {
                "site_id": req.site_id,
                "horizon": req.horizon,
                "start": req.start.isoformat(),
                "end": req.end.isoformat(),
                "resolution_minutes": req.resolution_minutes,
                "quantiles": req.quantiles,
                "weather_source": req.weather_source,
                "result": result
            }
            conn.execute(text("""
              INSERT INTO audit_log (id, actor, action, payload)
              VALUES (:id, :actor, :action, CAST(:payload AS jsonb))
            """), {
                "id": str(uuid.uuid4()),
                "actor": "system",
                "action": "forecast_run",
                "payload": json.dumps(payload_data)
            })
        
        return {"run_id": run_id, "status": "ok"}

@app.get("/forecast/latest", response_model=ForecastLatestResponse)
async def forecast_latest(site_id: str, horizon: str = "day_ahead"):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{FORECAST_SERVICE_URL}/forecast/latest", params={"site_id": site_id, "horizon": horizon})
        r.raise_for_status()
        return r.json()

class BessParams(BaseModel):
    capacity_kwh: float
    p_charge_max_kw: float
    p_discharge_max_kw: float
    soc0: float
    soc_min: float
    soc_max: float
    eta_charge: float
    eta_discharge: float

class GridLimits(BaseModel):
    grid_import_max_kw: float
    grid_export_max_kw: float
    transformer_max_kw: float

class Tariff(BaseModel):
    buy: list[float]
    sell: list[float]

class OptimizationWeights(BaseModel):
    cost: float = 1.0
    curtail: float = 0.2
    carbon: float = 0.0
    violation: float = 1000.0

class DispatchRunRequest(BaseModel):
    site_id: str
    start: datetime
    end: datetime
    resolution_minutes: int = 15
    forecast_quantile: float = 0.5
    load_kw: list[float]
    tariff: Tariff
    bess: BessParams
    limits: GridLimits
    weights: OptimizationWeights = OptimizationWeights()

@app.post("/dispatch/run")
async def dispatch_run(req: DispatchRunRequest):
    """触发调度优化，生成能源管理调度计划。符合统一接口契约：POST用JSON body。"""
    # Generate run_id
    run_id = str(uuid.uuid4())
    
    # Call downstream dispatch service (simplified for now, only pass essential params)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{DISPATCH_SERVICE_URL}/dispatch/run", json={
            "site_id": req.site_id,
            "resolution_minutes": req.resolution_minutes
            # Note: Full params (load_kw, tariff, bess, limits, weights) will be used in future iterations
        })
        r.raise_for_status()
        result = r.json()
        
        # Write audit log with full request details
        with engine.begin() as conn:
            payload_data = {
                "site_id": req.site_id,
                "start": req.start.isoformat(),
                "end": req.end.isoformat(),
                "resolution_minutes": req.resolution_minutes,
                "forecast_quantile": req.forecast_quantile,
                "load_kw": req.load_kw,
                "tariff": {"buy": req.tariff.buy, "sell": req.tariff.sell},
                "bess": req.bess.model_dump(),
                "limits": req.limits.model_dump(),
                "weights": req.weights.model_dump(),
                "result": result
            }
            conn.execute(text("""
              INSERT INTO audit_log (id, actor, action, payload)
              VALUES (:id, :actor, :action, CAST(:payload AS jsonb))
            """), {
                "id": str(uuid.uuid4()),
                "actor": "system",
                "action": "dispatch_run",
                "payload": json.dumps(payload_data)
            })
        
        return {"run_id": run_id, "status": "ok", "fallback_used": False}

@app.get("/dispatch/latest", response_model=DispatchLatestResponse)
async def dispatch_latest(site_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{DISPATCH_SERVICE_URL}/dispatch/latest", params={"site_id": site_id})
        r.raise_for_status()
        return r.json()

@app.post("/validate/run")
def validate_run(req: ValidateRunReq):
    import math

    # 1) query forecast p50 - use only the LATEST forecast run
    fq = text("""
      WITH latest_run AS (
        SELECT id
        FROM forecast_runs
        WHERE site_id=:sid AND horizon=:h
        ORDER BY created_at DESC
        LIMIT 1
      )
      SELECT f.ts, f.p50
      FROM forecasts f
      WHERE f.run_id = (SELECT id FROM latest_run)
        AND f.ts>=:s AND f.ts<=:e
      ORDER BY f.ts ASC
    """)

    # 2) query telemetry actual
    tq = text("""
      SELECT time_bucket((CAST(:step AS TEXT) || ' minutes')::interval, ts) AS b, AVG(value) AS v
      FROM telemetry
      WHERE site_id=:sid AND metric=:m AND ts>=:s AND ts<=:e
      GROUP BY b ORDER BY b
    """)

    with engine.connect() as conn:
        f_rows = conn.execute(fq, {"sid": req.site_id, "h": req.horizon, "s": req.start, "e": req.end}).all()
        t_rows = conn.execute(tq, {"step": req.resolution_minutes, "sid": req.site_id, "m": req.metric, "s": req.start, "e": req.end}).all()

    f_map = {r[0]: float(r[1]) for r in f_rows}
    t_map = {r[0]: float(r[1]) for r in t_rows}

    # 3) align by timestamp intersection
    common_ts = sorted(set(f_map.keys()) & set(t_map.keys()))
    if len(common_ts) < 10:
        return {"status": "not_enough_data", "common_points": len(common_ts)}

    errors = []
    actuals = []
    preds = []
    for ts in common_ts:
        p = f_map[ts]
        a = t_map[ts]
        preds.append(p)
        actuals.append(a)
        errors.append(p - a)

    # 4) compute KPIs
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e*e for e in errors) / len(errors))
    mean_actual = sum(actuals) / len(actuals)
    nrmse = rmse / mean_actual if mean_actual != 0 else 0.0
    bias = sum(errors) / len(errors)

    # 5) insert validation run
    vid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO validation_runs
          (id, site_id, horizon, start_ts, end_ts, resolution_minutes, metric, mae, nrmse, bias)
          VALUES
          (:id, :sid, :h, :s, :e, :res, :m, :mae, :nrmse, :bias)
        """), {"id": vid, "sid": req.site_id, "h": req.horizon, "s": req.start, "e": req.end,
               "res": req.resolution_minutes, "m": req.metric, "mae": mae, "nrmse": nrmse, "bias": bias})

    return {"status": "ok", "validation_id": vid, "mae": mae, "nrmse": nrmse, "bias": bias, "points": len(common_ts)}

@app.get("/validate/latest", response_model=ValidateLatestResponse)
def validate_latest(site_id: str, horizon: str = "day_ahead", metric: str = "pv_power_kw"):
    """
    Get the latest validation results for a site.
    Returns MAE, nRMSE, bias and other metrics.
    """
    with engine.connect() as conn:
        result = conn.execute(text("""
          SELECT id, site_id, horizon, metric, mae, nrmse, bias, start_ts, end_ts, created_at
          FROM validation_runs
          WHERE site_id=:sid AND horizon=:h AND metric=:m
          ORDER BY created_at DESC
          LIMIT 1
        """), {"sid": site_id, "h": horizon, "m": metric}).fetchone()
        
        if not result:
            # Return a default response if no validation data exists
            return ValidateLatestResponse(
                validation_id="00000000-0000-0000-0000-000000000000",
                site_id=site_id,
                horizon=horizon,
                metric=metric,
                mae=0.0,
                nrmse=0.0,
                bias=0.0,
                start_ts=datetime.now(timezone.utc),
                end_ts=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc)
            )
        
        return ValidateLatestResponse(
            validation_id=str(result[0]),
            site_id=str(result[1]),
            horizon=result[2],
            metric=result[3],
            mae=float(result[4]),
            nrmse=float(result[5]),
            bias=float(result[6]),
            start_ts=result[7],
            end_ts=result[8],
            created_at=result[9]
        )

class CalibrationRequest(BaseModel):
    site_id: str

@app.post("/calibration/apply_latest")
def apply_calibration(req: CalibrationRequest):
    """
    Apply calibration based on latest validation bias.
    符合统一接口契约：POST用JSON body。
    Updates model parameters (PR, soiling) to reduce bias.
    """
    site_id = req.site_id
    # 1) Get latest validation bias
    with engine.connect() as conn:
        latest_val = conn.execute(text("""
          SELECT bias FROM validation_runs
          WHERE site_id=:sid
          ORDER BY created_at DESC
          LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if not latest_val:
            return {"status": "error", "message": "No validation runs found for this site"}
        
        bias = float(latest_val[0])
        
        # 2) Get latest calibration params (default: PR=0.85, soiling=0.98)
        latest_cal = conn.execute(text("""
          SELECT params FROM model_calibration
          WHERE site_id=:sid
          ORDER BY valid_from DESC
          LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if latest_cal and latest_cal[0]:
            params = latest_cal[0]  # JSONB already parsed as dict
            pr_old = params.get("pr", 0.85)
            soiling_old = params.get("soiling", 0.98)
        else:
            pr_old = 0.85
            soiling_old = 0.98
    
    # 3) Update PR based on bias (k=0.001, smaller for stability)
    k = 0.001
    pr_new = pr_old - k * bias
    # Clamp to realistic range
    pr_new = max(0.70, min(0.95, pr_new))
    
    # Keep soiling unchanged for now (or could also adjust)
    soiling_new = soiling_old
    
    # 4) Save new calibration
    cal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    new_params = {"pr": pr_new, "soiling": soiling_new}
    
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO model_calibration
          (id, site_id, model_type, params, valid_from)
          VALUES (:id, :sid, :mt, CAST(:params AS jsonb), :vf)
        """), {"id": cal_id, "sid": site_id, "mt": "pv_baseline", 
               "params": json.dumps(new_params), "vf": now})
    
    return {
        "status": "ok",
        "calibration_id": cal_id,
        "bias": bias,
        "pr_old": pr_old,
        "pr_new": pr_new,
        "soiling": soiling_new
    }

# ============================================================================
# 3.1 Sites & Config Endpoints
# ============================================================================

class SiteDetail(BaseModel):
    id: str
    name: str
    timezone: str
    lat: float | None
    lon: float | None
    capacity_kw: float | None
    tilt_deg: float | None
    azimuth_deg: float | None
    created_at: datetime

class TariffProfile(BaseModel):
    id: str
    site_id: str
    name: str
    currency: str
    resolution_minutes: int
    buy: list[float]
    sell: list[float]
    valid_from: datetime

class TariffUpsertRequest(BaseModel):
    site_id: str
    name: str
    currency: str = "MYR"
    resolution_minutes: int = 15
    buy: list[float]
    sell: list[float]

class BessProfile(BaseModel):
    id: str
    site_id: str
    name: str
    params: dict
    valid_from: datetime

class BessUpsertRequest(BaseModel):
    site_id: str
    name: str
    params: dict

@app.get("/sites/{site_id}", response_model=SiteDetail)
def get_site(site_id: str):
    """获取单个站点详细信息"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, name, timezone, lat, lon, capacity_kw, tilt_deg, azimuth_deg, created_at
            FROM sites WHERE id=:sid
        """), {"sid": site_id}).fetchone()
        
        if not result:
            return {"error": "Site not found"}, 404
        
        return SiteDetail(
            id=str(result[0]),
            name=result[1],
            timezone=result[2],
            lat=result[3],
            lon=result[4],
            capacity_kw=result[5],
            tilt_deg=result[6],
            azimuth_deg=result[7],
            created_at=result[8]
        )

@app.get("/config/tariff/latest", response_model=TariffProfile)
def get_latest_tariff(site_id: str):
    """获取站点最新电价配置"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, site_id, name, currency, resolution_minutes, buy, sell, valid_from
            FROM tariff_profiles
            WHERE site_id=:sid
            ORDER BY valid_from DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if not result:
            # Return default tariff if none exists
            return TariffProfile(
                id="00000000-0000-0000-0000-000000000000",
                site_id=site_id,
                name="Default",
                currency="MYR",
                resolution_minutes=15,
                buy=[0.10] * 96,
                sell=[0.05] * 96,
                valid_from=datetime.now(timezone.utc)
            )
        
        return TariffProfile(
            id=str(result[0]),
            site_id=str(result[1]),
            name=result[2],
            currency=result[3],
            resolution_minutes=result[4],
            buy=result[5],
            sell=result[6],
            valid_from=result[7]
        )

@app.post("/config/tariff/upsert")
def upsert_tariff(req: TariffUpsertRequest):
    """创建或更新电价配置"""
    tariff_id = str(uuid.uuid4())
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tariff_profiles (id, site_id, name, currency, resolution_minutes, buy, sell, valid_from)
            VALUES (:id, :sid, :name, :cur, :res, CAST(:buy AS jsonb), CAST(:sell AS jsonb), NOW())
        """), {
            "id": tariff_id,
            "sid": req.site_id,
            "name": req.name,
            "cur": req.currency,
            "res": req.resolution_minutes,
            "buy": json.dumps(req.buy),
            "sell": json.dumps(req.sell)
        })
    
    return {"status": "ok", "tariff_id": tariff_id}

@app.get("/config/bess/latest", response_model=BessProfile)
def get_latest_bess(site_id: str):
    """获取站点最新BESS配置"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, site_id, name, params, valid_from
            FROM bess_profiles
            WHERE site_id=:sid
            ORDER BY valid_from DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if not result:
            # Return default BESS config
            default_params = {
                "capacity_kwh": 100.0,
                "p_charge_max_kw": 50.0,
                "p_discharge_max_kw": 50.0,
                "soc0": 0.5,
                "soc_min": 0.2,
                "soc_max": 0.9,
                "eta_charge": 0.95,
                "eta_discharge": 0.95
            }
            return BessProfile(
                id="00000000-0000-0000-0000-000000000000",
                site_id=site_id,
                name="Default",
                params=default_params,
                valid_from=datetime.now(timezone.utc)
            )
        
        return BessProfile(
            id=str(result[0]),
            site_id=str(result[1]),
            name=result[2],
            params=result[3],
            valid_from=result[4]
        )

@app.post("/config/bess/upsert")
def upsert_bess(req: BessUpsertRequest):
    """创建或更新BESS配置"""
    bess_id = str(uuid.uuid4())
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO bess_profiles (id, site_id, name, params, valid_from)
            VALUES (:id, :sid, :name, CAST(:params AS jsonb), NOW())
        """), {
            "id": bess_id,
            "sid": req.site_id,
            "name": req.name,
            "params": json.dumps(req.params)
        })
    
    return {"status": "ok", "bess_id": bess_id}

# ============================================================================
# 3.2 Forecast Runs History
# ============================================================================

class ForecastRun(BaseModel):
    id: str
    site_id: str
    horizon: str
    resolution_minutes: int
    model_version: str
    created_at: datetime

@app.get("/forecast/runs")
def get_forecast_runs(site_id: str, limit: int = 10):
    """获取预测运行历史"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, site_id, horizon, resolution_minutes, model_version, created_at
            FROM forecast_runs
            WHERE site_id=:sid
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"sid": site_id, "lim": limit}).all()
    
    return {
        "runs": [
            {
                "id": str(r[0]),
                "site_id": str(r[1]),
                "horizon": r[2],
                "resolution_minutes": r[3],
                "model_version": r[4],
                "created_at": r[5].isoformat()
            }
            for r in rows
        ]
    }

# ============================================================================
# 3.3 Load Forecast Endpoints
# ============================================================================

class LoadRunRequest(BaseModel):
    site_id: str
    start: datetime
    end: datetime
    resolution_minutes: int = 15

class LoadPoint(BaseModel):
    ts: datetime
    p50: float

class LoadLatestResponse(BaseModel):
    site_id: str
    resolution_minutes: int
    unit: str
    points: list[LoadPoint]

@app.post("/load/run")
def load_run(req: LoadRunRequest):
    """运行负荷预测（MVP: 生成典型负荷曲线）"""
    import math
    
    run_id = str(uuid.uuid4())
    
    # Generate typical load curve (sinusoidal with daily pattern)
    points = []
    current_ts = req.start
    
    while current_ts <= req.end:
        hour = current_ts.hour
        # Peak at 18:00 (120 kW), Low at 3:00 (50 kW)
        base_load = 85.0
        amplitude = 35.0
        phase = (hour - 3) * math.pi / 12  # Peak at 18:00
        load = base_load + amplitude * math.sin(phase)
        
        points.append({
            "ts": current_ts,
            "site_id": req.site_id,
            "run_id": run_id,
            "p50": load,
            "unit": "kW"
        })
        
        current_ts += timedelta(minutes=req.resolution_minutes)
    
    # Insert into database
    with engine.begin() as conn:
        for p in points:
            conn.execute(text("""
                INSERT INTO load_forecasts (ts, site_id, run_id, p50, unit)
                VALUES (:ts, :sid, :rid, :p50, :unit)
            """), {
                "ts": p["ts"],
                "sid": p["site_id"],
                "rid": p["run_id"],
                "p50": p["p50"],
                "unit": p["unit"]
            })
    
    return {"status": "ok", "run_id": run_id, "points": len(points)}

@app.get("/load/latest", response_model=LoadLatestResponse)
def load_latest(site_id: str):
    """获取最新负荷预测"""
    with engine.connect() as conn:
        # Get latest run_id by finding the max timestamp first
        latest_run = conn.execute(text("""
            SELECT run_id, MAX(ts) as max_ts
            FROM load_forecasts
            WHERE site_id=:sid
            GROUP BY run_id
            ORDER BY max_ts DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if not latest_run:
            return LoadLatestResponse(
                site_id=site_id,
                resolution_minutes=15,
                unit="kW",
                points=[]
            )
        
        run_id = latest_run[0]
        
        # Get all points for this run
        rows = conn.execute(text("""
            SELECT ts, p50
            FROM load_forecasts
            WHERE site_id=:sid AND run_id=:rid
            ORDER BY ts ASC
        """), {"sid": site_id, "rid": run_id}).all()
    
    return LoadLatestResponse(
        site_id=site_id,
        resolution_minutes=15,
        unit="kW",
        points=[LoadPoint(ts=r[0], p50=float(r[1])) for r in rows]
    )

# ============================================================================
# 3.4 Dispatch KPIs
# ============================================================================

class DispatchKPIs(BaseModel):
    run_id: str
    site_id: str
    total_cost: float
    total_curtail_kwh: float
    peak_grid_import_kw: float
    avg_soc: float
    created_at: datetime

@app.get("/dispatch/kpis", response_model=DispatchKPIs)
def get_dispatch_kpis(run_id: str):
    """获取调度优化的关键指标"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT run_id, site_id, total_cost, total_curtail_kwh, peak_grid_import_kw, avg_soc, created_at
            FROM dispatch_kpis
            WHERE run_id=:rid
        """), {"rid": run_id}).fetchone()
        
        if not result:
            # If KPIs not computed, calculate from dispatch_schedule
            schedule_rows = conn.execute(text("""
                SELECT curtail_kw, grid_imp_kw, soc, site_id
                FROM dispatch_schedule
                WHERE run_id=:rid
                ORDER BY ts ASC
            """), {"rid": run_id}).all()
            
            if not schedule_rows:
                return {"error": "Dispatch run not found"}, 404
            
            # Calculate KPIs (simplified)
            total_curtail_kwh = sum(r[0] for r in schedule_rows) * 0.25  # 15min intervals
            peak_grid_import_kw = max(r[1] for r in schedule_rows) if schedule_rows else 0.0
            avg_soc = sum(r[2] for r in schedule_rows) / len(schedule_rows) if schedule_rows else 0.5
            
            return DispatchKPIs(
                run_id=run_id,
                site_id=str(schedule_rows[0][3]),
                total_cost=0.0,  # Would need tariff data
                total_curtail_kwh=total_curtail_kwh,
                peak_grid_import_kw=peak_grid_import_kw,
                avg_soc=avg_soc,
                created_at=datetime.now(timezone.utc)
            )
        
        return DispatchKPIs(
            run_id=str(result[0]),
            site_id=str(result[1]),
            total_cost=float(result[2]),
            total_curtail_kwh=float(result[3]),
            peak_grid_import_kw=float(result[4]),
            avg_soc=float(result[5]),
            created_at=result[6]
        )

# ============================================================================
# 3.5 Model Health
# ============================================================================

class ModelHealth(BaseModel):
    id: str
    site_id: str
    model_type: str
    window_start: datetime
    window_end: datetime
    mae: float
    nrmse: float
    drift_score: float
    status: str
    created_at: datetime

@app.get("/health/latest", response_model=ModelHealth)
def get_model_health(site_id: str, model_type: str = "pv_forecast"):
    """获取模型健康状态（绿/黄/红灯）"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, site_id, model_type, window_start, window_end, mae, nrmse, drift_score, status, created_at
            FROM model_health
            WHERE site_id=:sid AND model_type=:mt
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": site_id, "mt": model_type}).fetchone()
        
        if not result:
            # Fallback to latest validation
            val_result = conn.execute(text("""
                SELECT id, site_id, horizon, start_ts, end_ts, mae, nrmse, bias, created_at
                FROM validation_runs
                WHERE site_id=:sid
                ORDER BY created_at DESC
                LIMIT 1
            """), {"sid": site_id}).fetchone()
            
            if not val_result:
                return ModelHealth(
                    id="00000000-0000-0000-0000-000000000000",
                    site_id=site_id,
                    model_type=model_type,
                    window_start=datetime.now(timezone.utc),
                    window_end=datetime.now(timezone.utc),
                    mae=0.0,
                    nrmse=0.0,
                    drift_score=0.0,
                    status="unknown",
                    created_at=datetime.now(timezone.utc)
                )
            
            # Derive health from validation
            nrmse = float(val_result[6])
            status = "green" if nrmse < 0.15 else "amber" if nrmse < 0.25 else "red"
            
            return ModelHealth(
                id=str(val_result[0]),
                site_id=str(val_result[1]),
                model_type=model_type,
                window_start=val_result[3],
                window_end=val_result[4],
                mae=float(val_result[5]),
                nrmse=nrmse,
                drift_score=abs(float(val_result[7])),  # Use bias as drift indicator
                status=status,
                created_at=val_result[8]
            )
        
        return ModelHealth(
            id=str(result[0]),
            site_id=str(result[1]),
            model_type=result[2],
            window_start=result[3],
            window_end=result[4],
            mae=float(result[5]),
            nrmse=float(result[6]),
            drift_score=float(result[7]),
            status=result[8],
            created_at=result[9]
        )

# ============================================================================
# 3.6 Alerts, Audit, Reports
# ============================================================================

class Alert(BaseModel):
    id: str
    site_id: str
    severity: str
    category: str
    title: str
    detail: str
    ts: datetime
    acknowledged: bool
    meta: dict

@app.get("/alerts")
def get_alerts(site_id: str, severity: str | None = None, limit: int = 50):
    """获取告警列表"""
    query = """
        SELECT id, site_id, severity, category, title, detail, ts, acknowledged, meta
        FROM alerts
        WHERE site_id=:sid
    """
    params = {"sid": site_id, "lim": limit}
    
    if severity:
        query += " AND severity=:sev"
        params["sev"] = severity
    
    query += " ORDER BY ts DESC LIMIT :lim"
    
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).all()
    
    return {
        "alerts": [
            {
                "id": str(r[0]),
                "site_id": str(r[1]),
                "severity": r[2],
                "category": r[3],
                "title": r[4],
                "detail": r[5],
                "ts": r[6].isoformat(),
                "acknowledged": r[7],
                "meta": r[8]
            }
            for r in rows
        ]
    }

@app.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: str):
    """确认告警"""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE alerts
            SET acknowledged=TRUE
            WHERE id=:aid
        """), {"aid": alert_id})
    
    return {"status": "ok", "alert_id": alert_id}

class AuditEntry(BaseModel):
    id: str
    actor: str
    action: str
    payload: dict
    created_at: datetime

@app.get("/audit")
def get_audit_log(site_id: str | None = None, action: str | None = None, limit: int = 100):
    """获取审计日志"""
    query = "SELECT id, actor, action, payload, created_at FROM audit_log WHERE 1=1"
    params = {"lim": limit}
    
    # Note: audit_log doesn't have site_id column, we filter by payload
    if site_id:
        query += " AND payload->>'site_id'=:sid"
        params["sid"] = site_id
    
    if action:
        query += " AND action=:act"
        params["act"] = action
    
    query += " ORDER BY created_at DESC LIMIT :lim"
    
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).all()
    
    return {
        "entries": [
            {
                "id": str(r[0]),
                "actor": r[1],
                "action": r[2],
                "payload": r[3],
                "created_at": r[4].isoformat()
            }
            for r in rows
        ]
    }

@app.get("/reports/dispatch.csv")
def export_dispatch_csv(run_id: str):
    """导出调度计划为CSV"""
    from fastapi.responses import Response
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ts, pv_set_kw, batt_ch_kw, batt_dis_kw, grid_imp_kw, grid_exp_kw, curtail_kw, soc, reason
            FROM dispatch_schedule
            WHERE run_id=:rid
            ORDER BY ts ASC
        """), {"rid": run_id}).all()
    
    if not rows:
        return {"error": "Dispatch run not found"}, 404
    
    # Build CSV
    csv_lines = ["timestamp,pv_set_kw,batt_ch_kw,batt_dis_kw,grid_imp_kw,grid_exp_kw,curtail_kw,soc,reason"]
    for r in rows:
        csv_lines.append(f"{r[0].isoformat()},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{r[7]},\"{r[8]}\"")
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dispatch_{run_id}.csv"}
    )
