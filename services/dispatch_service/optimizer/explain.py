"""
Explainable AI for dispatch decisions
Generate human-readable reasons for each timestep decision
"""
from typing import Dict, List, Optional
import numpy as np


class DispatchExplainer:
    """
    Generate explanations for dispatch decisions
    Provides human-readable reasons for optimization choices
    """
    
    def __init__(self):
        """Initialize explainer"""
        pass
    
    def explain_schedule(
        self,
        solution: Dict,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        tariff_buy: List[float],
        bess_params: Dict,
        limits: Dict,
        binding_constraints: Optional[List[Dict]] = None
    ) -> List[str]:
        """
        Generate explanation for each timestep
        
        Args:
            solution: Dispatch solution dict
            pv_forecast_kw: PV forecast array
            load_kw: Load forecast array
            tariff_buy: Buy tariff array
            bess_params: Battery parameters
            limits: Grid/transformer limits
            binding_constraints: Optional binding constraints from MILP
        
        Returns:
            List of reason strings, one per timestep
        """
        N = len(solution['soc'])
        reasons = []
        
        # Identify tariff periods
        tariff_median = np.median(tariff_buy)
        tariff_threshold_peak = tariff_median * 1.2  # Peak if 20% above median
        tariff_threshold_low = tariff_median * 0.8   # Low if 20% below median
        
        soc_min = bess_params.get('soc_min', 0.2)
        soc_max = bess_params.get('soc_max', 0.9)
        
        for t in range(N):
            reason_parts = []
            
            # Identify primary action
            pv_set = solution['pv_set_kw'][t]
            batt_ch = solution['batt_ch_kw'][t]
            batt_dis = solution['batt_dis_kw'][t]
            grid_imp = solution['grid_imp_kw'][t]
            grid_exp = solution['grid_exp_kw'][t]
            curtail = solution['curtail_kw'][t]
            soc = solution['soc'][t]
            
            pv_available = pv_forecast_kw[t]
            load_demand = load_kw[t]
            tariff = tariff_buy[t]
            
            # Determine primary action and reason
            
            # 1. Check for battery discharge
            if batt_dis > 1.0:  # Threshold: 1 kW
                if tariff >= tariff_threshold_peak:
                    reason_parts.append("Discharge battery during peak tariff hours")
                elif grid_imp > limits.get('grid_import_max_kw', 200) * 0.8:
                    reason_parts.append("Discharge battery to reduce grid import near limit")
                else:
                    reason_parts.append("Discharge battery to meet demand")
            
            # 2. Check for battery charge
            if batt_ch > 1.0:
                if curtail > 1.0:
                    reason_parts.append("Charge battery using curtailed PV")
                elif tariff <= tariff_threshold_low:
                    reason_parts.append("Charge battery during low tariff period")
                elif pv_available > load_demand:
                    reason_parts.append("Charge battery with excess PV")
                else:
                    reason_parts.append("Charge battery from grid")
            
            # 3. Check for curtailment
            if curtail > 1.0:
                if soc >= soc_max - 0.05:
                    reason_parts.append("PV curtailed (battery full)")
                elif grid_exp >= limits.get('grid_export_max_kw', 200) * 0.9:
                    reason_parts.append("PV curtailed (grid export limit)")
                else:
                    reason_parts.append("PV curtailed (economic decision)")
            
            # 4. Check for grid export
            if grid_exp > 1.0:
                reason_parts.append("Export excess PV to grid")
            
            # 5. Check for grid import
            if grid_imp > 1.0:
                if pv_available < 1.0 and batt_dis < 1.0:
                    reason_parts.append("Grid import to meet demand (no PV/battery)")
                elif load_demand > pv_available + batt_dis:
                    reason_parts.append("Grid import to meet remaining demand")
                else:
                    reason_parts.append("Grid import for battery charging")
            
            # 6. Check for SOC constraints
            if soc <= soc_min + 0.05:
                reason_parts.append("SOC protected at minimum threshold")
            elif soc >= soc_max - 0.05:
                reason_parts.append("SOC at maximum limit")
            
            # 7. Add binding constraint info if available
            if binding_constraints and t < len(binding_constraints):
                constraints = binding_constraints[t]['constraints']
                if constraints:
                    constraint_names = {
                        'soc_min': 'min SOC',
                        'soc_max': 'max SOC',
                        'p_charge_max': 'max charge power',
                        'p_discharge_max': 'max discharge power',
                        'grid_import_max': 'grid import limit',
                        'grid_export_max': 'grid export limit',
                        'transformer_max': 'transformer limit'
                    }
                    binding_str = ', '.join([constraint_names.get(c, c) for c in constraints])
                    reason_parts.append(f"Constraint: {binding_str}")
            
            # Combine reason parts
            if reason_parts:
                reason = "; ".join(reason_parts)
            else:
                # Default reason if nothing specific identified
                if pv_available > 0.5:
                    reason = "PV generation meets demand"
                else:
                    reason = "Normal operation"
            
            reasons.append(reason)
        
        return reasons
    
    def generate_detailed_explanation(
        self,
        t: int,
        solution: Dict,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        tariff_buy: List[float],
        tariff_sell: List[float],
        bess_params: Dict
    ) -> Dict:
        """
        Generate detailed explanation for a specific timestep
        
        Args:
            t: Timestep index
            solution: Dispatch solution
            pv_forecast_kw: PV forecast array
            load_kw: Load forecast array
            tariff_buy: Buy tariff array
            tariff_sell: Sell tariff array
            bess_params: Battery parameters
        
        Returns:
            Dict with detailed explanation
        """
        explanation = {
            'timestep': t,
            'state': {
                'pv_available_kw': pv_forecast_kw[t],
                'load_demand_kw': load_kw[t],
                'tariff_buy': tariff_buy[t],
                'tariff_sell': tariff_sell[t],
                'soc_before': solution['soc'][t-1] if t > 0 else bess_params.get('soc0', 0.5),
                'soc_after': solution['soc'][t]
            },
            'actions': {
                'pv_set_kw': solution['pv_set_kw'][t],
                'batt_ch_kw': solution['batt_ch_kw'][t],
                'batt_dis_kw': solution['batt_dis_kw'][t],
                'grid_imp_kw': solution['grid_imp_kw'][t],
                'grid_exp_kw': solution['grid_exp_kw'][t],
                'curtail_kw': solution['curtail_kw'][t]
            },
            'power_balance': {
                'supply': solution['pv_set_kw'][t] + solution['batt_dis_kw'][t] + solution['grid_imp_kw'][t],
                'demand': load_kw[t] + solution['batt_ch_kw'][t] + solution['grid_exp_kw'][t]
            }
        }
        
        # Calculate energy cost for this timestep
        dt_hours = 0.25  # Assuming 15-min resolution
        cost = (tariff_buy[t] * solution['grid_imp_kw'][t] - 
                tariff_sell[t] * solution['grid_exp_kw'][t]) * dt_hours
        
        explanation['cost'] = {
            'import_cost': tariff_buy[t] * solution['grid_imp_kw'][t] * dt_hours,
            'export_revenue': tariff_sell[t] * solution['grid_exp_kw'][t] * dt_hours,
            'net_cost': cost
        }
        
        return explanation
    
    def compare_scenarios(
        self,
        optimized_solution: Dict,
        baseline_solution: Dict,
        tariff_buy: List[float],
        tariff_sell: List[float],
        resolution_minutes: int = 15
    ) -> Dict:
        """
        Compare optimized vs baseline scenarios
        
        Args:
            optimized_solution: Optimized dispatch solution
            baseline_solution: Baseline solution (e.g., no battery)
            tariff_buy: Buy tariff array
            tariff_sell: Sell tariff array
            resolution_minutes: Time resolution
        
        Returns:
            Dict with comparison metrics
        """
        N = len(optimized_solution['soc'])
        dt_hours = resolution_minutes / 60.0
        
        # Calculate costs
        opt_cost = sum(
            (tariff_buy[t] * optimized_solution['grid_imp_kw'][t] -
             tariff_sell[t] * optimized_solution['grid_exp_kw'][t]) * dt_hours
            for t in range(N)
        )
        
        base_cost = sum(
            (tariff_buy[t] * baseline_solution['grid_imp_kw'][t] -
             tariff_sell[t] * baseline_solution['grid_exp_kw'][t]) * dt_hours
            for t in range(N)
        )
        
        savings = base_cost - opt_cost
        savings_pct = (savings / base_cost * 100) if base_cost > 0 else 0.0
        
        # Peak reduction
        opt_peak = max(optimized_solution['grid_imp_kw'])
        base_peak = max(baseline_solution['grid_imp_kw'])
        peak_reduction = base_peak - opt_peak
        
        # Energy arbitrage (battery cycling value)
        total_discharge = sum(optimized_solution['batt_dis_kw']) * dt_hours
        
        comparison = {
            'optimized_cost': round(opt_cost, 2),
            'baseline_cost': round(base_cost, 2),
            'savings': round(savings, 2),
            'savings_pct': round(savings_pct, 2),
            'optimized_peak_kw': round(opt_peak, 2),
            'baseline_peak_kw': round(base_peak, 2),
            'peak_reduction_kw': round(peak_reduction, 2),
            'battery_discharge_kwh': round(total_discharge, 2)
        }
        
        return comparison


