"""
GUÍA RÁPIDA DE USO - WFM Scheduling System

Este archivo contiene instrucciones paso a paso y comandos para ejecutar
el sistema refactorizado.
"""

# ==============================================================================
# 1. REQUISITOS
# ==============================================================================

# Instalar dependencias:
# pip install pandas numpy ortools openpyxl

# ==============================================================================
# 2. ESTRUCTURA DE ARCHIVOS ESPERADA
# ==============================================================================

"""
project-root/
├── main.py                  ← PUNTO DE ENTRADA (ejecutar esto)
├── config.py                ← EDITAR PARA CAMBIAR PARÁMETROS
├── Data/                    ← CARPETA CON DATOS DE ENTRADA
│   ├── Curva.csv           (Fecha, Intervalo, Requeridos)
│   ├── AgentsToCurva.csv   (AgentID, Nombre, Disponible, ...)
│   └── Suplencias.csv      (Turno_ID, Hora_Inicio, Hora_Termino, ...)
├── src/
│   ├── __init__.py
│   ├── config.py            ← PARÁMETROS
│   ├── time_utils.py        ← Conversiones de tiempo
│   ├── transforms.py        ← Normalización de datos
│   ├── io.py                ← Carga/exportación
│   ├── coverage.py          ← Ventana horaria
│   ├── shifts.py            ← Preselección, curvas exactas
│   ├── optimization.py      ← ILP/SCIP
│   ├── assignment.py        ← Asignación a agentes
│   └── utils.py             ← Logging, utilidades
└── Result/                  ← CARPETA DE SALIDA (se crea automáticamente)
    ├── AsignacionTurnos.xlsx       ← Resultado 1: Asignaciones
    ├── CoberturaFinal.xlsx         ← Resultado 2: Cobertura por intervalo
    └── Agents.xlsx                 ← Resultado 3: Estado de agentes
"""

# ==============================================================================
# 3. EJECUTAR EL SISTEMA
# ==============================================================================

"""
Opción A - Desde terminal (línea de comandos):
    cd c:\Users\juan.vaquiro\Downloads\test
    python main.py

Opción B - Desde PowerShell (Windows):
    Set-Location "c:\Users\juan.vaquiro\Downloads\test"
    python main.py

Opción C - Desde VS Code:
    1. Abre main.py
    2. Presiona F5 (o Ctrl+F5)
    3. Ve la salida en Terminal

Expected Output:
    [INFO] WFM Scheduling System iniciado a las 2025-01-28 14:30:45
    [INFO] Cargado Data/Curva.csv: 336 filas, 3 columnas
    [INFO] Cargado Data/AgentsToCurva.csv: 342 filas, 5 columnas
    [INFO] Cargado Data/Suplencias.csv: 512 filas, 8 columnas
    ...
    [INFO] ✓ Proceso completado exitosamente
"""

# ==============================================================================
# 4. CAMBIAR PARÁMETROS (Sin modificar código)
# ==============================================================================

"""
Edita config.py para ajustar el comportamiento sin tocar main.py:

# Restricciones laborales
MAX_HOURS_WEEK = 44              # horas máximas por agente/semana
REST_MIN_GAP = 11 * 60           # descanso mínimo entre días (minutos)

# Parámetros de optimización
K_PRESELECT = 500                # turnos preseleccionados (↓ = más rápido, menos exacto)
M_FINAL = 385                    # turnos finales para ILP
SOLVER_MS = 20000                # tiempo límite (ms)

# Pesos en función objetivo
ALPHA_UNDER = 0.501              # penalización por faltante
BETA_OVER = 1.180                # penalización por sobrante
GAMMA_HEAD = 0.001               # penalización por agentes

# Diversidad de horarios
CAP_PER_SHIFT = 30               # máximo agentes por turno (↓ = más diverso)
SEG_MULT_STEP = 0.15             # incremento de costo marginal (15% por segmento)

EJEMPLO DE AJUSTES:
    # Para más velocidad:
    K_PRESELECT = 300
    M_FINAL = 200
    SOLVER_MS = 10000
    
    # Para mejor cobertura (permite sobreasignación):
    ALPHA_UNDER = 1.0
    BETA_OVER = 0.5
    CAP_PER_SHIFT = 50
    
    # Para evitar "planitud" (más diversidad):
    CAP_PER_SHIFT = 10
    SEG_MULT_STEP = 0.25
"""

# ==============================================================================
# 5. ESTRUCTURA DE DATOS DE ENTRADA (CSV)
# ==============================================================================

