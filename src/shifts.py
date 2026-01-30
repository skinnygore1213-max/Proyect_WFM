"""
Procesamiento de catálogo de turnos.

Preselección heurística rápida, scoring y gestión de turnos.
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging
from src.utils import setup_logging
import config

#logger = logging.getLogger(__name__)
logger = setup_logging(__name__, level=logging.INFO, to_file=config.OUTPUT_LOG_FILE)

def quick_score_shifts(
    turnos: pd.DataFrame,
    itv_start: np.ndarray,
    itv_end: np.ndarray,
    required: np.ndarray
) -> pd.Series:
    """
    Scoring rápido: suma de requeridos cubiertos por cada turno (sin pausas).
    
    Aproximación: intervalo [t] está cubierto si turno.start <= t.start AND turno.end >= t.end
    
    Args:
        turnos: DataFrame de turnos con 'start_min' y 'end_min'
        itv_start: Array de inicio de intervalos (minutos)
        itv_end: Array de fin de intervalos (minutos)
        required: Array de requeridos por intervalo
        
    Returns:
        Series con score por cada turno
    """
    def score_one(start_m: int, end_m: int) -> int:
        cover = (start_m <= itv_start) & (end_m >= itv_end)
        return int(np.dot(cover.astype(int), required))
    
    turnos["quick_score"] = np.vectorize(score_one)(turnos["start_min"].values,
                                                        turnos["end_min"].values)
    #scores = turnos.apply(
    #    lambda row: score_one(int(row["start_min"]), int(row["end_min"])),
    #    axis=1
    #)
    return turnos

def preselect_shifts(
    turnos: pd.DataFrame,
    window_start: int,
    window_end: int,
    itv_start: np.ndarray,
    itv_end: np.ndarray,
    required: np.ndarray,
    k_preselect: int
) -> pd.DataFrame:
    """
    Preselecciona K mejores turnos por score rápido.
    
    1. Filtra turnos que solapan con ventana horaria
    2. Scoring rápido (sin pausas)
    3. Retorna top K
    
    Args:
        turnos: DataFrame de turnos disponibles
        window_start: Inicio de ventana detectada (minutos)
        window_end: Fin de ventana detectada (minutos)
        itv_start: Array de inicio de intervalos
        itv_end: Array de fin de intervalos
        required: Array de requeridos
        k_preselect: Número de turnos a preseleccionar
        
    Returns:
        DataFrame de K mejores turnos ordenados por score descendente
        
    Raises:
        RuntimeError: Si ningún turno pisa la ventana
    """
    # Filtro de overlap con ventana
    overlap_mask = ~((turnos["end_min"] <= window_start) | (turnos["start_min"] >= window_end))
    turnos_pref = turnos.loc[overlap_mask].copy().reset_index(drop=True)
    
    if len(turnos_pref) == 0:
        raise RuntimeError("Ningún turno pisa la ventana detectada. Revisa la data.")
    
    # Scoring rápido
    #turnos_pref["quick_score"] = quick_score_shifts(
    #    turnos_pref, itv_start, itv_end, required
    #)

    turnos_pref = quick_score_shifts(
        turnos_pref, itv_start, itv_end, required)

    # Seleccionar top K
    turnos_k = turnos_pref.sort_values("quick_score", ascending=False).head(k_preselect).reset_index(drop=True)
    
    logger.info(f"Preseleccionados {len(turnos_k)} turnos de {len(turnos_pref)} solapantes")
    
    return turnos_k


def build_exact_coverage_vector(
    start_m: int,
    end_m: int,
    descanso1: int,
    descanso2: int,
    inicio_refrigerio: str,
    fin_refrigerio: str,
    itv_start_full: np.ndarray,
    itv_end_full: np.ndarray
) -> np.ndarray:
    """
    Construye vector exacto de cobertura por turno, considerando pausas y almuerzo.
    
    Lógica:
    1. Base: 1 si [start, end) cubre completamente intervalo [i, f)
    2. Restar pausas (breaks) de 15 min
    3. Restar almuerzo (60 min) si existe
    4. Manejo de turnos que cruzan medianoche (+1440)
    
    Args:
        start_m: Inicio del turno (minutos desde medianoche)
        end_m: Fin del turno (minutos desde medianoche)
        descanso1: Boolean (¿hay break 1?)
        descanso2: Boolean (¿hay break 2?)
        inicio_refrigerio: String 'HH:MM' o vacío
        fin_refrigerio: String 'HH:MM' o vacío
        itv_start_full: Array de inicio de todos los intervalos
        itv_end_full: Array de fin de todos los intervalos
        
    Returns:
        Vector booleano (0/1) indicando cobertura por intervalo
    """
    from .time_utils import safe_hhmm_to_min
    
    # Vector base
    base = ((start_m <= itv_start_full) & (end_m >= itv_end_full)).astype(int)
    
    blocks = []  # (inicio, fin) de pausas a restar
    
    # Almuerzo explícito
    if inicio_refrigerio and fin_refrigerio and inicio_refrigerio.strip() and fin_refrigerio.strip():
        a0 = safe_hhmm_to_min(inicio_refrigerio)
        a1 = safe_hhmm_to_min(fin_refrigerio)
        
        if a0 is not None and a1 is not None:
            # Manejo de cruces de medianoche
            if a1 < a0:
                a1 += 60
            if not (start_m <= a0 < end_m):
                a0 += 1440
                a1 += 1440
            blocks.append((a0, a1))
    else:
        a0, a1 = None, None
    
    # Breaks
    if int(descanso1) > 0:
        if a0 is not None:
            b1s = a0 - 15
            b1e = a0
        else:
            b1s = start_m + max(90, (end_m - start_m) // 3)
            b1e = b1s + 15
        blocks.append((b1s, b1e))
    
    if int(descanso2) > 0:
        if a1 is not None:
            b2s = a1 + 120
            b2e = b2s + 15
        else:
            b2e = end_m - max(90, (end_m - start_m) // 3)
            b2s = b2e - 15
        blocks.append((b2s, b2e))
    
    # Aplicar pausas
    mask = base.copy()
    for (bs, be) in blocks:
        cut = ~((itv_end_full <= bs) | (itv_start_full >= be))
        mask[cut] = 0
    
    return mask


def compute_exact_curves(
    turnos: pd.DataFrame,
    itv_start_full: np.ndarray,
    itv_end_full: np.ndarray,
    required_full: np.ndarray
) -> pd.DataFrame:
    """
    Calcula vector de cobertura exacta para cada turno (incluye pausas).
    
    Args:
        turnos: DataFrame de turnos preseleccionados
        itv_start_full: Array de inicio de intervalos (todos)
        itv_end_full: Array de fin de intervalos (todos)
        required_full: Array de requeridos (todos)
        
    Returns:
        DataFrame con columnas 'curve_exact' y 'exact_score' agregadas
    """
    df = turnos.copy()
    
    curves = []
    scores = []
    
    for _, row in df.iterrows():
        curve = build_exact_coverage_vector(
            int(row["start_min"]),
            int(row["end_min"]),
            int(row.get("Descanso1", 0)),
            int(row.get("Descanso2", 0)),
            str(row.get("Inicio_Refrigerio", "")),
            str(row.get("Fin_Refrigerio", "")),
            itv_start_full,
            itv_end_full
        )
        curves.append(curve)
        scores.append(int(np.dot(curve, required_full)))
    
    df["curve_exact"] = curves
    df["exact_score"] = scores

    return df


def select_final_shifts(
    turnos: pd.DataFrame,
    m_final: int,
    cap_per_intensity: int
    ) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Selecciona M mejores turnos por exact_score y construye matriz de cobertura.
    
    Args:
        turnos: DataFrame con columna 'exact_score'
        m_final: Número de turnos a seleccionar
        
    Returns:
        Tupla (turnos_m, shift_matrix) donde:
        - turnos_m: DataFrame de M mejores turnos
        - shift_matrix: ndarray (M, T) con cobertura por turno/intervalo
    """
    # score por hora + híbrido
    turnos["score_por_h"]  = turnos["exact_score"] / turnos["Duracion_Horas"].clip(lower=0.25)
    turnos["score_hibrido"] = config.α*turnos["exact_score"] + config.β*turnos["score_por_h"]

    # penalización por bin de duración
    def bin_duracion(h):
        if h < 7:   return "lt7"
        if h < 8:   return "7_8"
        if h < 9:   return "8_9"
        return "ge9"

    turnos["dur_bin"] = turnos["Duracion_Horas"].apply(bin_duracion)
    freq_bin = turnos["dur_bin"].value_counts().to_dict()
    λ = 0.15
    turnos["penal_bin"] = turnos["dur_bin"].map(lambda b: λ*np.log1p(freq_bin[b]))
    turnos["score_final"] = turnos["score_hibrido"] - turnos["penal_bin"]

    # 1) Cuantizar intensidad
    turnos["intensity"] = turnos["Duracion_Horas"].astype(float).apply(lambda h: (round(h / 0.5) * 0.5))

    # 2) Ordenar por score
    turnos = turnos.sort_values("score_final", ascending=False)

    # 3) Top cap por intensidad
    groups = []
    for intensity, g in turnos.groupby("intensity", sort=False):
        g_top = g.head(cap_per_intensity)
        groups.append(g_top)

    prepool = pd.concat(groups, ignore_index=True)

    # 4) Si faltan para llegar a M_FINAL, rellenar round-robin entre intensidades
    if len(prepool) >= m_final:
        return prepool.head(m_final).reset_index(drop=True)

    # Construir colas por intensidad con los excedentes no tomados en el cap inicial
    taken_idx = set(prepool.index)
    # OJO: índices de prepool son nuevos; rehagamos 'taken' por _id_ estable:
    # Solución robusta: usar un id estable, por ejemplo el índice original:
    tk = turnos.reset_index().rename(columns={"index": "_orig_idx"})
    # recomputar cap inicial sobre tk con _orig_idx
    cap_map = {}
    for intensity, g in tk.groupby("intensity", sort=False):
        cap_map[intensity] = set(g.head(cap_per_intensity)["_orig_idx"].tolist())

    # prepool robusto por _orig_idx
    prepool_mask = tk.apply(lambda r: r["_orig_idx"] in cap_map.get(r["intensity"], set()), axis=1)
    prepool_df = tk[prepool_mask].copy()

    # excedentes por intensidad (cola para round-robin)
    rr_queues = {}
    for intensity, g in tk.groupby("intensity", sort=False):
        rr = g[~g["_orig_idx"].isin(cap_map.get(intensity, set()))]
        rr_queues[intensity] = rr.copy()

    # cuanto falta
    remaining = m_final - len(prepool_df)

    # round-robin: recorrer intensidades en orden de aparición de score
    intensity_order = list(tk["intensity"].drop_duplicates())

    rr_picks = []
    ptr = 0
    while remaining > 0 and len(intensity_order) > 0:
        intensity = intensity_order[ptr % len(intensity_order)]
        queue = rr_queues.get(intensity, None)
        if queue is None or queue.empty:
            # descartar intensidades vacías del round-robin
            intensity_order = [x for x in intensity_order if x != intensity]
            if not intensity_order:
                break
            ptr += 1
            continue

        pick_row = queue.iloc[[0]]  # mejor score restante de esa intensidad
        rr_picks.append(pick_row)
        # quitarlo de la cola
        rr_queues[intensity] = queue.iloc[1:].copy()
        remaining -= 1
        ptr += 1

    # Consolidar final
    if rr_picks:
        rr_block = pd.concat(rr_picks, ignore_index=True)
        final_df = pd.concat([prepool_df, rr_block], ignore_index=True)
    else:
        final_df = prepool_df

    # Orden final por score y recorte exacto
    # Elegimos M_FINAL mejores para el ILP
    final_df = final_df.sort_values("score_final", ascending=False).head(m_final).reset_index(drop=True)
    shift_matrix = np.stack(final_df["curve_exact"].values)  # shape (M, T)
  
    logger.info(f"Seleccionados {len(final_df)} turnos finales para ILP (matriz {shift_matrix.shape})")
    
    return final_df, shift_matrix

