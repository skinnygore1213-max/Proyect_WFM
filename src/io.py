"""
Módulo de I/O: carga y exportación de datos.

Funciones especializadas para leer CSV/XLSX y exportar resultados.
Maneja encoding, validaciones básicas y rutas.
"""

import pandas as pd
import os
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


def load_csv(
    filepath: str,
    sep: str = ";",
    encoding: str = "latin1"
) -> pd.DataFrame:
    """
    Carga un archivo CSV con manejo de errores.
    
    Args:
        filepath: Ruta del archivo CSV
        sep: Separador (default ';')
        encoding: Encoding (default 'latin1')
        
    Returns:
        DataFrame
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        pd.errors.ParserError: Si hay error en parseo
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Archivo no encontrado: {filepath}")
    
    try:
        df = pd.read_csv(filepath, sep=sep, encoding=encoding)
        logger.info(f"Cargado {filepath}: {len(df)} filas, {len(df.columns)} columnas")
        return df
    except Exception as e:
        logger.error(f"Error cargando {filepath}: {e}")
        raise


def load_data_bundle(
    curva_path: str,
    agentes_path: str,
    turnos_path: str,
    sep: str = ";",
    encoding: str = "latin1"
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carga los 3 archivos principales del sistema.
    
    Args:
        curva_path: Ruta a Curva.csv
        agentes_path: Ruta a AgentsToCurva.csv
        turnos_path: Ruta a Suplencias.csv
        sep: Separador CSV
        encoding: Encoding
        
    Returns:
        Tupla (curva, agentes, turnos)
        
    Raises:
        FileNotFoundError: Si falta algún archivo
    """
    curva = load_csv(curva_path, sep=sep, encoding=encoding)
    agentes = load_csv(agentes_path, sep=sep, encoding=encoding)
    turnos = load_csv(turnos_path, sep=sep, encoding=encoding)
    curva["Req_True"] = (curva["Requeridos"].astype(int) > 0).astype(int)
    
    logger.info("Todos los archivos cargados correctamente")
    return curva, agentes, turnos


def ensure_output_dir(output_dir: str) -> None:
    """
    Asegura que la carpeta de output existe.
    
    Args:
        output_dir: Ruta de carpeta de salida
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info(f"Creada carpeta de salida: {output_dir}")


def export_dataframe(
    df: pd.DataFrame,
    filepath: str,
    index: bool = False,
    encoding: str = "latin1"
) -> None:
    """
    Exporta DataFrame a Excel o CSV según extensión.
    
    Args:
        df: DataFrame a exportar
        filepath: Ruta de salida (*.xlsx o *.csv)
        index: Incluir índice
        encoding: Encoding para CSV
    """
    ensure_output_dir(os.path.dirname(filepath))
    
    try:
        if filepath.endswith('.xlsx'):
            df.to_excel(filepath, index=index, engine='openpyxl')
        elif filepath.endswith('.csv'):
            df.to_csv(filepath, index=index, sep=";", encoding=encoding)
        else:
            df.to_csv(filepath, index=index, sep=";", encoding=encoding)
        
        logger.info(f"Exportado: {filepath} ({len(df)} filas)")
    except Exception as e:
        logger.error(f"Error exportando {filepath}: {e}")
        raise


def export_assignment_results(
    asignacion_semanal: pd.DataFrame,
    cobertura_semanal: pd.DataFrame,
    agentes_final: pd.DataFrame,
    ILP_results_semanal: pd.DataFrame,
    turnos_k_semanal: pd.DataFrame,
    output_assignment: str,
    output_coverage: str,
    output_agents: str,
    output_ilp_results: str,
    output_turnos_k: str
) -> None:
    """
    Exporta los 3 archivos de resultado.
    
    Args:
        asignacion_semanal: Asignaciones por agente/turno
        cobertura_semanal: Cobertura por intervalo
        agentes_final: Estado final de agentes (horas, etc)
        output_assignment: Ruta de AsignacionTurnos.xlsx
        output_coverage: Ruta de CoberturaFinal.xlsx
        output_agents: Ruta de Agents.xlsx
    """
    export_dataframe(asignacion_semanal, output_assignment, index=False)
    export_dataframe(cobertura_semanal, output_coverage, index=False)
    export_dataframe(agentes_final, output_agents, index=False)
    export_dataframe(ILP_results_semanal, output_ilp_results, index=False)
    export_dataframe(turnos_k_semanal, output_turnos_k, index=False)
    
    logger.info("Resultados finales exportados")


def log_timestamp(msg: str) -> None:
    """
    Registra timestamp con mensaje (inicio/fin de proceso).
    
    Args:
        msg: Mensaje a registrar
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{msg}: {timestamp}")
