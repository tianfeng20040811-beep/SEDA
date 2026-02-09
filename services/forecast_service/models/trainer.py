"""
Model Trainer - Train LightGBM quantile regression models for PV forecast
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from pv_physics import compute_p_physical, batch_compute_physical
from data_repo import DataRepository
from models.model_registry import ModelRegistry


class ForecastTrainer:
    """
    Train ML models to predict residuals from physical baseline
    Uses LightGBM with quantile regression objective
    """
    
    def __init__(
        self,
        data_repo: Optional[DataRepository] = None,
        model_registry: Optional[ModelRegistry] = None
    ):
        """
        Initialize trainer
        
        Args:
            data_repo: Data repository instance
            model_registry: Model registry instance
        """
        self.data_repo = data_repo or DataRepository()
        self.model_registry = model_registry or ModelRegistry()
    
    def prepare_training_data(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        resolution_minutes: int = 15
    ) -> Tuple[pd.DataFrame, np.ndarray, Dict]:
        """
        Prepare training data: features (X) and target (y)
        
        Args:
            site_id: Site UUID
            start: Start timestamp
            end: End timestamp
            resolution_minutes: Time resolution (minutes)
        
        Returns:
            Tuple of (features_df, targets_array, metadata_dict)
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
        
        # Extract features and actual power
        timestamps, features_df = self.data_repo.align_features(
            site_id=site_id,
            start=start,
            end=end,
            resolution_minutes=resolution_minutes,
            required_features=['ghi', 'temp_amb', 'wind', 'pv_power_kw']
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
        
        # Compute residuals (actual - physical)
        features_df['residual'] = features_df['pv_power_kw'] - features_df['p_physical']
        
        # Add time-based features
        dt_series = pd.to_datetime(timestamps, unit='s', utc=True)
        features_df['hour'] = dt_series.hour
        features_df['minute'] = dt_series.minute
        features_df['day_of_year'] = dt_series.dayofyear
        features_df['month'] = dt_series.month
        
        # Add lagged features (simple approach)
        features_df['ghi_lag1'] = features_df['ghi'].shift(1).fillna(0)
        features_df['ghi_lag2'] = features_df['ghi'].shift(2).fillna(0)
        features_df['p_physical_lag1'] = features_df['p_physical'].shift(1).fillna(0)
        
        # Feature columns for model
        feature_cols = [
            'ghi', 'temp_amb', 'wind', 'p_physical',
            'hour', 'minute', 'day_of_year', 'month',
            'ghi_lag1', 'ghi_lag2', 'p_physical_lag1'
        ]
        
        X = features_df[feature_cols]
        y = features_df['residual'].values
        
        metadata = {
            "site_id": site_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "resolution_minutes": resolution_minutes,
            "n_samples": len(X),
            "capacity_kw": capacity_kw,
            "calibration_params": params,
            "feature_cols": feature_cols
        }
        
        return X, y, metadata
    
    def train_quantile_model(
        self,
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        quantile: float,
        params: Optional[Dict] = None
    ) -> lgb.Booster:
        """
        Train a single quantile regression model
        
        Args:
            X_train: Training features
            y_train: Training targets (residuals)
            quantile: Quantile level (e.g., 0.1, 0.5, 0.9)
            params: LightGBM parameters (uses defaults if None)
        
        Returns:
            Trained LightGBM Booster
        """
        if params is None:
            params = {
                'objective': 'quantile',
                'alpha': quantile,
                'metric': 'quantile',
                'boosting_type': 'gbdt',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.9,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1
            }
        else:
            params['objective'] = 'quantile'
            params['alpha'] = quantile
            params['metric'] = 'quantile'
        
        # Create LightGBM dataset
        train_data = lgb.Dataset(X_train, label=y_train)
        
        # Train model
        model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            valid_sets=[train_data],
            callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)]
        )
        
        return model
    
    def train(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        quantiles: Optional[List[float]] = None,
        test_size: float = 0.2,
        save_models: bool = True
    ) -> Dict:
        """
        Train quantile models for multiple quantiles
        
        Args:
            site_id: Site UUID
            start: Training data start timestamp
            end: Training data end timestamp
            quantiles: List of quantile levels (default: [0.1, 0.5, 0.9])
            test_size: Fraction of data for testing
            save_models: Whether to save models to registry
        
        Returns:
            Dict with training results and metrics
        """
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        
        print(f"Training models for site {site_id}")
        print(f"Period: {start} to {end}")
        
        # Prepare data
        X, y, metadata = self.prepare_training_data(site_id, start, end)
        
        print(f"Prepared {len(X)} samples with {len(X.columns)} features")
        
        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, shuffle=False  # Time series: don't shuffle
        )
        
        print(f"Train: {len(X_train)} samples, Test: {len(X_test)} samples")
        
        # Train models for each quantile
        models = {}
        metrics = {}
        
        for q in quantiles:
            print(f"\nTraining q{int(q*100):02d} model...")
            
            model = self.train_quantile_model(X_train, y_train, q)
            models[q] = model
            
            # Evaluate on test set
            y_pred = model.predict(X_test)
            
            # Quantile loss
            residuals = y_test - y_pred
            quantile_loss = np.mean(
                np.where(residuals >= 0, q * residuals, (q - 1) * residuals)
            )
            
            mae = np.mean(np.abs(residuals))
            
            metrics[q] = {
                "quantile_loss": float(quantile_loss),
                "mae": float(mae),
                "test_samples": len(y_test)
            }
            
            print(f"  Quantile loss: {quantile_loss:.4f}, MAE: {mae:.4f} kW")
        
        # Generate version and save models
        version = None
        if save_models:
            for q, model in models.items():
                version = self.model_registry.save_model(
                    site_id=site_id,
                    model_type="pv_forecast",
                    quantile=q,
                    model_obj=model,
                    metadata={
                        **metadata,
                        "metrics": metrics[q]
                    },
                    version=version  # Use same version for all quantiles
                )
            
            print(f"\nSaved models with version: {version}")
        
        result = {
            "version": version,
            "quantiles": quantiles,
            "metrics": metrics,
            "metadata": metadata,
            "feature_importance": {
                q: dict(zip(X.columns, models[q].feature_importance().tolist()))
                for q in quantiles
            }
        }
        
        return result


if __name__ == "__main__":
    # Test trainer
    from datetime import datetime, timezone, timedelta
    
    site_id = "11111111-1111-1111-1111-111111111111"
    
    # Training period: last 30 days
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=30)
    
    print("Forecast Trainer Test")
    print("=" * 60)
    
    trainer = ForecastTrainer()
    
    # Train models
    result = trainer.train(
        site_id=site_id,
        start=start,
        end=end,
        quantiles=[0.1, 0.5, 0.9],
        test_size=0.2,
        save_models=True
    )
    
    print("\n" + "=" * 60)
    print("Training Results:")
    print(f"Version: {result['version']}")
    print(f"\nMetrics:")
    for q, m in result['metrics'].items():
        print(f"  q{int(q*100):02d}: MAE={m['mae']:.2f} kW, Quantile Loss={m['quantile_loss']:.4f}")
    
    print(f"\nTop 5 Features (q50):")
    q50_importance = result['feature_importance'][0.5]
    top_features = sorted(q50_importance.items(), key=lambda x: x[1], reverse=True)[:5]
    for feat, importance in top_features:
        print(f"  {feat:20s}: {importance:.1f}")
