from logging import log
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ortools.linear_solver import pywraplp

# ============================================================
# 0) Parámetros ajustables (impactan performance/calidad)
# ============================================================

#Parameters for weekly scheduling
MAX_HOURS_WEEK = 44          # horas máximas semanales
MIN_RESTS = 1                # mínimo descansos por turno (si lo quieres)
MAX_RESTS = 2                # máximo descansos por turno (ya existe en catálogo)
REST_MIN_GAP = 11 * 60       # descanso mínimo entre días, p. ej. 11 horas (660 min)

#parameters for ajust dail curved scheduling
K_PRESELECT = 500   # turnos preseleccionados por score rápido (antes de construir curva)
M_FINAL     = 385    # turnos que entran al ILP (tras curva exacta)
SOLVER_MS   = 20000 # tiempo límite del ILP en milisegundos (20s)
ALPHA_UNDER = 0.501   # penalización por faltante
BETA_OVER   = 1.180  # penalización por sobrante
GAMMA_HEAD  = 0.001 # penalización por cantidad de turnos usados

CAP_PER_SHIFT  = 30      # tope por turno (evita "planitud")
SEG_WIDTH      = 15      # tamaño segmento para coste marginal creciente
SEG_MULT_STEP  = 0.15    # incremento por segmento (15% más caro cada bloque)
RANDOM_SEED    = 42      # reproducibilidad
NOISE_EPS      = 0.02    # ruido relativo en el costo de turnos

np.random.seed(RANDOM_SEED)

def extraer_HyM(turno):
    if turno != "":
            # Usar expresión regular para extraer las horas
            match = re.search(r'(\d{2}):(\d{2})\s+a\s+(\d{2}):(\d{2})', turno, re.IGNORECASE)
            if match:
                hora_inicio = int(match.group(1))
                minutos_inicio = int(match.group(2))
                hora_fin = int(match.group(3))
                minutos_fin = int(match.group(4))
                
                #if hora_fin < hora_inicio:
                #    hora_fin= hora_fin + 24
                return hora_inicio, minutos_inicio, hora_fin, minutos_fin  # Devolver como enteros
    return None,None,None,None

def calcular_tiempo(turno: object ):
    star,star_minute,end,end_minute = extraer_HyM(turno)
     # Calcular el total de horas en formato decimal
    if star!=None:
        total_horas = (end + end_minute / 60) - (star + star_minute / 60)
        return total_horas # Convertir a horas
    return  0

def hhmm_to_min(texto):
        s = str(texto).replace("\xa0", " ").strip()
        # Maneja HH:MM
        dt = datetime.strptime(s, "%H:%M")
        return dt.hour*60 + dt.minute

def hhmm_to_hour(texto):
        #s = str(texto).replace("\xa0", " ").strip()
        # Maneja HH:MM
        dt = datetime.strptime(texto, "%H:%M")
        return dt.hour + (dt.minute/60)
# ============================================================
# 1. CARGA DE ARCHIVOS
# ============================================================

curva = pd.read_csv(r"Data\Curva.csv", sep=";", encoding="latin1")
agentes = pd.read_csv(r"Data\AgentsToCurva.csv", sep=";", encoding="latin1")
turnos = pd.read_csv(r"Data\Suplencias.csv", sep=";", encoding="latin1")