"""
A. Data/Curva.csv (requeridos por intervalo)
   Columns: Fecha, Intervalo, Requeridos
   
   Ejemplo:
   Fecha,Intervalo,Requeridos
   2025-01-27,08:00:00 AM,10
   2025-01-27,08:30:00 AM,12
   2025-01-27,09:00:00 AM,14
   ...

B. Data/AgentsToCurva.csv (información de agentes)
   Columns: AgentID, Nombre, Disponible, Horas_Disponibles, ...
   
   Ejemplo:
   AgentID,Nombre,Disponible,Horas_Disponibles
   AG001,Juan Pérez,1,44
   AG002,María García,1,44
   AG003,Carlos López,0,0
   ...

C. Data/Suplencias.csv (catálogo de turnos)
   Columns: Turno_ID, Hora_Inicio, Hora_Termino, Avail, H.Efectivas, Descanso1, Descanso2, Inicio_Refrigerio, Fin_Refrigerio
   
   Ejemplo:
   Turno_ID,Hora_Inicio,Hora_Termino,Avail,H.Efectivas,Descanso1,Descanso2,Inicio_Refrigerio,Fin_Refrigerio
   T001,08:00,17:00,1,08:00,1,1,12:00,13:00
   T002,10:00,19:00,1,08:00,1,1,12:30,13:30
   T003,14:00,23:00,1,08:00,1,1,17:00,18:00
   ...
"""

# ==============================================================================
# 6. ESTRUCTURA DE DATOS DE SALIDA (XLSX)
# ==============================================================================

"""
A. Result/AsignacionTurnos.xlsx (asignaciones por agente)
   Columns: Agente, TurnoID, Inicio, Fin, Fecha
   
   Ejemplo:
   Agente,TurnoID,Inicio,Fin,Fecha
   AG001,T001,08:00,17:00,2025-01-27
   AG001,T002,10:00,19:00,2025-01-28
   AG002,T003,14:00,23:00,2025-01-27
   ...

B. Result/CoberturaFinal.xlsx (cobertura vs requeridos)
   Columns: Fecha, Inicio_HHMM, Fin_HHMM, Requeridos, Cubierto, Under, Over
   
   Ejemplo:
   Fecha,Inicio_HHMM,Fin_HHMM,Requeridos,Cubierto,Under,Over
   2025-01-27,08:00,08:30,10,10,0,0
   2025-01-27,08:30,09:00,12,12,0,0
   2025-01-27,09:00,09:30,14,14,0,0
   ...

C. Result/Agents.xlsx (estado final de agentes)
   Columns: AgentID, Nombre, Disponible, Horas_Disponibles, Horas_Asignadas, 2025-01-27, 2025-01-28, ...
   
   Ejemplo:
   AgentID,Nombre,Disponible,Horas_Disponibles,Horas_Asignadas,2025-01-27,2025-01-28
   AG001,Juan Pérez,1,0,44,8,8
   AG002,María García,1,12,32,8,8
   ...
"""

# ==============================================================================
# 7. TROUBLESHOOTING
# ==============================================================================

"""
Problema: ModuleNotFoundError: No module named 'ortools'
Solución:
    pip install ortools

Problema: FileNotFoundError: Data/Curva.csv
Solución:
    - Verifica que la carpeta "Data" exista en la raíz
    - Verifica nombres exactos de archivos (sensible a mayúsculas)
    - Verifica separador en CSV (debe ser ';')

Problema: Encoding error al leer CSV
Solución:
    - Edita config.py: CSV_ENCODING = "utf-8"  (si los archivos están en UTF-8)
    - O abre CSV en Excel y Guarda Como... latin1

Problema: ValueError: could not convert string to float
Solución:
    - Verifica que columnas numéricas no tengan texto
    - Verifica formato de horas: debe ser HH:MM (ej: 08:00, no 8:0)

Problema: Solver returns INFEASIBLE
Solución:
    - Reduce ALPHA_UNDER o aumenta BETA_OVER
    - Aumenta CAP_PER_SHIFT
    - Verifica que haya suficientes agentes y turnos
"""

# ==============================================================================
# 8. FLUJO PASO A PASO
# ==============================================================================

