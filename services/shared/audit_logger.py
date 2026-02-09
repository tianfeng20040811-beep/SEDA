"""
Audit Logger - Record all operations with full parameters and results
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from sqlalchemy import create_engine, text


class AuditLogger:
    """
    Centralized audit logging for all services
    
    Records to audit_log table with structure:
    {
        "site_id": "...",
        "request": {...},
        "result": {"run_id": "...", "status": "ok"},
        "versions": {"model_version": "v0003", "data_version": "d0010"},
        "runtime": {"ms": 1234, "fallback_used": false}
    }
    """
    
    def __init__(self, database_url: str):
        """
        Initialize audit logger
        
        Args:
            database_url: PostgreSQL connection string
        """
        self.engine = create_engine(database_url, pool_pre_ping=True)
    
    def log(
        self,
        actor: str,
        action: str,
        payload: Dict[str, Any]
    ) -> str:
        """
        Write audit log entry
        
        Args:
            actor: Who performed the action (e.g., "forecast_service", "user:123")
            action: What action was performed (e.g., "forecast_run", "dispatch_run")
            payload: Full context dictionary
        
        Returns:
            Audit log ID (UUID)
        """
        audit_id = str(uuid.uuid4())
        
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO audit_log (id, actor, action, payload, created_at)
                VALUES (:id, :actor, :action, :payload, :created_at)
            """), {
                "id": audit_id,
                "actor": actor,
                "action": action,
                "payload": json.dumps(payload),
                "created_at": datetime.now(timezone.utc)
            })
        
        return audit_id
    
    def log_forecast_run(
        self,
        site_id: str,
        request_params: Dict,
        run_id: str,
        status: str,
        model_version: Optional[str] = None,
        data_version: Optional[str] = None,
        runtime_ms: Optional[int] = None,
        error: Optional[str] = None
    ) -> str:
        """
        Log forecast run with full parameters
        
        Args:
            site_id: Site UUID
            request_params: Full request parameters
            run_id: Forecast run UUID
            status: "ok" or "error"
            model_version: ML model version used
            data_version: Data version/hash
            runtime_ms: Runtime in milliseconds
            error: Error message if failed
        
        Returns:
            Audit log ID
        """
        payload = {
            "site_id": site_id,
            "request": request_params,
            "result": {
                "run_id": run_id,
                "status": status,
                "error": error
            },
            "versions": {
                "model_version": model_version,
                "data_version": data_version
            },
            "runtime": {
                "ms": runtime_ms
            }
        }
        
        return self.log(
            actor="forecast_service",
            action="forecast_run",
            payload=payload
        )
    
    def log_dispatch_run(
        self,
        site_id: str,
        request_params: Dict,
        run_id: str,
        status: str,
        solver: str,
        solver_time_ms: int,
        fallback_used: bool,
        objective_value: Optional[float] = None,
        kpis: Optional[Dict] = None,
        error: Optional[str] = None
    ) -> str:
        """
        Log dispatch run with full parameters
        
        Args:
            site_id: Site UUID
            request_params: Full request (tariff, bess, limits, weights, forecast_quantile)
            run_id: Dispatch run UUID
            status: "ok", "fallback", or "error"
            solver: Solver name ("milp", "fallback_rule", etc.)
            solver_time_ms: Solver runtime in milliseconds
            fallback_used: Whether fallback was triggered
            objective_value: Optimization objective value
            kpis: KPI dictionary
            error: Error message if failed
        
        Returns:
            Audit log ID
        """
        payload = {
            "site_id": site_id,
            "request": request_params,
            "result": {
                "run_id": run_id,
                "status": status,
                "solver": solver,
                "objective_value": objective_value,
                "kpis": kpis,
                "error": error
            },
            "runtime": {
                "ms": solver_time_ms,
                "fallback_used": fallback_used
            }
        }
        
        return self.log(
            actor="dispatch_service",
            action="dispatch_run",
            payload=payload
        )
    
    def log_validation_run(
        self,
        site_id: str,
        request_params: Dict,
        validation_id: str,
        status: str,
        window_start: str,
        window_end: str,
        kpis: Dict,
        n_points: int,
        error: Optional[str] = None
    ) -> str:
        """
        Log validation run with window and KPIs
        
        Args:
            site_id: Site UUID
            request_params: Validation request parameters
            validation_id: Validation run UUID
            status: "ok" or "error"
            window_start: Start timestamp (ISO 8601)
            window_end: End timestamp (ISO 8601)
            kpis: KPI dictionary (mae, nrmse, bias, etc.)
            n_points: Number of data points validated
            error: Error message if failed
        
        Returns:
            Audit log ID
        """
        payload = {
            "site_id": site_id,
            "request": request_params,
            "result": {
                "validation_id": validation_id,
                "status": status,
                "error": error
            },
            "window": {
                "start": window_start,
                "end": window_end,
                "n_points": n_points
            },
            "kpis": kpis
        }
        
        return self.log(
            actor="forecast_service",
            action="validation_run",
            payload=payload
        )
    
    def log_calibration_run(
        self,
        site_id: str,
        calibration_id: str,
        bias: float,
        old_params: Dict,
        new_params: Dict,
        parameter_adjusted: str
    ) -> str:
        """
        Log calibration run
        
        Args:
            site_id: Site UUID
            calibration_id: Calibration run UUID
            bias: Validation bias that triggered calibration
            old_params: Old parameters
            new_params: New parameters
            parameter_adjusted: Which parameter was adjusted
        
        Returns:
            Audit log ID
        """
        payload = {
            "site_id": site_id,
            "result": {
                "calibration_id": calibration_id,
                "status": "ok"
            },
            "calibration": {
                "bias": bias,
                "parameter_adjusted": parameter_adjusted,
                "old_params": old_params,
                "new_params": new_params
            }
        }
        
        return self.log(
            actor="forecast_service",
            action="calibration_run",
            payload=payload
        )
    
    def get_recent_logs(
        self,
        action: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Retrieve recent audit logs
        
        Args:
            action: Filter by action type (optional)
            limit: Maximum number of logs to return
        
        Returns:
            List of audit log dictionaries
        """
        with self.engine.connect() as conn:
            if action:
                query = text("""
                    SELECT id, actor, action, payload, created_at
                    FROM audit_log
                    WHERE action = :action
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                rows = conn.execute(query, {"action": action, "limit": limit}).fetchall()
            else:
                query = text("""
                    SELECT id, actor, action, payload, created_at
                    FROM audit_log
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                rows = conn.execute(query, {"limit": limit}).fetchall()
        
        logs = []
        for row in rows:
            logs.append({
                "id": str(row[0]),
                "actor": row[1],
                "action": row[2],
                "payload": row[3],
                "created_at": row[4].isoformat()
            })
        
        return logs


# ============================================================================
# Test Code
# ============================================================================

if __name__ == "__main__":
    import os
    
    print("Testing AuditLogger...")
    
    # Initialize logger (use environment variable or default)
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sedai_db")
    logger = AuditLogger(database_url)
    
    # Test 1: Log forecast run
    print("\n" + "=" * 60)
    print("Test 1: Log forecast run")
    
    forecast_audit_id = logger.log_forecast_run(
        site_id="11111111-1111-1111-1111-111111111111",
        request_params={
            "horizon": "day_ahead",
            "resolution_minutes": 15,
            "use_ml_model": True,
            "weather_source": "mock"
        },
        run_id="22222222-2222-2222-2222-222222222222",
        status="ok",
        model_version="v20240315_001",
        data_version="d20240315",
        runtime_ms=1234
    )
    
    print(f"Forecast audit ID: {forecast_audit_id}")
    
    # Test 2: Log dispatch run
    print("\n" + "=" * 60)
    print("Test 2: Log dispatch run")
    
    dispatch_audit_id = logger.log_dispatch_run(
        site_id="11111111-1111-1111-1111-111111111111",
        request_params={
            "forecast_quantile": 0.5,
            "bess": {"capacity_kwh": 100, "p_charge_max_kw": 50},
            "limits": {"grid_import_max_kw": 200},
            "weights": {"cost": 1.0, "curtail": 0.2}
        },
        run_id="33333333-3333-3333-3333-333333333333",
        status="ok",
        solver="milp",
        solver_time_ms=2567,
        fallback_used=False,
        objective_value=145.32,
        kpis={
            "total_cost": 145.32,
            "total_curtail_kwh": 12.5,
            "peak_grid_import_kw": 87.3
        }
    )
    
    print(f"Dispatch audit ID: {dispatch_audit_id}")
    
    # Test 3: Log validation run
    print("\n" + "=" * 60)
    print("Test 3: Log validation run")
    
    validation_audit_id = logger.log_validation_run(
        site_id="11111111-1111-1111-1111-111111111111",
        request_params={
            "start": "2024-03-01T00:00:00Z",
            "end": "2024-03-02T00:00:00Z",
            "metric": "pv_power_kw"
        },
        validation_id="44444444-4444-4444-4444-444444444444",
        status="ok",
        window_start="2024-03-01T00:00:00Z",
        window_end="2024-03-02T00:00:00Z",
        kpis={
            "mae": 12.5,
            "nrmse": 0.15,
            "bias": -5.2,
            "r2": 0.92
        },
        n_points=96
    )
    
    print(f"Validation audit ID: {validation_audit_id}")
    
    # Test 4: Retrieve recent logs
    print("\n" + "=" * 60)
    print("Test 4: Retrieve recent logs")
    
    recent_logs = logger.get_recent_logs(limit=3)
    
    print(f"Retrieved {len(recent_logs)} recent logs:")
    for log in recent_logs:
        print(f"  - {log['action']} by {log['actor']} at {log['created_at']}")
    
    print("\n✓ AuditLogger test completed")
