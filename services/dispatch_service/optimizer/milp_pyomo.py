"""
MILP Optimizer using Pyomo for BESS dispatch optimization
Objective: Minimize cost while respecting all constraints
"""
import pyomo.environ as pyo
from pyomo.opt import SolverFactory, TerminationCondition
from typing import Dict, List, Optional, Tuple
import numpy as np


class MILPOptimizer:
    """
    Mixed-Integer Linear Programming optimizer for microgrid dispatch
    Uses Pyomo with CBC/GLPK solver
    """
    
    def __init__(self, solver_name: str = "cbc", timeout_seconds: float = 3.0):
        """
        Initialize MILP optimizer
        
        Args:
            solver_name: Pyomo solver ('cbc', 'glpk', 'gurobi')
            timeout_seconds: Maximum solver time
        """
        self.solver_name = solver_name
        self.timeout_seconds = timeout_seconds
        self.solver = None
        
    def _create_model(
        self,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        tariff_buy: List[float],
        tariff_sell: List[float],
        bess_params: Dict,
        limits: Dict,
        weights: Dict,
        dt_hours: float
    ) -> pyo.ConcreteModel:
        """
        Create Pyomo concrete model for dispatch optimization
        
        Args:
            pv_forecast_kw: PV forecast array [N]
            load_kw: Load forecast array [N]
            tariff_buy: Buy tariff array [N] (MYR/kWh)
            tariff_sell: Sell tariff array [N] (MYR/kWh)
            bess_params: Battery parameters dict
            limits: Grid/transformer limits dict
            weights: Objective weights dict
            dt_hours: Time step size (hours)
        
        Returns:
            Pyomo ConcreteModel
        """
        N = len(pv_forecast_kw)
        
        # Extract BESS parameters
        capacity_kwh = bess_params.get('capacity_kwh', 100.0)
        p_charge_max = bess_params.get('p_charge_max_kw', 50.0)
        p_discharge_max = bess_params.get('p_discharge_max_kw', 50.0)
        soc0 = bess_params.get('soc0', 0.5)
        soc_min = bess_params.get('soc_min', 0.2)
        soc_max = bess_params.get('soc_max', 0.9)
        eta_charge = bess_params.get('eta_charge', 0.95)
        eta_discharge = bess_params.get('eta_discharge', 0.95)
        
        # Extract limits
        grid_import_max = limits.get('grid_import_max_kw', 200.0)
        grid_export_max = limits.get('grid_export_max_kw', 200.0)
        transformer_max = limits.get('transformer_max_kw', 250.0)
        
        # Extract weights
        w_cost = weights.get('cost', 1.0)
        w_curtail = weights.get('curtail', 0.2)
        w_violation = weights.get('violation', 1000.0)
        
        # Create model
        model = pyo.ConcreteModel(name="MicrogridDispatch")
        
        # Sets
        model.T = pyo.RangeSet(0, N-1)
        
        # Decision variables
        model.pv_set = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, None))
        model.batt_ch = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, p_charge_max))
        model.batt_dis = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, p_discharge_max))
        model.grid_imp = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, grid_import_max))
        model.grid_exp = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, grid_export_max))
        model.curtail = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, None))
        model.soc = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(soc_min, soc_max))
        
        # Binary variables for mutual exclusivity
        model.b_charge = pyo.Var(model.T, domain=pyo.Binary)
        model.b_import = pyo.Var(model.T, domain=pyo.Binary)
        
        # Slack variables for soft constraints (violations)
        model.slack_transformer = pyo.Var(model.T, domain=pyo.NonNegativeReals)
        
        # Objective: Minimize cost + curtailment penalty + violation penalty
        def objective_rule(m):
            cost_term = sum(
                tariff_buy[t] * m.grid_imp[t] * dt_hours - 
                tariff_sell[t] * m.grid_exp[t] * dt_hours
                for t in m.T
            )
            curtail_term = sum(m.curtail[t] for t in m.T) * dt_hours
            violation_term = sum(m.slack_transformer[t] for t in m.T)
            
            return w_cost * cost_term + w_curtail * curtail_term + w_violation * violation_term
        
        model.obj = pyo.Objective(rule=objective_rule, sense=pyo.minimize)
        
        # Constraints
        
        # 1. Power balance at each timestep
        def power_balance_rule(m, t):
            return m.pv_set[t] + m.batt_dis[t] + m.grid_imp[t] == \
                   load_kw[t] + m.batt_ch[t] + m.grid_exp[t]
        
        model.power_balance = pyo.Constraint(model.T, rule=power_balance_rule)
        
        # 2. PV curtailment constraint
        def pv_curtail_rule(m, t):
            return m.pv_set[t] + m.curtail[t] == pv_forecast_kw[t]
        
        model.pv_curtail = pyo.Constraint(model.T, rule=pv_curtail_rule)
        
        # 3. SOC dynamics
        def soc_dynamics_rule(m, t):
            if t == 0:
                return m.soc[t] == soc0 + \
                       (m.batt_ch[t] * eta_charge - m.batt_dis[t] / eta_discharge) * dt_hours / capacity_kwh
            else:
                return m.soc[t] == m.soc[t-1] + \
                       (m.batt_ch[t] * eta_charge - m.batt_dis[t] / eta_discharge) * dt_hours / capacity_kwh
        
        model.soc_dynamics = pyo.Constraint(model.T, rule=soc_dynamics_rule)
        
        # 4. Battery charge/discharge mutual exclusivity (no simultaneous charge and discharge)
        def charge_mutex_rule(m, t):
            return m.batt_ch[t] <= m.b_charge[t] * p_charge_max
        
        model.charge_mutex = pyo.Constraint(model.T, rule=charge_mutex_rule)
        
        def discharge_mutex_rule(m, t):
            return m.batt_dis[t] <= (1 - m.b_charge[t]) * p_discharge_max
        
        model.discharge_mutex = pyo.Constraint(model.T, rule=discharge_mutex_rule)
        
        # 5. Grid import/export mutual exclusivity
        def import_mutex_rule(m, t):
            return m.grid_imp[t] <= m.b_import[t] * grid_import_max
        
        model.import_mutex = pyo.Constraint(model.T, rule=import_mutex_rule)
        
        def export_mutex_rule(m, t):
            return m.grid_exp[t] <= (1 - m.b_import[t]) * grid_export_max
        
        model.export_mutex = pyo.Constraint(model.T, rule=export_mutex_rule)
        
        # 6. Transformer capacity (soft constraint with slack)
        def transformer_limit_rule(m, t):
            net_power = m.grid_imp[t] + m.grid_exp[t]
            return net_power <= transformer_max + m.slack_transformer[t]
        
        model.transformer_limit = pyo.Constraint(model.T, rule=transformer_limit_rule)
        
        return model
    
    def optimize(
        self,
        pv_forecast_kw: List[float],
        load_kw: List[float],
        tariff_buy: List[float],
        tariff_sell: List[float],
        bess_params: Dict,
        limits: Optional[Dict] = None,
        weights: Optional[Dict] = None,
        resolution_minutes: int = 15
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Run MILP optimization
        
        Args:
            pv_forecast_kw: PV forecast array [N]
            load_kw: Load forecast array [N]
            tariff_buy: Buy tariff array [N]
            tariff_sell: Sell tariff array [N]
            bess_params: Battery parameters
            limits: Grid/transformer limits (optional)
            weights: Objective weights (optional)
            resolution_minutes: Time resolution
        
        Returns:
            Tuple of (success, results_dict, error_message)
            - success: True if optimization succeeded
            - results_dict: Dict with arrays for each variable
            - error_message: Error description if failed
        """
        # Validate inputs
        N = len(pv_forecast_kw)
        if not (len(load_kw) == len(tariff_buy) == len(tariff_sell) == N):
            return False, None, "Input arrays must have same length"
        
        if N == 0:
            return False, None, "Empty input arrays"
        
        # Set defaults
        if limits is None:
            limits = {
                'grid_import_max_kw': 200.0,
                'grid_export_max_kw': 200.0,
                'transformer_max_kw': 250.0
            }
        
        if weights is None:
            weights = {
                'cost': 1.0,
                'curtail': 0.2,
                'violation': 1000.0
            }
        
        dt_hours = resolution_minutes / 60.0
        
        try:
            # Create model
            model = self._create_model(
                pv_forecast_kw, load_kw, tariff_buy, tariff_sell,
                bess_params, limits, weights, dt_hours
            )
            
            # Create solver
            self.solver = SolverFactory(self.solver_name)
            
            if self.solver is None:
                return False, None, f"Solver {self.solver_name} not available"
            
            # Set solver options
            solver_options = {
                'seconds': self.timeout_seconds,
                'ratio': 0.01  # 1% optimality gap acceptable
            }
            
            # Solve
            results = self.solver.solve(model, options=solver_options, tee=False)
            
            # Check termination condition
            if results.solver.termination_condition == TerminationCondition.optimal:
                status = "optimal"
            elif results.solver.termination_condition == TerminationCondition.maxTimeLimit:
                status = "timeout"
                # Check if solution is feasible
                if not hasattr(results.solution, 'status') or results.solution.status != pyo.SolutionStatus.feasible:
                    return False, None, "Solver timeout without feasible solution"
            elif results.solver.termination_condition == TerminationCondition.infeasible:
                return False, None, "Problem is infeasible"
            else:
                return False, None, f"Solver failed: {results.solver.termination_condition}"
            
            # Extract solution
            solution = {
                'pv_set_kw': [pyo.value(model.pv_set[t]) for t in model.T],
                'batt_ch_kw': [pyo.value(model.batt_ch[t]) for t in model.T],
                'batt_dis_kw': [pyo.value(model.batt_dis[t]) for t in model.T],
                'grid_imp_kw': [pyo.value(model.grid_imp[t]) for t in model.T],
                'grid_exp_kw': [pyo.value(model.grid_exp[t]) for t in model.T],
                'curtail_kw': [pyo.value(model.curtail[t]) for t in model.T],
                'soc': [pyo.value(model.soc[t]) for t in model.T],
                'slack_transformer': [pyo.value(model.slack_transformer[t]) for t in model.T],
                'objective_value': pyo.value(model.obj),
                'solver_status': status,
                'solve_time': results.solver.time if hasattr(results.solver, 'time') else None
            }
            
            return True, solution, None
            
        except Exception as e:
            return False, None, f"Optimization error: {str(e)}"
    
    def get_binding_constraints(
        self,
        solution: Dict,
        bess_params: Dict,
        limits: Dict,
        tolerance: float = 1e-3
    ) -> List[Dict]:
        """
        Identify binding constraints from solution
        
        Args:
            solution: Optimization solution dict
            bess_params: Battery parameters
            limits: Grid/transformer limits
            tolerance: Constraint violation tolerance
        
        Returns:
            List of dicts describing binding constraints at each timestep
        """
        N = len(solution['soc'])
        binding = []
        
        soc_min = bess_params.get('soc_min', 0.2)
        soc_max = bess_params.get('soc_max', 0.9)
        p_charge_max = bess_params.get('p_charge_max_kw', 50.0)
        p_discharge_max = bess_params.get('p_discharge_max_kw', 50.0)
        grid_import_max = limits.get('grid_import_max_kw', 200.0)
        grid_export_max = limits.get('grid_export_max_kw', 200.0)
        transformer_max = limits.get('transformer_max_kw', 250.0)
        
        for t in range(N):
            t_bindings = []
            
            # Check SOC bounds
            if abs(solution['soc'][t] - soc_min) < tolerance:
                t_bindings.append('soc_min')
            if abs(solution['soc'][t] - soc_max) < tolerance:
                t_bindings.append('soc_max')
            
            # Check power limits
            if abs(solution['batt_ch_kw'][t] - p_charge_max) < tolerance:
                t_bindings.append('p_charge_max')
            if abs(solution['batt_dis_kw'][t] - p_discharge_max) < tolerance:
                t_bindings.append('p_discharge_max')
            
            if abs(solution['grid_imp_kw'][t] - grid_import_max) < tolerance:
                t_bindings.append('grid_import_max')
            if abs(solution['grid_exp_kw'][t] - grid_export_max) < tolerance:
                t_bindings.append('grid_export_max')
            
            # Check transformer limit
            net_power = solution['grid_imp_kw'][t] + solution['grid_exp_kw'][t]
            if abs(net_power - transformer_max) < tolerance:
                t_bindings.append('transformer_max')
            
            binding.append({
                'timestep': t,
                'constraints': t_bindings
            })
        
        return binding


if __name__ == "__main__":
    # Test MILP optimizer
    print("=" * 60)
    print("MILP Optimizer Test")
    print("=" * 60)
    
    # Create test data (24 hours, 15-min resolution = 96 points)
    N = 96
    
    # Simple PV profile (sinusoidal, peak at noon)
    import math
    pv_forecast = []
    for i in range(N):
        hour = i * 0.25  # 15-min intervals
        if 6 <= hour <= 18:
            pv_forecast.append(200 * math.sin((hour - 6) / 12 * math.pi))
        else:
            pv_forecast.append(0.0)
    
    # Load profile (higher during day)
    load = []
    for i in range(N):
        hour = i * 0.25
        if 8 <= hour <= 20:
            load.append(100.0 + 20 * math.sin((hour - 8) / 12 * math.pi))
        else:
            load.append(60.0)
    
    # Simple TOU tariff
    tariff_buy = []
    tariff_sell = []
    for i in range(N):
        hour = i * 0.25
        if 18 <= hour <= 22:  # Peak hours
            tariff_buy.append(0.50)  # MYR/kWh
        else:
            tariff_buy.append(0.30)
        tariff_sell.append(0.20)  # Feed-in tariff
    
    # BESS parameters
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
    
    # Create optimizer
    optimizer = MILPOptimizer(solver_name='cbc', timeout_seconds=5.0)
    
    # Run optimization
    print("\nRunning MILP optimization...")
    success, solution, error = optimizer.optimize(
        pv_forecast_kw=pv_forecast,
        load_kw=load,
        tariff_buy=tariff_buy,
        tariff_sell=tariff_sell,
        bess_params=bess_params,
        resolution_minutes=15
    )
    
    if success:
        print(f"✅ Optimization succeeded!")
        print(f"Status: {solution['solver_status']}")
        print(f"Objective value: {solution['objective_value']:.2f} MYR")
        if solution['solve_time']:
            print(f"Solve time: {solution['solve_time']:.3f} seconds")
        
        # Show first 5 timesteps
        print("\nFirst 5 timesteps:")
        print(f"{'t':<3} {'PV':<6} {'BattCh':<8} {'BattDis':<8} {'GridImp':<8} {'SOC':<6}")
        for t in range(5):
            print(f"{t:<3} {solution['pv_set_kw'][t]:6.1f} {solution['batt_ch_kw'][t]:8.1f} "
                  f"{solution['batt_dis_kw'][t]:8.1f} {solution['grid_imp_kw'][t]:8.1f} {solution['soc'][t]:6.3f}")
        
        # Check binding constraints
        binding = optimizer.get_binding_constraints(
            solution, bess_params,
            {'grid_import_max_kw': 200, 'grid_export_max_kw': 200, 'transformer_max_kw': 250}
        )
        
        print("\nBinding constraints (first 5 timesteps):")
        for i in range(5):
            if binding[i]['constraints']:
                print(f"t={i}: {', '.join(binding[i]['constraints'])}")
    else:
        print(f"❌ Optimization failed: {error}")
