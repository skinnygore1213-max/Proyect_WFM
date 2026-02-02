"""
Transformación y normalización de datos.

Funciones de limpieza, normalización de formatos (AM/PM, HH:MM),
relleno de NaNs y conversión a tipos adecuados.
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from typing import Tuple

from .time_utils import hhmm_to_min, hhmm_to_hour, safe_hhmm_to_min


def normalize_am_pm(series: pd.Series) -> pd.Series:
    """
    Normaliza formatos de AM/PM en una Series (convierte a 24h si es necesario).
    
    Reemplaza patrones como 'a. m.' y 'p. m.' por 'AM' y 'PM'.
    
    Args:
        series: Series con strings potencialmente con patrones AM/PM
        
    Returns:
        Series normalizada con 'AM' y 'PM' únicamente
    """
    s = series.astype(str).str.strip()
    s = s.str.replace(r"a\.\s*m\.", "AM", regex=True)
    s = s.str.replace(r"p\.\s*m\.", "PM", regex=True)
    return s


def parse_time_intervals(curva: pd.DataFrame) -> pd.DataFrame:
    """
    Parsea columna 'Intervalo' de la curva a datetime y genera 'Fin'.
    
    Asume que cada intervalo es de 30 minutos.
    Normaliza AM/PM antes de parsear.
    
    Args:
        curva: DataFrame con columna 'Intervalo' en formato 'HH:MM:SS AM/PM'
        
    Returns:
        DataFrame con columnas 'Intervalo' (datetime) y 'Fin' agregada
    """
    df = curva.copy()
    
    # Normalizar AM/PM
    df["Intervalo"] = df["Intervalo"].astype(str).str.strip()
    df["Intervalo"] = normalize_am_pm(df["Intervalo"])
    
    # Parsear a datetime
    df["Intervalo"] = pd.to_datetime(
        df["Intervalo"], 
        format="%I:%M:%S %p",
        errors='coerce'
    )
    
    # Generar 'Fin' (30 min después)
    df["Fin"] = df["Intervalo"] + timedelta(minutes=30)
    
    return df


def process_turnos_catalog(turnos: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia y normaliza el catálogo de turnos.
    
    - Filtra solo turnos disponibles (Avail==1)
    - Convierte horas a minutos desde medianoche
    - Maneja turnos que cruzan medianoche (+1440 minutos)
    - Normaliza Descanso1, Descanso2 como int
    - Limpia Inicio_Refrigerio, Fin_Refrigerio
    
    Args:
        turnos: DataFrame con catálogo completo de turnos
        
    Returns:
        DataFrame filtrado y normalizado
    """
    df = turnos.copy()
    
    # Filtrar disponibles
    df = df[df["Avail"] == 1].copy().reset_index(drop=True)
    
    # Normalizar strings
    df["Hora_Inicio"] = df["Hora_Inicio"].astype(str).str.strip()
    df["Hora_Termino"] = df["Hora_Termino"].astype(str).str.strip()
    
    # Convertir a minutos
    df["start_min"] = df["Hora_Inicio"].apply(safe_hhmm_to_min)
    df["end_min"] = df["Hora_Termino"].apply(safe_hhmm_to_min)
    
    # Manejo de turno que cruza medianoche
    df.loc[df["end_min"] < df["start_min"], "end_min"] += 1440
    
    # Normalizar descansos
    for col in ["Descanso1", "Descanso2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        else:
            df[col] = 0
    
    # Normalizar refrigerios
    for col in ["Inicio_Refrigerio", "Fin_Refrigerio"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        else:
            df[col] = ""
    
    # Duración en horas (desde H.Efectivas)
    if "H.Efectivas" in df.columns:
        df["Duracion_Horas"] = df["H.Efectivas"].astype(str).str.strip().apply(
            lambda x: hhmm_to_hour(x) if x and x != "" else 0
        )
    else:
        # Calcular desde start_min y end_min como fallback
        df["Duracion_Horas"] = (df["end_min"] - df["start_min"]) / 60
    
    return df

def process_agentes_catalog(agentes: pd.DataFrame, max_hours_week: int) -> pd.DataFrame:
    df = _normalize_columns(agentes)

    # 1) Detectar columna de disponibilidad (sin romper si cambió de nombre)
    if "Disponible" not in df.columns:
        candidates = ["Avail", "Available", "Disponibilidad", "Disponibles", "DISPONIBLE"]
        found = next((c for c in candidates if c in df.columns), None)

        if found is not None:
            df["Disponible"] = df[found]
            logger.warning(f"No existe 'Disponible'. Usando '{found}' como disponibilidad.")
        else:
            # si no existe ninguna, asumimos todos disponibles (o puedes asumir 0 si prefieres)
            df["Disponible"] = 1
            logger.warning("No existe columna de disponibilidad. Se asume Disponible=1 para todos.")

    # 2) Normalizar a 0/1
    df["Disponible"] = _to_binary_available(df["Disponible"])

    # 3) Tracking de horas
    df["Horas_Disponibles"] = max_hours_week
    df["Horas_Asignadas"] = 0

    return df

def convert_to_minutes(curva: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte columnas de datetime 'Intervalo' y 'Fin' a minutos desde medianoche.
    
    Agrega columnas:
    - i_min: inicio en minutos
    - f_min: fin en minutos
    
    Args:
        curva: DataFrame con columnas 'Intervalo' y 'Fin' como datetime
        
    Returns:
        DataFrame con columnas i_min y f_min agregadas
    """
    df = curva.copy()
    
    def to_min(t: pd.Timestamp) -> int:
        return t.hour * 60 + t.minute
    
    df["i_min"] = df["Intervalo"].apply(to_min)
    df["f_min"] = df["Fin"].apply(to_min)
    
    # Manejo de cruces de medianoche
    df.loc[df["f_min"] < df["i_min"], "f_min"] += 1440
    
    return df


def filter_by_date(curva: pd.DataFrame) -> list:
    """
    Agrupa curva por fecha y retorna lista de fechas únicas ordenadas.
    
    Args:
        curva: DataFrame con columna 'Fecha'
        
    Returns:
        Lista de fechas únicas ordenadas
    """
    curva =sorted(curva['Fecha'].unique())
    #curva["dia"] = pd.to_datetime(curva["Fecha"],format="%ddd")

    return curva


def filter_available_agents(
    agentes: pd.DataFrame, 
    disponible_col: str,
    hours_available_col: str = 'Horas_Disponibles'
) -> pd.DataFrame:
    """
    Filtra agentes que están disponibles y tienen horas pendientes.
    
    Args:
        agentes: DataFrame de agentes
        disponible_col: Nombre de columna de disponibilidad
        hours_available_col: Nombre de columna de horas disponibles
        
    Returns:
        DataFrame filtrado solo con agentes disponibles y con horas > 0
    """
    df = agentes[agentes[disponible_col] == 1].copy()
    df = df[df[hours_available_col] > 0].copy()
    return df.reset_index(drop=True)

import logging

logger = logging.getLogger(__name__)

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)  # quita BOM si viene en el header
        .str.strip()                             # quita espacios al inicio/fin
    )
    return df

def _to_binary_available(s: pd.Series) -> pd.Series:
    # Convierte varios formatos a 0/1: 1/0, True/False, SI/NO, YES/NO, etc.
    s2 = s.astype(str).str.strip().str.lower()

    mapping = {
        "1": 1, "0": 0,
        "true": 1, "false": 0,
        "si": 1, "sí": 1, "no": 0,
        "yes": 1, "y": 1, "n": 0,
        "disponible": 1, "nodisponible": 0,
        "": 0, "nan": 0
    }

    out = s2.map(mapping)

    # si no mapeó, intenta numérico
    out = out.fillna(pd.to_numeric(s2, errors="coerce"))

    # default 0 si sigue NaN
    out = out.fillna(0).astype(int)

    # fuerza binario
    return out.clip(0, 1)

def safe_numeric(series: pd.Series, fillna_value: int = 0) -> pd.Series:
    """
    Convierte Series a numérico, rellenando NaNs y manteniendo como int.
    
    Args:
        series: Series a convertir
        fillna_value: Valor para rellenar NaNs
        
    Returns:
        Series numérica (int)
    """
    return pd.to_numeric(series, errors='coerce').fillna(fillna_value).astype(int)
