"""
WFM Scheduling System - Punto de entrada principal.

Generador de horarios óptimos usando Integer Linear Programming.
Coordina flujo: carga → transformación → optimización → exportación.

Uso:
    python main.py

Resultado:

    - Result/AsignacionTurnos.xlsx
    - Result/CoberturaFinal.xlsx
    - Result/Agents.xlsx
"""

import datetime as dt
import sys
import logging
import numpy as np
import pandas as pd

import config
from src.utils import setup_logging, log_startup, log_completion, summarize_execution
from src.io import load_data_bundle, ensure_output_dir, export_assignment_results
from src.transforms import (
    parse_time_intervals,
    process_turnos_catalog,
    process_agentes_catalog,
    process_avalagentes_catalog,
    convert_to_minutes,
    filter_by_date,
    filter_available_agents,
)
from src.time_utils import min_to_hhmm
from src.coverage import detect_time_window, filter_to_window, log_window_info
from src.shifts import prepare_ilp_inputs, preselect_shifts, compute_exact_curves, select_final_shifts, select_ilp_shifts, select_shifts_by_intensity
from src.optimization import build_daily_ilp, extract_solution, is_solution_valid,solve_wfm_semanal
from src.assignment import (
    assign_shifts_to_agents,
    build_assignment_dataframe,
    build_coverage_dataframe,
    format_coverage_for_export,
)


