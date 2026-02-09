import os, uuid, sys, time
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from audit_logger import AuditLogger

# Import new modules
from pv_physics import compute_p_physical, generate_mock_weather
from data_repo import DataRepository
from models.predictor import ForecastPredictor
from models.trainer import ForecastTrainer
from models.model_registry import ModelRegistry
from validation.validator import ForecastValidator
from validation.drift_detector import DriftDetector
from validation.calibrator import ModelCalibrator

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Initialize components
data_repo = DataRepository(DATABASE_URL)
model_registry = ModelRegistry()
predictor = ForecastPredictor(data_repo, model_registry)
trainer = ForecastTrainer(data_repo, model_registry)
validator = ForecastValidator()
drift_detector = DriftDetector(baseline_days=30, recent_days=7)
calibrator = ModelCalibrator(k_pr=0.001, pr_min=0.70, pr_max=0.95)
audit_logger = AuditLogger(DATABASE_URL)

app = FastAPI(title="Forecast Service - Enhanced with ML")


# ============================================================================
# Request Models
# ============================================================================

class RunReq(BaseModel):
    site_id: str
    horizon: str = "day_ahead"
    resolution_minutes: int = 15
    start: Optional[str] = None  # ISO 8601, defaults to tomorrow 00:00
    end: Optional[str] = None    # ISO 8601, defaults to start + 24h
    quantiles: Optional[List[float]] = None  # Default [0.1, 0.5, 0.9]
    use_ml_model: bool = True    # Use ML model if available
    weather_source: str = "mock"  # "telemetry" or "mock"

class TrainReq(BaseModel):
    site_id: str
    start: str  # ISO 8601
    end: str    # ISO 8601
    quantiles: Optional[List[float]] = None
    test_size: float = 0.2


# ============================================================================
# Endpoints
# ============================================================================

@app.post("/forecast/run")
def run_forecast(req: RunReq):
    """
    Run PV forecast using physical model + ML residual correction
    Supports both baseline physics and ML-enhanced prediction
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
    
    quantiles = req.quantiles or [0.1, 0.5, 0.9]
    
    # Determine model version to use
    model_version = None
    use_ml = req.use_ml_model
    
    if use_ml:
        # Check if ML models exist
        model_version = model_registry.get_latest_version(req.site_id, "pv_forecast")
        if model_version is None:
            print(f"No ML model found for site {req.site_id}, falling back to physical model")
            use_ml = False
    
    # Generate forecast
    error_msg = None
    try:
        if use_ml:
            # ML-enhanced prediction
            forecast_result = predictor.predict(
                site_id=req.site_id,
                start=start,
                end=end,
                resolution_minutes=req.resolution_minutes,
                quantiles=quantiles,
                model_version=model_version,
                use_mock_weather=(req.weather_source == "mock")
            )
            model_version_str = forecast_result['model_version']
            fallback_used = False
        else:
            # Physical model only
            forecast_result = predictor.predict_physical_only(
                site_id=req.site_id,
                start=start,
                end=end,
                resolution_minutes=req.resolution_minutes,
                use_mock_weather=(req.weather_source == "mock")
            )
            model_version_str = "physical_baseline"
            fallback_used = True
        
    except Exception as e:
        # Fallback to simple mock if prediction fails
        error_msg = str(e)
        print(f"Forecast prediction failed: {e}, using simple mock")
        forecast_result = _generate_simple_mock(req.site_id, start, end, req.resolution_minutes)
        model_version_str = "simple_mock_fallback"
        fallback_used = True
    
    # Insert forecast run metadata
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO forecast_runs (id, site_id, horizon, resolution_minutes, model_version, feature_version, data_version)
          VALUES (:id, :sid, :h, :res, :mv, :fv, :dv)
        """), {
            "id": run_id,
            "sid": req.site_id,
            "h": req.horizon,
            "res": req.resolution_minutes,
            "mv": model_version_str,
            "fv": "weather_mock" if req.weather_source == "mock" else "weather_telemetry",
            "dv": datetime.now(timezone.utc).strftime("%Y%m%d")
        })
        
        # Insert forecast points
        rows = []
        for point in forecast_result['points']:
            ts = datetime.fromisoformat(point['ts'].replace('Z', '+00:00'))
            rows.append({
                "ts": ts,
                "sid": req.site_id,
                "rid": run_id,
                "p10": point.get('p10', 0.0),
                "p50": point.get('p50', 0.0),
                "p90": point.get('p90', 0.0)
            })
        
        conn.execute(text("""
          INSERT INTO forecasts (ts, site_id, run_id, p10, p50, p90, unit)
          VALUES (:ts, :sid, :rid, :p10, :p50, :p90, 'kW')
        """), rows)
    
    # Calculate runtime
    runtime_ms = int((time.time() - start_time) * 1000)
    
    # Audit log
    audit_logger.log_forecast_run(
        site_id=req.site_id,
        request_params=req.dict(),
        run_id=run_id,
        status="ok" if error_msg is None else "error",
        model_version=model_version_str,
        data_version=datetime.now(timezone.utc).strftime("%Y%m%d"),
        runtime_ms=runtime_ms,
        error=error_msg
    )
    
    return {
        "run_id": run_id,
        "status": "ok",
        "model_version": model_version_str,
        "fallback_used": fallback_used,
        "points_generated": len(forecast_result['points'])
    }


