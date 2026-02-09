"""
KPI Calculator for dispatch schedules
Computes key performance indicators for optimization results
"""
from typing import Dict, List
import numpy as np


class KPICalculator:
    """
    Calculate Key Performance Indicators from dispatch schedule
    """
    
    def __init__(self):
        """Initialize KPI calculator"""
        pass
    
    def calculate_kpis(
        self,
        solution: Dict,
        tariff_buy: List[float],
        tariff_sell: List[float],
        resolution_minutes: int = 15
    ) -> Dict:
        """
        Calculate all KPIs from dispatch solution
        
        Args:
            solution: Dispatch solution dict with arrays
            tariff_buy: Buy tariff array [N]
            tariff_sell: Sell tariff array [N]
            resolution_minutes: Time resolution
        
        Returns:
            Dict with KPI values
        """
        N = len(solution['soc'])
        dt_hours = resolution_minutes / 60.0
        
        # 1. Total cost (objective value)
        total_cost = sum(
            tariff_buy[t] * solution['grid_imp_kw'][t] * dt_hours -
            tariff_sell[t] * solution['grid_exp_kw'][t] * dt_hours
            for t in range(N)
        )
        
        # 2. Total curtailment energy
        total_curtail_kwh = sum(solution['curtail_kw']) * dt_hours
        
        # 3. Peak grid import power
        peak_grid_import_kw = max(solution['grid_imp_kw']) if solution['grid_imp_kw'] else 0.0
        
        # 4. Average SOC
        avg_soc = np.mean(solution['soc'])
        
        # 5. Additional useful KPIs
        
        # Total grid import energy
        total_grid_import_kwh = sum(solution['grid_imp_kw']) * dt_hours
        
        # Total grid export energy
        total_grid_export_kwh = sum(solution['grid_exp_kw']) * dt_hours
        
        # Total battery charge energy
        total_batt_charge_kwh = sum(solution['batt_ch_kw']) * dt_hours
        
        # Total battery discharge energy
        total_batt_discharge_kwh = sum(solution['batt_dis_kw']) * dt_hours
        
        # Battery cycling (full cycles)
        # Assuming symmetric: cycle count = total_charge / capacity
        # This is stored separately if needed
        
        # Self-consumption rate (if PV data available in solution)
        if 'pv_set_kw' in solution:
            total_pv_generated = sum(solution['pv_set_kw']) * dt_hours + total_curtail_kwh
            total_pv_used = sum(solution['pv_set_kw']) * dt_hours
            self_consumption_rate = total_pv_used / total_pv_generated if total_pv_generated > 0 else 0.0
        else:
            self_consumption_rate = None
        
        # Peak grid import time
        peak_import_timestep = int(np.argmax(solution['grid_imp_kw']))
        
        # SOC range
        min_soc = min(solution['soc'])
        max_soc = max(solution['soc'])
        
        # Cost breakdown
        total_import_cost = sum(
            tariff_buy[t] * solution['grid_imp_kw'][t] * dt_hours
            for t in range(N)
        )
        total_export_revenue = sum(
            tariff_sell[t] * solution['grid_exp_kw'][t] * dt_hours
            for t in range(N)
        )
        
        kpis = {
            # Main KPIs (written to dispatch_kpis table)
            'total_cost': round(total_cost, 2),
            'total_curtail_kwh': round(total_curtail_kwh, 2),
            'peak_grid_import_kw': round(peak_grid_import_kw, 2),
            'avg_soc': round(avg_soc, 4),
            
            # Extended KPIs (for detailed analysis)
            'total_grid_import_kwh': round(total_grid_import_kwh, 2),
            'total_grid_export_kwh': round(total_grid_export_kwh, 2),
            'total_batt_charge_kwh': round(total_batt_charge_kwh, 2),
            'total_batt_discharge_kwh': round(total_batt_discharge_kwh, 2),
            'self_consumption_rate': round(self_consumption_rate, 4) if self_consumption_rate is not None else None,
            'peak_import_timestep': peak_import_timestep,
            'min_soc': round(min_soc, 4),
            'max_soc': round(max_soc, 4),
            'total_import_cost': round(total_import_cost, 2),
            'total_export_revenue': round(total_export_revenue, 2),
            'net_cost': round(total_import_cost - total_export_revenue, 2)
        }
        
        return kpis
    
    def calculate_savings(
        self,
        optimized_kpis: Dict,
        baseline_kpis: Dict
    ) -> Dict:
        """
        Calculate savings compared to baseline scenario
        
        Args:
            optimized_kpis: KPIs from optimized dispatch
            baseline_kpis: KPIs from baseline (e.g., no battery)
        
        Returns:
            Dict with savings metrics
        """
        cost_savings = baseline_kpis['total_cost'] - optimized_kpis['total_cost']
        cost_savings_pct = (cost_savings / baseline_kpis['total_cost'] * 100) if baseline_kpis['total_cost'] > 0 else 0.0
        
        peak_reduction = baseline_kpis['peak_grid_import_kw'] - optimized_kpis['peak_grid_import_kw']
        peak_reduction_pct = (peak_reduction / baseline_kpis['peak_grid_import_kw'] * 100) if baseline_kpis['peak_grid_import_kw'] > 0 else 0.0
        
        curtail_reduction = baseline_kpis['total_curtail_kwh'] - optimized_kpis['total_curtail_kwh']
        
        savings = {
            'cost_savings': round(cost_savings, 2),
            'cost_savings_pct': round(cost_savings_pct, 2),
            'peak_reduction_kw': round(peak_reduction, 2),
            'peak_reduction_pct': round(peak_reduction_pct, 2),
            'curtail_reduction_kwh': round(curtail_reduction, 2)
        }
        
        return savings
    
    def generate_summary(self, kpis: Dict) -> str:
        """
        Generate human-readable summary of KPIs
        
        Args:
            kpis: KPIs dict
        
        Returns:
            Formatted summary string
        """
        lines = [
            "=" * 60,
            "DISPATCH KPI SUMMARY",
            "=" * 60,
            f"Total Cost:              {kpis['total_cost']:>10.2f} MYR",
            f"  - Import Cost:         {kpis.get('total_import_cost', 0):>10.2f} MYR",
            f"  - Export Revenue:      {kpis.get('total_export_revenue', 0):>10.2f} MYR",
            f"  - Net Cost:            {kpis.get('net_cost', 0):>10.2f} MYR",
            "",
            f"Peak Grid Import:        {kpis['peak_grid_import_kw']:>10.2f} kW (t={kpis.get('peak_import_timestep', 0)})",
            f"Total Curtailment:       {kpis['total_curtail_kwh']:>10.2f} kWh",
            "",
            f"Battery Utilization:",
            f"  - Average SOC:         {kpis['avg_soc']:>10.1%}",
            f"  - SOC Range:           {kpis.get('min_soc', 0):>10.1%} - {kpis.get('max_soc', 0):.1%}",
            f"  - Total Charge:        {kpis.get('total_batt_charge_kwh', 0):>10.2f} kWh",
            f"  - Total Discharge:     {kpis.get('total_batt_discharge_kwh', 0):>10.2f} kWh",
            "",
            f"Grid Interaction:",
            f"  - Total Import:        {kpis.get('total_grid_import_kwh', 0):>10.2f} kWh",
            f"  - Total Export:        {kpis.get('total_grid_export_kwh', 0):>10.2f} kWh",
        ]
        
        if kpis.get('self_consumption_rate') is not None:
            lines.append(f"  - Self-Consumption:    {kpis['self_consumption_rate']:>10.1%}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test KPI calculator
    print("=" * 60)
    print("KPI Calculator Test")
    print("=" * 60)
    
    # Create sample solution (24 timesteps)
    N = 24
    
    # Mock solution data
    solution = {
        'pv_set_kw': [50.0] * 12 + [0.0] * 12,
        'batt_ch_kw': [10.0] * 6 + [0.0] * 18,
        'batt_dis_kw': [0.0] * 18 + [30.0] * 6,
        'grid_imp_kw': [40.0] * 6 + [50.0] * 12 + [60.0] * 6,
        'grid_exp_kw': [0.0] * N,
        'curtail_kw': [5.0] * 6 + [0.0] * 18,
        'soc': [0.5 + i * 0.01 for i in range(N)]
    }
    
    # Mock tariff
    tariff_buy = [0.30] * 18 + [0.50] * 6
    tariff_sell = [0.20] * N
    
    # Create calculator
    calc = KPICalculator()
    
    # Calculate KPIs
    kpis = calc.calculate_kpis(solution, tariff_buy, tariff_sell, resolution_minutes=60)
    
    print("\nCalculated KPIs:")
    print(calc.generate_summary(kpis))
    
    # Test savings calculation
    print("\n" + "=" * 60)
    print("SAVINGS CALCULATION (vs baseline)")
    print("=" * 60)
    
    # Mock baseline (no battery, higher cost)
    baseline_solution = {
        'pv_set_kw': solution['pv_set_kw'],
        'batt_ch_kw': [0.0] * N,
        'batt_dis_kw': [0.0] * N,
        'grid_imp_kw': [60.0] * N,
        'grid_exp_kw': [0.0] * N,
        'curtail_kw': [10.0] * 6 + [0.0] * 18,
        'soc': [0.5] * N
    }
    
    baseline_kpis = calc.calculate_kpis(baseline_solution, tariff_buy, tariff_sell, resolution_minutes=60)
    
    savings = calc.calculate_savings(kpis, baseline_kpis)
    
    print(f"Cost Savings:         {savings['cost_savings']:>10.2f} MYR ({savings['cost_savings_pct']:.1f}%)")
    print(f"Peak Reduction:       {savings['peak_reduction_kw']:>10.2f} kW ({savings['peak_reduction_pct']:.1f}%)")
    print(f"Curtail Reduction:    {savings['curtail_reduction_kwh']:>10.2f} kWh")
    print("=" * 60)
