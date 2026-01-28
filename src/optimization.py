"""
Módulo de optimización ILP.

Construye y resuelve el ILP compacto diario usando OR-Tools (SCIP).
Incluye coste marginal creciente y penalizaciones under/over.
"""

import numpy as np
from ortools.linear_solver import pywraplp
from typing import Tuple, List
import logging

logger = logging.getLogger(__name__)


def build_daily_ilp(
    shift_matrix: np.ndarray,
    required_full: np.ndarray,
    n_agents: int,
    alpha_under: float,
    beta_over: float,
    gamma_head: float,
    cap_per_shift: int,
    seg_width: int,
    seg_mult_step: float,
    noise_eps: float,
    solver_ms: int = 20000,
    random_seed: int = 42
) -> Tuple[pywraplp.Solver, List, List, List, int, int, np.ndarray]:
    """
    Construye el modelo ILP diario con coste marginal creciente.
    
    Variables:
    - y[j]: número de agentes asignados al turno j (0 <= y[j] <= cap_per_shift)
    - u[t]: undercoverage en intervalo t
    - o[t]: overcoverage en intervalo t
    - seg[j][k]: segmentos para coste marginal creciente
    
    Restricciones:
    1. Balance por intervalo: sum_j y[j] * cobertura[j,t] - required[t] = o[t] - u[t]
    2. Capacidad total: sum_j y[j] <= n_agents
    3. Segmentación: sum_k seg[j][k] = y[j]
    
    Objetivo:
    Minimizar: alpha_under * sum_u + beta_over * sum_o + costo_marginal_creciente
    
    Args:
        shift_matrix: ndarray (M, T) con cobertura por turno/intervalo
        required_full: ndarray (T,) de requeridos
        n_agents: Número de agentes disponibles
        alpha_under: Penalización por undercoverage
        beta_over: Penalización por overcoverage
        gamma_head: Costo base por agente/turno
        cap_per_shift: Tope máximo de agentes por turno
        seg_width: Ancho de segmento para coste marginal
        seg_mult_step: Multiplicador de incremento por segmento
        noise_eps: Ruido relativo para romper empates
        solver_ms: Tiempo límite del solver (ms)
        random_seed: Semilla para reproducibilidad
        
    Returns:
        Tupla (solver, y, u, o, M, T, status_info)
        
    Raises:
        ValueError: Si shift_matrix o required_full tienen forma inconsistente
    """
    M, T = shift_matrix.shape
    
    if T != len(required_full):
        raise ValueError(f"Inconsistencia: shift_matrix.T={T} != required.len={len(required_full)}")
    
    # Crear solver
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("No se pudo crear solver SCIP. Verifica instalación de OR-Tools.")
    
    # Variables principales
    y = [solver.IntVar(0, cap_per_shift, f"y_{j}") for j in range(M)]
    u = [solver.NumVar(0, solver.infinity(), f"u_{t}") for t in range(T)]
    o = [solver.NumVar(0, solver.infinity(), f"o_{t}") for t in range(T)]
    
    # Restricción 1: Balance por intervalo
    for t in range(T):
        coverage_expr = sum(y[j] * int(shift_matrix[j, t]) for j in range(M))
        solver.Add(coverage_expr - int(required_full[t]) == o[t] - u[t])
    
    # Restricción 2: No exceder agentes disponibles
    solver.Add(sum(y[j] for j in range(M)) <= n_agents)
    
    # Restricción 3 + Objetivo: Coste marginal creciente (segmentación)
    seg_vars = []
    seg_costs = []
    
    np.random.seed(random_seed)
    
    for j in range(M):
        segs_j = []
        costs_j = []
        
        # Número de segmentos máximo
        Kseg = (cap_per_shift + seg_width - 1) // seg_width
        noise = 1.0 + noise_eps * np.random.rand(Kseg)
        
        for k in range(Kseg):
            # Upper bound del segmento
            ub = seg_width if (k < Kseg - 1) else (cap_per_shift - seg_width * (Kseg - 1))
            v = solver.NumVar(0, ub, f"seg_{j}_{k}")
            segs_j.append(v)
            
            # Multiplicador de costo creciente
            mult = (1.0 + k * seg_mult_step) * noise[k]
            costs_j.append(gamma_head * mult)
        
        seg_vars.append(segs_j)
        seg_costs.append(costs_j)
        
        # Reconstrucción de y[j]
        solver.Add(sum(segs_j) == y[j])
    
    # Objetivo
    obj = alpha_under * sum(u) + beta_over * sum(o)
    for j in range(M):
        for k, v in enumerate(seg_vars[j]):
            obj = obj + seg_costs[j][k] * v
    
    solver.Minimize(obj)
    solver.SetTimeLimit(solver_ms)
    
    status = solver.Solve()
    
    logger.info(f"ILP Solver resuelto: status={status} (OPTIMAL=0, FEASIBLE=1, INFEASIBLE=2)")
    
    return solver, y, u, o, M, T, status


def extract_solution(
    solver: pywraplp.Solver,
    y: List,
    u: List,
    o: List,
    shift_matrix: np.ndarray,
    required_full: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extrae valores de la solución del ILP.
    
    Args:
        solver: Solver con solución
        y: Variables de asignación
        u: Variables de undercoverage
        o: Variables de overcoverage
        shift_matrix: Matriz de cobertura
        required_full: Requeridos
        
    Returns:
        Tupla (y_val, coverage, metrics_dict)
    """
    y_val = np.array([int(round(v.solution_value())) for v in y])
    
    # Recalcular cobertura según solución
    coverage = np.zeros(len(required_full), dtype=int)
    for j, count in enumerate(y_val):
        coverage += count * shift_matrix[j]
    
    # Métricas
    under_val = np.array([u[t].solution_value() for t in range(len(u))])
    over_val = np.array([o[t].solution_value() for t in range(len(o))])
    
    metrics = {
        "total_assignments": y_val.sum(),
        "undercoverage_total": under_val.sum(),
        "overcoverage_total": over_val.sum(),
        "objective": solver.Objective().Value()
    }
    
    logger.info(f"Solución: {metrics['total_assignments']} asignaciones, "
                f"bajo={metrics['undercoverage_total']:.0f}, "
                f"sobre={metrics['overcoverage_total']:.0f}")
    
    return y_val, coverage, metrics


def is_solution_valid(status: int) -> bool:
    """
    Verifica si el solver encontró solución válida.
    
    Args:
        status: Estado retornado por solver.Solve()
        
    Returns:
        True si status es OPTIMAL (0) o FEASIBLE (1)
    """
    return status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE)


def log_solver_result(status: int, total_head: int, n_agents: int) -> str:
    """
    Genera línea de log del resultado del solver.
    
    Args:
        status: Estado del solver
        total_head: Número total de asignaciones
        n_agents: Agentes disponibles
        
    Returns:
        String con información
    """
    status_name = {0: "OPTIMAL", 1: "FEASIBLE", 2: "INFEASIBLE"}.get(status, "UNKNOWN")
    msg = f"ILP result ({status_name}): {total_head} asignaciones (límite {n_agents})"
    logger.info(msg)
    return msg
