"""
Model Predictor - Use trained models to generate PV forecasts
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from pv_physics import compute_p_physical, generate_mock_weather
from data_repo import DataRepository
from models.model_registry import ModelRegistry


class ForecastPredictor:
    """
    Generate PV forecasts using physical model + ML residual correction
    """
    
    def __init__(
        self,
        data_repo: Optional[DataRepository] = None,
        model_registry: Optional[ModelRegistry] = None
    ):
        """
        Initialize predictor
        
        Args:
            data_repo: Data repository instance
            model_registry: Model registry instance
        """
        self.data_repo = data_repo or DataRepository()
        self.model_registry = model_registry or ModelRegistry()
    
    def prepare_prediction_features(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        resolution_minutes: int = 15,
        use_mock_weather: bool = False
    ) -> Tuple[List[float], pd.DataFrame, Dict]:
        """
        Prepare features for prediction
        
        Args:
            site_id: Site UUID
            start: Start timestamp
            end: End timestamp
            resolution_minutes: Time resolution (minutes)
            use_mock_weather: Use mock weather instead of telemetry
        
        Returns:
            Tuple of (timestamps_unix, features_df, metadata)
        """
        # Get site info
        capacity_kw = self.data_repo.get_site_capacity(site_id)
        lat, lon = self.data_repo.get_site_location(site_id)
        
        # Get calibration parameters
        with self.data_repo.engine.connect() as conn:
            from sqlalchemy import text
            cal_row = conn.execute(text("""
                SELECT params FROM model_calibration
                WHERE site_id = :sid
                ORDER BY valid_from DESC
                LIMIT 1
            """), {"sid": site_id}).fetchone()
            
            if cal_row and cal_row[0]:
                params = cal_row[0]
            else:
                params = {"pr": 0.85, "soiling": 0.98}
        
        # Get weather data (historical or mock)
        if use_mock_weather:
            # Generate mock weather for future prediction
            mock_weather = generate_mock_weather(
                start.timestamp(),
                end.timestamp(),
                resolution_minutes,
                lat
            )
            
            timestamps = [w['timestamp'] for w in mock_weather]
            features_df = pd.DataFrame({
                'ghi': [w['ghi'] for w in mock_weather],
                'temp_amb': [w['t_amb'] for w in mock_weather],
                'wind': [w['wind'] for w in mock_weather]
            })
        else:
            # Extract from telemetry
            timestamps, features_df = self.data_repo.align_features(
                site_id=site_id,
                start=start,
                end=end,
                resolution_minutes=resolution_minutes,
                required_features=['ghi', 'temp_amb', 'wind']
            )
        
        # Compute physical baseline
        physical_predictions = []
        for idx, row in features_df.iterrows():
            p_phys = compute_p_physical(
                ghi=row['ghi'],
                t_amb=row['temp_amb'],
                wind=row['wind'],
                capacity_kw=capacity_kw,
                params=params
            )
            physical_predictions.append(p_phys)
        
        features_df['p_physical'] = physical_predictions
        
        # Add time-based features
        dt_series = pd.to_datetime(timestamps, unit='s', utc=True)
        features_df['hour'] = dt_series.hour
        features_df['minute'] = dt_series.minute
        features_df['day_of_year'] = dt_series.dayofyear
        features_df['month'] = dt_series.month
        
        # Add lagged features (assume last known values for future forecast)
        # For real-time forecast, these would come from recent telemetry
        features_df['ghi_lag1'] = features_df['ghi'].shift(1).fillna(features_df['ghi'].iloc[0] if len(features_df) > 0 else 0)
        features_df['ghi_lag2'] = features_df['ghi'].shift(2).fillna(features_df['ghi'].iloc[0] if len(features_df) > 0 else 0)
        features_df['p_physical_lag1'] = features_df['p_physical'].shift(1).fillna(features_df['p_physical'].iloc[0] if len(features_df) > 0 else 0)
        
        metadata = {
            "site_id": site_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "resolution_minutes": resolution_minutes,
            "capacity_kw": capacity_kw,
            "calibration_params": params,
            "use_mock_weather": use_mock_weather,
            "n_points": len(timestamps)
        }
        
        return timestamps, features_df, metadata
    
    def predict(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        resolution_minutes: int = 15,
        quantiles: Optional[List[float]] = None,
        model_version: Optional[str] = None,
        use_mock_weather: bool = True
    ) -> Dict:
        """
        Generate quantile forecasts
        
        Args:
            site_id: Site UUID
            start: Forecast start timestamp
            end: Forecast end timestamp
            resolution_minutes: Time resolution (minutes)
            quantiles: List of quantile levels (default: [0.1, 0.5, 0.9])
            model_version: Model version to use (uses latest if None)
            use_mock_weather: Use mock weather for future forecast
        
        Returns:
            Dict with forecast results
        """
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        
        # Prepare features
        timestamps, features_df, metadata = self.prepare_prediction_features(
            site_id, start, end, resolution_minutes, use_mock_weather
        )
        
        # Feature columns (must match training)
        feature_cols = [
            'ghi', 'temp_amb', 'wind', 'p_physical',
            'hour', 'minute', 'day_of_year', 'month',
            'ghi_lag1', 'ghi_lag2', 'p_physical_lag1'
        ]
        
        X = features_df[feature_cols]
        
        # Load models and predict residuals
        predictions = {}
        models_used = {}
        
        for q in quantiles:
            model = self.model_registry.load_model(
                site_id=site_id,
                model_type="pv_forecast",
                quantile=q,
                version=model_version
            )
            
            if model is None:
                # Fallback: use physical model only with quantile spread
                print(f"Warning: No ML model found for q{int(q*100):02d}, using physical baseline")
                if q == 0.1:
                    predictions[q] = features_df['p_physical'].values * 0.8
                elif q == 0.9:
                    predictions[q] = features_df['p_physical'].values * 1.2
                else:
                    predictions[q] = features_df['p_physical'].values
                
                models_used[q] = "physical_baseline_only"
            else:
                # Predict residuals and add to physical baseline
                residual_pred = model.predict(X)
                predictions[q] = features_df['p_physical'].values + residual_pred
                
                # Ensure non-negative
                predictions[q] = np.maximum(predictions[q], 0.0)
                
                models_used[q] = model_version or self.model_registry.get_latest_version(site_id, "pv_forecast")
        
        # Get actual model version used
        if model_version is None:
            model_version = self.model_registry.get_latest_version(site_id, "pv_forecast")
        
        # Build result
        points = []
        for i, ts in enumerate(timestamps):
            point = {
                "ts": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            }
            for q in quantiles:
                point[f"p{int(q*100):02d}"] = float(predictions[q][i])
            points.append(point)
        
        result = {
            "site_id": site_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "resolution_minutes": resolution_minutes,
            "unit": "kW",
            "model_version": model_version,
            "models_used": models_used,
            "metadata": metadata,
            "points": points
        }
        
        return result
    
    def predict_physical_only(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        resolution_minutes: int = 15,
        use_mock_weather: bool = True
    ) -> Dict:
        """
        Generate forecast using physical model only (no ML correction)
        Useful for baseline comparison
        
        Args:
            site_id: Site UUID
            start: Forecast start timestamp
            end: Forecast end timestamp
            resolution_minutes: Time resolution (minutes)
            use_mock_weather: Use mock weather for future forecast
        
        Returns:
            Dict with forecast results
        """
        timestamps, features_df, metadata = self.prepare_prediction_features(
            site_id, start, end, resolution_minutes, use_mock_weather
        )
        
        p_physical = features_df['p_physical'].values
        
        points = []
        for i, ts in enumerate(timestamps):
            points.append({
                "ts": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "p10": float(p_physical[i] * 0.8),
                "p50": float(p_physical[i]),
                "p90": float(p_physical[i] * 1.2)
            })
        
        result = {
            "site_id": site_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "resolution_minutes": resolution_minutes,
            "unit": "kW",
            "model_version": "physical_baseline",
            "metadata": metadata,
            "points": points
        }
        
        return result


if __name__ == "__main__":
    # Test predictor
    from datetime import datetime, timezone, timedelta
    
    site_id = "11111111-1111-1111-1111-111111111111"
    
    # Forecast for tomorrow (day-ahead)
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=24)
    
    print("Forecast Predictor Test")
    print("=" * 60)
    
    predictor = ForecastPredictor()
    
    # Test 1: Physical model only
    print("\n1. Physical model only (baseline):")
    result_physical = predictor.predict_physical_only(
        site_id=site_id,
        start=start,
        end=end,
        resolution_minutes=60,  # Hourly for test
        use_mock_weather=True
    )
    
    print(f"Generated {len(result_physical['points'])} points")
    print(f"First 3 points:")
    for p in result_physical['points'][:3]:
        print(f"  {p['ts']}: p10={p['p10']:.1f}, p50={p['p50']:.1f}, p90={p['p90']:.1f} kW")
    
    # Test 2: ML-enhanced prediction (if models available)
    print("\n2. ML-enhanced prediction:")
    result_ml = predictor.predict(
        site_id=site_id,
        start=start,
        end=end,
        resolution_minutes=60,
        quantiles=[0.1, 0.5, 0.9],
        use_mock_weather=True
    )
    
    print(f"Model version: {result_ml['model_version']}")
    print(f"Generated {len(result_ml['points'])} points")
    print(f"First 3 points:")
    for p in result_ml['points'][:3]:
        print(f"  {p['ts']}: p10={p['p10']:.1f}, p50={p['p50']:.1f}, p90={p['p90']:.1f} kW")
