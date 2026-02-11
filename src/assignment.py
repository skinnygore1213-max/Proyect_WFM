"""
Módulo de asignación de turnos a agentes.

Asignación greedy de turnos a agentes respetando restricciones de horas disponibles.
Mantiene seguimiento de horas asignadas por agente y por día.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
import logging
from src.utils import setup_logging

logger = setup_logging(__name__, level=logging.INFO)

def assign_shifts_to_agents(
    y_val: np.ndarray,
    turnos_m: pd.DataFrame,
    agentes: pd.DataFrame,
    agentes_disponibles_list: List[str],
    dia: str
) -> List[Dict]:
    """
    Asigna turnos a agentes de forma greedy.
    
    Lógica:
    1. Para cada turno j con y_val[j] > 0:
    2.   - Obtener duración del turno
    3.   - Iterar sobre agentes disponibles
    4.   - Si agente tiene horas disponibles >= duración:
    5.     - Asignar turno
    6.     - Restar horas disponibles
    7.     - Remover agente de lista (solo 1 turno por día)
    
    Args:
        y_val: ndarray con número de asignaciones por turno
        turnos_m: DataFrame de turnos con 'Turno_ID', 'Hora_Inicio', 'Hora_Termino', 'Duracion_Horas'
        agentes: DataFrame maestro de agentes (se modifica in-place)
        agentes_disponibles_list: Lista de IDs de agentes disponibles (se modifica in-place)
        
    Returns:
        Lista de diccionarios con asignaciones {Agente, TurnoID, Inicio, Fin}
    """
    asignaciones = []
    agent_ids_copy = agentes_disponibles_list.copy()  # Copia para iterar sin perder el original
    
    for j in range(len(turnos_m)):
        cnt = int(turnos_m.loc[j, "Asignados"])
        
        if cnt == 0:
            continue
        
        # Info del turno
        turno_id = turnos_m.loc[j, "Turno_ID"] if "Turno_ID" in turnos_m.columns else f"T{j:03d}"
        h_ini = str(turnos_m.loc[j, "Hora_Inicio"])
        h_fin = str(turnos_m.loc[j, "Hora_Termino"])
        duracion = int(turnos_m.loc[j, "Duracion_Horas"])
        
        # Asignar cnt veces este turno
        ptr = 0
        for _ in range(cnt):
            while ptr < len(agent_ids_copy):
                agent_id = agent_ids_copy[ptr]
                
                # Verificar si agente tiene horas disponibles
                horas_disp = float(
                    agentes.loc[agentes["AgentID"] == agent_id, "Horas_Disponibles"].values[0]
                )
                
                #fundamental por que no hay otro filtro dentro del ciclo que verifique las horas, si el agente no tiene horas disponibles, se pasa al siguiente
                if horas_disp >= duracion:
                    # Asignar
                    asignaciones.append({
                        "Agente": agent_id,
                        "TurnoID": turno_id,
                        "Inicio": h_ini,
                        "Fin": h_fin
                    })
                    
                    # Actualizar agentes
                    agentes.loc[agentes["AgentID"] == agent_id, "Horas_Asignadas"] += duracion
                    agentes.loc[agentes["AgentID"] == agent_id, "Horas_Disponibles"] -= duracion# actualizamos horas del día
                    agentes.loc[agentes["AgentID"] == agent_id, [dia]] += duracion
                    
                    # Remover agente (1 turno por día max)
                    agent_ids_copy.remove(agent_id)
                    break
                
                ptr += 1
        
        if ptr >= len(agent_ids_copy):
            logger.warning(f"No hay agentes disponibles para turno {turno_id}")
    
    #logger.info(f"Asignadas {len(asignaciones)} asignaciones de turnos")
    
    return asignaciones


def update_daily_hours(
    agentes: pd.DataFrame,
    asignaciones: List[Dict],
    fecha: str,
    turnos_m: pd.DataFrame
) -> pd.DataFrame:
    """
    Actualiza columna de horas por día en dataframe de agentes.
    
    Crea columna con nombre = fecha (si no existe) e incrementa
    para cada agente el número de horas asignadas ese día.
    
    Args:
        agentes: DataFrame de agentes
        asignaciones: Lista de asignaciones del día
        fecha: Identificador del día (string)
        turnos_m: DataFrame de turnos (para consultar duración)
        
    Returns:
        DataFrame actualizado
    """
    df = agentes.copy()
    
    # Crear columna si no existe
    if fecha not in df.columns:
        df[fecha] = 0
    
    # Actualizar horas por agente
    for asig in asignaciones:
        agent_id = asig["Agente"]
        turno_id = asig["TurnoID"]
        
        # Buscar duración en turnos_m
        matching = turnos_m[
            (turnos_m.get("Turno_ID", "") == turno_id) |
            (turnos_m.index.astype(str) == str(turno_id).replace("T", ""))
        ]
        
        if not matching.empty:
            duracion = float(matching.iloc[0]["Duracion_Horas"])
            df.loc[df["AgentID"] == agent_id, fecha] += duracion
    
    return df


def build_assignment_dataframe(asignaciones: List[Dict], fecha: str) -> pd.DataFrame:
    """
    Construye DataFrame de asignaciones para un día con columna de fecha.
    
    Args:
        asignaciones: Lista de diccionarios {Agente, TurnoID, Inicio, Fin}
        fecha: Identificador del día
        
    Returns:
        DataFrame con asignaciones del día
    """
    if not asignaciones:
        return pd.DataFrame(columns=["Agente", "TurnoID", "Inicio", "Fin", "Fecha"])
    
    df = pd.DataFrame(asignaciones)
    df["Fecha"] = fecha
    return df


def build_coverage_dataframe(
    i_min_full: np.ndarray,
    f_min_full: np.ndarray,
    required_full: np.ndarray,
    covered: np.ndarray,
    Real_covered: np.ndarray,
    fecha: str
) -> pd.DataFrame:
    """
    Construye DataFrame de cobertura para un día.
    
    Args:
        i_min_full: Array de inicio de intervalos (minutos)
        f_min_full: Array de fin de intervalos (minutos)
        required_full: Array de requeridos
        covered: Array de cobertura alcanzada
        fecha: Identificador del día
        
    Returns:
        DataFrame con cobertura por intervalo
    """
    under = np.maximum(required_full - Real_covered, 0)
    over = np.maximum(Real_covered - required_full, 0)
    
    df = pd.DataFrame({
        "Inicio_min": i_min_full,
        "Fin_min": f_min_full,
        "Requeridos": required_full,
        "Ideal_Cubierto": covered,
        "Real_Cubierto": Real_covered,
        "Under": under,
        "Over": over,
        "Fecha": fecha
    })
    
    return df


def format_coverage_for_export(coverage_df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas formateadas 'Inicio_HHMM' y 'Fin_HHMM' a cobertura.
    
    Args:
        coverage_df: DataFrame de cobertura
        
    Returns:
        DataFrame con columnas HH:MM agregadas
    """
    df = coverage_df.copy()
    
    def min_to_hhmm(m):
        return f"{int(m)//60:02d}:{int(m)%60:02d}"
    
    df["Inicio_HHMM"] = df["Inicio_min"].apply(min_to_hhmm)
    df["Fin_HHMM"] = df["Fin_min"].apply(min_to_hhmm)
    
    return df
