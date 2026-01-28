# 📑 ÍNDICE - WFM Refactorización Completa

## 📂 Archivos Principales

### 🚀 Para ejecutar (START HERE)
- **[main.py](main.py)** - Punto de entrada del sistema
  - 150 líneas claras
  - Flujo: Carga → Transformación → Loop diario → Exportación
  - Coordina todos los módulos
  - Ejecutar con: `python main.py`

### ⚙️ Para configurar (SIN TOCAR CÓDIGO)
- **[config.py](config.py)** - Parámetros centralizados
  - 20 parámetros ajustables
  - Restricciones laborales (44h, descansos, etc)
  - Parámetros ILP (K, M, alpha, beta, gamma)
  - Rutas de archivos
  - **Edita este archivo para experimentar**

### 📚 Documentación (LEE ESTO)
1. **[SUMMARY.md](SUMMARY.md)** ← **COMIENZA AQUÍ**
   - Resumen ejecutivo de la refactorización
   - Comparativa antes/después
   - Principios de ingeniería aplicados
   - Estado de producción

2. **[QUICK_START.md](QUICK_START.md)**
   - Guía paso a paso
   - Estructura de archivos esperada
   - Cómo ejecutar
   - Troubleshooting
   - Estructura de datos entrada/salida

3. **[REFACTORING_GUIDE.md](REFACTORING_GUIDE.md)**
   - Mapa detallado de migración (Origen.py → Módulos)
   - Tablas de equivalencia función por función
   - Cómo hacer cambios
   - Casos de uso y extensiones

4. **[README.md](README.md)** - Original
   - Contexto del problema WFM
   - Teoría de ILP y Matheurísticas
   - Arquitectura recomendada

### 📦 Código Original (REFERENCIA)
- **[Origen.py](Origen.py)** - Código sin refactorizar
  - 539 líneas monolíticas
  - Preservado para referencia
  - Ya no usar (usar main.py en su lugar)

---

## 🎯 Módulos (src/)

| Archivo | Funciones | Responsabilidad |
|---|---|---|
| **[time_utils.py](src/time_utils.py)** | 6 | Conversiones HH:MM ↔ minutos, AM/PM |
| **[transforms.py](src/transforms.py)** | 8 | Normalización datos, limpieza NaNs, parsing |
| **[io.py](src/io.py)** | 6 | Carga CSV, exportación XLSX, validación rutas |
| **[coverage.py](src/coverage.py)** | 4 | Detección ventana horaria, métricas cobertura |
| **[shifts.py](src/shifts.py)** | 5 | Preselección heurística K, curvas exactas, scoring |
| **[optimization.py](src/optimization.py)** | 4 | ILP/SCIP, coste marginal creciente, solver |
| **[assignment.py](src/assignment.py)** | 5 | Asignación greedy, tracking horas, DataFrames |
| **[utils.py](src/utils.py)** | 4 | Logging centralizado, validaciones, helpers |
| **[__init__.py](src/__init__.py)** | - | Metadatos del paquete |

**Total**: 42 funciones + 100% documentadas (docstrings + type hints)

---

## 📊 Diagrama de Flujo

```
main.py (Flujo maestro)
│
├─→ config.py (Parámetros)
│
├─→ FASE 1: CARGA
│   ├─ io.load_data_bundle()
│   └─ → (curva, agentes, turnos)
│
├─→ FASE 2: TRANSFORMACIÓN
│   ├─ transforms.parse_time_intervals()
│   ├─ transforms.process_turnos_catalog()
│   ├─ transforms.process_agentes_catalog()
│   └─ transforms.convert_to_minutes()
│
├─→ FASE 3: LOOP POR DÍA (7 iteraciones)
│   │
│   ├─→ 3a. DETECCIÓN VENTANA
│   │   ├─ coverage.detect_time_window()
│   │   └─ coverage.filter_to_window()
│   │
│   ├─→ 3b. PRESELECCIÓN HEURÍSTICA (K=500)
│   │   ├─ shifts.quick_score_shifts()
│   │   └─ shifts.preselect_shifts()
│   │
│   ├─→ 3c. CURVAS EXACTAS (M=385)
│   │   ├─ shifts.build_exact_coverage_vector()
│   │   ├─ shifts.compute_exact_curves()
│   │   └─ shifts.select_final_shifts()
│   │
│   ├─→ 3d. RESOLUCIÓN ILP
│   │   ├─ optimization.build_daily_ilp()
│   │   ├─ (SCIP solver 20s)
│   │   └─ optimization.extract_solution()
│   │
│   ├─→ 3e. ASIGNACIÓN A AGENTES
│   │   ├─ assignment.assign_shifts_to_agents()
│   │   └─ assignment.build_*_dataframe()
│   │
│   └─→ 3f. REGISTRO DE COBERTURA
│       └─ coverage.validate_coverage_vector()
│
├─→ FASE 4: EXPORTACIÓN
│   ├─ io.export_assignment_results()
│   ├─ → AsignacionTurnos.xlsx
│   ├─ → CoberturaFinal.xlsx
│   └─ → Agents.xlsx
│
└─→ RESUMEN & LOGGING
    ├─ utils.log_completion()
    └─ utils.summarize_execution()
```

---

## 📥 Datos de Entrada Requeridos

