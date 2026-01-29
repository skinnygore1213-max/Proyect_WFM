"""
Detección de ventana horaria y cálculo de cobertura.

Funciones para identificar la ventana de operación automáticamente
y gestionar la cobertura por intervalo.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def detect_time_window(
    required: np.ndarray,
    i_min: np.ndarray,
    f_min: np.ndarray
) -> Tuple[Optional[int], Optional[int]]:
    """
    Detecta ventana horaria automáticamente de la curva de requeridos.
    
    Lógica:
    - Si todos los intervalos tienen required > 0 => ventana 24/7
    - Si no => desde primer intervalo con required > 0 hasta el último
    - Si ninguno tiene required > 0 => retorna (None, None)
    
    Args:
        required: Array de requeridos por intervalo
        i_min: Array de inicio de intervalos (minutos)
        f_min: Array de fin de intervalos (minutos)
        
    Returns:
        Tupla (window_start, window_end) en minutos desde medianoche,
        o (None, None) si no hay demanda
    """
    pos_mask = required > 0
    
    if pos_mask.sum() == len(required):
        # Todos > 0 => 24h
        window_start = i_min.min()
        window_end = f_min.max()
    elif pos_mask.any():
        # Desde primer a último intervalo con demanda
        window_start = i_min[pos_mask].min()
        window_end = f_min[pos_mask].max()
    else:
        # Sin demanda positiva
        window_start, window_end = None, None
    
    return window_start, window_end


def filter_to_window(
    i_min: np.ndarray,
    f_min: np.ndarray,
    required: np.ndarray,
    window_start: int,
    window_end: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """
    Filtra intervalos a la ventana detectada.
    
    Args:
        i_min: Array de inicio de intervalos
        f_min: Array de fin de intervalos
        required: Array de requeridos
        window_start: Inicio de ventana
        window_end: Fin de ventana
        
    Returns:
        Tupla (i_min_ventana, f_min_ventana, required_ventana, T)
        donde T es el número de intervalos dentro de la ventana
    """
    win_mask = (i_min >= window_start) & (f_min <= window_end)
    i_min_w = i_min[win_mask]
    f_min_w = f_min[win_mask]
    required_w = required[win_mask]
    T = len(required_w)
    
    return i_min_w, f_min_w, required_w, T


def format_time_range(start_min: int, end_min: int) -> str:
    """
    Formatea un rango de tiempo [start_min, end_min) como 'HH:MM a HH:MM'.
    
    Args:
        start_min: Inicio en minutos
        end_min: Fin en minutos
        
    Returns:
        String formateado 'HH:MM a HH:MM'
    """
    h_s, m_s = start_min // 60, start_min % 60
    h_e, m_e = end_min // 60, end_min % 60
    return f"{h_s:02d}:{m_s:02d} a {h_e:02d}:{m_e:02d}"


def log_window_info(
    window_start: int,
    window_end: int,
    num_intervals: int
) -> str:
    """
    Genera línea de log con información de ventana.
    
    Args:
        window_start: Inicio de ventana (minutos)
        window_end: Fin de ventana (minutos)
        num_intervals: Número de intervalos en ventana
        
    Returns:
        String con información formateada
    """
    window_str = format_time_range(window_start, window_end)
    msg = f"Ventana horaria: {window_str} ({num_intervals} intervalos)"
    logger.info(msg)
    return msg


def validate_coverage_vector(
    coverage: np.ndarray,
    required: np.ndarray
) -> dict:
    """
    Calcula métricas de cobertura básicas.
    
    Args:
        coverage: Array de cobertura alcanzada
        required: Array de requeridos
        
    Returns:
        Dict con métricas: undercoverage, overcoverage, mae, rmse, mape
    """
    diff = coverage - required
    under = np.maximum(-diff, 0.0)
    over = np.maximum(diff, 0.0)
    
    mae = np.mean(np.abs(diff))
    rmse = np.sqrt(np.mean(diff ** 2))
    
    mask_pos = required > 0
    if mask_pos.any():
        mape = np.mean(np.abs(diff[mask_pos]) / required[mask_pos])
    else:
        mape = 0.0
    
    return {
        "under": under,
        "over": over,
        "undercoverage_total": under.sum(),
        "overcoverage_total": over.sum(),
        "mae": mae,
        "rmse": rmse,
        "mape": mape
    }
