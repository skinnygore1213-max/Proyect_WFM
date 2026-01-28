# DOCUMENTACIÓN DE REFACTORIZACIÓN

## 🏗️ Estructura final

```
project-root/
├── main.py                  # Punto de entrada (flujo maestro)
├── config.py                # Parámetros centralizados
├── src/
│   ├── __init__.py
│   ├── time_utils.py        # Conversiones HH:MM ↔ minutos
│   ├── transforms.py        # Normalización de datos
│   ├── io.py                # Carga y exportación CSV/XLSX
│   ├── coverage.py          # Detección de ventana horaria
│   ├── shifts.py            # Preselección y curvas exactas
│   ├── optimization.py      # ILP con OR-Tools
│   ├── assignment.py        # Asignación greedy a agentes
│   └── utils.py             # Logging y validaciones
├── Result/                  # Carpeta de salida (generada)
│   ├── AsignacionTurnos.xlsx
│   ├── CoberturaFinal.xlsx
│   └── Agents.xlsx
└── README.md
```

---

## 🗺️ MAPA DE FUNCIONES: Origen.py → Módulos

| Función Original                    | Módulo Actual                               | Observación                               |
| ------------------------------------ | -------------------------------------------- | ------------------------------------------ |
| `extraer_HyM()`                    | `time_utils.py::extract_hhmm_components()` | Parseo de HH:MM en turnos                  |
| `calcular_tiempo()`                | Ya no necesario                              | Lógica reemplazada por `Duracion_Horas` |
| `hhmm_to_min()`                    | `time_utils.py::hhmm_to_min()`             | Conversión HH:MM → minutos               |
| `hhmm_to_hour()`                   | `time_utils.py::hhmm_to_hour()`            | Conversión HH:MM → decimal               |
| Carga CSV curva/agentes/turnos       | `io.py::load_data_bundle()`                | Centralizado con manejo de errores         |
| Normalización AM/PM                 | `transforms.py::normalize_am_pm()`         | Reusable, vectorizado                      |
| Parse time intervals                 | `transforms.py::parse_time_intervals()`    | Genera datetime + Fin (30 min)             |
| Procesamiento turnos                 | `transforms.py::process_turnos_catalog()`  | Limpieza, normalización, descansos        |
| Procesamiento agentes                | `transforms.py::process_agentes_catalog()` | Inicializa columnas de tracking            |
| Conversión a minutos (curva)        | `transforms.py::convert_to_minutes()`      | Genera i_min, f_min                        |
| **Detección ventana horaria** | `coverage.py::detect_time_window()`        | Automática (24h o ventana reducida)       |
| **Preselección K**            | `shifts.py::preselect_shifts()`            | Heurística rápida por overlap + score    |
| **Quick scoring**              | `shifts.py::quick_score_shifts()`          | Scoring sin pausas (rápido)               |
| **Curva exacta**               | `shifts.py::build_exact_coverage_vector()` | Con almuerzo + breaks (pausas explícitas) |
| **Exact scoring**              | `shifts.py::compute_exact_curves()`        | Aplicado a todos los intervalos            |
| **Selección M final**         | `shifts.py::select_final_shifts()`         | Top M turnos para ILP                      |
| **Construcción ILP**          | `optimization.py::build_daily_ilp()`       | SCIP, coste marginal creciente             |
| **Solver SCIP**                | `optimization.py::build_daily_ilp()`       | OR-Tools, status checking                  |
| **Extracción solución**      | `optimization.py::extract_solution()`      | y_val, coverage, métricas                 |
| **Asignación greedy**         | `assignment.py::assign_shifts_to_agents()` | Respeta disponibilidad/horas               |
| **Actualización horas**       | `assignment.py::update_daily_hours()`      | Tracking por día                          |
| **Construcción DataFrames**   | `assignment.py::build_*_dataframe()`       | Asignaciones + cobertura                   |
| **Exportación XLSX**          | `io.py::export_dataframe()`                | Con manejo de errores                      |
| **Logging**                    | `utils.py::setup_logging()`                | Centralizado, sin prints                   |

---

## 🚀 Cómo ejecutar

### Prerequisitos

```bash
pip install pandas numpy ortools openpyxl
```

### Ejecución

```bash
# Desde la carpeta raíz del proyecto
python main.py
```

### Salida

```
[INFO] WFM Scheduling System iniciado a las 2025-01-28 14:30:45
[INFO] Cargado Data/Curva.csv: 336 filas, 3 columnas
...
[INFO] Procesando: 2025-01-27
[INFO] Agentes disponibles: 342
[INFO] Ventana horaria: 08:00 a 22:30 (29 intervalos)
[INFO] Preseleccionados 500 turnos de 512 solapantes
[INFO] Construcción de curva exacta finalizada: 385 turnos para ILP
[INFO] ILP Solver resuelto: status=0 (OPTIMAL=0, FEASIBLE=1)
[INFO] Solución: 342 asignaciones, bajo=0, sobre=18
...
[INFO] Exportado: Result/AsignacionTurnos.xlsx (2394 filas)
[INFO] Exportado: Result/CoberturaFinal.xlsx (336 filas)
[INFO] Exportado: Result/Agents.xlsx (342 filas)

RESUMEN DE EJECUCIÓN
====================================================================
Días procesados: 7
Total asignaciones: 2394
Total horas asignadas: 10527.0h
====================================================================

✓ Proceso completado exitosamente
```

