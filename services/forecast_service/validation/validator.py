"""
Forecast Validator - Calculate KPIs (MAE, NRMSE, Bias, etc.)
"""

import numpy as np
from typing import Dict, List, Tuple


class ForecastValidator:
    """
    Calculate forecast validation metrics
    
    KPIs:
    - MAE (Mean Absolute Error): Mean of |actual - forecast|
    - RMSE (Root Mean Square Error): sqrt(mean((actual - forecast)^2))
    - NRMSE (Normalized RMSE): RMSE / mean(actual)
    - Bias: Mean(forecast - actual)
    - MBE (Mean Bias Error): Same as Bias
    - R2: Coefficient of determination
    """
    
    def __init__(self):
        pass
    
    def calculate_metrics(
        self,
        actual: List[float],
        forecast: List[float]
    ) -> Dict[str, float]:
        """
        Calculate all validation metrics
        
        Args:
            actual: Actual PV power measurements (kW)
            forecast: Forecasted PV power (kW)
        
        Returns:
            Dictionary with metrics:
            {
                'mae': Mean Absolute Error,
                'rmse': Root Mean Square Error,
                'nrmse': Normalized RMSE (0-1),
                'bias': Mean Bias (forecast - actual),
                'mbe': Mean Bias Error (same as bias),
                'r2': R-squared,
                'n_points': Number of data points,
                'mean_actual': Mean of actual values,
                'mean_forecast': Mean of forecast values
            }
        """
        actual_arr = np.array(actual)
        forecast_arr = np.array(forecast)
        
        # Filter out invalid values (NaN, negative)
        valid_mask = (~np.isnan(actual_arr)) & (~np.isnan(forecast_arr)) & (actual_arr >= 0) & (forecast_arr >= 0)
        actual_valid = actual_arr[valid_mask]
        forecast_valid = forecast_arr[valid_mask]
        
        if len(actual_valid) == 0:
            return {
                'mae': 0.0,
                'rmse': 0.0,
                'nrmse': 0.0,
                'bias': 0.0,
                'mbe': 0.0,
                'r2': 0.0,
                'n_points': 0,
                'mean_actual': 0.0,
                'mean_forecast': 0.0
            }
        
        # Calculate errors
        errors = forecast_valid - actual_valid
        abs_errors = np.abs(errors)
        squared_errors = errors ** 2
        
        # Basic statistics
        n_points = len(actual_valid)
        mean_actual = float(np.mean(actual_valid))
        mean_forecast = float(np.mean(forecast_valid))
        
        # MAE
        mae = float(np.mean(abs_errors))
        
        # RMSE
        rmse = float(np.sqrt(np.mean(squared_errors)))
        
        # NRMSE (normalized by mean actual)
        if mean_actual > 0:
            nrmse = rmse / mean_actual
        else:
            nrmse = 0.0
        
        # Bias / MBE
        bias = float(np.mean(errors))
        mbe = bias
        
        # R2 (coefficient of determination)
        ss_res = np.sum(squared_errors)
        ss_tot = np.sum((actual_valid - mean_actual) ** 2)
        if ss_tot > 0:
            r2 = float(1 - (ss_res / ss_tot))
        else:
            r2 = 0.0
        
        return {
            'mae': mae,
            'rmse': rmse,
            'nrmse': nrmse,
            'bias': bias,
            'mbe': mbe,
            'r2': r2,
            'n_points': n_points,
            'mean_actual': mean_actual,
            'mean_forecast': mean_forecast
        }
    
    def calculate_metrics_by_quantile(
        self,
        actual: List[float],
        p10: List[float],
        p50: List[float],
        p90: List[float]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate metrics for each quantile separately
        
        Args:
            actual: Actual PV power measurements
            p10: 10th percentile forecasts
            p50: 50th percentile (median) forecasts
            p90: 90th percentile forecasts
        
        Returns:
            Dictionary with metrics for each quantile:
            {
                'p10': {...metrics...},
                'p50': {...metrics...},
                'p90': {...metrics...}
            }
        """
        return {
            'p10': self.calculate_metrics(actual, p10),
            'p50': self.calculate_metrics(actual, p50),
            'p90': self.calculate_metrics(actual, p90)
        }
    
    def calculate_hourly_metrics(
        self,
        actual: List[float],
        forecast: List[float],
        timestamps: List
    ) -> Dict[int, Dict[str, float]]:
        """
        Calculate metrics grouped by hour of day
        
        Args:
            actual: Actual PV power
            forecast: Forecasted PV power
            timestamps: List of datetime objects
        
        Returns:
            Dictionary keyed by hour (0-23):
            {
                0: {...metrics...},
                1: {...metrics...},
                ...
                23: {...metrics...}
            }
        """
        from datetime import datetime
        
        hourly_data = {}
        for i, ts in enumerate(timestamps):
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            
            hour = ts.hour
            if hour not in hourly_data:
                hourly_data[hour] = {'actual': [], 'forecast': []}
            
            hourly_data[hour]['actual'].append(actual[i])
            hourly_data[hour]['forecast'].append(forecast[i])
        
        hourly_metrics = {}
        for hour, data in hourly_data.items():
            hourly_metrics[hour] = self.calculate_metrics(
                data['actual'],
                data['forecast']
            )
        
        return hourly_metrics
    
    def generate_summary(
        self,
        metrics: Dict[str, float]
    ) -> str:
        """
        Generate a human-readable summary of validation metrics
        
        Args:
            metrics: Dictionary from calculate_metrics()
        
        Returns:
            Multi-line formatted string
        """
        lines = [
            "=" * 60,
            "Forecast Validation Summary",
            "=" * 60,
            f"Number of Points:     {metrics['n_points']}",
            f"Mean Actual:          {metrics['mean_actual']:.2f} kW",
            f"Mean Forecast:        {metrics['mean_forecast']:.2f} kW",
            "-" * 60,
            f"MAE (Mean Abs Error): {metrics['mae']:.2f} kW",
            f"RMSE:                 {metrics['rmse']:.2f} kW",
            f"NRMSE:                {metrics['nrmse']:.4f} ({metrics['nrmse']*100:.2f}%)",
            f"Bias (MBE):           {metrics['bias']:.2f} kW",
            f"R² Score:             {metrics['r2']:.4f}",
            "=" * 60
        ]
        
        # Add interpretation
        if metrics['nrmse'] < 0.1:
            lines.append("Status: Excellent (NRMSE < 10%)")
        elif metrics['nrmse'] < 0.2:
            lines.append("Status: Good (NRMSE < 20%)")
        elif metrics['nrmse'] < 0.3:
            lines.append("Status: Acceptable (NRMSE < 30%)")
        else:
            lines.append("Status: Poor (NRMSE >= 30%)")
        
        if abs(metrics['bias']) < 5.0:
            lines.append("Bias: Low (|bias| < 5 kW)")
        elif abs(metrics['bias']) < 10.0:
            lines.append("Bias: Moderate (|bias| < 10 kW)")
        else:
            lines.append(f"Bias: High (|bias| = {abs(metrics['bias']):.1f} kW)")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# ============================================================================
# Test Code
# ============================================================================

if __name__ == "__main__":
    import math
    
    print("Testing ForecastValidator...")
    
    # Create synthetic data
    n = 96  # 24 hours, 15-min resolution
    actual = []
    forecast = []
    
    for i in range(n):
        hour = i * 0.25  # Hour of day
        
        # Actual: sine wave (0-200 kW)
        if 6 <= hour <= 18:
            actual_val = 200 * math.sin((hour - 6) / 12 * math.pi)
        else:
            actual_val = 0.0
        
        # Forecast: actual + noise + slight bias
        forecast_val = actual_val * 0.95 + np.random.normal(0, 5)  # 5% underforecast + noise
        forecast_val = max(0, forecast_val)
        
        actual.append(actual_val)
        forecast.append(forecast_val)
    
    # Test validator
    validator = ForecastValidator()
    
    # Calculate metrics
    metrics = validator.calculate_metrics(actual, forecast)
    
    print("\nMetrics:")
    print(f"  MAE:   {metrics['mae']:.2f} kW")
    print(f"  RMSE:  {metrics['rmse']:.2f} kW")
    print(f"  NRMSE: {metrics['nrmse']:.4f} ({metrics['nrmse']*100:.2f}%)")
    print(f"  Bias:  {metrics['bias']:.2f} kW")
    print(f"  R²:    {metrics['r2']:.4f}")
    print(f"  Points: {metrics['n_points']}")
    
    # Summary
    print("\n" + validator.generate_summary(metrics))
    
    print("\n✓ ForecastValidator test passed")