def select_ilp_shifts(
    turnos_m: pd.DataFrame,
    # opcionales si quieres crear las vars aquí (no se devuelven):
    solver=None,
    cap_per_shift: int = None,
    n_agents: int = None,
) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Prepara insumos ILP a partir del set final de turnos (turnos_m):

    - Filtra turnos con Asignados > 0.
    - Construye matriz Real_Matrix (stack de 'curve_exact').
    - (Opcional) Crea variables y_r si 'solver' y 'cap_per_shift' están provistos.

    Args:
        turnos_m: DataFrame con al menos columnas:
                  - 'Asignados' (int): cupos asignados por turno
                  - 'curve_exact' (np.ndarray[int]): cobertura 0/1 por intervalo
        solver:   (opcional) instancia de OR-Tools si deseas crear vars aquí.
        cap_per_shift: (opcional) cota superior para y_r si creas vars aquí.
        n_agents: (opcional) solo para logging informativo.

    Returns:
        (turnos_ilp, real_matrix)
        - turnos_ilp : DataFrame filtrado (Asignados > 0), index reseteado.
        - real_matrix: np.ndarray de forma (M_ilp, T) con cobertura por turno/intervalo.
    """
    #Filtrar turnos con demanda positiva para el ILP
    if "Asignados" not in turnos_m.columns:
        raise ValueError("turnos_m debe incluir la columna 'Asignados'.")
    
    if "curve_exact" not in turnos_m.columns:
        raise ValueError("turnos_m debe incluir la columna 'curve_exact'.")

    turnos_ilp = turnos_m[turnos_m["Asignados"] > 0].copy().reset_index(drop=True)

    #Construir matriz real (MxT)
    try:
        real_matrix = np.stack(turnos_ilp["curve_exact"].values)  # shape: (M_ilp, T)
    except Exception as e:
        raise ValueError(f"No fue posible apilar 'curve_exact' a matriz: {e}")

    # Crear variables y_r si se provee solver y cap
    if solver is not None and cap_per_shift is not None:
        # Nota: no retornamos 'y_r' porque el contrato del usuario pide
        # solo (Real_Matrix, Turnos_ILP). Si lo requieres luego, podemos añadirlo.
        _ = [solver.IntVar(0, cap_per_shift, f"y_{j}") for j in range(len(turnos_ilp))]

    # Logging/print
    logger.info(
        f"ILP result: {int(turnos_ilp["Asignados"].sum())} asignaciones de {len(turnos_ilp)} turnos (con límite {n_agents})."
    )

    return turnos_ilp, real_matrix