@app.get("/forecast/latest")
def latest(site_id: str, horizon: str = "day_ahead"):
    """Get latest forecast for a site"""
    q = text("""
      SELECT f.ts, f.p10, f.p50, f.p90
      FROM forecasts f
      JOIN forecast_runs r ON r.id=f.run_id
      WHERE f.site_id=:sid AND r.horizon=:h
      ORDER BY r.created_at DESC, f.ts ASC
      LIMIT 96
    """)
    with engine.connect() as conn:
        rows = conn.execute(q, {"sid": site_id, "h": horizon}).all()

    points = [{"ts": r[0], "p10": float(r[1]), "p50": float(r[2]), "p90": float(r[3])} for r in rows]
    return {"site_id": site_id, "horizon": horizon, "resolution_minutes": 15, "unit": "kW", "points": points}


@app.post("/train")
def train_models(req: TrainReq):
    """
    Train ML models for a site using historical data
    This should be run periodically (e.g., weekly) to update models
    """
    try:
        # Parse timestamps
        start = datetime.fromisoformat(req.start.replace('Z', '+00:00'))
        end = datetime.fromisoformat(req.end.replace('Z', '+00:00'))
        
        # Train models
        result = trainer.train(
            site_id=req.site_id,
            start=start,
            end=end,
            quantiles=req.quantiles or [0.1, 0.5, 0.9],
            test_size=req.test_size,
            save_models=True
        )
        
        return {
            "status": "ok",
            "version": result['version'],
            "metrics": result['metrics'],
            "training_samples": result['metadata']['n_samples']
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


@app.get("/models/list")
def list_models(site_id: str):
    """List available model versions for a site"""
    versions = model_registry.list_versions(site_id, "pv_forecast")
    return {"site_id": site_id, "versions": versions}


@app.get("/models/info")
def model_info(site_id: str, version: Optional[str] = None):
    """Get detailed info about a model version"""
    info = model_registry.get_model_info(site_id, "pv_forecast", version)
    
    if info is None:
        raise HTTPException(status_code=404, detail="Model not found")
    
    return info


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_simple_mock(site_id: str, start: datetime, end: datetime, resolution_minutes: int):
    """
    Fallback: generate simple mock forecast
    Used when ML models fail or don't exist
    """
    # Get calibration parameters
    with engine.connect() as conn:
        cal_row = conn.execute(text("""
          SELECT params FROM model_calibration
          WHERE site_id=:sid
          ORDER BY valid_from DESC
          LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if cal_row and cal_row[0]:
            params = cal_row[0]
            pr = params.get("pr", 0.85)
            soiling = params.get("soiling", 0.98)
        else:
            pr = 0.85
            soiling = 0.98
    
    calibration_factor = pr * soiling
    
    # Generate simple profile
    points = []
    t = start
    while t < end:
        base = 10.0
        if 7 <= t.hour <= 18:
            base = 50.0 + (t.hour - 7) * 10.0
        
        p50 = base * calibration_factor
        points.append({
            "ts": t.isoformat(),
            "p10": p50 * 0.8,
            "p50": p50,
            "p90": p50 * 1.2
        })
        t += timedelta(minutes=resolution_minutes)
    
    return {"points": points}


# ============================================================================
# Validation, Drift Detection, and Calibration Endpoints
# ============================================================================

class ValidateReq(BaseModel):
    site_id: str
    start: str  # ISO 8601
    end: str    # ISO 8601
    resolution_minutes: int = 15
    forecast_run_id: Optional[str] = None  # Use specific forecast run, or latest
    metric: str = "pv_power_kw"  # Telemetry metric to compare against


@app.post("/validate/run")
def run_validation(req: ValidateReq):
    """
    Run forecast validation against actual telemetry
    
    Calculates: MAE, NRMSE, Bias, R² and other metrics
    Writes results to validation_runs table
    
    Returns validation_run_id and metrics
    """
    import json
    
    start = datetime.fromisoformat(req.start.replace('Z', '+00:00'))
    end = datetime.fromisoformat(req.end.replace('Z', '+00:00'))
    
    with engine.begin() as conn:
        # Fetch actual telemetry
        actual_rows = conn.execute(text("""
            SELECT ts, value
            FROM telemetry
            WHERE site_id = :sid
              AND metric = :metric
              AND ts >= :start
              AND ts < :end
            ORDER BY ts ASC
        """), {
            "sid": req.site_id,
            "metric": req.metric,
            "start": start,
            "end": end
        }).fetchall()
        
        if len(actual_rows) == 0:
            raise HTTPException(status_code=404, detail="No actual telemetry found")
        
        # Fetch forecast
        if req.forecast_run_id:
            forecast_rows = conn.execute(text("""
                SELECT ts, p50
                FROM forecasts
                WHERE site_id = :sid
                  AND run_id = :rid
                  AND ts >= :start
                  AND ts < :end
                ORDER BY ts ASC
            """), {
                "sid": req.site_id,
                "rid": req.forecast_run_id,
                "start": start,
                "end": end
            }).fetchall()
        else:
            # Use latest forecast run
            forecast_rows = conn.execute(text("""
                SELECT f.ts, f.p50
                FROM forecasts f
                JOIN forecast_runs r ON r.id = f.run_id
                WHERE f.site_id = :sid
                  AND f.ts >= :start
                  AND f.ts < :end
                ORDER BY r.created_at DESC, f.ts ASC
                LIMIT 96
            """), {
                "sid": req.site_id,
                "start": start,
                "end": end
            }).fetchall()
        
        if len(forecast_rows) == 0:
            raise HTTPException(status_code=404, detail="No forecast found")
        
        # Align timestamps
        actual_dict = {row[0]: float(row[1]) for row in actual_rows}
        forecast_dict = {row[0]: float(row[1]) for row in forecast_rows}
        
        common_ts = sorted(set(actual_dict.keys()) & set(forecast_dict.keys()))
        
        if len(common_ts) == 0:
            raise HTTPException(status_code=400, detail="No overlapping timestamps")
        
        actual = [actual_dict[ts] for ts in common_ts]
        forecast = [forecast_dict[ts] for ts in common_ts]
        
        # Calculate metrics
        metrics = validator.calculate_metrics(actual, forecast)
        
        # Save validation run
        validation_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO validation_runs (
                id, site_id, horizon, start_ts, end_ts, resolution_minutes,
                run_id_forecast, metric, mae, nrmse, bias
            )
            VALUES (
                :id, :sid, :horizon, :start, :end, :res,
                :fid, :metric, :mae, :nrmse, :bias
            )
        """), {
            "id": validation_id,
            "sid": req.site_id,
            "horizon": "day_ahead",
            "start": start,
            "end": end,
            "res": req.resolution_minutes,
            "fid": req.forecast_run_id,
            "metric": req.metric,
            "mae": metrics['mae'],
            "nrmse": metrics['nrmse'],
            "bias": metrics['bias']
        })
    
    # Audit log
    audit_logger.log_validation_run(
        site_id=req.site_id,
        request_params=req.dict(),
        validation_id=validation_id,
        status="ok",
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        kpis={
            "mae": metrics['mae'],
            "rmse": metrics['rmse'],
            "nrmse": metrics['nrmse'],
            "bias": metrics['bias'],
            "r2": metrics['r2']
        },
        n_points=metrics['n_points']
    )
    
    return {
        "validation_id": validation_id,
        "status": "ok",
        "metrics": {
            "mae": metrics['mae'],
            "rmse": metrics['rmse'],
            "nrmse": metrics['nrmse'],
            "bias": metrics['bias'],
            "r2": metrics['r2']
        },
        "points": {
            "n_points": metrics['n_points'],
            "mean_actual": metrics['mean_actual'],
            "mean_forecast": metrics['mean_forecast']
        }
    }


@app.get("/validate/latest")
def get_latest_validation(site_id: str):
    """Get latest validation result for a site"""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, mae, nrmse, bias, created_at
            FROM validation_runs
            WHERE site_id = :sid
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if row is None:
            raise HTTPException(status_code=404, detail="No validation found")
        
        return {
            "validation_id": str(row[0]),
            "mae": float(row[1]),
            "nrmse": float(row[2]),
            "bias": float(row[3]),
            "created_at": row[4].isoformat()
        }


@app.post("/drift/check")
def check_drift(site_id: str):
    """
    Check for model drift
    
    Compares recent NRMSE (last 7 days) to baseline (30 days)
    Returns drift_score and status (green/amber/red)
    Writes result to model_health table
    """
    with engine.begin() as conn:
        # Detect drift
        drift_result = drift_detector.detect_drift_from_db(
            conn, site_id, datetime.now(timezone.utc)
        )
        
        # Calculate window times
        now = datetime.now(timezone.utc)
        window_end = now
        window_start = now - timedelta(days=drift_detector.baseline_days)
        
        # Save to model_health
        health_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO model_health (
                id, site_id, model_type, window_start, window_end,
                mae, nrmse, drift_score, status
            )
            VALUES (
                :id, :sid, :model, :wstart, :wend,
                :mae, :nrmse, :drift, :status
            )
        """), {
            "id": health_id,
            "sid": site_id,
            "model": "forecast_ml",
            "wstart": window_start,
            "wend": window_end,
            "mae": 0.0,  # Not calculated in drift detection
            "nrmse": drift_result['recent_nrmse'],
            "drift": drift_result['drift_score'],
            "status": drift_result['status']
        })
    
    return {
        "health_id": health_id,
        "status": drift_result['status'],
        "drift_score": drift_result['drift_score'],
        "baseline_nrmse": drift_result['baseline_nrmse'],
        "recent_nrmse": drift_result['recent_nrmse'],
        "message": drift_result['message']
    }


@app.get("/health/latest")
def get_latest_health(site_id: str):
    """Get latest model health check result"""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, drift_score, status, nrmse, created_at
            FROM model_health
            WHERE site_id = :sid
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if row is None:
            raise HTTPException(status_code=404, detail="No health check found")
        
        return {
            "health_id": str(row[0]),
            "drift_score": float(row[1]),
            "status": row[2],
            "nrmse": float(row[3]),
            "created_at": row[4].isoformat()
        }


@app.post("/calibrate/run")
def run_calibration(site_id: str, capacity_kw: float = 200.0):
    """
    Auto-calibrate baseline physics model parameters
    
    Uses latest validation bias to adjust PR or soiling factor
    Writes new parameters to model_calibration table
    
    Returns calibration_id and new parameters
    """
    import json
    
    with engine.begin() as conn:
        # Get latest validation bias
        val_row = conn.execute(text("""
            SELECT bias
            FROM validation_runs
            WHERE site_id = :sid
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if val_row is None:
            raise HTTPException(status_code=404, detail="No validation found, run validation first")
        
        bias = float(val_row[0])
        
        # Get current calibration parameters
        cal_row = conn.execute(text("""
            SELECT params
            FROM model_calibration
            WHERE site_id = :sid
            ORDER BY valid_from DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if cal_row and cal_row[0]:
            current_params = cal_row[0]
        else:
            current_params = {"pr": 0.85, "soiling": 0.98}
        
        # Auto-calibrate
        calibration_result = calibrator.auto_calibrate(
            bias=bias,
            current_params=current_params,
            capacity_kw=capacity_kw
        )
        
        # Prepare new parameters
        new_params = {
            "pr": calibration_result.get('pr_new', current_params.get('pr', 0.85)),
            "soiling": calibration_result.get('soiling_new', current_params.get('soiling', 0.98)),
            "bias": bias,
            "calibrated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Save calibration
        calibration_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO model_calibration (
                id, site_id, model_type, params, valid_from
            )
            VALUES (
                :id, :sid, :model, :params, :valid
            )
        """), {
            "id": calibration_id,
            "sid": site_id,
            "model": "forecast_baseline",
            "params": json.dumps(new_params),
            "valid": datetime.now(timezone.utc)
        })
    
    # Audit log
    audit_logger.log_calibration_run(
        site_id=site_id,
        calibration_id=calibration_id,
        bias=bias,
        old_params=current_params,
        new_params=new_params,
        parameter_adjusted=calibration_result.get('parameter', 'pr')
    )
    
    return {
        "calibration_id": calibration_id,
        "status": "ok",
        "bias": bias,
        "parameter": calibration_result.get('parameter', 'pr'),
        "old_params": current_params,
        "new_params": new_params,
        "delta": {
            "pr": calibration_result.get('pr_delta', 0.0),
            "soiling": calibration_result.get('soiling_delta', 0.0)
        }
    }


@app.get("/calibrate/latest")
def get_latest_calibration(site_id: str):
    """Get latest calibration parameters for a site"""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, params, valid_from
            FROM model_calibration
            WHERE site_id = :sid
            ORDER BY valid_from DESC
            LIMIT 1
        """), {"sid": site_id}).fetchone()
        
        if row is None:
            # Return default parameters
            return {
                "calibration_id": None,
                "params": {"pr": 0.85, "soiling": 0.98},
                "valid_from": None
            }
        
        return {
            "calibration_id": str(row[0]),
            "params": row[1],
            "valid_from": row[2].isoformat()
        }
