"""
Fallback rule-based dispatch scheduler
Used when MILP solver fails or times out
Provides a guaranteed feasible (though suboptimal) solution
"""
from typing import Dict, List
import numpy as np


class FallbackScheduler:
    """
    Simple rule-based scheduler as fallback when MILP fails
    Uses greedy heuristics to create a feasible dispatch schedule
    """
    
    def __init__(self):
        """Initialize fallback scheduler"""
        pass
    
    def schedule(
        self,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        tariff_buy: List[float],
        tariff_sell: List[float],
        bess_params: Dict,
        limits: Dict,
        resolution_minutes: int = 15
    ) -> Dict:
        """
        Create dispatch schedule using simple rules
        
        Strategy:
        1. Use PV to meet load first
        2. Charge battery with excess PV during low tariff periods
        3. Discharge battery during peak tariff periods
        4. Use grid import/export as needed
        
        Args:
            pv_forecast_kw: PV forecast array [N]
            load_kw: Load forecast array [N]
            tariff_buy: Buy tariff array [N]
            tariff_sell: Sell tariff array [N]
            bess_params: Battery parameters
            limits: Grid/transformer limits
            resolution_minutes: Time resolution
        
        Returns:
            Dict with schedule arrays
        """
        N = len(pv_forecast_kw)
        dt_hours = resolution_minutes / 60.0
        
        # Extract BESS parameters
        capacity_kwh = bess_params.get('capacity_kwh', 100.0)
        p_charge_max = bess_params.get('p_charge_max_kw', 50.0)
        p_discharge_max = bess_params.get('p_discharge_max_kw', 50.0)
        soc = bess_params.get('soc0', 0.5)
        soc_min = bess_params.get('soc_min', 0.2)
        soc_max = bess_params.get('soc_max', 0.9)
        eta_charge = bess_params.get('eta_charge', 0.95)
        eta_discharge = bess_params.get('eta_discharge', 0.95)
        
        # Extract limits
        grid_import_max = limits.get('grid_import_max_kw', 200.0)
        grid_export_max = limits.get('grid_export_max_kw', 200.0)
        
        # Identify peak tariff hours
        tariff_median = np.median(tariff_buy)
        tariff_threshold = tariff_median * 1.2  # 20% above median = peak
        is_peak = [t >= tariff_threshold for t in tariff_buy]
        
        # Initialize output arrays
        pv_set = []
        batt_ch = []
        batt_dis = []
        grid_imp = []
        grid_exp = []
        curtail = []
        soc_arr = []
        
        for t in range(N):
            pv_available = pv_forecast_kw[t]
            load_demand = load_kw[t]
            
            # Step 1: Use PV to meet load first
            pv_to_load = min(pv_available, load_demand)
            pv_excess = pv_available - pv_to_load
            load_remaining = load_demand - pv_to_load
            
            # Initialize timestep variables
            ch = 0.0
            dis = 0.0
            imp = 0.0
            exp = 0.0
            curt = 0.0
            
            # Step 2: Battery dispatch logic
            if is_peak[t] and load_remaining > 0 and soc > soc_min:
                # Peak period: discharge battery to reduce grid import
                max_dis_power = min(
                    p_discharge_max,
                    load_remaining,
                    (soc - soc_min) * capacity_kwh / dt_hours
                )
                dis = max_dis_power
                soc -= (dis / eta_discharge) * dt_hours / capacity_kwh
                load_remaining -= dis
            
            elif not is_peak[t] and pv_excess > 0 and soc < soc_max:
                # Off-peak with excess PV: charge battery
                max_ch_energy = (soc_max - soc) * capacity_kwh
                max_ch_power = min(
                    p_charge_max,
                    pv_excess,
                    max_ch_energy / dt_hours
                )
                ch = max_ch_power
                soc += (ch * eta_charge) * dt_hours / capacity_kwh
                pv_excess -= ch
            
            # Step 3: Handle remaining imbalance with grid
            if load_remaining > 0:
                # Need grid import
                imp = min(load_remaining, grid_import_max)
                if imp < load_remaining:
                    # Grid limit exceeded - this is infeasible but handle gracefully
                    imp = grid_import_max
            
            if pv_excess > 0:
                # Have excess PV - either export or curtail
                exp = min(pv_excess, grid_export_max)
                curt = pv_excess - exp
            
            # Clamp SOC to valid range (safety check)
            soc = max(soc_min, min(soc_max, soc))
            
            # Store results
            pv_set.append(pv_to_load + ch)  # PV used for load and charging
            batt_ch.append(ch)
            batt_dis.append(dis)
            grid_imp.append(imp)
            grid_exp.append(exp)
            curtail.append(curt)
            soc_arr.append(soc)
        
        # Calculate simple objective estimate
        total_cost = sum(
            tariff_buy[t] * grid_imp[t] * dt_hours - 
            tariff_sell[t] * grid_exp[t] * dt_hours
            for t in range(N)
        )
        total_curtail = sum(curtail) * dt_hours
        objective_estimate = total_cost + 0.2 * total_curtail
        
        solution = {
            'pv_set_kw': pv_set,
            'batt_ch_kw': batt_ch,
            'batt_dis_kw': batt_dis,
            'grid_imp_kw': grid_imp,
            'grid_exp_kw': grid_exp,
            'curtail_kw': curtail,
            'soc': soc_arr,
            'objective_value': objective_estimate,
            'solver_status': 'fallback_rule',
            'solve_time': 0.0
        }
        
        return solution
    
    def validate_schedule(
        self,
        solution: Dict,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        resolution_minutes: int = 15
    ) -> Tuple[bool, List[str]]:
        """
        Validate that schedule satisfies power balance
        
        Args:
            solution: Schedule solution dict
            pv_forecast_kw: PV forecast array
            load_kw: Load forecast array
            resolution_minutes: Time resolution
        
        Returns:
            Tuple of (is_valid, list_of_violations)
        """
        N = len(load_kw)
        violations = []
        tolerance = 1e-2  # 10W tolerance for numerical errors
        
        for t in range(N):
            # Check power balance
            supply = solution['pv_set_kw'][t] + solution['batt_dis_kw'][t] + solution['grid_imp_kw'][t]
            demand = load_kw[t] + solution['batt_ch_kw'][t] + solution['grid_exp_kw'][t]
            
            if abs(supply - demand) > tolerance:
                violations.append(f"t={t}: Power imbalance {supply:.2f} != {demand:.2f}")
            
            # Check PV curtailment
            pv_total = solution['pv_set_kw'][t] + solution['curtail_kw'][t]
            if abs(pv_total - pv_forecast_kw[t]) > tolerance:
                violations.append(f"t={t}: PV balance {pv_total:.2f} != {pv_forecast_kw[t]:.2f}")
        
        return len(violations) == 0, violations


