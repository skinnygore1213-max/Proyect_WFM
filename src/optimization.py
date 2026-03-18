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
from ortools.sat.python import cp_model
from typing import Tuple, List, Dict
import logging
from datetime import timedelta

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
    required_min = np.asarray(required_full, dtype=float) #* 30.0 se convierte en parse_time_intervals de transforms.py 
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
    coverage = coverage_min #/ 30.0 todo se esta calculando en minutos

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

def solve_wfm_semanal(
        n_agents :np.ndarray,
        agents_results :np.ndarray,
        days :np.ndarray, 
        shifts_by_day :np.ndarray,
        shifts_info :np.ndarray,
        quotas :np.ndarray, 
        heuristic_results :np.ndarray,
        MAX_HOURS_WEEK :int,
        REST_MIN_GAP :int,
        #agent_params
        ):
    """
    n_agents: int
    days: range(7)
    shifts_by_day: dict con listas de indices de turnos por dia d
    quotas: dict (j, d) -> cantidad de agentes requeridos
    heuristic_results: dict (i, d) -> indice del turno asignado por tu Fase 1
    agent_params: dict con min_hours, max_hours, pref_windows, etc.
    """
    model = cp_model.CpModel()
    solver = cp_model.CpSolver()

    # -------------------------
    # Preprocesamiento (dicts/sets)
    # -------------------------
    if isinstance(n_agents, (int, np.integer)):
        agent_ids = list(range(int(n_agents)))
    else:
        agent_ids = [int(a) for a in n_agents]

    if days is None:
        days_list = sorted(shifts_by_day.keys())
    else:
        days_list = [int(d) for d in days]
    days_set = set(days_list)

    shifts_by_day = {int(d): [j for j in shifts_by_day.get(d, [])] for d in days_list}

    if isinstance(shifts_info, dict):
        start_min = {j: int(v[0]) for j, v in shifts_info.items()}
        end_min = {j: int(v[1]) for j, v in shifts_info.items()}
        duration = {j: v[2] for j, v in shifts_info.items()}
    else:
        start_min = {j: int(shifts_info[j][0]) for j in range(len(shifts_info))}
        end_min = {j: int(shifts_info[j][1]) for j in range(len(shifts_info))}
        duration = {j: int(shifts_info[j][2]) for j in range(len(shifts_info))}

    if isinstance(heuristic_results, dict):
        assignments = [(int(i), int(d), j) for (i, d), j in heuristic_results.items() if j is not None]
        heuristic_map = {(i, d): j for i, d, j in assignments}
    else:
        assignments = [(int(i), int(d), j) for i, d, j in heuristic_results]
        heuristic_map = {(i, d): j for i, d, j in assignments}

    # 1. VARIABLES, mejorado a partir de todas las signaciones en turnos en ILP, seleccionado en el paso anterior a esta funcion (Bloque 1)
    x = {}
    x_by_agent_day = {}
    x_by_agent_day_shift = {}
    x_by_shift_day = {}
    x_by_agent = {}
    seen = set()

    # Estan en el orden agente, dia, turno
    for i in n_agents:
        for d in days:
            # permitir todos los turnos del catálogo para ese día, no solo el que sugirió el Daily-ILP .
            for j in len(shifts_info):
                key = (int(i), int(d), int(j))
                var = model.NewBoolVar(f"x_{i}_{d}_{j}")
                x[key] = var
                x_by_agent_day.setdefault((int(i), int(d)), []).append(var)
                x_by_agent.setdefault(int(i), []).append((var, int(duration.get(j, 0))))

    # RESTRICCIONES DURAS 
    # 3.Cumplir los cupos (Bloque 3)
    '''
    if isinstance(quotas, dict):
        quota_items = quotas.items()
    else:
        quota_items = (((j, d), quotas[j, d]) for d in days_list for j in shifts_by_day.get(d, []))

    for (j, d), q in quota_items:
        q_int = int(q)
        if q_int <= 0:
            continue
        vars_shift_day = x_by_shift_day.get((j, int(d)))
        if vars_shift_day:
            model.Add(sum(vars_shift_day) >= q_int)
        else:
            model.Add(0 >= q_int)
    '''
    # Descanso minimo entre dias (Bloque 5)
    # REST_MIN_GAP = 660 (11 horas)
    '''
    conflict_next_by_day = {}
    for d in days_list:
        d_next = d + 1
        if d_next not in days_set:
            continue
        shifts_d = shifts_by_day.get(d, [])
        shifts_next = shifts_by_day.get(d_next, [])
        if not shifts_d or not shifts_next:
            continue
        next_starts = np.array([start_min[jp] for jp in shifts_next], dtype=int) + 1440
        conflict_map = {}
        for j in shifts_d:
            rest = next_starts - end_min[j]
            idx = np.nonzero(rest < REST_MIN_GAP)[0]
            if idx.size:
                conflict_map[j] = {shifts_next[k] for k in idx}
        if conflict_map:
            conflict_next_by_day[d] = conflict_map

    for i in agent_ids:
        for d, conflict_map in conflict_next_by_day.items():
            vars_d = x_by_agent_day_shift.get((i, d))
            vars_next = x_by_agent_day_shift.get((i, d + 1))
            if not vars_d or not vars_next:
                continue
            for j, var in vars_d:
                bad_next = conflict_map.get(j)
                if not bad_next:
                    continue
                for jp, var_next in vars_next:
                    if jp in bad_next:
                        model.Add(var + var_next <= 1)
'''
    # Horas semanales: Minimas y Maximas
    # 2.Un turno por dia por agente (Bloque 2)
    '''
    for vars_day in x_by_agent_day.values():
        if len(vars_day) > 1:
            model.AddAtMostOne(vars_day)
    '''
    # BLOQUE 6 - Horas maximas semanales por agente
    for i in n_agents:
        dias_trabajados_vars = []
        for d in days:
            vars_day = x_by_agent_day.get((int(i), int(d)), [])
            if vars_day:
                # Máximo un turno por día
                model.AddAtMostOne(vars_day)
                
                # Variable auxiliar para contar si trabajó el día d
                trabaja_hoy = model.NewBoolVar(f"trabaja_{i}_{d}")
                model.Add(trabaja_hoy == sum(vars_day))
                dias_trabajados_vars.append(trabaja_hoy)

        # Restricción de días: máximo 5 o 6 según tu requerimiento 
        model.Add(sum(dias_trabajados_vars) <= 6) 

        # REQUERIMIENTO IMPERATIVO: Exactamente 44 horas (en minutos)
        pairs = x_by_agent.get(int(i), [])
        if pairs:
            # Usamos igualdad (==) porque es un requerimiento "sí o sí"
            model.Add(sum(var * dur for var, dur in pairs) <= MAX_HOURS_WEEK)

    # 3. SOFT CONSTRAINT: Respetar la Heuristica (Fase 1)
    # Creamos una penalizacion si el Solver decide cambiar lo que se calculo
    penalidades_cambio = []

    for (i, d), turno_h in heuristic_map.items():
        var = x.get((i, d, turno_h))
        if var is None:
            continue
        # Si x[i, d, turno_h] es 0, significa que el solver CAMBIO la propuesta.
        # Queremos MAXIMIZAR la coincidencia, o MINIMIZAR el cambio.
        cambio = model.NewBoolVar(f"cambio_{i}_{d}")
        model.Add(cambio + var == 1)
        penalidades_cambio.append(cambio)

    # 4. OBJETIVO (Bloque 9 + Soft Constraints)
    # Peso alto a mantener la heuristica, peso bajo a romper empates
    costo_cambio = sum(penalidades_cambio) * 10
    tie_breaker = sum((0.0001 * (int(i) + int(d) + j)) * var for (i, d, j), var in x.items())

    model.Minimize(costo_cambio + tie_breaker)

    # 5. EJECUCION
    #status = solver.Solve()
    status = solver.Solve(model)

    return solver, status, x, x_by_agent_day, x_by_shift_day, x_by_agent

def extract_solution_IMLP(solver, status, x, idx_to_turno, shifts_info):
    if status not in [0, 1]: # 0: OPTIMAL, 1: FEASIBLE
        print("No se pudo generar el informe: El solver no encontró una solución legal.")
        return None

    resultados = []
    
    # Recorremos todas las variables x definidas en el solver
    for (agent_id, dia, t_idx), var in x.items():
        if solver.Value(var) == 1: # Si el solver asignó este turno
            # Recuperamos el nombre original del turno y su duración
            turno_id = idx_to_turno[t_idx]
            # Convertimos minutos a horas para el reporte final
            duracion_horas = shifts_info[t_idx][2] / 60 
            
            resultados.append({
                "AgentID": agent_id,
                "Dia_Semana": dia,
                "Turno_ID": turno_id,
                "Horas_Asignadas": duracion_horas
            })

    return resultados
