"""
Procesamiento de catálogo de turnos.

Preselección heurística rápida, scoring y gestión de turnos.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple
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
    cap_per_intensity: int,
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
    turnos_pref = quick_score_shifts(
        turnos_pref, itv_start, itv_end, required)
    
    # 1) Cuantizar intensidad
    turnos_pref["intensity"] = turnos_pref["Duracion_Horas"].astype(float).apply(lambda h: (round(h / 0.5) * 0.5))
    
    # Seleccionar top K
    
    #turnos_k = turnos_pref.sort_values("quick_score", ascending=False).head(k_preselect).reset_index(drop=True)
    
    logger.info(f"Preseleccionados {len(turnos_pref)} turnos solapantes")
    
    return turnos_pref


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
    Construye vector exacto de cobertura por turno, considerando pausas y refrigerio.

    ✅ Mantiene exactamente los 48 intervalos de 30 minutos (00:00–23:30).
    ✅ Retorna minutos efectivos trabajables dentro del intervalo (0..30), NO binario.

    Lógica por intervalo [is, ie):
        base    = overlap([start_m, end_m), [is, ie))
        blocked = overlap(union(bloques_no_disponibles), [is, ie))
        work    = max(0, base - blocked)

    Bloques no disponibles:
      - Refrigerio: desde Inicio_Refrigerio hasta Fin_Refrigerio (si ambos existen)
      - Breaks (Descanso1/2): 15 min cada uno (ubicados de forma razonable dentro del turno)
    """
    from .time_utils import parse_time_to_min

    shift_s = int(start_m)
    shift_e = int(end_m)

    # Base: minutos de solape turno vs intervalo (0..30 por bucket)
    base = np.maximum(
        0,
        np.minimum(shift_e, itv_end_full) - np.maximum(shift_s, itv_start_full)
    ).astype(int)

    blocks = []  # lista de (inicio, fin) en minutos, dentro del turno

    def _clip_to_shift(bs: int, be: int):
        bs = max(int(bs), shift_s)
        be = min(int(be), shift_e)
        if be <= bs:
            return None
        return (bs, be)

    def _overlap_len(a_s: int, a_e: int, b_s: int, b_e: int) -> int:
        return max(0, min(a_e, b_e) - max(a_s, b_s))

    # -------------------------
    # 1) Refrigerio (si hay inicio/fin)
    # -------------------------
    a0 = parse_time_to_min(inicio_refrigerio, default=None)
    a1 = parse_time_to_min(fin_refrigerio, default=None)

    a0_adj = a1_adj = None
    if a0 is not None and a1 is not None:
        # Si el bloque cruza medianoche, empújalo al día siguiente
        if a1 < a0:
            a1 += 1440

        # Alineación al turno: elegimos la versión (día base o +1440) que más solape tenga con el turno
        cand0 = (a0, a1)
        cand1 = (a0 + 1440, a1 + 1440)
        best = max([cand0, cand1], key=lambda ab: _overlap_len(shift_s, shift_e, ab[0], ab[1]))
        clipped = _clip_to_shift(best[0], best[1])
        if clipped is not None:
            blocks.append(clipped)
            a0_adj, a1_adj = clipped

    # -------------------------
    # 2) Breaks (15 min cada uno)
    # -------------------------
    shift_len = max(0, shift_e - shift_s)

    def _place_break_15(preferred_start: int, *, prefer_end_at: int | None = None, min_start: int | None = None):
        """
        Crea un bloque [bs, bs+15) dentro del turno, con clamps.
        - Si prefer_end_at está definido, intenta terminar exactamente ahí (útil para break antes de refrigerio).
        - min_start fuerza bs >= min_start (útil para break después de refrigerio).
        """
        if shift_len < 15:
            return None

        if prefer_end_at is not None:
            be = int(max(shift_s, min(prefer_end_at, shift_e)))
            bs = be - 15
            if min_start is not None:
                bs = max(bs, int(min_start))
                be = bs + 15
            if bs < shift_s or be > shift_e:
                return None
            return (bs, be)

        bs = int(preferred_start)
        if min_start is not None:
            bs = max(bs, int(min_start))
        bs = max(shift_s, min(bs, shift_e - 15))
        return (bs, bs + 15)

    # Break 1
    if int(descanso1) > 0:
        if a0_adj is not None:
            b1 = _place_break_15(a0_adj - 15, prefer_end_at=a0_adj)
        else:
            # ~1/3 del turno, pero al menos 60 min después de iniciar
            b1 = _place_break_15(shift_s + int(max(60, shift_len * 0.33)))
        if b1 is not None:
            blocks.append(b1)

    # Break 2
    if int(descanso2) > 0:
        if a1_adj is not None:
            # después del refrigerio (+120 min, clamped) y nunca antes de a1
            b2 = _place_break_15(a1_adj + 120, min_start=a1_adj)
        else:
            # ~2/3 del turno, pero deja aire antes de terminar
            b2 = _place_break_15(shift_s + int(max(shift_len * 0.66, shift_len - 120)))
        if b2 is not None:
            blocks.append(b2)

    # -------------------------
    # 3) Unir (union) bloques para no doble-contar solapes
    # -------------------------
    merged = []
    if blocks:
        blocks_sorted = sorted(blocks, key=lambda x: x[0])
        cur_s, cur_e = blocks_sorted[0]
        for bs, be in blocks_sorted[1:]:
            if bs <= cur_e:
                cur_e = max(cur_e, be)
            else:
                merged.append((cur_s, cur_e))
                cur_s, cur_e = bs, be
        merged.append((cur_s, cur_e))

    # -------------------------
    # 4) blocked por intervalo y work final
    # -------------------------
    blocked = np.zeros_like(base, dtype=int)
    for bs, be in merged:
        blocked += np.maximum(
            0,
            np.minimum(be, itv_end_full) - np.maximum(bs, itv_start_full)
        ).astype(int)

    work = base - blocked
    work = np.clip(work, 0, 30).astype(int)
    return work


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
    score_column: str,
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
    turnos["score_por_h"]  = turnos[score_column] / turnos["Duracion_Horas"].clip(lower=0.25)
    turnos["score_hibrido"] = config.α*turnos[score_column] + config.β*turnos["score_por_h"]

    # penalización por bin de duración
    def bin_duracion(h):
        if h < 4:   return "lt4"
        if h < 5:   return "4_5"
        if h < 6:   return "5_6"
        if h < 7:   return "6_7"
        #if h < 8:   return "7_8"
        #if h < 9:   return "8_9"
        return "ge7"

    turnos["dur_bin"] = turnos["Duracion_Horas"].apply(bin_duracion)
    freq_bin = turnos["dur_bin"].value_counts().to_dict()
    λ = 0.15
    turnos["penal_bin"] = turnos["dur_bin"].map(lambda b: λ*np.log1p(freq_bin[b]))
    turnos["score_final"] = turnos["score_hibrido"] - turnos["penal_bin"]

    # Orden final por score y recorte exacto
    # Elegimos M_FINAL mejores para el ILP
    #final_df = turnos.sort_values("score_final", ascending=False).head(m_final).reset_index(drop=True)
    #shift_matrix = np.stack(final_df["curve_exact"].values)  # shape (M, T)
  
    #logger.info(f"Seleccionados {len(final_df)} turnos finales para ILP (M={m_final})")
    
    return turnos

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
        
    """
    #Filtrar turnos con demanda positiva para el ILP
    if "Asignados" not in turnos_m.columns:
        raise ValueError("turnos_m debe incluir la columna 'Asignados'.")
    
    if "curve_exact" not in turnos_m.columns:
        raise ValueError("turnos_m debe incluir la columna 'curve_exact'.")

    turnos_ilp = turnos_m[turnos_m["Asignados"] > 0].copy().reset_index(drop=True)

    # Crear variables y_r si se provee solver y cap
    if solver is not None and cap_per_shift is not None:
        # Nota: no retornamos 'y_r' porque el contrato del usuario pide
        # solo (Real_Matrix, Turnos_ILP). Si lo requieres luego, podemos añadirlo.
        _ = [solver.IntVar(0, cap_per_shift, f"y_{j}") for j in range(len(turnos_ilp))]

    # Logging/print
    logger.info(
       f"ILP result: {int(turnos_ilp['Asignados'].sum())} asignaciones de {len(turnos_ilp)} turnos (con límite {n_agents})."
    )

    return turnos_ilp

def select_shifts_by_intensity(
    turnos: pd.DataFrame,
    score_column: str,
    n_preselect: int,
    cap_per_intensity: int
    #intensity_levels: List[float],
) -> pd.DataFrame:
    """
    Selecciona turnos por niveles de intensidad, limitando por cap por nivel.
    
    Args:
        turnos: DataFrame de turnos con columna 'Duracion_Horas'
        intensity_levels: Lista de niveles de intensidad (horas)
        cap_per_intensity: Límite de turnos a seleccionar por nivel
    Returns:
        DataFrame de turnos seleccionados
    """
    
    # 2) Ordenar por score
    turnos = turnos.sort_values(score_column, ascending=False)
    
    # 3) Top cap por intensidad
    groups = []
    for intensity, g in turnos.groupby("intensity", sort=False):
        g_top = g.head(cap_per_intensity)
        groups.append(g_top)

    prepool = pd.concat(groups, ignore_index=True)

    # 4) Si faltan para llegar a M_FINAL, rellenar round-robin entre intensidades
    if len(prepool) >= n_preselect:
        return prepool.head(n_preselect).reset_index(drop=True)

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
    remaining = n_preselect - len(prepool_df)

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

    # Volver a las columnas originales (quitamos auxiliares)
    final_df = final_df.drop(columns=["_orig_idx"], errors="ignore").reset_index(drop=True)
    # Seleccionar top K
    turnos_k = final_df.sort_values(score_column, ascending=False).head(n_preselect).reset_index(drop=True)
        
    logger.info(f"Preseleccionados {len(turnos_k)} turnos de {len(turnos)} procesados por intensidad.")
    
    return turnos_k

def prepare_ilp_inputs(
    turnos: pd.DataFrame,
) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Prepara insumos ILP a partir del set final de turnos (turnos_m):

    - Filtra turnos con Asignados > 0.
    - Construye matriz Matrix (stack de 'curve_exact').

    Args:
        turnos_m: DataFrame con al menos columnas:
                  - 'Asignados' (int): cupos asignados por turno
                  - 'curve_exact' (np.ndarray[int]): cobertura 0/1 por intervalo
    Returns:    matrix para cobertura de turnos/intervalos
    """
#Construir matriz real (MxT)
    try:
        return_matrix = np.stack(turnos["curve_exact"].values)  # shape: (M_ilp, T)
    except Exception as e:
        raise ValueError(f"No fue posible apilar 'curve_exact' a matriz: {e}")
    
    return return_matrix