"""
1. CARGA (Líneas ~1-20 de main.py)
   - Lee Data/Curva.csv
   - Lee Data/AgentsToCurva.csv
   - Lee Data/Suplencias.csv

2. TRANSFORMACIÓN (Líneas ~20-35)
   - Normaliza AM/PM → 24h
   - Convierte HH:MM → minutos desde medianoche
   - Maneja turnos que cruzan medianoche (+1440)
   - Inicializa columnas de tracking

3. LOOP POR DÍA (Líneas ~35-100)
   Para cada fecha en Curva:
   
   a) DETECCIÓN DE VENTANA
      - Si todos los intervalos tienen requeridos > 0 → ventana 24h
      - Si no → ventana desde primer intervalo con demanda > 0 hasta último
   
   b) PRESELECCIÓN HEURÍSTICA (K=500 turnos)
      - Filtra turnos que solapan con ventana
      - Scoring rápido: suma de requeridos cubiertos (sin pausas)
      - Top K por score
   
   c) CURVAS EXACTAS (M=385 turnos)
      - Para cada turno: construye vector de cobertura
      - Considera: start-end del turno
      - Resta: breaks de 15 min (Descanso1, Descanso2)
      - Resta: almuerzo explícito (Inicio_Refrigerio, Fin_Refrigerio)
      - Scoring exacto: suma de requeridos verdaderamente cubiertos
      - Selecciona top M turnos
   
   d) RESOLUCIÓN ILP
      - Variables: y[j] = agentes por turno, u[t] = undercoverage, o[t] = overcoverage
      - Restricción: cobertura = demanda + (over - under)
      - Objetivo: minimizar under + 0.5*over + costo_marginal_creciente
      - Solver SCIP (20s max)
   
   e) ASIGNACIÓN GREEDY
      - Para cada turno j: asignar y_val[j] agentes
      - Si agente tiene horas disponibles → asignar y restar horas
      - Si no hay más horas → pasar al siguiente agente
   
   f) COBERTURA DEL DÍA
      - Calcular covered[t] = sum_j (agentes en turno j) × (turno j cubre intervalo t)
      - Calcular under/over por intervalo

4. EXPORTACIÓN (Líneas ~100-120)
   - Concatenar asignaciones de todos los días
   - Concatenar coberturas de todos los días
   - Exportar a XLSX con manejo de errores

5. RESUMEN (Líneas ~120-130)
   - Imprimir métricas finales
   - Timestamp de finalización
"""

# ==============================================================================
# 9. VALIDACIÓN: Cómo sé que funciona?
# ==============================================================================

"""
Checklist de validación:

✓ Archivos de entrada existen:
    - Data/Curva.csv (336 filas)
    - Data/AgentsToCurva.csv (342 filas)
    - Data/Suplencias.csv (512 filas)

✓ Archivos de salida creados:
    - Result/AsignacionTurnos.xlsx (debe tener 2000+ filas)
    - Result/CoberturaFinal.xlsx (debe tener 336 filas: 48 int × 7 días)
    - Result/Agents.xlsx (debe tener 342 filas)

✓ Métricas esperadas:
    - Cobertura Under = 0 (ideal) o muy bajo
    - Cobertura Over = bajo (< 20% de picos)
    - Total Asignaciones ≈ 342 agentes × 7 días = 2394 (aprox)
    - Total Horas Asignadas ≈ 44h/agente × 342 agentes = 15048h (máx)

✓ Logs informativos:
    - [INFO] Cargado Data/Curva.csv: 336 filas, 3 columnas
    - [INFO] Preseleccionados 500 turnos
    - [INFO] Construcción de curva exacta finalizada: 385 turnos para ILP
    - [INFO] ILP Solver resuelto: status=0 (OPTIMAL)
    - [INFO] Asignadas XXX asignaciones de turnos
"""

# ==============================================================================
# 10. PRÓXIMOS PASOS (Extensiones)
# ==============================================================================

"""
1. AGREGAR RESTRICCIÓN DE DESCANSO MÍNIMO ENTRE DÍAS
   - Editar: src/optimization.py
   - Agregar restricción: Día N → Descanso 11h → Día N+1 no antes de 11h después

2. INCLUIR VENTANAS PREFERENTES POR AGENTE
   - Nueva columna en AgentsToCurva.csv: Ventana_Preferida (08-17, 10-19, etc)
   - Editar: src/assignment.py
   - Validar antes de asignar

3. LIMITAR CAMBIOS DE HORARIO POR AGENTE
   - Histórico: resultado del día anterior
   - Restricción: si fue 08-17 hoy, mañana solo 08-17 o 10-19 (con buffer)

4. EXPORTAR A BASE DE DATOS
   - Editar: src/io.py::export_to_database()
   - Usar: sqlalchemy, pymysql, psycopg2

5. AGREGAR DASHBOARD DE MÉTRICAS
   - Nueva archivo: src/dashboard.py
   - Usar: matplotlib, plotly
   - Visualizar: cobertura, utilización, diversidad de turnos
"""

# ==============================================================================
# 11. CONTACTO / SOPORTE
# ==============================================================================

"""
Preguntas frecuentes:
- "¿Cómo cambio los parámetros?" → Edita config.py
- "¿Por qué tarda tanto?" → Aumenta K_PRESELECT o reduce SOLVER_MS
- "¿Por qué hay over-cobertura?" → Reduce BETA_OVER en config.py
- "¿Cómo agrego restricciones?" → Edita src/optimization.py
- "¿Cómo exporto a BD?" → Crea función en src/io.py

Recursos:
- OR-Tools docs: https://developers.google.com/optimization/install/python
- Pandas docs: https://pandas.pydata.org/
- NumPy docs: https://numpy.org/
"""

