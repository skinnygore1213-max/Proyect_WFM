"""
Configuración centralizada del sistema WFM.

Parámetros de optimización, restricciones legales y rutas de archivos.
Modifica estos valores para experimentar sin tocar el código.
"""

# ============================================================
# RESTRICCIONES LABORALES (Legislación / Políticas)
# ============================================================
MAX_HOURS_WEEK = 44              # horas máximas por agente por semana
MIN_RESTS = 1                    # mínimo descansos/breaks por turno
MAX_RESTS = 2                    # máximo descansos/breaks por turno
REST_MIN_GAP = 12 * 60           # descanso mínimo entre días (minutos, ej: 11h)

# ============================================================
# PARÁMETROS DE OPTIMIZACIÓN ILP/HEURÍSTICA
# ============================================================
K_PRESELECT = 300                # turnos preseleccionados por quick_score
M_FINAL = 100                    # turnos que entran al ILP final
SOLVER_MS = 20000                # tiempo límite del solver (ms)

# Pesos en la función objetivo
ALPHA_UNDER = 0.501              # penalización por undercoverage
BETA_OVER = 1.180                # penalización por overcoverage
GAMMA_HEAD = 0.001               # penalización por cantidad de turnos

# ============================================================
# RESTRICCIONES DE CAPACIDAD Y DIVERSIDAD
# ============================================================
CAP_PER_SHIFT = 15               # máximo agentes por turno (evita "planitud")
CAP_PER_INTENSITY = 4            # máximo de turnos por intensidad (nueva restricción)
SEG_WIDTH = 10                   # ancho de segmento para coste marginal creciente
SEG_MULT_STEP = 0.35             # incremento % por segmento (15% más caro)
NOISE_EPS = 0.05                 # ruido relativo para romper empates
# pesos para score híbrido
α = 0.55      # alfa= peso de exact_score o cubrimiento de curva
β = 0.45      # beta= peso de score por hora

# ============================================================
# REPRODUCIBILIDAD
# ============================================================
RANDOM_SEED = 42                 # semilla para numpy (resultados reproducibles)

# ============================================================
# RUTAS DE DATOS
# ============================================================
DATA_DIR = "Data"
CURVA_FILE = f"{DATA_DIR}/Curva.csv"
AGENTS_FILE = f"{DATA_DIR}/AgentsToCurva.csv"
TURNOS_FILE = f"{DATA_DIR}/Suplencias.csv"

OUTPUT_DIR = "Result"
OUTPUT_ASSIGNMENT = f"{OUTPUT_DIR}/AsignacionTurnos.xlsx"
OUTPUT_COVERAGE = f"{OUTPUT_DIR}/CoberturaFinal.xlsx"
OUTPUT_AGENTS = f"{OUTPUT_DIR}/Agents.xlsx"
OUTPUT_ILP_RESULTS = f"{OUTPUT_DIR}/ILP_Results.xlsx"
OUTPUT_TURNOS_K = f"{OUTPUT_DIR}/Turnos_K.xlsx"
OUTPUT_NOVEDADES = f"{OUTPUT_DIR}/Novedades.xlsx"

OUTPUT_LOG_FILE = f"{OUTPUT_DIR}/execution.log"

# ============================================================
# CONFIGURACIÓN DE LECTURA DE DATOS
# ============================================================
CSV_ENCODING = "latin1"          # encoding de archivos CSV
CSV_SEPARATOR = ";"              # separador de columnas
