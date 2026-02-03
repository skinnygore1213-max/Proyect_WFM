"""
Módulo de optimización ILP.

Construye y resuelve el ILP compacto diario usando OR-Tools (SCIP).
Incluye coste marginal creciente y penalizaciones under/over.

IMPORTANTE (nueva lógica en minutos):
  - shift_matrix[j,t] representa MINUTOS (0..30) cubiertos por turno j en intervalo t
  - required_full[t] viene en AGENTES, pero la restricción usa required_full[t] * 30 (minutos)
  - u/o están en MINUTOS
  - costos under/over se escalan por 30 para mantener equivalencia a “agentes”
"""

import numpy as np
from ortools.linear_solver import pywraplp
from typing import Tuple, List, Dict
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
) -> Tuple[pywraplp.Solver, List, List, List, int, int, int]:
    """
    Construye y resuelve el ILP diario con coste marginal creciente.

    Returns:
        (solver, y, u, o, M, T, status)
        - status es el estado de solver.Solve()
    """
    if shift_matrix is None or not isinstance(shift_matrix, np.ndarray):
        raise ValueError("shift_matrix debe ser un np.ndarray (M, T).")

    M, T = shift_matrix.shape

    if required_full is None:
        raise ValueError("required_full no puede ser None.")
    if len(required_full) != T:
        raise ValueError(f"Inconsistencia: shift_matrix.T={T} != required.len={len(required_full)}")

    # Solver
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("No se pudo crear el solver SCIP. Verifica instalación OR-Tools + SCIP.")

    solver.SetTimeLimit(int(solver_ms))
    # Nota: algunos builds de SCIP aceptan random_seed así; si no, simplemente ignora la línea
    try:
        solver.SetSolverSpecificParametersAsString(f"random_seed={int(random_seed)}")
    except Exception:
        pass

    # Variables
    y = [solver.IntVar(0, int(cap_per_shift), f"y_{j}") for j in range(M)]
    u = [solver.NumVar(0.0, solver.infinity(), f"u_{t}") for t in range(T)]  # minutos
    o = [solver.NumVar(0.0, solver.infinity(), f"o_{t}") for t in range(T)]  # minutos

    # Segmentación (coste marginal creciente)
    seg_width = int(seg_width)
    if seg_width <= 0:
        raise ValueError("seg_width debe ser > 0.")
    K = int(np.ceil(cap_per_shift / seg_width))
    seg = [[solver.IntVar(0, seg_width, f"seg_{j}_{k}") for k in range(K)] for j in range(M)]

    # y[j] = sum_k seg[j][k]
    for j in range(M):
        solver.Add(y[j] == sum(seg[j]))

    # Restricción balance por intervalo (en minutos)
    required_min = np.asarray(required_full, dtype=float) * 30.0
    for t in range(T):
        coverage_expr = sum(y[j] * int(shift_matrix[j, t]) for j in range(M))  # minutos
        solver.Add(coverage_expr - required_min[t] == o[t] - u[t])

    # No exceder agentes disponibles
    solver.Add(sum(y) <= int(n_agents))

    # Objetivo:
    # - u/o en minutos -> dividir alpha/beta por 30 para equivalencia a costo por “agente”
    obj = (alpha_under / 30.0) * sum(u) + (beta_over / 30.0) * sum(o)

    # Coste marginal creciente por turno (por segmento)
    for j in range(M):
        for k in range(K):
            mult = (1.0 + seg_mult_step * k)
            obj += float(gamma_head) * float(mult) * seg[j][k]

    # Ruido pequeño opcional para romper empates (sobre y[j])
    if noise_eps and noise_eps > 0:
        rng = np.random.default_rng(int(random_seed))
        for j in range(M):
            obj += float(rng.uniform(0, noise_eps)) * y[j]

    solver.Minimize(obj)

    # Resolver aquí (tu main.py espera que build_daily_ilp retorne status)
    status = solver.Solve()
    logger.info(
        f"ILP Solver resuelto: status={status} "
        f"(OPTIMAL={pywraplp.Solver.OPTIMAL}, FEASIBLE={pywraplp.Solver.FEASIBLE}, "
        f"INFEASIBLE={pywraplp.Solver.INFEASIBLE})"
    )

    return solver, y, u, o, M, T, status


def extract_solution(
    solver: pywraplp.Solver,
    y: List,
    u: List,
    o: List,
    shift_matrix: np.ndarray,
    required_full: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    Extrae la solución:
      - y_val: asignaciones por turno (agentes)
      - coverage: cobertura por intervalo en "agente-equivalente" (minutos/30)
      - metrics: under/over en minutos y también en agentes-equivalente
    """
    y_val = np.array([int(round(v.solution_value())) for v in y], dtype=int)

    # Cobertura en minutos
    coverage_min = np.zeros(len(required_full), dtype=float)
    for j, cnt in enumerate(y_val):
        coverage_min += float(cnt) * shift_matrix[j]

    # Convertimos a agentes-equivalente
    coverage = coverage_min / 30.0

    under_val = np.array([float(u[t].solution_value()) for t in range(len(u))], dtype=float)  # minutos
    over_val  = np.array([float(o[t].solution_value()) for t in range(len(o))], dtype=float)  # minutos

    metrics = {
        "total_assignments": int(y_val.sum()),
        "undercoverage_total_min": float(under_val.sum()),
        "overcoverage_total_min": float(over_val.sum()),
        "undercoverage_total_agents": float(under_val.sum() / 30.0),
        "overcoverage_total_agents": float(over_val.sum() / 30.0),
        "objective": float(solver.Objective().Value())
    }

    logger.info(
        f"Solución: {metrics['total_assignments']} asignaciones, "
        f"bajo={metrics['undercoverage_total_agents']:.2f} agentes-eq "
        f"({metrics['undercoverage_total_min']:.0f} min), "
        f"sobre={metrics['overcoverage_total_agents']:.2f} agentes-eq "
        f"({metrics['overcoverage_total_min']:.0f} min)"
    )

    return y_val, coverage, metrics


def is_solution_valid(status: int) -> bool:
    """
    Verifica si el solver encontró solución válida.
    True si status es OPTIMAL o FEASIBLE.
    """
    return status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE)