Coloca estos archivos en carpeta **Data/**:

```
Data/
├── Curva.csv
│   Columns: Fecha, Intervalo, Requeridos
│   336 filas (48 intervalos × 7 días)
│
├── AgentsToCurva.csv
│   Columns: AgentID, Nombre, Disponible, Horas_Disponibles, ...
│   342 filas (agentes)
│
└── Suplencias.csv
    Columns: Turno_ID, Hora_Inicio, Hora_Termino, Avail, H.Efectivas, Descanso1, Descanso2, ...
    512 filas (catálogo de turnos)
```

---

## 📤 Datos de Salida Generados

Se crean automáticamente en carpeta **Result/**:

```
Result/
├── AsignacionTurnos.xlsx
│   Asignaciones por agente/turno (2000+ filas)
│   Columns: Agente, TurnoID, Inicio, Fin, Fecha
│
├── CoberturaFinal.xlsx
│   Cobertura por intervalo (336 filas)
│   Columns: Fecha, Inicio_HHMM, Fin_HHMM, Requeridos, Cubierto, Under, Over
│
└── Agents.xlsx
    Estado final de agentes (342 filas)
    Columns: AgentID, Nombre, Disponible, Horas_Disponibles, Horas_Asignadas, [días]
```

---

## 🚀 Quick Start (30 segundos)

1. **Instalar dependencias**
   ```bash
   pip install pandas numpy ortools openpyxl
   ```

2. **Colocar datos de entrada**
   ```
   Data/Curva.csv
   Data/AgentsToCurva.csv
   Data/Suplencias.csv
   ```

3. **Ejecutar**
   ```bash
   python main.py
   ```

4. **Ver resultados**
   ```
   Result/AsignacionTurnos.xlsx
   Result/CoberturaFinal.xlsx
   Result/Agents.xlsx
   ```

---

## 🔧 Cómo Cambiar Parámetros (SIN EDITAR CÓDIGO)

### Opción A: Más velocidad
```python
# config.py
K_PRESELECT = 300         # ↓ de 500
M_FINAL = 200             # ↓ de 385
SOLVER_MS = 10000         # ↓ de 20000 (10 segundos)
```

### Opción B: Mejor cobertura
```python
# config.py
ALPHA_UNDER = 1.0         # ↑ penaliza más faltantes
BETA_OVER = 0.5           # ↓ permite sobre-cobertura
```

### Opción C: Más diversidad de horarios
```python
# config.py
CAP_PER_SHIFT = 10        # ↓ máximo 10 agentes por turno
SEG_MULT_STEP = 0.25      # ↑ incremento de costo (25% vs 15%)
```

**Luego ejecuta**: `python main.py`

---

## 🗺️ Mapa Mental de Modules

```
ENTRADA (I/O)
    ↓
    io.load_data_bundle()
    ↓
TRANSFORMACIÓN
    ├─ transforms.parse_time_intervals()
    ├─ transforms.process_turnos_catalog()
    ├─ transforms.process_agentes_catalog()
    ├─ transforms.convert_to_minutes()
    └─ time_utils.* (conversiones HH:MM)
    ↓
LÓGICA DIARIA (× 7 días)
    ├─ coverage.detect_time_window()
    ├─ shifts.preselect_shifts()
    ├─ shifts.compute_exact_curves()
    ├─ optimization.build_daily_ilp()
    ├─ assignment.assign_shifts_to_agents()
    └─ coverage.validate_coverage_vector()
    ↓
SALIDA (I/O)
    ↓
    io.export_assignment_results()
    ↓
RESULTADO
    ├─ AsignacionTurnos.xlsx
    ├─ CoberturaFinal.xlsx
    └─ Agents.xlsx
```

---

## ✅ Checklist de Validación

- [ ] Archivos en Data/ existen
- [ ] Python 3.7+ instalado
- [ ] Dependencias instaladas: `pip install pandas numpy ortools openpyxl`
- [ ] Ejecutaste: `python main.py`
- [ ] Carpeta Result/ creada con 3 archivos XLSX
- [ ] Logs mostrados sin errores
- [ ] Resultados tienen datos (>0 filas)

---

## 🎓 Principios de Diseño Aplicados

✅ **SOLID**
- Single Responsibility Principle
- Open/Closed Principle (fácil extender)
- Dependency Inversion (config.py centralizado)

✅ **Clean Code**
- Nombres significativos
- Funciones pequeñas (<50 líneas)
- No repetición (DRY)

✅ **Python Best Practices**
- Type hints 100%
- Docstrings Google-style
- Logging estructurado
- PEP 8 compatible

---

## 📖 Lectura Recomendada (en orden)

1. **SUMMARY.md** - Entiende qué se hizo (5 min)
2. **QUICK_START.md** - Cómo ejecutar (10 min)
3. **main.py** - Flujo general (10 min)
4. **config.py** - Qué cambiar (5 min)
5. **src/optimization.py** - Lógica ILP (10 min)
6. **REFACTORING_GUIDE.md** - Detalles profundos (20 min)

---

## 🆘 Soporte

**Error: ModuleNotFoundError**
→ `pip install ortools`

**Error: FileNotFoundError: Data/Curva.csv**
→ Verifica carpeta Data/ existe y tiene archivos correctos

**Error: Solver INFEASIBLE**
→ Edita config.py: aumenta CAP_PER_SHIFT, reduce ALPHA_UNDER

**Pregunta: ¿Cómo agrego restricción de descanso mínimo?**
→ Lee REFACTORING_GUIDE.md sección "Extensiones"

---

## 📈 Próximos Pasos

1. ✅ Refactorización completada
2. 🧪 (Opcional) Agregar tests unitarios
3. 📊 (Opcional) Dashboard web con Streamlit
4. 🗄️ (Opcional) Exportar a base de datos
5. 🔌 (Opcional) API REST (FastAPI)

---

**Última actualización**: 28 de enero de 2025  
**Versión**: 1.0.0  
**Estado**: ✅ PRODUCCIÓN

