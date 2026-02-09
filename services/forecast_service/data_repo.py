"""
Data Repository - Extract and align time series data from telemetry
"""
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy import create_engine, text
import pandas as pd


class DataRepository:
    """
    Repository for extracting time series data from telemetry tables
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize data repository
        
        Args:
            database_url: Database connection string (defaults to env var)
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.engine = create_engine(self.database_url, pool_pre_ping=True)
    
    def get_series(
        self,
        site_id: str,
        metric: str,
        start: datetime,
        end: datetime,
        step_minutes: int = 15
    ) -> List[Dict]:
        """
        Get time series data for a specific metric
        
        Args:
            site_id: Site UUID
            metric: Metric name (e.g., 'pv_power_kw', 'ghi', 'temp_amb')
            start: Start timestamp (timezone-aware)
            end: End timestamp (timezone-aware)
            step_minutes: Time bucket size (minutes)
        
        Returns:
            List of dicts with: timestamp (Unix seconds), value
        """
        query = text("""
            SELECT 
                time_bucket(:step_int, ts) AS bucket,
                AVG(value) AS avg_value
            FROM telemetry
            WHERE site_id = :site_id
              AND metric = :metric
              AND ts >= :start
              AND ts < :end
            GROUP BY bucket
            ORDER BY bucket
        """)
        
        step_interval = f"{step_minutes} minutes"
        
        with self.engine.connect() as conn:
            rows = conn.execute(query, {
                "site_id": site_id,
                "metric": metric,
                "start": start,
                "end": end,
                "step_int": step_interval
            }).fetchall()
        
        series = []
        for row in rows:
            series.append({
                "timestamp": row[0].timestamp(),  # Convert to Unix timestamp
                "value": float(row[1]) if row[1] is not None else 0.0
            })
        
        return series
    
    def get_multivariate_series(
        self,
        site_id: str,
        metrics: List[str],
        start: datetime,
        end: datetime,
        step_minutes: int = 15
    ) -> Dict[str, List[Dict]]:
        """
        Get multiple time series at once
        
        Args:
            site_id: Site UUID
            metrics: List of metric names
            start: Start timestamp
            end: End timestamp
            step_minutes: Time bucket size (minutes)
        
        Returns:
            Dict mapping metric name to list of {timestamp, value} dicts
        """
        result = {}
        for metric in metrics:
            result[metric] = self.get_series(
                site_id, metric, start, end, step_minutes
            )
        
        return result
    
    def align_features(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        resolution_minutes: int = 15,
        required_features: Optional[List[str]] = None
    ) -> Tuple[List[float], pd.DataFrame]:
        """
        Extract and align features for ML model training/prediction
        
        Args:
            site_id: Site UUID
            start: Start timestamp
            end: End timestamp
            resolution_minutes: Time resolution (minutes)
            required_features: List of feature names to extract
                Default: ['ghi', 'temp_amb', 'wind', 'pv_power_kw']
        
        Returns:
            Tuple of (timestamps_unix, feature_dataframe)
            - timestamps_unix: List of Unix timestamps
            - feature_dataframe: pandas DataFrame with columns for each feature
        """
        if required_features is None:
            required_features = ['ghi', 'temp_amb', 'wind', 'pv_power_kw']
        
        # Create complete time grid
        time_grid = []
        current = start
        while current < end:
            time_grid.append(current)
            current += timedelta(minutes=resolution_minutes)
        
        # Fetch all metrics
        data = self.get_multivariate_series(
            site_id=site_id,
            metrics=required_features,
            start=start,
            end=end,
            step_minutes=resolution_minutes
        )
        
        # Convert to DataFrame for easier alignment
        df_list = []
        for metric_name, series in data.items():
            if len(series) > 0:
                df_metric = pd.DataFrame(series)
                df_metric['timestamp_dt'] = pd.to_datetime(df_metric['timestamp'], unit='s', utc=True)
                df_metric = df_metric.rename(columns={'value': metric_name})
                df_metric = df_metric[['timestamp_dt', metric_name]]
                df_list.append(df_metric)
        
        # Merge all metrics on timestamp
        if len(df_list) > 0:
            df = df_list[0]
            for df_metric in df_list[1:]:
                df = df.merge(df_metric, on='timestamp_dt', how='outer')
        else:
            # No data available - create empty DataFrame
            df = pd.DataFrame({'timestamp_dt': pd.to_datetime(time_grid)})
        
        # Align to complete time grid
        df_grid = pd.DataFrame({'timestamp_dt': pd.to_datetime(time_grid)})
        df = df_grid.merge(df, on='timestamp_dt', how='left')
        
        # Forward fill missing values (simple imputation)
        for feature in required_features:
            if feature in df.columns:
                df[feature] = df[feature].fillna(method='ffill').fillna(0.0)
            else:
                df[feature] = 0.0
        
        # Extract timestamps as Unix seconds
        timestamps_unix = [dt.timestamp() for dt in time_grid]
        
        # Return timestamps and feature DataFrame
        features_df = df[required_features]
        
        return timestamps_unix, features_df
    
    def get_site_capacity(self, site_id: str) -> float:
        """
        Get site PV capacity from sites table
        
        Args:
            site_id: Site UUID
        
        Returns:
            Capacity in kW (default 500.0 if not found)
        """
        query = text("""
            SELECT capacity_kw
            FROM sites
            WHERE id = :site_id
        """)
        
        with self.engine.connect() as conn:
            row = conn.execute(query, {"site_id": site_id}).fetchone()
        
        if row and row[0]:
            return float(row[0])
        else:
            return 500.0  # Default capacity
    
    def get_site_location(self, site_id: str) -> Tuple[float, float]:
        """
        Get site latitude and longitude
        
        Args:
            site_id: Site UUID
        
        Returns:
            Tuple of (latitude, longitude) in degrees
        """
        query = text("""
            SELECT lat, lon
            FROM sites
            WHERE id = :site_id
        """)
        
        with self.engine.connect() as conn:
            row = conn.execute(query, {"site_id": site_id}).fetchone()
        
        if row and row[0] and row[1]:
            return float(row[0]), float(row[1])
        else:
            return 5.4164, 100.3327  # Default: Penang, Malaysia
    
    def check_data_availability(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        required_metrics: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """
        Check data availability and quality for each metric
        
        Args:
            site_id: Site UUID
            start: Start timestamp
            end: End timestamp
            required_metrics: List of metric names to check
        
        Returns:
            Dict mapping metric to stats: {count, coverage_pct, has_gaps}
        """
        if required_metrics is None:
            required_metrics = ['ghi', 'temp_amb', 'wind', 'pv_power_kw']
        
        total_expected_points = int((end - start).total_seconds() / (15 * 60))
        
        result = {}
        for metric in required_metrics:
            query = text("""
                SELECT COUNT(*) as cnt
                FROM (
                    SELECT time_bucket('15 minutes', ts) AS bucket
                    FROM telemetry
                    WHERE site_id = :site_id
                      AND metric = :metric
                      AND ts >= :start
                      AND ts < :end
                    GROUP BY bucket
                ) AS buckets
            """)
            
            with self.engine.connect() as conn:
                row = conn.execute(query, {
                    "site_id": site_id,
                    "metric": metric,
                    "start": start,
                    "end": end
                }).fetchone()
            
            count = row[0] if row else 0
            coverage_pct = (count / total_expected_points * 100) if total_expected_points > 0 else 0
            has_gaps = count < total_expected_points
            
            result[metric] = {
                "count": count,
                "expected": total_expected_points,
                "coverage_pct": coverage_pct,
                "has_gaps": has_gaps
            }
        
        return result


if __name__ == "__main__":
    # Test data repository
    import os
    from datetime import datetime, timezone, timedelta
    
    # Use demo site
    site_id = "11111111-1111-1111-1111-111111111111"
    
    # Test time range: yesterday
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    
    repo = DataRepository()
    
    print("Data Repository Test")
    print("=" * 60)
    
    # Test 1: Get single series
    print("\n1. Get single series (pv_power_kw):")
    series = repo.get_series(site_id, "pv_power_kw", start, end, step_minutes=60)
    print(f"Retrieved {len(series)} data points")
    if len(series) > 0:
        print(f"First point: {series[0]}")
        print(f"Last point: {series[-1]}")
    
    # Test 2: Get multivariate series
    print("\n2. Get multivariate series:")
    metrics = ['ghi', 'temp_amb', 'pv_power_kw']
    multi_data = repo.get_multivariate_series(site_id, metrics, start, end, step_minutes=60)
    for metric, data in multi_data.items():
        print(f"{metric:15s}: {len(data)} points")
    
    # Test 3: Align features
    print("\n3. Align features for ML:")
    timestamps, features_df = repo.align_features(site_id, start, end, resolution_minutes=15)
    print(f"Timestamps: {len(timestamps)}")
    print(f"Features shape: {features_df.shape}")
    print(f"Columns: {list(features_df.columns)}")
    print("\nFirst 5 rows:")
    print(features_df.head())
    
    # Test 4: Check data availability
    print("\n4. Check data availability:")
    availability = repo.check_data_availability(site_id, start, end)
    for metric, stats in availability.items():
        print(f"{metric:15s}: {stats['count']:4d}/{stats['expected']:4d} points ({stats['coverage_pct']:.1f}% coverage)")
    
    # Test 5: Get site info
    print("\n5. Site information:")
    capacity = repo.get_site_capacity(site_id)
    lat, lon = repo.get_site_location(site_id)
    print(f"Capacity: {capacity} kW")
    print(f"Location: {lat:.4f}°N, {lon:.4f}°E")