def main():
    """
    Flujo principal de generación de horarios.
    
    1. Carga de datos (curva, agentes, turnos)
    2. Transformación y normalización
    3. Para cada día:
       a. Detección de ventana horaria
       b. Preselección heurística de turnos
       c. Cálculo de curvas exactas (con pausas)
       d. Resolución ILP
       e. Asignación a agentes
       f. Registro de cobertura
    4. Exportación de resultados
    """
    
    # ============================================================
    # SETUP
    # ============================================================
    logger = setup_logging(__name__, level=logging.INFO, to_file=config.OUTPUT_LOG_FILE)
    log_startup("WFM Scheduling System")
    np.random.seed(config.RANDOM_SEED)
    ensure_output_dir(config.OUTPUT_DIR)
    
    try:
        # ============================================================
        # 1. CARGA DE DATOS
        # ============================================================
        logger.info("="*70)
        logger.info("FASE 1: Carga de datos")
        logger.info("="*70)
        
        curva, agentes, turnos = load_data_bundle(
            config.CURVA_FILE,
            config.AGENTS_FILE,
            config.TURNOS_FILE,
            sep=config.CSV_SEPARATOR,
            encoding=config.CSV_ENCODING
        )
        
        # ============================================================
        # 2. TRANSFORMACIÓN DE DATOS
        # ============================================================
        logger.info("="*70)
        logger.info("FASE 2: Transformación y normalización")
        logger.info("="*70)
        
        # Procesar curva
        curva = parse_time_intervals(curva)
        curva = convert_to_minutes(curva)
        
        # Procesar turnos
        turnos = process_turnos_catalog(turnos)
        
        # Procesar agentes
        agentes = process_agentes_catalog(agentes, config.MAX_HOURS_WEEK)
        
        # Fechas disponibles
        dias_disponibles = filter_by_date(curva)

        logger.info(f"Días a procesar: {len(dias_disponibles)}")
        
        # ============================================================
        # 3. LOOP POR DÍA
        # ============================================================
        logger.info("="*70)
        logger.info("FASE 3: Procesamiento diario (ILP)")
        logger.info("="*70)
        
        asignacion_semanal = []
        cobertura_semanal = []
        ILP_results_semanal = []
        Turnos_K_Week = []
        Novedades_semanal = []
        
        for dia in dias_disponibles:
            dia_w = dt.datetime.strptime(dia, "%d/%m/%Y").date().strftime('%A')
            #dia_w.upper()
            logger.info("")
            logger.info(f"{'*'*70}")
            logger.info(f"Procesando: {dia}")
            logger.info(f"Procesando: {dia_w}")
            logger.info(f"{'*'*70}")

            # Crear columna de tracking del día si no existe
            if dia not in agentes.columns:
                agentes[dia] = 0
            
            # Filtrar curva del día
            curva_dia = curva[curva['Fecha'] == dia].copy()

            # Vectores de datos
            required_curva = curva_dia["Requeridos"].astype(int).values
            required_full = curva_dia["Req_True"].values
            i_min_full = curva_dia["i_min"].values
            f_min_full = curva_dia["f_min"].values
            
            # -------- 3a. Detección de ventana --------
            window_start, window_end = detect_time_window(required_full, i_min_full, f_min_full)
            
            if window_start is None:
                logger.warning(f"Sin demanda positiva en {dia}. Saltando.")
                continue

            #Mesnaje en formato HH:MM "Ventana horaria: 00:00 a 24:00 (48 intervalos)"
            msg_window=log_window_info(window_start, window_end, len(required_full))
            logger.info(msg_window)

            # Filtrar a ventana
            vector_i_min, vector_f_min, vector_required, T = filter_to_window(
                i_min_full, f_min_full, required_full, window_start, window_end
            )

            #Logica de turnos preferidos por agente por día de la semana
            agentes_Def = filter_available_agents(agentes,dia_w,0)
            agentes_Def = process_avalagentes_catalog(agentes_Def,dia_w)
            preferentes_count = len(agentes_Def) if agentes_Def is not None else 0
            logger.info(f"Agentes con turnos preferentes para {dia_w}: {preferentes_count}")

            if preferentes_count > 0:
                agentes_Def = agentes_Def.rename(columns={dia_w: 'disponible'})
                agentes_Def["Turno_ID"] = "Sin preferencia"
                agentes_Def['Fecha']=dia
                for index,row in agentes_Def.iterrows():
                    agent_id = row["AgentID"]
                    curva_agent=row["Curva"]
                    window_start_agent = row["inicio_min"], 
                    window_end_agent = row["fin_min"],
                    #convertimos curva por agente a dataframe para sacar vectores de i_min, f_min y required
                    curva_agent_df = pd.DataFrame({
                        "Intervalo": curva_agent,
                        "agent_count": 1
                    })
                    curva_dia_agent = curva_dia.merge(curva_agent_df, on="Intervalo", how="left")
                    # Vectores de datos
                    required_agent = curva_dia_agent["agent_count"].values
                    i_min_agent = curva_dia_agent["i_min"].values
                    f_min_agent = curva_dia_agent["f_min"].values

                    vector_i_min_agent, vector_f_min_agent, vector_required_agent, T = filter_to_window(
                        i_min_agent, f_min_agent, required_agent, window_start_agent, window_end_agent
                    )
                    turnos_k_agent = preselect_shifts(
                        turnos,
                        window_start_agent,
                        window_end_agent,
                        vector_i_min_agent, 
                        vector_f_min_agent, 
                        vector_required_agent,
                    )
                    turnos_k_agent = select_final_shifts(
                        turnos_k_agent,
                        "quick_score",
                        config.M_FINAL,
                        config.CAP_PER_INTENSITY
                    )
                    turnos_k_agent = select_shifts_by_intensity(
                        turnos_k_agent,
                        score_column="score_final",
                        n_preselect=config.M_FINAL,
                        cap_per_intensity=config.CAP_PER_INTENSITY
                    )
                    #print(turnos_k_agent)
                    for index, row in turnos_k_agent.iterrows():
                        turno_id = row["Turno_ID"]
                        duracion = int(row["Duracion_Horas"])
                        horas_disp = float(agentes.loc[agentes["AgentID"] == agent_id, "Horas_Disponibles"].values[0])
                        #fundamental por que no hay otro filtro dentro del ciclo que verifique las horas, si el agente no tiene horas disponibles, se pasa al siguiente
                        if horas_disp >= duracion:
                            #asignamos el turno preferente al agente en la tabla de agentes_def
                            agentes_Def.loc[agentes_Def["AgentID"] == agent_id, "Turno_ID"] = turno_id
                            # Actualizar agentes
                            agentes.loc[agentes["AgentID"] == agent_id, "Horas_Asignadas"] += duracion
                            agentes.loc[agentes["AgentID"] == agent_id, "Horas_Disponibles"] -= duracion# actualizamos horas del día
                            agentes.loc[agentes["AgentID"] == agent_id, [dia]] += duracion
                            #print(turno_id)
                            turnos_asignados = True  # Se ha asignado al menos un turno en este ciclo
                            break
                    if not turnos_asignados:
                    #else:
                        logger.warning(f"No hay turnos preferentes disponibles para el agente {agent_id} en {dia_w}. Se considera sin preferencia.")
                        agentes_Def.loc[agentes_Def["AgentID"] == agent_id, "Turno_ID"] = "Sin preferencia"
                #Construcción del dataframe de novedades diarias por agente
                agentes_Def = pd.merge(agentes_Def, turnos[["Turno_ID", "Hora_Inicio", "Hora_Termino"]], on="Turno_ID", how="left")
                agentes_Pref = agentes_Def[["AgentID", "Turno_ID", "Hora_Inicio", "Hora_Termino", "Fecha", "disponible"]]
                turnos_IDPref = agentes_Pref["Turno_ID"].unique().tolist()
                #si en realidad hay turnos preferentes por novedades ejerce la logica
                if turnos_IDPref is not None:
                    turnos_pref = turnos.loc[turnos["Turno_ID"].isin(turnos_IDPref)].reset_index(drop=True)
                    turnos_pref = compute_exact_curves(turnos_pref, i_min_full, f_min_full, required_full)
                    turnos_pref["Asignados"] = 0
                    turnos_pref["Fecha"] = dia
                    pref_matrix = prepare_ilp_inputs(turnos_pref)
                    turnos_pref["Real_Agendas"] = (agentes_Pref["Turno_ID"].value_counts().reindex(turnos_pref["Turno_ID"]).fillna(0).astype(int).values) if not agentes_Pref.empty else 0
                    # Real_Matrix está en minutos (0..30 por intervalo). Para comparar con 'Requeridos' (en agentes),
                    # convertimos a agente-equivalente dividiendo entre 30.
                    pref_covered_min = np.zeros(48, dtype=float)
                    for j in range(len(turnos_pref)):
                        pref_covered_min += int(turnos_pref.loc[j, "Real_Agendas"]) * pref_matrix[j]
                    Pref_covered = pref_covered_min / 30.0
                    required_NoPref = required_curva - Pref_covered
                Novedades_semanal.append(agentes_Pref)
            else:
                required_NoPref = required_curva

            # Agentes disponibles
            agentes_disponibles = filter_available_agents(agentes,dia_w,1)
            #si el día es mayor al lunes se reordena la base de agentes por las horas disponibles
            #dt.datetime.strptime(dia, "%d/%m/%Y").date()
            ndayw = dt.datetime.strptime(dia, "%d/%m/%Y").date().weekday()
            if ndayw > 0:
                agentes_disponibles = agentes_disponibles.sort_values(by="Horas_Disponibles",ascending=False)
            n_agents = len(agentes_disponibles)
            logger.info(f"Agentes disponibles: {n_agents}")
            if n_agents == 0:
                logger.warning(f"No hay agentes disponibles para {dia}. Saltando.")
                continue
            
            # -------- 3b. Preselección heurística --------
            #logger.info(f"Preselección heurística K={config.K_PRESELECT}...")
            turnos_solap = preselect_shifts(
                turnos,
                window_start,
                window_end,
                vector_i_min, 
                vector_f_min, 
                vector_required
            )
            logger.info(f"Preseleccionados {len(turnos_solap)} turnos solapantes")
            turnos_solap = select_final_shifts(
                turnos_solap,
                "quick_score",
                config.K_PRESELECT,
                config.CAP_PER_INTENSITY
            )
            turnos_k = select_shifts_by_intensity(
                turnos_solap,
                score_column="score_final",
                n_preselect=config.K_PRESELECT,
                cap_per_intensity=config.CAP_PER_INTENSITY
            )
            logger.info(f"Preseleccionados {len(turnos_k)} turnos por intensidad de {len(turnos_solap)} turnos solapantes.")
            
            # -------- 3c. Curvas exactas --------
            #logger.info(f"Cálculo de curvas exactas para K={config.K_PRESELECT}...")
            turnos_k = compute_exact_curves(turnos_k, i_min_full, f_min_full, required_full)
            turnos_k["Fecha"] = dia
            
            turnos_k = select_final_shifts(
                turnos_k,
                "exact_score",
                config.M_FINAL,
                config.CAP_PER_INTENSITY
            )
            turnos_m = select_shifts_by_intensity(
                turnos_k,
                score_column="score_final",
                n_preselect=config.M_FINAL,
                cap_per_intensity=config.CAP_PER_INTENSITY
            )
            logger.info(f"Seleccionados {len(turnos_m)} turnos de {len(turnos_k)} procesados por intensidad.")
            shift_matrix = prepare_ilp_inputs(turnos_m)

            M = shift_matrix.shape[0]
            #logger.info(f"Matriz de cobertura: {M} turnos × 48 intervalos")
            
            # -------- 3d. Resolución ILP --------
            logger.info(f"Resolviendo ILP diario...")
            
            solver, y, u, o, M_check, T_check, status = build_daily_ilp(
                shift_matrix,
                required_NoPref,
                n_agents,
                config.ALPHA_UNDER,
                config.BETA_OVER,
                config.GAMMA_HEAD,
                config.CAP_PER_SHIFT,
                config.SEG_WIDTH,
                config.SEG_MULT_STEP,
                config.NOISE_EPS,
                config.SOLVER_MS,
                config.RANDOM_SEED
            )
            
            # -------- 3e. Extracción de solución --------
            if is_solution_valid(status):
                y_val, covered, metrics = extract_solution(
                    solver, y, u, o, shift_matrix, required_full
                )
                
                #registrar asignaciones en turnos_m
                turnos_m["Asignados"] = [int(round(y[j].solution_value())) for j in range(M)]

                #reduce la selección de turnos a los asignados
                turnos_ilp  = select_ilp_shifts(
                    turnos_m=turnos_m,
                    solver=solver,                 # opcional
                    cap_per_shift=config.CAP_PER_SHIFT,   # opcional
                    n_agents=n_agents              # opcional (solo logging)
                )
  
                real_matrix = prepare_ilp_inputs(turnos_ilp)

                # -------- 3f. Asignación a agentes --------
                logger.info(f"Asignando turnos a agentes...")
                
                agentes_ids = agentes_disponibles["AgentID"].tolist()
                asignaciones = assign_shifts_to_agents(
                    y_val, turnos_ilp, agentes, agentes_ids, dia
                )

                # Construir dataframes
                df_asig = build_assignment_dataframe(asignaciones, dia)
                #inclusión de turnos asignados en el tracking de novedades diarias por agente
                #si y solo si hay asignaciones de turnos preferentes en el día
                #if preferentes_count > 0:
                    #Incluimos en las asignaciones los turnos preferenciales asignados por los novedades de losa gentes
                #    df_asig = pd.concat([agentes_Pref, df_asig], ignore_index=True)
                #conteo de agendas reales asignadas por turno, incluyendo los turnos preferentes de los agentes con novedades
                turnos_ilp["Real_Agendas"] = (df_asig["Turno_ID"].value_counts().reindex(turnos_ilp["Turno_ID"]).fillna(0).astype(int).values) if not df_asig.empty else 0
                
                # Real_Matrix está en minutos (0..30 por intervalo). Para comparar con 'Requeridos' (en agentes),
                # convertimos a agente-equivalente dividiendo entre 30.
                Real_covered_min = np.zeros(48, dtype=float)
                for j in range(len(turnos_ilp)):
                    Real_covered_min += int(turnos_ilp.loc[j, "Real_Agendas"]) * real_matrix[j]
                Real_covered = Real_covered_min / 30.0

                #consolidados datos de turnos preferentes y turnos del ILP y el solver final
                Real_covered = Real_covered + Pref_covered
                df_asig = pd.concat([agentes_Pref, df_asig], ignore_index=True)
                turnos_ilp = pd.concat([turnos_ilp, turnos_pref], ignore_index=True)

                asignacion_semanal.append(df_asig)
                turnos_ilp["Fecha"] = dia
                ILP_results_semanal.append(turnos_ilp)

                df_cov = build_coverage_dataframe(i_min_full, f_min_full, required_curva, Real_covered, dia)
                cobertura_semanal.append(df_cov)
                Turnos_K_Week.append(turnos_m)

                logger.info(f"Día {dia} completado: {len(asignaciones)} asignaciones")
                
            else:
                logger.error(f"ILP no encontró solución para {dia}")
            
            # Actualizar agentes disponibles
            #agentes_disponibles = filter_available_agents(agentes)
            #logger.info(f"Agentes con horas disponibles para próximo día: {len(agentes_disponibles)}")
        
        # Concatenar resultados semanales
        asignacion_semanal = pd.concat(asignacion_semanal, ignore_index=True)
        cobertura_semanal = pd.concat(cobertura_semanal, ignore_index=True)
        ILP_results_semanal = pd.concat(ILP_results_semanal, ignore_index=True)
        Turnos_K_Week = pd.concat(Turnos_K_Week, ignore_index=True)
        Novedades_semanal = pd.concat(Novedades_semanal, ignore_index=True)

        # ============================================================
        # 3.1 MILP SEMANAL
        # ============================================================
        agentes_ids = agentes["AgentID"].astype(int).values
        # Pasamos data de agentes de formato matriz a formato BBDD
        # La llave será (AgenteID, Fecha) y el valor la Duración
        agents_results = agentes.drop(columns=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday","Disponible","Horas_Disponibles","Horas_Asignadas"])
        agents_results = agents_results.melt(
            id_vars=['AgentID'], 
            value_vars=dias_disponibles, 
            var_name='Fecha', 
            value_name='Duracion'
        )
        agents_results['Fecha'] = pd.to_datetime(agents_results['Fecha'], format="%d/%m/%Y")
        agents_results['dia'] = agents_results['Fecha'].dt.weekday
        agents_results = agents_results.set_index(["AgentID","dia"])["Duracion"].to_dict()
        #tomamos el maximo por cada día para establecer el requerido para cada día rapídamente.
        curva_by_dia = curva.groupby('Fecha').agg({'Requeridos': 'max'}).reset_index()
        curva_by_dia['Fecha'] = pd.to_datetime(curva_by_dia['Fecha'], format="%d/%m/%Y")
        curva_by_dia['dia'] = curva_by_dia['Fecha'].dt.weekday
        dias_disponibles = sorted(curva_by_dia['dia'].unique())
        demand_dict = curva_by_dia.set_index('dia')['Requeridos'].to_dict()
        # Creamos un diccionario donde la llave es el ID y el valor es una tupla o lista
        turnos_unicos = ILP_results_semanal['Turno_ID'].unique()
        turno_to_idx = {turno_str: idx for idx, turno_str in enumerate(turnos_unicos)}
        # dict inverso para traducir el output del solver después
        idx_to_turno = {idx: turno_str for turno_str, idx in turno_to_idx.items()}
        ILP_results_semanal['Turno_Index'] = ILP_results_semanal['Turno_ID'].map(turno_to_idx)
        ILP_results_semanal['Fecha'] = pd.to_datetime(ILP_results_semanal['Fecha'], format="%d/%m/%Y")
        ILP_results_semanal['dia'] = ILP_results_semanal['Fecha'].dt.weekday
        ILP_results_semanal['Duracion_Minutos'] = (ILP_results_semanal['Duracion_Horas'] * 60).astype(int)
        MAX_HOURS_WEEK_MIN = int(config.MAX_HOURS_WEEK * 60)
        turnos_by_fecha = ILP_results_semanal.groupby("dia")["Turno_Index"].apply(list).to_dict()
        MILP_info = ILP_results_semanal.set_index(["Turno_Index", "dia"])["Real_Agendas"].to_dict()
        turnos_dict = ILP_results_semanal.drop_duplicates(subset=['Turno_Index','start_min','end_min','Duracion_Minutos'])
        turnos_dict = turnos_dict.set_index('Turno_Index')[['start_min','end_min','Duracion_Minutos']].T.to_dict('list')
        #resultado del proceos No1, se condensa para pasara a MILP
        asignacion_semanal["AgentID"] = asignacion_semanal["AgentID"].astype(int).values
        asignacion_semanal['Fecha'] = pd.to_datetime(asignacion_semanal['Fecha'], format="%d/%m/%Y")
        asignacion_semanal['dia'] = asignacion_semanal['Fecha'].dt.weekday
        asignacion_semanal['Turno_Index'] = asignacion_semanal['Turno_ID'].map(turno_to_idx)
        MILP_Source = list(asignacion_semanal[["AgentID", "dia", "Turno_Index"]].itertuples(index=False, name=None))

        #'''
        solverMILP, statusMILP = solve_wfm_semanal(
                        agentes_ids,
                        agents_results,
                        dias_disponibles,
                        turnos_by_fecha,
                        turnos_dict,
                        MILP_info,
                        MILP_Source,
                        MAX_HOURS_WEEK_MIN,
                        config.REST_MIN_GAP,                
        )#'''
        # ============================================================
        # 4. EXPORTACIÓN DE RESULTADOS
        # ============================================================
        logger.info("="*70)
        logger.info("FASE 4: Exportación de resultados")
        logger.info("="*70)
         
        # Formatear cobertura
        cobertura_semanal = format_coverage_for_export(cobertura_semanal)
        
        # Exportar
        export_assignment_results(
            asignacion_semanal,
            cobertura_semanal[["Fecha", "Inicio_HHMM", "Fin_HHMM", "Requeridos", "Real_Cubierto" ,"Under", "Over"]],
            agentes,
            ILP_results_semanal,
            Turnos_K_Week,
            Novedades_semanal,
            config.OUTPUT_ASSIGNMENT,
            config.OUTPUT_COVERAGE,
            config.OUTPUT_AGENTS,
            config.OUTPUT_ILP_RESULTS,
            config.OUTPUT_TURNOS_K,
            config.OUTPUT_NOVEDADES
        )
        
        # ============================================================
        # 5. RESUMEN FINAL
        # ============================================================
        total_assignments = len(asignacion_semanal)
        total_hours = agentes["Horas_Asignadas"].sum()
        
        summarize_execution(
            len(dias_disponibles),
            total_assignments,
            total_hours
        )
        
        log_completion("WFM Scheduling System")
        logger.info("\n✓ Proceso completado exitosamente\n")
        
        return 0
    
    except Exception as e:
        logger.exception(f"Error en ejecución: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
