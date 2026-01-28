"""
Utilidades generales: logging, validaciones, helpers.
"""

import logging
import sys
from datetime import datetime
from typing import List, Optional


def setup_logging(name: str = __name__, 
    level=logging.INFO,
    to_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configura logger con salida a consola y (opcionalmente) archivo.
    Args:
        name: Nombre del logger
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR)
        to_file: Ruta de archivo para log (opcional).
        file_level: Nivel específico para el archivo (si None, usa 'level')
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Evita duplicados por propagación al root
    logger.propagate = False
    new_handlers = []
    # Handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    # Formato
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    #new_handlers.append(console_handler)

    # Agregar si no existe
    if not logger.handlers:
        logger.addHandler(console_handler)

    
    if to_file:
        file_handler = logging.FileHandler(to_file, mode="a", encoding="utf-8", delay=False)
        file_handler.setLevel(level)
        # En archivo normalmente conviene un formato un poco más detallado
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def log_startup(script_name: str) -> str:
    """
    Registra timestamp de inicio de ejecución.
    
    Args:
        script_name: Nombre del script/programa
        
    Returns:
        String con timestamp
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{script_name} iniciado a las {timestamp}"
    logging.info(msg)
    return timestamp


def log_completion(script_name: str) -> str:
    """
    Registra timestamp de finalización.
    
    Args:
        script_name: Nombre del script/programa
        
    Returns:
        String con timestamp
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{script_name} finalizado a las {timestamp}"
    logging.info(msg)
    return timestamp


def validate_data_files(file_list: List[str]) -> bool:
    """
    Valida que existan los archivos de entrada.
    
    Args:
        file_list: Lista de rutas de archivos
        
    Returns:
        True si todos existen, False si alguno falta
    """
    import os
    missing = [f for f in file_list if not os.path.exists(f)]
    
    if missing:
        logging.error(f"Archivos faltantes: {', '.join(missing)}")
        return False
    
    return True


def summarize_execution(
    n_days: int,
    total_assignments: int,
    total_hours: float
) -> str:
    """
    Genera resumen de ejecución.
    
    Args:
        n_days: Número de días procesados
        total_assignments: Total de asignaciones realizadas
        total_hours: Total de horas asignadas
        
    Returns:
        String con resumen
    """
    msg = (
        f"\n{'='*60}\n"
        f"RESUMEN DE EJECUCIÓN\n"
        f"{'='*60}\n"
        f"Días procesados: {n_days}\n"
        f"Total asignaciones: {total_assignments}\n"
        f"Total horas asignadas: {total_hours:.1f}h\n"
        f"{'='*60}"
    )
    logging.info(msg)
    return msg