#curva["Intervalo"] = curva["Intervalo"].str.replace("a. m.", "AM") #.str.replace("p. m.", "PM")
curva["Intervalo"] = curva["Intervalo"].astype(str).str.strip()
curva["Intervalo"] = curva["Intervalo"].str.replace(r"a\.\s*m\.", "AM", regex=True)
curva["Intervalo"] = curva["Intervalo"].str.replace(r"p\.\s*m\.", "PM", regex=True)
curva["Intervalo"] = pd.to_datetime(curva["Intervalo"], format="%I:%M:%S %p", errors='coerce')#.dt.time
curva["Fin"] = curva["Intervalo"] + timedelta(minutes=30)
#curva["Intervalo"] = pd.to_datetime(curva["Intervalo"], format="%I:%M:%S %p").dt.time
turnos=turnos[turnos["Avail"]==1].copy()
turnos["Hora_Inicio"] = turnos["Hora_Inicio"].astype(str).str.strip()
turnos["Hora_Termino"] = turnos["Hora_Termino"].astype(str).str.strip()
turnos["Descanso1"] = pd.to_numeric(turnos["Descanso1"], errors='coerce').fillna(0).astype(int)
turnos["Descanso2"] = pd.to_numeric(turnos["Descanso2"], errors='coerce').fillna(0).astype(int)
turnos[["Inicio_Refrigerio", "Fin_Refrigerio"]] = turnos[["Inicio_Refrigerio", "Fin_Refrigerio"]].fillna("")
turnos["Inicio_Refrigerio"] = turnos["Inicio_Refrigerio"].astype(str).str.strip()
turnos["Fin_Refrigerio"] = turnos["Fin_Refrigerio"].astype(str).str.strip()
#Agregamos columna con los minutos asignados por día
turnos["start_min"] = turnos["Hora_Inicio"].astype(str).str.strip().apply(hhmm_to_min)
turnos["end_min"]   = turnos["Hora_Termino"].astype(str).str.strip().apply(hhmm_to_min)
# Resolver turno cruzando medianoche (end < start => +1440)
turnos.loc[turnos["end_min"] < turnos["start_min"], "end_min"] += 1440
#calculamos la duración del turno en horas
turnos["Duracion_Horas"] = turnos["H.Efectivas"].astype(str).str.strip().apply(hhmm_to_hour)
#turnos["Duracion_Horas"] = (turnos["end_min"] - turnos["start_min"]) / 60
agentes["Horas_Disponibles"] = MAX_HOURS_WEEK
agentes["Horas_Asignadas"] = 0
agentes_disponibles = agentes[agentes['Disponible'] == 1].copy()

dias_disponibles = sorted(curva['Fecha'].unique())
#print(f"Número de agentes disponibles: {N_agents}")
print(datetime.now().strftime("Fecha y hora de cargue de datos: %Y-%m-%d %H:%M:%S"))
#log("Cargue de datos ok.")
#print(turnos.head())

asignacion_semanal = []
cobertura_semanal = []

