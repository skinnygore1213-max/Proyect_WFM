"""
Utilidades de conversión de tiempo.

Funciones puras para convertir entre formatos HH:MM, minutos, horas decimales.
Maneja normalizaciones de AM/PM y cruces de medianoche.
"""

from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Tuple, Optional, Any
import math
import re


def hhmm_to_min(texto: str) -> int:
    """
    Convierte 'HH:MM' a minutos desde medianoche.
    """
    s = str(texto).replace("\xa0", " ").strip()
    dt = datetime.strptime(s, "%H:%M")
    return dt.hour * 60 + dt.minute


def hhmm_to_hour(texto: str) -> float:
    """
    Convierte 'HH:MM' a horas en formato decimal.
    """
    dt = datetime.strptime(texto, "%H:%M")
    return dt.hour + (dt.minute / 60)


def min_to_hhmm(minutos: int) -> str:
    """
    Convierte minutos desde medianoche a formato 'HH:MM'.
    """
    h = minutos // 60
    m = minutos % 60
    return f"{h:02d}:{m:02d}"


def parse_hhmm_with_am_pm(texto: str) -> Optional[int]:
    """
    Parsea 'HH:MM:SS AM/PM' (normalizado previamente) a minutos.
    """
    s = str(texto).replace("\xa0", " ").strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%I:%M:%S %p")  # ✅ 12h clock
        return dt.hour * 60 + dt.minute
    except ValueError:
        try:
            dt = datetime.strptime(s, "%I:%M %p")
            return dt.hour * 60 + dt.minute
        except ValueError:
            return None


def extract_hhmm_components(turno: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Extrae componentes de hora de un string como '08:00 a 17:00'.
    """
    if not turno or turno == "":
        return None, None, None, None

    match = re.search(r"(\d{2}):(\d{2})\s+a\s+(\d{2}):(\d{2})", str(turno), re.IGNORECASE)
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
    """
    try:
        return hhmm_to_min(texto)
    except (ValueError, TypeError):
        return default


def parse_time_to_min(value: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Parsea múltiples formatos de tiempo/datetime (típicos de Excel/CSV) a minutos desde medianoche [0..1439].

    Soporta:
    - Strings: 'HH:MM', 'HH:MM:SS', 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM',
              'DD/MM/YYYY HH:MM:SS', variantes con AM/PM (ej. '08:30:00 AM').
    - Objetos: datetime.datetime, datetime.time, pandas.Timestamp.
    - Numéricos estilo Excel:
        * fracción del día (0..1)  -> minutos = frac*1440
        * serial con fracción (ej. 45234.5) -> usa solo la fracción

    Nota:
    - Si no puede parsear, retorna `default` (por defecto None).
    - Para segundos, se ignoran (se trunca a minuto).
    """
    if value is None:
        return default

    # pandas NaN/NaT
    try:
        import pandas as pd  # type: ignore
        if pd.isna(value):
            return default
        if isinstance(value, pd.Timestamp):
            return int(value.hour) * 60 + int(value.minute)
    except Exception:
        pass

    if isinstance(value, datetime):
        return value.hour * 60 + value.minute

    if isinstance(value, dtime):
        return int(value.hour) * 60 + int(value.minute)

    # Excel numeric time / serial
    if isinstance(value, (int, float)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default

        # Caso ambiguo: si te pasan minutos exactos (ej. 510), lo aceptamos
        frac = v - math.floor(v)
        if 0 <= v < 1440 and abs(frac) < 1e-9 and v >= 1:
            return int(v) % 1440

        # Excel: usa la fracción del día
        if 0 <= frac < 1:
            minutes = int(math.floor(frac * 1440 + 1e-9)) % 1440
            return minutes

        return default

    s = str(value).replace("\xa0", " ").strip()
    if not s:
        return default

    low = s.lower()
    if low in {"nan", "nat", "none", "null"}:
        return default

    # Normalización básica de AM/PM tipo Excel latino
    s2 = re.sub(r"\ba\.\s*m\.\b", "AM", s, flags=re.IGNORECASE)
    s2 = re.sub(r"\bp\.\s*m\.\b", "PM", s2, flags=re.IGNORECASE)
    s2 = s2.replace("a. m.", "AM").replace("p. m.", "PM").strip()

    fmts = [
        "%H:%M",
        "%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%I:%M %p",
        "%I:%M:%S %p",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s2, fmt)
            return dt.hour * 60 + dt.minute
        except ValueError:
            continue

    # ISO con "T"
    try:
        if "T" in s2:
            dt = datetime.fromisoformat(s2)
            return dt.hour * 60 + dt.minute
    except Exception:
        pass

    # Último recurso: capturar HH:MM dentro del string
    m = re.search(r"(\d{1,2}):(\d{2})", s2)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh < 24 and 0 <= mm < 60:
            return hh * 60 + mm

    return default

def extraer_horas(turno: object):
    star,star_minute,end,end_minute = extract_hhmm_components(turno)
    if star!=None:
            return {
                'inicio': f"{star:02}:{star_minute:02}",  # Formato HH:MM
                'fin': f"{end:02}:{end_minute:02}"           # Formato HH:MM
                #'Horas_Totales': total_horas
            }
    return {'inicio': None, 'fin': None}  # Devuelve None si está vacío o no se encuentra el patrón

