"""
Utilidades de conversión de tiempo.

Funciones puras para convertir entre formatos HH:MM, minutos, horas decimales.
Maneja normalizaciones de AM/PM y cruces de medianoche.
"""

from datetime import datetime
from typing import Tuple, Optional


def hhmm_to_min(texto: str) -> int:
    """
    Convierte 'HH:MM' a minutos desde medianoche.
    
    Args:
        texto: String en formato 'HH:MM'
        
    Returns:
        Minutos desde medianoche (0-1439)
        
    Ejemplo:
        >>> hhmm_to_min("08:30")
        510
    """
    s = str(texto).replace("\xa0", " ").strip()
    dt = datetime.strptime(s, "%H:%M")
    return dt.hour * 60 + dt.minute


def hhmm_to_hour(texto: str) -> float:
    """
    Convierte 'HH:MM' a horas en formato decimal.
    
    Args:
        texto: String en formato 'HH:MM'
        
    Returns:
        Horas en decimal (ej: 8.5 = 8h30m)
        
    Ejemplo:
        >>> hhmm_to_hour("08:30")
        8.5
    """
    dt = datetime.strptime(texto, "%H:%M")
    return dt.hour + (dt.minute / 60)


def min_to_hhmm(minutos: int) -> str:
    """
    Convierte minutos desde medianoche a formato 'HH:MM'.
    
    Args:
        minutos: Entero en rango [0, 1439]
        
    Returns:
        String en formato 'HH:MM'
        
    Ejemplo:
        >>> min_to_hhmm(510)
        '08:30'
    """
    h = minutos // 60
    m = minutos % 60
    return f"{h:02d}:{m:02d}"


def parse_hhmm_with_am_pm(texto: str) -> Optional[int]:
    """
    Parsea 'HH:MM:SS AM/PM' (normalizado previamente) a minutos.
    
    Args:
        texto: String en formato 'HH:MM:SS AM' o 'HH:MM:SS PM'
        
    Returns:
        Minutos desde medianoche, o None si no puede parsear
        
    Ejemplo:
        >>> parse_hhmm_with_am_pm("08:30:00 AM")
        510
    """
    s = str(texto).replace("\xa0", " ").strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%H:%M:%S %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        return None


def extract_hhmm_components(turno: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Extrae componentes de hora de un string como '08:00 a 17:00'.
    
    Args:
        turno: String con formato 'HH:MM a HH:MM'
        
    Returns:
        Tupla (hora_inicio, minutos_inicio, hora_fin, minutos_fin), o (None, None, None, None)
        
    Ejemplo:
        >>> extract_hhmm_components("08:00 a 17:00")
        (8, 0, 17, 0)
    """
    import re
    
    if not turno or turno == "":
        return None, None, None, None
    
    match = re.search(r'(\d{2}):(\d{2})\s+a\s+(\d{2}):(\d{2})', turno, re.IGNORECASE)
    if match:
        hora_inicio = int(match.group(1))
        minutos_inicio = int(match.group(2))
        hora_fin = int(match.group(3))
        minutos_fin = int(match.group(4))
        return hora_inicio, minutos_inicio, hora_fin, minutos_fin
    
    return None, None, None, None


def safe_hhmm_to_min(texto: str, default: int = 0) -> int:
    """
    Conversión segura con valor por defecto en caso de error.
    
    Args:
        texto: String en formato 'HH:MM'
        default: Valor a retornar si falla el parseo
        
    Returns:
        Minutos desde medianoche, o default si error
    """
    try:
        return hhmm_to_min(texto)
    except (ValueError, TypeError):
        return default