if __name__ == "__main__":
    # Test explainer
    print("=" * 60)
    print("Dispatch Explainer Test")
    print("=" * 60)
    
    # Create sample solution
    N = 24
    
    solution = {
        'pv_set_kw': [80.0] * 12 + [0.0] * 12,
        'batt_ch_kw': [20.0] * 6 + [0.0] * 18,
        'batt_dis_kw': [0.0] * 18 + [40.0] * 6,
        'grid_imp_kw': [30.0] * 12 + [50.0] * 6 + [70.0] * 6,
        'grid_exp_kw': [0.0] * N,
        'curtail_kw': [10.0] * 6 + [0.0] * 18,
        'soc': [0.5 + i * 0.01 for i in range(N)]
    }
    
    pv_forecast = [100.0] * 12 + [0.0] * 12
    load = [100.0] * N
    tariff_buy = [0.30] * 18 + [0.50] * 6  # Peak hours at end
    tariff_sell = [0.20] * N
    
    bess_params = {
        'capacity_kwh': 100.0,
        'soc_min': 0.2,
        'soc_max': 0.9,
        'soc0': 0.5
    }
    
    limits = {
        'grid_import_max_kw': 200.0,
        'grid_export_max_kw': 200.0
    }
    
    # Create explainer
    explainer = DispatchExplainer()
    
    # Generate explanations
    reasons = explainer.explain_schedule(
        solution, pv_forecast, load, tariff_buy, bess_params, limits
    )
    
    print("\nExplanations for each timestep:")
    print("=" * 60)
    for t in range(min(8, N)):  # Show first 8
        print(f"t={t:2d} | {reasons[t]}")
    
    # Detailed explanation for one timestep
    print("\n" + "=" * 60)
    print("Detailed Explanation for t=20 (peak period)")
    print("=" * 60)
    
    detailed = explainer.generate_detailed_explanation(
        20, solution, pv_forecast, load, tariff_buy, tariff_sell, bess_params
    )
    
    import json
    print(json.dumps(detailed, indent=2))
