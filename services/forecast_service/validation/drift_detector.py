"""
Drift Detector - Monitor model health over time
"""

import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta


class DriftDetector:
    """
    Detect forecast model drift using rolling window statistics
    
    Strategy:
    - Calculate NRMSE for recent validation runs
    - Compare to baseline (mean of past N days)
    - Flag drift if NRMSE increases significantly
    
    Status Thresholds:
    - GREEN: drift_score < 0.15 (NRMSE increase < 15%)
    - AMBER: 0.15 <= drift_score < 0.30 (NRMSE increase 15-30%)
    - RED: drift_score >= 0.30 (NRMSE increase >= 30%)
    """
    
    def __init__(
        self,
        baseline_days: int = 30,
        recent_days: int = 7,
        green_threshold: float = 0.15,
        amber_threshold: float = 0.30
    ):
        """
        Args:
            baseline_days: Days to calculate baseline NRMSE mean
            recent_days: Days to calculate recent NRMSE mean
            green_threshold: Threshold for green status (< 15% increase)
            amber_threshold: Threshold for amber status (< 30% increase)
        """
        self.baseline_days = baseline_days
        self.recent_days = recent_days
        self.green_threshold = green_threshold
        self.amber_threshold = amber_threshold
    
    def calculate_drift(
        self,
        historical_nrmse: List[Tuple[datetime, float]],
        current_time: datetime = None
    ) -> Dict[str, any]:
        """
        Calculate drift score and status
        
        Args:
            historical_nrmse: List of (timestamp, nrmse) tuples
            current_time: Current timestamp (defaults to now)
        
        Returns:
            {
                'drift_score': float,  # Relative increase in NRMSE
                'status': str,  # 'green', 'amber', or 'red'
                'baseline_nrmse': float,  # Mean NRMSE of baseline period
                'recent_nrmse': float,  # Mean NRMSE of recent period
                'baseline_count': int,  # Number of baseline points
                'recent_count': int,  # Number of recent points
                'message': str  # Human-readable status message
            }
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Split data into baseline and recent periods
        baseline_cutoff = current_time - timedelta(days=self.baseline_days)
        recent_cutoff = current_time - timedelta(days=self.recent_days)
        
        baseline_values = []
        recent_values = []
        
        for ts, nrmse in historical_nrmse:
            if baseline_cutoff <= ts < recent_cutoff:
                baseline_values.append(nrmse)
            elif ts >= recent_cutoff:
                recent_values.append(nrmse)
        
        # Calculate means
        baseline_nrmse = float(np.mean(baseline_values)) if baseline_values else 0.0
        recent_nrmse = float(np.mean(recent_values)) if recent_values else 0.0
        
        # Calculate drift score
        if baseline_nrmse > 0:
            drift_score = (recent_nrmse - baseline_nrmse) / baseline_nrmse
        else:
            drift_score = 0.0
        
        # Determine status
        if drift_score < self.green_threshold:
            status = 'green'
            message = f"Model healthy (drift {drift_score*100:.1f}%)"
        elif drift_score < self.amber_threshold:
            status = 'amber'
            message = f"Model degrading (drift {drift_score*100:.1f}%), consider recalibration"
        else:
            status = 'red'
            message = f"Model drifted (drift {drift_score*100:.1f}%), recalibration recommended"
        
        return {
            'drift_score': drift_score,
            'status': status,
            'baseline_nrmse': baseline_nrmse,
            'recent_nrmse': recent_nrmse,
            'baseline_count': len(baseline_values),
            'recent_count': len(recent_values),
            'message': message
        }
    
    def detect_drift_from_db(
        self,
        conn,
        site_id: str,
        current_time: datetime = None
    ) -> Dict[str, any]:
        """
        Detect drift by querying validation_runs table
        
        Args:
            conn: Database connection
            site_id: Site identifier
            current_time: Current timestamp
        
        Returns:
            Same as calculate_drift()
        """
        from sqlalchemy import text
        
        if current_time is None:
            current_time = datetime.now()
        
        # Query validation runs from past baseline_days
        query = text("""
            SELECT created_at, nrmse
            FROM validation_runs
            WHERE site_id = :sid
              AND created_at >= :cutoff
              AND nrmse IS NOT NULL
            ORDER BY created_at ASC
        """)
        
        cutoff = current_time - timedelta(days=self.baseline_days)
        rows = conn.execute(query, {
            "sid": site_id,
            "cutoff": cutoff
        }).fetchall()
        
        historical_nrmse = [(row[0], float(row[1])) for row in rows]
        
        return self.calculate_drift(historical_nrmse, current_time)
    
    def generate_report(
        self,
        drift_result: Dict[str, any]
    ) -> str:
        """
        Generate human-readable drift report
        
        Args:
            drift_result: Output from calculate_drift()
        
        Returns:
            Formatted string
        """
        lines = [
            "=" * 60,
            "Model Health Report",
            "=" * 60,
            f"Status: {drift_result['status'].upper()}",
            f"Drift Score: {drift_result['drift_score']:.4f} ({drift_result['drift_score']*100:.2f}%)",
            "-" * 60,
            f"Baseline NRMSE: {drift_result['baseline_nrmse']:.4f} (n={drift_result['baseline_count']})",
            f"Recent NRMSE:   {drift_result['recent_nrmse']:.4f} (n={drift_result['recent_count']})",
            "-" * 60,
            f"Message: {drift_result['message']}",
            "=" * 60
        ]
        
        # Add emoji indicators
        if drift_result['status'] == 'green':
            lines.insert(3, "🟢 Model is performing well")
        elif drift_result['status'] == 'amber':
            lines.insert(3, "🟡 Model performance declining")
        else:
            lines.insert(3, "🔴 Model requires attention")
        
        return "\n".join(lines)


# ============================================================================
# Test Code
# ============================================================================

if __name__ == "__main__":
    print("Testing DriftDetector...")
    
    # Create synthetic historical data
    current_time = datetime(2024, 3, 15, 12, 0, 0)
    
    historical_nrmse = []
    
    # Past 30 days: baseline NRMSE around 0.15
    for i in range(30, 7, -1):
        ts = current_time - timedelta(days=i)
        nrmse = 0.15 + np.random.normal(0, 0.02)
        historical_nrmse.append((ts, nrmse))
    
    # Recent 7 days: NRMSE drifting to 0.20 (33% increase)
    for i in range(7, 0, -1):
        ts = current_time - timedelta(days=i)
        nrmse = 0.20 + np.random.normal(0, 0.02)
        historical_nrmse.append((ts, nrmse))
    
    # Test detector
    detector = DriftDetector(
        baseline_days=30,
        recent_days=7,
        green_threshold=0.15,
        amber_threshold=0.30
    )
    
    drift_result = detector.calculate_drift(historical_nrmse, current_time)
    
    print("\nDrift Detection Result:")
    print(f"  Status:         {drift_result['status']}")
    print(f"  Drift Score:    {drift_result['drift_score']:.4f} ({drift_result['drift_score']*100:.2f}%)")
    print(f"  Baseline NRMSE: {drift_result['baseline_nrmse']:.4f}")
    print(f"  Recent NRMSE:   {drift_result['recent_nrmse']:.4f}")
    print(f"  Baseline Count: {drift_result['baseline_count']}")
    print(f"  Recent Count:   {drift_result['recent_count']}")
    print(f"  Message:        {drift_result['message']}")
    
    # Report
    print("\n" + detector.generate_report(drift_result))
    
    # Test green status
    print("\n" + "=" * 60)
    print("Testing GREEN status (no drift)...")
    
    green_data = []
    for i in range(30, 0, -1):
        ts = current_time - timedelta(days=i)
        nrmse = 0.15 + np.random.normal(0, 0.01)  # Stable NRMSE
        green_data.append((ts, nrmse))
    
    green_result = detector.calculate_drift(green_data, current_time)
    print(f"Status: {green_result['status']} (drift {green_result['drift_score']*100:.2f}%)")
    
    # Test red status
    print("\n" + "=" * 60)
    print("Testing RED status (severe drift)...")
    
    red_data = []
    for i in range(30, 7, -1):
        ts = current_time - timedelta(days=i)
        nrmse = 0.15 + np.random.normal(0, 0.01)
        red_data.append((ts, nrmse))
    
    for i in range(7, 0, -1):
        ts = current_time - timedelta(days=i)
        nrmse = 0.25 + np.random.normal(0, 0.01)  # 67% increase
        red_data.append((ts, nrmse))
    
    red_result = detector.calculate_drift(red_data, current_time)
    print(f"Status: {red_result['status']} (drift {red_result['drift_score']*100:.2f}%)")
    
    print("\n✓ DriftDetector test passed")