if __name__ == "__main__":
    # Test fallback scheduler
    print("=" * 60)
    print("Fallback Scheduler Test")
    print("=" * 60)
    
    # Create simple test case (24 timesteps = 6 hours, 15-min resolution)
    import math
    
    N = 24
    
    # PV profile
    pv_forecast = []
    for i in range(N):
        hour = 8 + i * 0.25  # Start at 8am
        if hour < 18:
            pv_forecast.append(100 * math.sin((hour - 8) / 10 * math.pi))
        else:
            pv_forecast.append(0.0)
    
    # Load profile
    load = [80.0] * N
    
    # Tariff (peak during hours 18-22)
    tariff_buy = []
    for i in range(N):
        hour = 8 + i * 0.25
        if 18 <= hour <= 22:
            tariff_buy.append(0.50)
        else:
            tariff_buy.append(0.30)
    
    tariff_sell = [0.20] * N
    
    # BESS params
    bess_params = {
        'capacity_kwh': 100.0,
        'p_charge_max_kw': 50.0,
        'p_discharge_max_kw': 50.0,
        'soc0': 0.5,
        'soc_min': 0.2,
        'soc_max': 0.9,
        'eta_charge': 0.95,
        'eta_discharge': 0.95
    }
    
    limits = {
        'grid_import_max_kw': 200.0,
        'grid_export_max_kw': 200.0
    }
    
    # Create scheduler
    scheduler = FallbackScheduler()
    
    # Run scheduling
    print("\nRunning fallback rule-based scheduling...")
    solution = scheduler.schedule(
        pv_forecast_kw=pv_forecast,
        load_kw=load,
        tariff_buy=tariff_buy,
        tariff_sell=tariff_sell,
        bess_params=bess_params,
        limits=limits,
        resolution_minutes=15
    )
    
    print(f"✅ Scheduling completed!")
    print(f"Status: {solution['solver_status']}")
    print(f"Objective estimate: {solution['objective_value']:.2f} MYR")
    
    # Validate
    is_valid, violations = scheduler.validate_schedule(solution, pv_forecast, load, 15)
    
    if is_valid:
        print("✅ Schedule is valid (power balance satisfied)")
    else:
        print(f"❌ Schedule has {len(violations)} violations:")
        for v in violations[:5]:  # Show first 5
            print(f"  {v}")
    
    # Show first 5 timesteps
    print("\nFirst 5 timesteps:")
    print(f"{'t':<3} {'PV':<6} {'Load':<6} {'BattCh':<8} {'BattDis':<8} {'GridImp':<8} {'SOC':<6}")
    for t in range(min(5, N)):
        print(f"{t:<3} {solution['pv_set_kw'][t]:6.1f} {load[t]:6.1f} "
              f"{solution['batt_ch_kw'][t]:8.1f} {solution['batt_dis_kw'][t]:8.1f} "
              f"{solution['grid_imp_kw'][t]:8.1f} {solution['soc'][t]:6.3f}")
