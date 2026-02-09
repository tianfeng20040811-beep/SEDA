"""
Model Calibrator - Automatic parameter adjustment based on bias
"""

import numpy as np
from typing import Dict, Optional
from datetime import datetime


class ModelCalibrator:
    """
    Automatically calibrate baseline physics model parameters
    
    Strategy:
    - Measure forecast bias (mean error)
    - Adjust PR (Performance Ratio) or soiling to compensate
    - Simple linear adjustment: PR_new = PR_old - k * bias
    - Clamp PR to realistic range [0.70, 0.95]
    
    This is a minimal viable calibration that can provide
    immediate improvements to forecast accuracy.
    """
    
    def __init__(
        self,
        k_pr: float = 0.001,  # Sensitivity: ΔPR per kW bias
        k_soiling: float = 0.002,  # Sensitivity: Δsoiling per kW bias
        pr_min: float = 0.70,
        pr_max: float = 0.95,
        soiling_min: float = 0.90,
        soiling_max: float = 1.00
    ):
        """
        Args:
            k_pr: Adjustment sensitivity for PR (ΔPR per kW bias)
            k_soiling: Adjustment sensitivity for soiling factor
            pr_min: Minimum allowed PR
            pr_max: Maximum allowed PR
            soiling_min: Minimum allowed soiling factor
            soiling_max: Maximum allowed soiling factor (1.0 = clean)
        """
        self.k_pr = k_pr
        self.k_soiling = k_soiling
        self.pr_min = pr_min
        self.pr_max = pr_max
        self.soiling_min = soiling_min
        self.soiling_max = soiling_max
    
    def calibrate_pr(
        self,
        current_pr: float,
        bias: float,
        capacity_kw: float = 200.0
    ) -> Dict[str, float]:
        """
        Calibrate PR based on forecast bias
        
        Logic:
        - If bias > 0: forecast overestimates → reduce PR
        - If bias < 0: forecast underestimates → increase PR
        
        Args:
            current_pr: Current Performance Ratio (0.70-0.95)
            bias: Forecast bias in kW (forecast - actual)
            capacity_kw: System capacity (for normalization)
        
        Returns:
            {
                'pr_old': float,
                'pr_new': float,
                'pr_delta': float,
                'bias': float,
                'bias_pct': float,  # Bias as % of capacity
                'method': str
            }
        """
        # Normalize bias by capacity
        bias_pct = bias / capacity_kw if capacity_kw > 0 else 0.0
        
        # Calculate adjustment (negative bias → increase PR)
        pr_delta = -self.k_pr * bias
        pr_new = current_pr + pr_delta
        
        # Clamp to valid range
        pr_new = np.clip(pr_new, self.pr_min, self.pr_max)
        pr_delta = pr_new - current_pr
        
        return {
            'pr_old': current_pr,
            'pr_new': pr_new,
            'pr_delta': pr_delta,
            'bias': bias,
            'bias_pct': bias_pct,
            'method': 'linear_bias_adjustment'
        }
    
    def calibrate_soiling(
        self,
        current_soiling: float,
        bias: float,
        capacity_kw: float = 200.0
    ) -> Dict[str, float]:
        """
        Calibrate soiling factor based on forecast bias
        
        Logic:
        - If bias > 0: forecast overestimates → assume more soiling
        - If bias < 0: forecast underestimates → assume cleaner panels
        
        Args:
            current_soiling: Current soiling factor (0.90-1.00)
            bias: Forecast bias in kW
            capacity_kw: System capacity
        
        Returns:
            {
                'soiling_old': float,
                'soiling_new': float,
                'soiling_delta': float,
                'bias': float,
                'method': str
            }
        """
        # Calculate adjustment
        soiling_delta = -self.k_soiling * bias
        soiling_new = current_soiling + soiling_delta
        
        # Clamp to valid range
        soiling_new = np.clip(soiling_new, self.soiling_min, self.soiling_max)
        soiling_delta = soiling_new - current_soiling
        
        return {
            'soiling_old': current_soiling,
            'soiling_new': soiling_new,
            'soiling_delta': soiling_delta,
            'bias': bias,
            'method': 'linear_bias_adjustment'
        }
    
    def calibrate_both(
        self,
        current_pr: float,
        current_soiling: float,
        bias: float,
        capacity_kw: float = 200.0,
        prefer_pr: bool = True
    ) -> Dict[str, any]:
        """
        Calibrate both PR and soiling
        
        Args:
            current_pr: Current PR
            current_soiling: Current soiling factor
            bias: Forecast bias
            capacity_kw: System capacity
            prefer_pr: If True, put more weight on PR adjustment
        
        Returns:
            Combined calibration results
        """
        pr_result = self.calibrate_pr(current_pr, bias, capacity_kw)
        soiling_result = self.calibrate_soiling(current_soiling, bias, capacity_kw)
        
        if prefer_pr:
            # Use PR calibration primarily
            return {
                'parameter': 'pr',
                'pr_old': pr_result['pr_old'],
                'pr_new': pr_result['pr_new'],
                'pr_delta': pr_result['pr_delta'],
                'soiling_old': current_soiling,
                'soiling_new': current_soiling,
                'soiling_delta': 0.0,
                'bias': bias,
                'method': 'pr_primary'
            }
        else:
            # Use soiling calibration primarily
            return {
                'parameter': 'soiling',
                'pr_old': current_pr,
                'pr_new': current_pr,
                'pr_delta': 0.0,
                'soiling_old': soiling_result['soiling_old'],
                'soiling_new': soiling_result['soiling_new'],
                'soiling_delta': soiling_result['soiling_delta'],
                'bias': bias,
                'method': 'soiling_primary'
            }
    
    def auto_calibrate(
        self,
        bias: float,
        current_params: Optional[Dict] = None,
        capacity_kw: float = 200.0
    ) -> Dict[str, any]:
        """
        Auto-calibrate using default or provided parameters
        
        Args:
            bias: Forecast bias in kW
            current_params: Current parameters {pr, soiling}
            capacity_kw: System capacity
        
        Returns:
            Calibration result with new parameters
        """
        if current_params is None:
            current_params = {
                'pr': 0.85,
                'soiling': 0.98
            }
        
        current_pr = current_params.get('pr', 0.85)
        current_soiling = current_params.get('soiling', 0.98)
        
        # Decide which parameter to adjust based on bias magnitude
        bias_pct = abs(bias) / capacity_kw if capacity_kw > 0 else 0.0
        
        if bias_pct > 0.10:
            # Large bias: adjust PR (more impactful)
            result = self.calibrate_pr(current_pr, bias, capacity_kw)
            result['parameter'] = 'pr'
            result['soiling_new'] = current_soiling
        else:
            # Small bias: adjust soiling (finer tuning)
            result = self.calibrate_soiling(current_soiling, bias, capacity_kw)
            result['parameter'] = 'soiling'
            result['pr_new'] = current_pr
        
        return result
    
    def generate_report(
        self,
        calibration_result: Dict[str, any]
    ) -> str:
        """
        Generate human-readable calibration report
        
        Args:
            calibration_result: Output from calibrate_*()
        
        Returns:
            Formatted string
        """
        lines = [
            "=" * 60,
            "Model Calibration Report",
            "=" * 60,
            f"Method: {calibration_result.get('method', 'unknown')}",
            f"Bias: {calibration_result['bias']:.2f} kW",
            "-" * 60
        ]
        
        # PR adjustment
        if 'pr_new' in calibration_result:
            pr_old = calibration_result.get('pr_old', 0)
            pr_new = calibration_result.get('pr_new', 0)
            pr_delta = calibration_result.get('pr_delta', 0)
            
            lines.append(f"Performance Ratio (PR):")
            lines.append(f"  Old: {pr_old:.4f}")
            lines.append(f"  New: {pr_new:.4f}")
            lines.append(f"  Δ:   {pr_delta:+.4f} ({pr_delta/pr_old*100:+.2f}%)" if pr_old > 0 else f"  Δ:   {pr_delta:+.4f}")
        
        # Soiling adjustment
        if 'soiling_new' in calibration_result:
            soil_old = calibration_result.get('soiling_old', 0)
            soil_new = calibration_result.get('soiling_new', 0)
            soil_delta = calibration_result.get('soiling_delta', 0)
            
            lines.append(f"Soiling Factor:")
            lines.append(f"  Old: {soil_old:.4f}")
            lines.append(f"  New: {soil_new:.4f}")
            lines.append(f"  Δ:   {soil_delta:+.4f} ({soil_delta/soil_old*100:+.2f}%)" if soil_old > 0 else f"  Δ:   {soil_delta:+.4f}")
        
        lines.append("=" * 60)
        
        # Add recommendation
        if abs(calibration_result['bias']) < 5.0:
            lines.append("✓ Bias is low, minor adjustment applied")
        elif abs(calibration_result['bias']) < 10.0:
            lines.append("⚠ Moderate bias, adjustment recommended")
        else:
            lines.append("⚠ High bias, recalibration strongly recommended")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# ============================================================================