for dia in dias_disponibles:
    print(f"\n=== Procesando día {dia} ===")
    curva_dia = curva[curva['Fecha'] == dia].copy()
    N_agents = len(agentes_disponibles)
    #incluimos columna con el día para el seguimiento de horas por día
    agentes[dia] = 0
    #agentes[{dia}] = 0
    
    # ============================================================
    # 2. PROCESAR CURVA DE REQUERIDOS
    # ============================================================

    #def parse_time(t):
    #    return datetime.strptime(t.strip(), "%H:%M:%S %p")

    curva_dia["Inicio"] = curva_dia["Intervalo"].copy()
    #curva["Fin"] = curva["Inicio"] + timedelta(minutes=30)

    # Minutos desde medianoche (enteros) para vectorizar
    def to_min(t: pd.Timestamp) -> int:
        return t.hour*60 + t.minute

    curva_dia["i_min"] = curva_dia["Inicio"].apply(lambda x: to_min(x))
    curva_dia["f_min"] = curva_dia["Fin"].apply(lambda x: to_min(x))
    curva_dia.loc[curva_dia["f_min"] < curva_dia["i_min"], "f_min"] += 1440

    #intervalos = curva[["Inicio", "Fin"]].copy()
    #required = curva["Requeridos"].values

    # Vector de demanda
    required_full = curva_dia["Requeridos"].astype(int).values
    i_min_full    = curva_dia["i_min"].values
    f_min_full    = curva_dia["f_min"].values

    #curva_dia.to_excel("CurvaFinal.xlsx", index=False)
    #print("Curva procesada y exportada a CurvaFinal.xlsx")

    # ============================================================
    # 3) Detectar ventana horaria automáticamente
    #    (si todos los 48 intervalos > 0 => 24x7)
    # ============================================================
    pos_mask = required_full > 0
    if pos_mask.sum() == len(required_full):  # todos > 0 => 24h
        window_start, window_end = i_min_full.min(), f_min_full.max()
    else:
        # ventana = desde el primer intervalo con demanda >0 hasta el último >0
        if pos_mask.any():
            window_start = i_min_full[pos_mask].min()
            window_end   = f_min_full[pos_mask].max()
        else:
            # Si no hay demanda >0, hacemos ventana vacía y salimos
            print("No hay demanda positiva en la curva. Nada que programar.")
            window_start, window_end = None, None

    print(f"Ventana horaria detectada: {window_start//60:02d}:{window_start%60:02d} "
        f"a {window_end//60:02d}:{window_end%60:02d}")

    # Recortamos a la ventana (reduce T y acelera)
    win_mask = (i_min_full >= window_start) & (f_min_full <= window_end)
    i_min    = i_min_full[win_mask]
    f_min    = f_min_full[win_mask]
    required = required_full[win_mask]
    T        = len(required)
    #print(i_min)

    # ============================================================
    # 4) Heurística previa: prefiltrar turnos *antes* de construir curvas
    #    - Descartar los que NO pisan la ventana
    #    - Puntuación rápida ignorando breaks/almuerzo
    # ============================================================ 
    # Filtramos por solapamiento con la ventana
    # (Turno útil si [start,end) intersecta [window_start, window_end))
    #turnos_pref=None
    overlap_mask = ~((turnos["end_min"] <= window_start) | (turnos["start_min"] >= window_end))
    turnos_pref = turnos.loc[overlap_mask].copy().reset_index(drop=True)

    if len(turnos_pref) == 0:
        raise RuntimeError("Ningún turno pisa la ventana detectada. Revisa la data o la lógica de ventana.")

    # Puntuación rápida: suma de requeridos donde el turno tiene cobertura básica (sin pausas)
    # Construimos un vector booleano básico por turno de manera aproximada:
    # Para acelerar, aproximamos que un intervalo [i_min[t], f_min[t]) está cubierto si:
    # start_min <= i_min[t] y end_min >= f_min[t]
    itv_start = i_min  # T
    itv_end   = f_min  # T

    def quick_score(start_m, end_m):
        cover = (start_m <= itv_start) & (end_m >= itv_end)
        return int(np.dot(cover.astype(int), required))

    turnos_pref["quick_score"] = np.vectorize(quick_score)(turnos_pref["start_min"].values,
                                                        turnos_pref["end_min"].values)

    # Elegimos K_PRESELECT mejores por quick_score
    #turnos_k = None
    turnos_k = turnos_pref.sort_values("quick_score", ascending=False).head(K_PRESELECT).reset_index(drop=True)

    print(f"Selección de turnos finalizada: {len(turnos_k)} turnos preseleccionados para curva exacta de "
        f"{T} intervalos.")

    # ============================================================
    # 5) Curva exacta por turno (ahora sí: almuerzo y breaks)
    #    - Si hay almuerzo explícito (Inicio_Refrigerio / Fin_Refrigerio), lo usamos
    #    - Breaks de 15 min: si no hay hora explícita, se infieren alrededor del almuerzo
    # ============================================================
    # Limpieza previa
    for col in ["Descanso1", "Descanso2"]:
        if col in turnos_k.columns:
            turnos_k[col] = pd.to_numeric(turnos_k[col], errors="coerce").fillna(0).astype(int)
        else:
            turnos_k[col] = 0

    for col in ["Inicio_Refrigerio", "Fin_Refrigerio"]:
        if col not in turnos_k.columns:
            turnos_k[col] = ""

    turnos_k["Inicio_Refrigerio"] = turnos_k["Inicio_Refrigerio"].astype(str).str.strip()
    turnos_k["Fin_Refrigerio"]    = turnos_k["Fin_Refrigerio"].astype(str).str.strip()

    def opt_hhmm_to_min(texto):
        s = str(texto).replace("\xa0", " ").strip()
        if s == "" or s.lower() in ("nan", "none"):
            return None
        dt = datetime.strptime(s, "%H:%M")
        return dt.hour*60 + dt.minute

    def build_exact_curve(row):
        s = int(row["start_min"])
        e = int(row["end_min"])

        # vector base: 1 si cubre completamente el intervalo de 30' [i_min[t], f_min[t])
        base = ((s <= i_min_full) & (e >= f_min_full)).astype(int)

        # ventanas de no-trabajo: almuerzo (60 min) y breaks (15 min)
        blocks = []

        # almuerzo explícito
        a0 = opt_hhmm_to_min(row["Inicio_Refrigerio"])
        a1 = opt_hhmm_to_min(row["Fin_Refrigerio"])
        if a0 is not None and a1 is not None:
            # Si el turno cruza medianoche y el almuerzo viene "en el día base",
            # mapeamos almuerzo al mismo "frame" del turno (posible +1440)
            if a1 < a0:  # improbable en catálogos, pero por robustez:
                a1 += 60  # 1h
            # si almuerzo está fuera del [s,e], intentamos mover a +1440 si aplica
            if not (s <= a0 < e):
                a0 += 1440
                a1 += 1440
            blocks.append((a0, a1))
        else:
            # sin almuerzo explícito: nada (o podrías inferir uno si el turno >= 9h)
            pass

        # breaks
        # si hay almuerzo explícito, ponemos break1 justo antes (15') y break2 2h después
        # si no hay almuerzo, inferimos 2 breaks medianos dentro del turno
        if int(row["Descanso1"]) > 0:
            if a0 is not None:
                b1s = a0 - 15
                b1e = a0
            else:
                b1s = s + max(90, (e - s)//3)  # aprox 1.5h o 1/3 de turno
                b1e = b1s + 15
            blocks.append((b1s, b1e))
        if int(row["Descanso2"]) > 0:
            if a1 is not None:
                b2s = a1 + 120  # ~2h después de almuerzo
                b2e = b2s + 15
            else:
                b2e = e - max(90, (e - s)//3)
                b2s = b2e - 15
            blocks.append((b2s, b2e))

        # convertir blocks en máscara 0 en los intervalos afectados
        mask = base.copy()
        for (bs, be) in blocks:
            # un intervalo [itv_start, itv_end) queda anulado si intersecta [bs,be)
            cut = ~((f_min_full <= bs) | (i_min_full >= be))  # intersección no vacía
            mask[cut] = 0

        return mask

    turnos_k["curve_exact"] = [build_exact_curve(row) for _, row in turnos_k.iterrows()]
    turnos_k["exact_score"] = [int(np.dot(c, required_full)) for c in turnos_k["curve_exact"]]

    # Elegimos M_FINAL mejores para el ILP
    turnos_m = None
    turnos_m = turnos_k.sort_values("exact_score", ascending=False).head(M_FINAL).reset_index(drop=True)

    # Matriz de cobertura MxT
    shift_matrix = None
    shift_matrix = np.stack(turnos_m["curve_exact"].values)  # shape (M, T)
    M = shift_matrix.shape[0]

    print(f"Construcción de curva exacta finalizada: {M} turnos para ILP sobre todos los intervalos.")

    # ============================================================
    # 6) ILP compacto (rápido): y_j por turno + slacks u_t / o_t
    #    Minimiza under + 0.1*over + 0.001*headcount
    #    Sujeto a: sum_j y_j * c_{j,t} - required_t = o_t - u_t
    #              y_j <= N_agents
    #              sum_j y_j <= N_agents
    # ============================================================
    solver = None
    y= None
    u= None
    o= None
    solver = pywraplp.Solver.CreateSolver("SCIP")
    y = [solver.IntVar(0, CAP_PER_SHIFT, f"y_{j}") for j in range(M)]
    u = [solver.NumVar(0, solver.infinity(), f"u_{t}") for t in range(48)]
    o = [solver.NumVar(0, solver.infinity(), f"o_{t}") for t in range(48)]

    # Balance
    #  por intervalo: cobertura - requerido = o - u
    for t in range(T):
        solver.Add(
            sum(y[j] * int(shift_matrix[j, t]) for j in range(M)) - int(required_full[t]) == o[t] - u[t]
        )

    # No usar más agentes que los disponibles
    solver.Add(sum(y[j] for j in range(M)) <= N_agents)

    # -------- Coste marginal creciente por turno (segmentos) ----
    # y_j = sum_k seg_jk,  seg_jk ∈ [0, SEG_WIDTH] (último puede ser menor)
    # coste = GAMMA_HEAD * (1 + k*SEG_MULT_STEP + ruido) * seg_jk
    seg_vars = []
    seg_costs = []
    for j in range(M):
        segs_j = []
        costs_j = []
        # número de segmentos máximo = ceil(CAP_PER_SHIFT/SEG_WIDTH)
        Kseg = (CAP_PER_SHIFT + SEG_WIDTH - 1) // SEG_WIDTH
        noise = 1.0 + NOISE_EPS * np.random.rand(Kseg)  # rompe empates
        for k in range(Kseg):
            ub = SEG_WIDTH if (k < Kseg-1) else CAP_PER_SHIFT - SEG_WIDTH*(Kseg-1)
            v = solver.NumVar(0, ub, f"seg_{j}_{k}")
            segs_j.append(v)
            mult = (1.0 + k*SEG_MULT_STEP) * noise[k]
            costs_j.append(GAMMA_HEAD * mult)
        seg_vars.append(segs_j)
        seg_costs.append(costs_j)
        solver.Add(sum(segs_j) == y[j])  # reconstrucción de y_j

    # Objetivo
    obj = ALPHA_UNDER * sum(u) + BETA_OVER * sum(o)
    # añade coste marginal creciente
    for j in range(M):
        for k, v in enumerate(seg_vars[j]):
            obj = obj + seg_costs[j][k] * v

    solver.Minimize(obj)
    solver.SetTimeLimit(SOLVER_MS)  # límite estricto de tiempo
    status = solver.Solve()

    print(f"ILP Solver status: {status}")
    # ============================================================
    # 7) Construcción de la asignación a agentes (greedy)
    # ============================================================
    asignaciones = []
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        # Recuperamos cantidades por turno
        y_val = None
        y_val = np.array([int(round(v.solution_value())) for v in y])
        total_head = y_val.sum()
        print(f"ILP result: {total_head} asignaciones de turnos (con límite {N_agents}).")
        # Asignar a agentes disponibles secuencialmente
        agent_ids = agentes_disponibles["AgentID"].tolist()

        for j in range(M):
            ptr = 0
            cnt = int(y_val[j])
            #print(f"Turno {j}: {cnt} asignaciones.")
            if cnt > 0:
                turno_id = turnos_m.loc[j, "Turno_ID"] if "Turno_ID" in turnos_m.columns else f"T{j:03d}"
                h_ini = str(turnos_m.loc[j, "Hora_Inicio"])
                h_fin   = str(turnos_m.loc[j, "Hora_Termino"])
                #h_ini   = f"{start_m//60:02d}:{start_m%60:02d}"
                #h_fin   = f"{end_m//60:02d}:{end_m%60:02d}"
                # Obtenemos las horas del turno de la base de turnos
                duracion_turno = int(turnos_m.loc[j, "Duracion_Horas"])#print(f"Turno {j} no asignado.")
                ptr = 0
                cnt_avail = cnt
                for _ in range(cnt):
                    #for ptr in range(len(agent_ids)):
                    while cnt_avail > 0:
                        #si el conteo de agentes supera la lista de agentes, es debido a que no hay más agentes disponibles
                        if ptr >= len(agent_ids):
                            break
                            #verificamos si el agente tiene horas disponibles
                        if agentes.loc[agentes["AgentID"].isin([agent_ids[ptr]]), "Horas_Disponibles"].values[0] >= duracion_turno:
                            asignaciones.append({
                                "Agente": agent_ids[ptr],
                                "TurnoID": turno_id,
                                "Inicio": h_ini,
                                "Fin": h_fin
                            })
                            # Actualizamos horas asignadas a los agentes
                            agentes.loc[agentes["AgentID"].isin([agent_ids[ptr]]), "Horas_Asignadas"] += duracion_turno
                            # actaulizamos horas disponibles
                            agentes.loc[agentes["AgentID"].isin([agent_ids[ptr]]), "Horas_Disponibles"] -= duracion_turno
                            # actualizamos horas del día
                            agentes.loc[agentes["AgentID"].isin([agent_ids[ptr]]), [dia]] += duracion_turno
                            # remover el agente que ya no puede recibir otro turno hoy
                            agent_ids.remove(agent_ids[ptr])
                            cnt_avail -= 1
                        ptr += 1
            
    print(f"Total de asignaciones generadas: {len(asignaciones)}")
    # ============================================================
    # 8) Métrica de cobertura final sobre la ventana
    # ============================================================
    # Curva cobierta por los y_j
    covered = np.zeros(48, dtype=int)
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        for j in range(M):
            covered += y_val[j] * shift_matrix[j]

    # Export
    df_asig = pd.DataFrame(asignaciones)
    df_cov  = pd.DataFrame({
        "Inicio_min": i_min_full,
        "Fin_min":    f_min_full,
        "Requeridos": required_full,
        "Cubierto":   covered,
        "Under":      np.maximum(required_full - covered, 0),
        "Over":       np.maximum(covered - required_full, 0)
    })

    df_asig["Fecha"] = dia
    asignacion_semanal.append(df_asig)
    df_cov["Fecha"] = dia
    cobertura_semanal.append(df_cov)

    # Actualizamos lista de agentes disponibles para el siguiente día
    agentes_disponibles = agentes[agentes['Disponible'] == 1].copy()
    agentes_disponibles = agentes_disponibles[agentes_disponibles["Horas_Disponibles"] > 0].copy()
    print(f"Agentes disponibles para el siguiente día: {len(agentes_disponibles)}")
    #agentes = agentes[~agentes["AgentID"].isin(agentes_disponibles)].copy()

#print(y_val)

asignacion_semanal = pd.concat(asignacion_semanal, ignore_index=True)
cobertura_semanal = pd.concat(cobertura_semanal, ignore_index=True)

# Agregamos columnas legibles HH:MM
cobertura_semanal["Inicio_HHMM"] = cobertura_semanal["Inicio_min"].apply(lambda m: f"{m//60:02d}:{m%60:02d}")
cobertura_semanal["Fin_HHMM"]    = cobertura_semanal["Fin_min"].apply(lambda m: f"{m//60:02d}:{m%60:02d}")

asignacion_semanal.to_excel("Result/AsignacionTurnos.xlsx", index=False)
cobertura_semanal[["Fecha","Inicio_HHMM","Fin_HHMM","Requeridos","Cubierto","Under","Over"]].to_excel("Result/CoberturaFinal.xlsx", index=False)
#exportamos agentes con horas asignadas por día
agentes.to_excel("Result/Agents.xlsx", index=False)
print("Proceso completado. Archivos: AsignacionTurnos.xlsx, CoberturaFinal.xlsx")
print(datetime.now().strftime("Fecha y hora de finalización: %Y-%m-%d %H:%M:%S"))
#log("Proceso de generación de horarios completado.")

'''
# ============================================================
# 8) Métricas de evaluación
# ============================================================

import numpy as np

req = df_cov["Requeridos"].to_numpy(dtype=float)
cub = df_cov["Cubierto"].to_numpy(dtype=float)
diff = cub - req

under = np.maximum(-diff, 0.0)
over  = np.maximum( diff, 0.0)

# A) Ajuste de cobertura
under_sum = under.max()
over_sum  = over.max()
mae  = np.mean(np.abs(diff))
rmse = np.sqrt(np.mean(diff**2))

mask_pos = req > 0
mape = np.mean(np.abs(diff[mask_pos]) / req[mask_pos]) if mask_pos.any() else np.nan

# % dentro de banda
delta = 3  # ajusta según sensibilidad
within_band = np.mean(np.abs(diff) <= delta) * 100.0

# Cobertura relativa (solo Req>0)
cov_ratio = (cub[mask_pos] / req[mask_pos]) if mask_pos.any() else np.array([])
cov_mean  = np.mean(cov_ratio) if cov_ratio.size else np.nan
p10 = np.percentile(cov_ratio, 10) if cov_ratio.size else np.nan
p50 = np.percentile(cov_ratio, 50) if cov_ratio.size else np.nan
p90 = np.percentile(cov_ratio, 90) if cov_ratio.size else np.nan

# B) Hotspots
worst_under_idx = np.argsort(-under)[:5]
worst_over_idx  = np.argsort(-over)[:5]

def to_hhmm(m): return f"{int(m)//60:02d}:{int(m)%60:02d}"

print("\n=== MÉTRICAS DE EFECTIVIDAD ===")
print(f"Under total (pers-intervals): {under_sum:,.0f}")
print(f"Over  total (pers-intervals): {over_sum:,.0f}")
print(f"MAE:  {mae:,.3f} | RMSE: {rmse:,.3f} | MAPE: {mape:.3%}" if np.isfinite(mape) else f"MAE: {mae:,.3f} | RMSE: {rmse:,.3f}")
print(f"% intervalos dentro de ±{delta}: {within_band:.1f}%")
print(f"Cobertura media Req>0: {cov_mean:.3f}  (p10={p10:.3f}, p50={p50:.3f}, p90={p90:.3f})")

print("\nPeores UNDER:")
for i in worst_under_idx:
    print(f"  {to_hhmm(df_cov.loc[i, 'Inicio_min'])}-{to_hhmm(df_cov.loc[i, 'Fin_min'])} | Under={under[i]:.0f} (Req={req[i]:.0f}, Cub={cub[i]:.0f})")

print("\nPeores OVER:")
for i in worst_over_idx:
    print(f"  {to_hhmm(df_cov.loc[i, 'Inicio_min'])}-{to_hhmm(df_cov.loc[i, 'Fin_min'])} | Over={over[i]:.0f} (Req={req[i]:.0f}, Cub={cub[i]:.0f})")

# C) Diversidad de turnos
if not df_asig.empty and "TurnoID" in df_asig.columns:
    counts = df_asig["TurnoID"].value_counts().to_numpy(dtype=float)
    p = counts / counts.sum()
    hhi = np.sum(p**2)
    shannon_H = -np.sum(p * np.log(p))
    n_eff = np.exp(shannon_H)

    topk = min(3, len(counts))
    topk_share = counts[:topk].sum() / counts.sum()

    print("\nDiversidad de turnos:")
    print(f"  HHI={hhi:.4f} (↓ mejor),  Entropía={shannon_H:.3f},  N_efectivo={n_eff:.1f}")
    print(f"  % Top-{topk} turnos: {topk_share:.1%}")
else:
    print("\nDiversidad de turnos: sin asignaciones o sin TurnoID.")

'''#'''