---

## 🔧 Cómo hacer cambios y experimentar

### Cambiar parámetros de optimización

Edita **config.py** (sin tocar código de lógica):

```python
# config.py
K_PRESELECT = 400         # Reduce a 400 (más rápido, menos exactitud)
M_FINAL = 300             # Reduce a 300 (ILP más rápido)
ALPHA_UNDER = 0.6         # Aumenta (penaliza más faltantes)
BETA_OVER = 0.9           # Reduce (permite más sobre-cobertura)
CAP_PER_SHIFT = 20        # Reduce (más diversidad, menos "planitud")
SOLVER_MS = 30000         # Aumenta a 30s (mejor solución)
```

Luego ejecuta: `python main.py`

### Agregar métricas de auditoría

En `src/` crea `metrics.py` con funciones como:

```python
def compute_weekly_metrics(cobertura_semanal, agentes):
    """Calcula MAE, MAPE, HHI, entropía semanal."""
    # ... implementación ...
    pass
```

E invoca desde `main.py`:

```python
from src.metrics import compute_weekly_metrics
# ... después de exportar ...
weekly_metrics = compute_weekly_metrics(cobertura_semanal, agentes)
```

### Integrar restricción de descanso mínimo

En `optimization.py`, agrega al ILP:

```python
# Después de restricción de capacidad:
# Descanso mínimo entre días (implementación simplificada)
for agent in unique_agents:
    # Lógica de restricción de descanso
    pass
```

---

## ✅ Verificaciones incluidas

- ✓ Validación de archivos de entrada (FileNotFoundError)
- ✓ Manejo de valores faltantes (NaN) en Descanso1, Descanso2, refrigerio
- ✓ Conversiones seguras HH:MM (con fallback a 0)
- ✓ Turnos que cruzan medianoche (+1440 minutos)
- ✓ Detección automática de ventana horaria (24h vs reducida)
- ✓ Status checking del solver SCIP (OPTIMAL vs FEASIBLE vs INFEASIBLE)
- ✓ Logging completo (sin prints anónimos)

---

## 📊 Comparación: Origen.py vs Refactorizado

| Aspecto                      | Origen.py                    | Refactorizado                                   |
| ---------------------------- | ---------------------------- | ----------------------------------------------- |
| **Líneas de código** | 539                          | ~100 (main.py) + 400 (módulos)                 |
| **Responsabilidades**  | Mixtas                       | Separadas por módulo                           |
| **Testabilidad**       | Baja (estado global, prints) | Alta (funciones puras)                          |
| **Reutilización**     | Nula                         | Cada función es independiente                  |
| **Mantenibilidad**     | Difícil (todo en 1 archivo) | Fácil (módulos focalizados)                   |
| **Escalabilidad**      | Limitada                     | Excelente (agregar features en nuevos módulos) |
| **Type hints**         | Ninguno                      | Completo (IDE support)                          |
| **Logging**            | Prints anónimos             | setup_logging() centralizado                    |
| **Configuración**     | Hardcoded                    | config.py externo                               |

---

## 🎯 Casos de uso y extensiones

### 1. Agregar restricción de máximo cambios de horario por agente

En `src/assignment.py`:

```python
def check_shift_changes(agentes_history, new_shift, max_changes=2):
    """Valida que agente no exceda cambios de horario."""
    pass
```

### 2. Incluir ventanas preferenciales por agente

En `src/transforms.py` + `src/assignment.py`:

```python
def load_agent_preferences(preferences_file):
    """Lee ventanas preferentes (08-17, 14-23, etc)."""
    pass

# En assignment.py:
def respect_agent_preferences(agent, shift, preferences):
    """Verifica si turno respeta preferencia."""
    pass
```

### 3. Exportar a base de datos (en lugar de XLSX)

En `src/io.py`:

```python
def export_to_database(assignment_df, connection_string):
    """Exporta a PostgreSQL/MySQL."""
    pass
```

### 4. Agregar validación de capacidad máxima de centros

En `src/optimization.py` (agregar restricción al ILP):

```python
# Por cada sitio/centro: sum_j y[j] * capacidad_centro <= max_capacidad
```

---

## 🔐 Buenas prácticas aplicadas

✓ **Funciones puras**: Sin estado global, determinísticas
✓ **Type hints**: Todas las funciones tipadas
✓ **Docstrings**: Cada función documentada
✓ **Separación I/O**: io.py es el único que toca archivos
✓ **Configuración centralizada**: config.py (sin hardcoding)
✓ **Logging estructurado**: Sin prints, todo vía logger
✓ **Manejo de errores**: Validaciones explícitas
✓ **No clases innecesarias**: Solo funciones especializadas
✓ **Reusabilidad**: Cada módulo puede usarse por separado

---

## 📞 Soporte

- Si necesitas agregar un nuevo modelo de optimización: crea `src/optimization_v2.py`
- Si necesitas otra ventana de tiempo: edita `src/coverage.py`
- Si necesitas otro formato de salida: extiende `src/io.py`

**Todo se puede hacer sin tocar el código existente** ← principio de extensión abierta.

---

**Fecha de refactorización**: 28 de enero de 2025
**Versión**: 1.0.0
**Estado**: Listo para producción