# Test Code
# ============================================================================

if __name__ == "__main__":
    print("Testing ModelCalibrator...")
    
    calibrator = ModelCalibrator(
        k_pr=0.001,
        k_soiling=0.002,
        pr_min=0.70,
        pr_max=0.95
    )
    
    # Test 1: Positive bias (overforecast) → reduce PR
    print("\n" + "=" * 60)
    print("Test 1: Positive bias (+10 kW overforecast)")
    
    result1 = calibrator.calibrate_pr(
        current_pr=0.85,
        bias=10.0,
        capacity_kw=200.0
    )
    
    print(f"  PR Old: {result1['pr_old']:.4f}")
    print(f"  PR New: {result1['pr_new']:.4f}")
    print(f"  Delta:  {result1['pr_delta']:+.4f}")
    print(f"  Bias:   {result1['bias']:.2f} kW ({result1['bias_pct']*100:.2f}% of capacity)")
    
    # Test 2: Negative bias (underforecast) → increase PR
    print("\n" + "=" * 60)
    print("Test 2: Negative bias (-15 kW underforecast)")
    
    result2 = calibrator.calibrate_pr(
        current_pr=0.80,
        bias=-15.0,
        capacity_kw=200.0
    )
    
    print(f"  PR Old: {result2['pr_old']:.4f}")
    print(f"  PR New: {result2['pr_new']:.4f}")
    print(f"  Delta:  {result2['pr_delta']:+.4f}")
    print(f"  Bias:   {result2['bias']:.2f} kW")
    
    # Test 3: Soiling calibration
    print("\n" + "=" * 60)
    print("Test 3: Soiling calibration (bias +8 kW)")
    
    result3 = calibrator.calibrate_soiling(
        current_soiling=0.98,
        bias=8.0,
        capacity_kw=200.0
    )
    
    print(f"  Soiling Old: {result3['soiling_old']:.4f}")
    print(f"  Soiling New: {result3['soiling_new']:.4f}")
    print(f"  Delta:       {result3['soiling_delta']:+.4f}")
    
    # Test 4: Auto calibration
    print("\n" + "=" * 60)
    print("Test 4: Auto calibration (large bias -25 kW)")
    
    result4 = calibrator.auto_calibrate(
        bias=-25.0,
        current_params={'pr': 0.82, 'soiling': 0.96},
        capacity_kw=200.0
    )
    
    print(f"  Parameter adjusted: {result4['parameter']}")
    print(f"  PR:      {result4.get('pr_old', 0):.4f} → {result4.get('pr_new', 0):.4f}")
    print(f"  Soiling: {result4.get('soiling_old', 0):.4f} → {result4.get('soiling_new', 0):.4f}")
    
    # Test 5: Generate report
    print("\n" + calibrator.generate_report(result4))
    
    # Test 6: Clamping
    print("\n" + "=" * 60)
    print("Test 6: PR clamping (extreme bias -100 kW)")
    
    result6 = calibrator.calibrate_pr(
        current_pr=0.85,
        bias=-100.0,  # Extreme underforecast
        capacity_kw=200.0
    )
    
    print(f"  PR Old: {result6['pr_old']:.4f}")
    print(f"  PR New: {result6['pr_new']:.4f} (clamped to max)")
    print(f"  Delta:  {result6['pr_delta']:+.4f}")
    
    print("\n✓ ModelCalibrator test passed")
