# Programador_progress_v2_cp_only_with_breaks_and_exports.py
# Versión: CP-only (sin greedy) + breaks placement + 12h rest enforcement + export con breaks + persist export en session_state
# Requisitos: pandas, numpy, matplotlib, openpyxl, ortools, streamlit
# Ejecutar: streamlit run Programador_progress_v2_cp_only_with_breaks_and_exports.py

import os
import math
import time
import io
import unicodedata
import threading
from datetime import datetime, timedelta, date

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from ortools.sat.python import cp_model

st.set_page_config(layout="wide", page_title="Programador WFM - CP-Only (breaks+exports)")
st.title("📊 Programador WFM/Reporting")

# -------------------------
# Constants (ajustables)
# -------------------------
MIN_DAYS_HORIZON = 7
MAX_DAYS_HORIZON = 28
MAX_SUNDAYS_PER_AGENT = 2
FESTIVO_HOURS_DISCOUNT = 7.33
MAX_OVERTIME_PER_DAY_MIN = 2 * 60
MIN_REST_MIN = 12 * 60            # 12 hours rest between end and next start (in minutes)
ROUND_TO_MIN = 15                 # round breaks to multiples of 15 minutes

# -------------------------
# Utils / readers / parsers
# -------------------------
def normalize(s):
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')

def detect_column_by_candidates(df, candidates):
    if df is None:
        return None
    norm_map = {normalize(c): c for c in df.columns}
    for cand in candidates:
        nc = normalize(cand)
        if nc in norm_map:
            return norm_map[nc]
    for k, v in norm_map.items():
        for cand in candidates:
            if normalize(cand) in k:
                return v
    return None

def time_str_to_min(val):
    if pd.isna(val):
        return 0
    try:
        import datetime as _dt
        if isinstance(val, _dt.time):
            return val.hour * 60 + val.minute
    except Exception:
        pass
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    s = str(val).strip()
    if s == "":
        return 0
    if ":" in s:
        try:
            parts = s.split(":")
            h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
            return h * 60 + m
        except:
            pass
    try:
        return int(float(s))
    except:
        try:
            dt = pd.to_datetime(s, errors='coerce')
            if not pd.isna(dt):
                return dt.hour * 60 + dt.minute
        except:
            pass
    return 0

def _has_module(modname):
    try:
        __import__(modname)
        return True
    except Exception:
        return False

def safe_read_excel(fileobj_or_path):
    def choose_engine_for_ext(ext):
        ext = ext.lower()
        if ext == "xlsx":
            if not _has_module("openpyxl"):
                raise RuntimeError("Falta 'openpyxl'. Instálalo: pip install openpyxl")
            return "openpyxl"
        if ext == "xls":
            if not _has_module("xlrd"):
                raise RuntimeError("Para leer .xls necesitas 'xlrd' (pip install xlrd)")
            return "xlrd"
        if ext == "xlsb":
            if not _has_module("pyxlsb"):
                raise RuntimeError("Para leer .xlsb necesitas 'pyxlsb' (pip install pyxlsb)")
            return "pyxlsb"
        return None

    if isinstance(fileobj_or_path, str):
        path = fileobj_or_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"No existe el archivo: {path}")
        ext = path.lower().split('.')[-1]
        if ext == "csv":
            return pd.read_csv(path)
        elif ext in ("xlsx","xls","xlsb"):
            engine = choose_engine_for_ext(ext)
            if engine:
                return pd.read_excel(path, engine=engine)
            else:
                return pd.read_excel(path)
        else:
            raise ValueError("Solo se permiten archivos .xlsx, .xls, .xlsb o .csv.")

    file = fileobj_or_path
    filename = getattr(file, "name", None)
    try:
        file.seek(0)
    except Exception:
        pass

    head_bytes = None
    try:
        raw = file.read(4096)
        if isinstance(raw, bytes):
            head_bytes = raw
        else:
            head_bytes = str(raw).encode('utf-8', errors='ignore')
    except Exception:
        head_bytes = None

    try:
        file.seek(0)
    except Exception:
        pass

    ext = None
    if filename:
        ext = filename.lower().split('.')[-1]

    is_zip_like = False
    is_ole2 = False
    looks_like_text = False
    if head_bytes is not None:
        if head_bytes.startswith(b'PK'):
            is_zip_like = True
        if head_bytes.startswith(b'\xD0\xCF'):
            is_ole2 = True
        txt = head_bytes.lstrip()
        if len(txt) > 0 and (b',' in txt[:512] or b'\t' in txt[:512] or txt.startswith(b'<' ) or txt.startswith(b'"') or b';' in txt[:512]):
            looks_like_text = True

    ext_error = None
    if ext in ("xlsx","xls","xlsb","csv"):
        try:
            if ext == "csv":
                file.seek(0); return pd.read_csv(file)
            engine = choose_engine_for_ext(ext) if ext != "csv" else None
            file.seek(0)
            if engine:
                return pd.read_excel(file, engine=engine)
            else:
                return pd.read_excel(file)
        except Exception as e_ext:
            ext_error = e_ext

    if is_zip_like:
        if not _has_module("openpyxl"):
            raise RuntimeError("El archivo parece ser .xlsx pero falta 'openpyxl'. Instálalo: pip install openpyxl")
        try:
            file.seek(0)
            data = file.read()
            bio = io.BytesIO(data); bio.seek(0)
            return pd.read_excel(bio, engine="openpyxl")
        except Exception as e:
            raise RuntimeError(f"No pude leer como .xlsx (openpyxl). Detalle: {e}")

    if is_ole2:
        if not _has_module("xlrd"):
            raise RuntimeError("El archivo parece ser .xls pero no tienes 'xlrd'. Instálalo: pip install xlrd")
        try:
            file.seek(0)
            data = file.read()
            bio = io.BytesIO(data); bio.seek(0)
            return pd.read_excel(bio, engine="xlrd")
        except Exception as e:
            raise RuntimeError(f"No pude leer como .xls (xlrd). Detalle: {e}")

    if looks_like_text:
        try:
            file.seek(0)
            data = file.read()
            if isinstance(data, bytes):
                bio = io.BytesIO(data); bio.seek(0)
                return pd.read_csv(bio)
            else:
                return pd.read_csv(io.StringIO(str(data)))
        except Exception as e:
            raise RuntimeError(f"El archivo parece texto (CSV) pero falló la lectura. Detalle: {e}")

    try:
        file.seek(0)
        data = file.read()
        if isinstance(data, bytes):
            bio = io.BytesIO(data); bio.seek(0)
            return pd.read_excel(bio)
        else:
            return pd.read_csv(io.StringIO(str(data)))
    except Exception as e_final:
        msg = ("No pude determinar el formato. "
               "Sugerencias: guarda como .xlsx o instala xlrd/pyxlsb si corresponde. "
               f"Detalle: {e_final}")
        if ext_error is not None:
            msg += f" Ext error: {ext_error}"
        raise RuntimeError(msg)

def validate_file(fileobj_or_path, label):
    try:
        df = safe_read_excel(fileobj_or_path)
        return df, None
    except Exception as e:
        head = None
        try:
            if isinstance(fileobj_or_path, str):
                with open(fileobj_or_path, "rb") as f:
                    head = f.read(128)
            else:
                try:
                    fileobj_or_path.seek(0)
                    raw = fileobj_or_path.read(128)
                    fileobj_or_path.seek(0)
                    if isinstance(raw, bytes):
                        head = raw
                    else:
                        head = str(raw).encode('utf-8', errors='ignore')
                except Exception:
                    head = None
        except Exception:
            head = None
        debug = repr(head[:64]) if head else "<no head>"
        msg = f"Error leyendo {label}: {e}\nDEBUG_FIRST_BYTES={debug}"
        return None, msg

def load_master_turns_from_df(df):
    if df is None or df.shape[0] == 0:
        raise ValueError("Maestra de turnos vacía.")
    id_col = detect_column_by_candidates(df, ['descripcion','turno','turno_id','id','nombre'])
    start_col = detect_column_by_candidates(df, ['hora_inicio','hora_ini','hora_ingreso','inicio','start','hora_entrada','entrada'])
    end_col = detect_column_by_candidates(df, ['hora_termino','hora_fin','fin','end','hora_salida','salida'])
    d1_col = detect_column_by_candidates(df, ['descanso1','descanso_1','break1','descanso'])
    d2_col = detect_column_by_candidates(df, ['descanso2','descanso_2','break2'])
    lunch_col = detect_column_by_candidates(df, ['refrigerio','almuerzo','tiempo_de_almuerzo','lunch'])
    heff_col = detect_column_by_candidates(df, ['h.efectivas','h_efectivas','tiempo_disponible','h_efectiva'])
    if start_col is None or end_col is None:
        raise ValueError("No encontré columnas de inicio/fin en la maestra de turnos. Columnas: " + ", ".join(df.columns.astype(str)))
    out = pd.DataFrame()
    out['turno_id'] = df[id_col] if id_col is not None else df.index.astype(str)
    out['start_raw'] = df[start_col]
    out['end_raw'] = df[end_col]
    out['break1_min'] = df[d1_col].fillna(0).astype(float) if d1_col and d1_col in df.columns else 0.0
    out['break2_min'] = df[d2_col].fillna(0).astype(float) if d2_col and d2_col in df.columns else 0.0
    out['lunch_min'] = df[lunch_col].fillna(0).astype(float) if lunch_col and lunch_col in df.columns else 0.0
    out['break_min'] = out['break1_min'] + out['break2_min']
    out['effective_min_raw'] = df[heff_col] if heff_col and heff_col in df.columns else np.nan
    out['start_min'] = out['start_raw'].apply(time_str_to_min)
    out['end_min'] = out['end_raw'].apply(time_str_to_min)
    def compute_duration(s,e):
        s = int(s); e = int(e)
        if e >= s:
            return e - s
        else:
            return (24*60 - s) + e
    out['duration_min'] = out.apply(lambda r: compute_duration(r['start_min'], r['end_min']), axis=1)
    def compute_effective(row):
        if not pd.isna(row['effective_min_raw']):
            try:
                return float(row['effective_min_raw'])
            except:
                pass
        return max(0.0, row['duration_min'] - row['break_min'] - row['lunch_min'])
    out['effective_min'] = out.apply(compute_effective, axis=1)
    out['shift_type'] = out['start_min'].apply(lambda s: 'day' if 5*60 <= s <= 20*60+59 else 'night')
    for c in ['start_min','end_min','duration_min','break1_min','break2_min','break_min','lunch_min','effective_min']:
        out[c] = out[c].astype(float)
    out['start'] = out['start_raw'].astype(str)
    out['end'] = out['end_raw'].astype(str)
    cols = ['turno_id','start','end','start_min','end_min','duration_min','break1_min','break2_min','break_min','lunch_min','effective_min','shift_type']
    return out[cols]

def load_forecast_from_df(df):
    if df is None or df.shape[0] == 0:
        raise ValueError("Forecast vacío.")
    date_col = detect_column_by_candidates(df, ['fecha','date'])
    time_col = detect_column_by_candidates(df, ['intervalo','interval','hora','time','hora_inicio'])
    calls_col = detect_column_by_candidates(df, ['recibidas','calls','llamadas','pronosticadas','volume','volumen','y'])
    fest_col = detect_column_by_candidates(df, ['festivo','feriado','holiday'])
    if calls_col is None:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            calls_col = numeric_cols[0]
        else:
            raise ValueError("No encontré columna de llamadas en Input.xlsx. Columnas: " + ", ".join(df.columns.astype(str)))
    if date_col is not None and time_col is not None:
        dates = pd.to_datetime(df[date_col], errors='coerce')
        intervals = df[time_col].astype(str).fillna('')
        combined = []
        fest_list = []
        for d, inter, orig_idx in zip(dates, intervals, df.index):
            if pd.isna(d):
                combined.append(pd.NaT); fest_list.append(False); continue
            inter = str(inter).strip()
            if inter == '':
                combined.append(pd.NaT); fest_list.append(False); continue
            if ':' in inter:
                try:
                    hp = inter.split(':'); h=int(hp[0]); m=int(hp[1]) if len(hp)>1 else 0
                    combined.append(datetime.combine(d.date(), datetime.min.time()) + timedelta(hours=h, minutes=m))
                except:
                    try:
                        combined.append(pd.to_datetime(f"{d.date()} {inter}", errors='coerce'))
                    except:
                        combined.append(pd.NaT)
            else:
                try:
                    combined.append(datetime.combine(d.date(), datetime.min.time()) + timedelta(minutes=int(float(inter))))
                except:
                    try:
                        combined.append(pd.to_datetime(f"{d.date()} {inter}", errors='coerce'))
                    except:
                        combined.append(pd.NaT)
            if fest_col and fest_col in df.columns:
                val = df.loc[orig_idx, fest_col]
                fest_list.append(str(val).strip().lower() in ['si','s','yes','y','true','1', 't'])
            else:
                fest_list.append(False)
        out = pd.DataFrame({'ds': combined, 'calls': pd.to_numeric(df[calls_col], errors='coerce').fillna(0), 'festivo': fest_list})
        out = out[~out['ds'].isna()].sort_values('ds').reset_index(drop=True)
        out['festivo'] = out['festivo'].astype(bool)
        return out
    dt_col = detect_column_by_candidates(df, ['ds','datetime','timestamp','fecha_hora','fecha_hora'])
    if dt_col is not None:
        out = df[[dt_col, calls_col]].copy()
        out.columns = ['ds','calls']
        out['ds'] = pd.to_datetime(out['ds'], errors='coerce')
        out['calls'] = pd.to_numeric(out['calls'], errors='coerce').fillna(0)
        out = out[~out['ds'].isna()].sort_values('ds').reset_index(drop=True)
        if fest_col and fest_col in df.columns:
            fest_vals = df.loc[out.index, fest_col].fillna(False)
            out['festivo'] = fest_vals.apply(lambda v: str(v).strip().lower() in ['si','s','yes','y','true','1','t'])
        else:
            out['festivo'] = False
        return out
    try:
        maybe_ds = pd.to_datetime(df.iloc[:,0], errors='coerce')
        maybe_calls = pd.to_numeric(df.iloc[:,1], errors='coerce').fillna(0)
        out = pd.DataFrame({'ds': maybe_ds, 'calls': maybe_calls})
        out = out[~out['ds'].isna()].sort_values('ds').reset_index(drop=True)
        out['festivo'] = False
        return out
    except Exception:
        raise ValueError("No pude interpretar Input.xlsx: proporciona Fecha+Intervalo+Recibidas o columna datetime + llamadas.")

# -------------------------
# Erlang helpers
# -------------------------
def erlang_c_probability(a, n):
    if n <= 0:
        return 1.0
    sum_terms = 0.0
    for k in range(n):
        sum_terms += (a**k) / math.factorial(k)
    if n - a == 0:
        last_term = (a**n) / math.factorial(n) * 1e6
    else:
        last_term = (a**n) / (math.factorial(n) * (1 - a / n))
    p0 = 1.0 / (sum_terms + last_term)
    numerator = ((a**n) / math.factorial(n)) * (n / (n - a)) if n > a else (a**n) / math.factorial(n) * 1e6
    erlangC = numerator * p0
    return min(max(erlangC, 0.0), 1.0)

def service_level_from_erlangC(erlangC, n, a, asa, aht):
    if n <= a:
        return 0.0
    exponent = - (n - a) * (asa) / aht
    try:
        val = 1.0 - erlangC * math.exp(exponent)
    except OverflowError:
        val = 0.0
    return max(0.0, min(1.0, val))

def required_agents_for_interval(calls, aht_sec, service_level_target, interval_sec, asa=20):
    if calls <= 0:
        return 0
    lam = calls / interval_sec
    a = lam * aht_sec
    n = max(1, int(math.ceil(a)))
    maxn = max(200, n + 400)
    while n <= maxn:
        erc = erlang_c_probability(a, n)
        sl = service_level_from_erlangC(erc, n, a, asa, aht_sec)
        if sl >= service_level_target:
            return n
        n += 1
    return n

# -------------------------
# break placement helper
# -------------------------
def round_to_multiple(x, base=ROUND_TO_MIN):
    return int(base * round(float(x) / base))

def compute_break_schedule_for_shift(start_dt, duration_min, lunch_min, break1_min, break2_min):
    """
    Returns list of dicts: [{'type':'lunch'/'break1'/'break2','start':dt,'end':dt,'minutes':int}, ...]
    Placement heuristics:
      - if lunch present:
          - lunch at ~50% of shift
          - other breaks (if any): if one extra -> ~25%, if two -> ~25% and ~75%
      - if no lunch:
          - 1 break -> 50%
          - 2 breaks -> ~33% and ~66%
    All break starts rounded to nearest ROUND_TO_MIN, constrained inside shift.
    """
    L = int(duration_min)
    breaks = []
    def safe_place(offset_pct, length_min):
        center = start_dt + timedelta(minutes=int(round(offset_pct * L)))
        half = int(round(length_min / 2.0))
        s = center - timedelta(minutes=half)
        e = s + timedelta(minutes=int(length_min))
        s_min = start_dt
        e_max = start_dt + timedelta(minutes=L)
        if s < s_min:
            s = s_min
            e = s + timedelta(minutes=int(length_min))
        if e > e_max:
            e = e_max
            s = e - timedelta(minutes=int(length_min))
        s_rounded_min = round_to_multiple(s.hour*60 + s.minute)
        s_rounded = datetime.combine(s.date(), datetime.min.time()) + timedelta(minutes=s_rounded_min)
        if s_rounded < s_min:
            s_rounded = s_min
        if s_rounded + timedelta(minutes=int(length_min)) > e_max:
            s_rounded = e_max - timedelta(minutes=int(length_min))
        e_rounded = s_rounded + timedelta(minutes=int(length_min))
        return s_rounded, e_rounded

    break_items = []
    if lunch_min and lunch_min > 0:
        break_items.append(('lunch', int(round(lunch_min))))
    extra_breaks = []
    if break1_min and break1_min > 0:
        extra_breaks.append(('break1', int(round(break1_min))))
    if break2_min and break2_min > 0:
        extra_breaks.append(('break2', int(round(break2_min))))

    if break_items and extra_breaks:
        s_l, e_l = safe_place(0.5, break_items[0][1])
        breaks.append({'type': break_items[0][0], 'start': s_l, 'end': e_l, 'minutes': int((e_l - s_l).total_seconds()//60)})
        if len(extra_breaks) == 1:
            tname, tlen = extra_breaks[0]
            s_b, e_b = safe_place(0.25, tlen)
            breaks.append({'type': tname, 'start': s_b, 'end': e_b, 'minutes': int((e_b - s_b).total_seconds()//60)})
        else:
            for idx, (tname, tlen) in enumerate(extra_breaks):
                pct = 0.25 if idx == 0 else 0.75
                s_b, e_b = safe_place(pct, tlen)
                breaks.append({'type': tname, 'start': s_b, 'end': e_b, 'minutes': int((e_b - s_b).total_seconds()//60)})
    else:
        if len(extra_breaks) == 1:
            tname, tlen = extra_breaks[0]
            s_b, e_b = safe_place(0.5, tlen)
            breaks.append({'type': tname, 'start': s_b, 'end': e_b, 'minutes': int((e_b - s_b).total_seconds()//60)})
        elif len(extra_breaks) == 2:
            for idx, (tname, tlen) in enumerate(extra_breaks):
                pct = 1/3 if idx == 0 else 2/3
                s_b, e_b = safe_place(pct, tlen)
                breaks.append({'type': tname, 'start': s_b, 'end': e_b, 'minutes': int((e_b - s_b).total_seconds()//60)})
    return breaks

# -------------------------
# compute_min_agents_for_coverage
# -------------------------
def compute_min_agents_for_coverage(interval_summary, coverage_target_pct, aht_sec, absenteeism_pct, interval_seconds, asa, service_level_target):
    if interval_summary is None or interval_summary.empty:
        return 0
    reqs = []
    for _, row in interval_summary.iterrows():
        calls = float(row['calls'])
        calls_target = calls * float(coverage_target_pct)
        req = required_agents_for_interval(calls=calls_target, aht_sec=aht_sec, service_level_target=service_level_target, interval_sec=interval_seconds, asa=asa)
        if (1 - absenteeism_pct) > 0:
            req = math.ceil(req / (1 - absenteeism_pct))
        reqs.append(int(req))
    return int(max(reqs)) if reqs else 0

# -------------------------
# optimize_roster - CP-only (sin decomposición ni greedy)
# -------------------------
def optimize_roster(turns_df, forecast_df,
                    agents_pool=40,
                    aht_sec=300,
                    absenteeism_pct=0.15,
                    weekly_hours=44,
                    service_level_target=0.8,
                    interval_seconds=1800,
                    asa=20,
                    time_limit_seconds=60,
                    days_to_optimize=7,
                    max_slots_for_cp_override=None):
    """
    CP-only optimizer with explicit break placement and 12h rest enforcement.
    """
    if turns_df is None or forecast_df is None:
        raise ValueError("turns_df o forecast_df es None.")

    days_to_optimize = max(MIN_DAYS_HORIZON, min(MAX_DAYS_HORIZON, int(days_to_optimize)))

    forecast = forecast_df.copy()
    if 'festivo' not in forecast.columns:
        forecast['festivo'] = False
    forecast['date'] = forecast['ds'].dt.date
    unique_days = sorted(forecast['date'].unique())[:max(1, int(days_to_optimize))]
    intervals = forecast[forecast['date'].isin(unique_days)].reset_index(drop=True)
    if intervals.empty:
        raise ValueError("No intervals found for the selected days.")

    intervals.attrs['interval_seconds'] = int(interval_seconds)
    intervals.attrs['aht_sec'] = int(aht_sec)

    # compute required agents (Erlang)
    required_agents = []
    for idx, row in intervals.iterrows():
        calls = float(row['calls'])
        req = required_agents_for_interval(calls=calls, aht_sec=aht_sec, service_level_target=service_level_target, interval_sec=interval_seconds, asa=asa)
        if (1 - absenteeism_pct) > 0:
            req = math.ceil(req / (1 - absenteeism_pct))
        required_agents.append(int(req))
    intervals['required_agents'] = required_agents

    day_to_indices = {d: list(intervals[intervals['date'] == d].index) for d in unique_days}
    def minute_of_day(ts): return ts.hour*60 + ts.minute

    # coverage_map: for each (date, shift index) list of interval indices covered by that shift on that date
    coverage_map = {}
    shift_has_coverage = set()
    for d in unique_days:
        idxs = day_to_indices[d]
        for s_i, srow in turns_df.iterrows():
            covered = []
            for idx in idxs:
                ts = intervals.loc[idx,'ds']
                mod = minute_of_day(ts)
                s = int(srow['start_min']); e = int(srow['end_min'])
                if s <= e:
                    in_shift = (mod >= s and mod < e)
                else:
                    in_shift = (mod >= s or mod < e)
                if in_shift:
                    covered.append(idx)
            coverage_map[(d, s_i)] = covered
            if covered:
                shift_has_coverage.add(s_i)

    relevant_shifts = sorted(list(shift_has_coverage))
    if not relevant_shifts:
        raise ValueError("Ningún turno cubre las ventanas de pronóstico seleccionadas.")
    turns_df = turns_df.loc[relevant_shifts].reset_index(drop=True)
    new_coverage_map = {}
    for d in unique_days:
        for new_idx, orig_idx in enumerate(relevant_shifts):
            new_coverage_map[(d, new_idx)] = coverage_map[(d, orig_idx)]
    coverage_map = new_coverage_map
    shifts_idx = list(range(len(turns_df)))

    # estimated upper bound slots (cota superior)
    max_req = int(max(intervals['required_agents'])) if len(intervals)>0 else 0
    margin = max(10, int(max_req * 0.2))
    estimated_needed_slots = max(20, max_req + margin)
    num_slots = int(min(int(agents_pool), int(max(estimated_needed_slots, 1))))
    if max_slots_for_cp_override:
        num_slots = min(num_slots, int(max_slots_for_cp_override))

    # warn if big
    num_intervals_per_day = int(round(24*60 / float(max(1, interval_seconds))))
    big_intervals_threshold = num_intervals_per_day * 14  # 2 weeks
    if (len(intervals) > big_intervals_threshold) or (num_slots > 400):
        st.warning("El problema es grande. CP puede tardar bastante. Aumenta 'time_limit_solver (s)' si quieres una solución más cercana al óptimo.")

    # --- BUILD CP MODEL ---
    num_days = len(unique_days)
    num_weeks = int(math.ceil(num_days / 7.0))
    week_to_dates = {}
    for w in range(num_weeks):
        start_pos = w * 7
        week_dates = unique_days[start_pos:start_pos+7]
        week_to_dates[w] = week_dates
    daypos_to_week = {pos: pos // 7 for pos, d in enumerate(unique_days)}
    festivo_by_date = {row['date']: bool(row['festivo']) for _, row in intervals.iterrows()}
    festivos_per_week = {}
    for w in range(num_weeks):
        cnt = 0
        for d in week_to_dates[w]:
            if festivo_by_date.get(d, False):
                cnt += 1
        festivos_per_week[w] = cnt

    model = cp_model.CpModel()
    num_agents = num_slots  # cota superior de agentes/slots que el solver puede usar
    days = list(range(len(unique_days)))

    # x[(a,d,s)] == 1 si el agente/slot 'a' toma turno s en el día d
    x = {}
    for a in range(num_agents):
        for d in days:
            for s in shifts_idx:
                x[(a,d,s)] = model.NewBoolVar(f"x_a{a}_d{d}_s{s}")

    # y[(a,d)] == 1 si el agente 'a' está asignado en el día 'd' (cualquier turno)
    y = {}
    for a in range(num_agents):
        for d in days:
            y[(a,d)] = model.NewBoolVar(f"assigned_a{a}_d{d}")
            model.Add(sum(x[(a,d,s)] for s in shifts_idx) >= y[(a,d)])
            bigM = len(shifts_idx) if len(shifts_idx) > 0 else 1
            model.Add(sum(x[(a,d,s)] for s in shifts_idx) <= bigM * y[(a,d)])
            model.Add(sum(x[(a,d,s)] for s in shifts_idx) <= 1)

    # z[a] == 1 si el agente/slot 'a' es usado al menos un día (variable de "usar agente")
    z = {}
    for a in range(num_agents):
        z[a] = model.NewBoolVar(f"used_slot_{a}")
        model.Add(sum(y[(a,d)] for d in days) >= z[a])
        model.Add(sum(y[(a,d)] for d in days) <= len(days) * z[a])

    # indicadores día/noche por agente/día (para reglas de mezcla)
    day_is_day = {}; day_is_night = {}
    for a in range(num_agents):
        for d in days:
            day_is_day[(a,d)] = model.NewBoolVar(f"dayflag_{a}_{d}")
            day_is_night[(a,d)] = model.NewBoolVar(f"nightflag_{a}_{d}")
            model.Add(sum(x[(a,d,s)] for s in shifts_idx if turns_df.loc[s,'shift_type']=='day') >= day_is_day[(a,d)])
            model.Add(sum(x[(a,d,s)] for s in shifts_idx if turns_df.loc[s,'shift_type']=='day') <= (len(shifts_idx) * day_is_day[(a,d)]))
            model.Add(sum(x[(a,d,s)] for s in shifts_idx if turns_df.loc[s,'shift_type']=='night') >= day_is_night[(a,d)])
            model.Add(sum(x[(a,d,s)] for s in shifts_idx if turns_df.loc[s,'shift_type']=='night') <= (len(shifts_idx) * day_is_night[(a,d)]))

    # flags semanales de day/night
    week_day_flag = {}
    week_night_flag = {}
    for a in range(num_agents):
        for w in range(num_weeks):
            week_day_flag[(a,w)] = model.NewBoolVar(f"week_day_{a}_{w}")
            week_night_flag[(a,w)] = model.NewBoolVar(f"week_night_{a}_{w}")
            days_in_week = [i for i, dd in enumerate(unique_days) if daypos_to_week[i] == w]
            if days_in_week:
                model.Add(sum(day_is_day[(a,d)] for d in days_in_week) >= week_day_flag[(a,w)])
                model.Add(sum(day_is_day[(a,d)] for d in days_in_week) <= len(days_in_week) * week_day_flag[(a,w)])
                model.Add(sum(day_is_night[(a,d)] for d in days_in_week) >= week_night_flag[(a,w)])
                model.Add(sum(day_is_night[(a,d)] for d in days_in_week) <= len(days_in_week) * week_night_flag[(a,w)])
            # no mezclar day & night en misma semana
            model.Add(week_day_flag[(a,w)] + week_night_flag[(a,w)] <= 1)

    # limite domingos
    sunday_positions = [pos for pos, d in enumerate(unique_days) if d.weekday() == 6]
    for a in range(num_agents):
        if sunday_positions:
            model.Add(sum(y[(a,pos)] for pos in sunday_positions) <= MAX_SUNDAYS_PER_AGENT)

    # horas semanales por agente (respetando festivos y permitiendo overtime limitado)
    for a in range(num_agents):
        for w in range(num_weeks):
            days_in_week_positions = [pos for pos, d in enumerate(unique_days) if daypos_to_week[pos] == w]
            if not days_in_week_positions:
                continue
            fest_cnt = festivos_per_week.get(w, 0)
            weekly_hours_eff = max(0.0, float(weekly_hours) - FESTIVO_HOURS_DISCOUNT * fest_cnt)
            total_minutes_assigned = sum(int(turns_df.loc[s,'duration_min']) * x[(a,d,s)]
                                         for d in days_in_week_positions for s in shifts_idx)
            overtime_cap = MAX_OVERTIME_PER_DAY_MIN * sum(y[(a,d)] for d in days_in_week_positions)
            model.Add(total_minutes_assigned <= int(round(weekly_hours_eff * 60)) + overtime_cap)

    # -------------------------
    # Enforce 12-hour rest between consecutive assigned days for same agent
    # -------------------------
    for a in range(num_agents):
        for d_idx in range(len(unique_days)-1):
            for s1 in shifts_idx:
                for s2 in shifts_idx:
                    s1_start = int(turns_df.loc[s1,'start_min'])
                    s1_end = int(turns_df.loc[s1,'end_min'])
                    s2_start = int(turns_df.loc[s2,'start_min'])
                    prev_end_abs = s1_end + (0 if s1_end >= s1_start else 1440)
                    next_start_abs = s2_start + 1440
                    gap_const = next_start_abs - prev_end_abs
                    if gap_const < MIN_REST_MIN:
                        model.Add(x[(a,d_idx,s1)] + x[(a,d_idx+1,s2)] <= 1)

    # -------------------------
    # work_var + coverage + shortfall
    # -------------------------
    work_var = {}
    for a in range(num_agents):
        for d_idx, d in enumerate(unique_days):
            for s in shifts_idx:
                covered = coverage_map.get((d, s), [])
                if not covered:
                    continue
                for j in covered:
                    work_var[(a,d_idx,s,j)] = model.NewBoolVar(f"work_{a}_{d_idx}_{s}_j{j}")
                    model.Add(work_var[(a,d_idx,s,j)] == x[(a,d_idx,s)])

    coverage = {}
    for j in intervals.index:
        coverage[j] = model.NewIntVar(0, num_agents, f"coverage_{j}")
        terms = []
        for a in range(num_agents):
            for d_idx, d in enumerate(unique_days):
                for s in shifts_idx:
                    if (a,d_idx,s,j) in work_var:
                        terms.append(work_var[(a,d_idx,s,j)])
        if terms:
            model.Add(coverage[j] == sum(terms))
        else:
            model.Add(coverage[j] == 0)

    shortfall = {}
    for j in intervals.index:
        req = int(intervals.loc[j,'required_agents'])
        shortfall[j] = model.NewIntVar(0, req, f"shortfall_{j}")
        model.Add(shortfall[j] >= req - coverage[j])
        model.Add(shortfall[j] >= 0)

    total_shortfall = model.NewIntVar(0, 10**9, "total_shortfall")
    model.Add(total_shortfall == sum(shortfall[j] for j in intervals.index))

    total_assigned = model.NewIntVar(0, num_agents*len(days)*len(shifts_idx), "total_assigned")
    model.Add(total_assigned == sum(x[(a,d,s)] for a in range(num_agents) for d in days for s in shifts_idx))

    total_agents_used = model.NewIntVar(0, num_agents, "total_agents_used")
    model.Add(total_agents_used == sum(z[a] for a in range(num_agents)))

    # Objetivo
    W1 = max(1, int(intervals['required_agents'].max() if len(intervals)>0 else 1)) * len(intervals) * 100000
    W2 = 1000
    model.Minimize(total_shortfall * W1 + total_agents_used * W2 + total_assigned)

    # --- Solver ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(5, int(time_limit_seconds))
    solver.parameters.num_search_workers = max(1, (os.cpu_count() or 2)//2)
    solver.parameters.cp_model_presolve = True

    res_container = {'res': None, 'error': None}
    def solver_thread_fn():
        try:
            res_container['res'] = solver.Solve(model)
        except Exception as e:
            res_container['error'] = str(e)
            res_container['res'] = None

    th = threading.Thread(target=solver_thread_fn, daemon=True)
    th.start()

    start_time = time.time()
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    while th.is_alive():
        elapsed = time.time() - start_time
        pct = min(elapsed / float(time_limit_seconds), 0.9999)
        progress_bar.progress(pct)
        status_text.text(f"Optimizando CP... {int(pct*100)}% — elapsed {int(elapsed)}s (time_limit={time_limit_seconds}s)")
        if elapsed > float(time_limit_seconds):
            try:
                solver.StopSearch()
            except Exception:
                pass
        time.sleep(0.3)

    progress_bar.progress(1.0)
    status_text.text("Solver terminó. Recolectando resultados...")

    if res_container['error'] is not None:
        raise RuntimeError("Solver thread error: " + res_container['error'])

    res = res_container['res']

    # --- Build schedule_df and breaks list (with summaries) ---
    assigned_rows = []
    breaks_list_for_assignments = []
    if res == cp_model.OPTIMAL or res == cp_model.FEASIBLE:
        for a in range(num_agents):
            if solver.Value(z[a]) == 0:
                continue
            for d_idx, d in enumerate(unique_days):
                for s in shifts_idx:
                    if solver.Value(x[(a,d_idx,s)]) == 1:
                        sample_ts = intervals[intervals['date'] == d]['ds'].iloc[0]
                        start_min = int(turns_df.loc[s,'start_min'])
                        end_min = int(turns_df.loc[s,'end_min'])
                        duration_min = int(turns_df.loc[s,'duration_min'])
                        effective_min = float(turns_df.loc[s,'effective_min'])
                        start_dt = datetime.combine(sample_ts.date(), datetime.min.time()) + timedelta(minutes=start_min)
                        if turns_df.loc[s,'end_min'] >= turns_df.loc[s,'start_min']:
                            end_dt = datetime.combine(sample_ts.date(), datetime.min.time()) + timedelta(minutes=end_min)
                        else:
                            end_dt = datetime.combine(sample_ts.date(), datetime.min.time()) + timedelta(days=1, minutes=end_min)
                        # compute breaks and create a human-friendly summary for schedule export
                        brks = compute_break_schedule_for_shift(start_dt, duration_min,
                                                               int(turns_df.loc[s,'lunch_min']),
                                                               int(turns_df.loc[s,'break1_min']),
                                                               int(turns_df.loc[s,'break2_min']))
                        # summary string: "lunch 13:00-13:30 (30); break1 10:15-10:30 (15)"
                        summary_items = []
                        for b in brks:
                            summary_items.append(f"{b['type']} {b['start'].strftime('%H:%M')}-{b['end'].strftime('%H:%M')} ({b['minutes']}m)")
                        summary_str = " | ".join(summary_items) if summary_items else ""
                        assigned_rows.append({
                            'agent_id': f"ID_{a+1}",
                            'date': d,
                            'turno_id': turns_df.loc[s,'turno_id'],
                            'start': start_dt,
                            'end': end_dt,
                            'duration_min': duration_min,
                            'effective_min': effective_min,
                            'shift_type': turns_df.loc[s,'shift_type'],
                            'shift_index': s,
                            'slot_index': a,
                            'breaks_summary': summary_str
                        })
                        breaks_list_for_assignments.append({
                            'agent_id': f"ID_{a+1}",
                            'slot_index': a,
                            'date': d,
                            'shift_index': s,
                            'start': start_dt,
                            'end': end_dt,
                            'breaks': brks
                        })

    schedule_df = pd.DataFrame(assigned_rows)

    # Build break_detail_df: per interval break minutes and timestamp
    break_rows = []
    interval_windows = {}
    for j in intervals.index:
        int_start = intervals.loc[j,'ds']
        int_end = int_start + timedelta(seconds=interval_seconds)
        interval_windows[j] = (int_start, int_end)

    for asg in breaks_list_for_assignments:
        agent_id = asg['agent_id']
        d = asg['date']
        for br in asg['breaks']:
            btype = br['type']
            bstart = br['start']
            bend = br['end']
            for j in intervals.index:
                int_start, int_end = interval_windows[j]
                overlap_start = max(bstart, int_start)
                overlap_end = min(bend, int_end)
                minutes = max(0, int((overlap_end - overlap_start).total_seconds()//60))
                if minutes > 0:
                    break_rows.append({
                        'agent_id': agent_id,
                        'date': d,
                        'interval_index': j,
                        'interval_ds': intervals.loc[j,'ds'],
                        'break_type': btype,
                        'break_start': bstart,
                        'break_end': bend,
                        'break_minutes': minutes
                    })

    break_detail_df = pd.DataFrame(break_rows)

    # --- Recompute interval summary subtracting breaks per agent/interval ---
    interval_rows = []
    for j in intervals.index:
        calls = float(intervals.loc[j,'calls'])
        req = int(intervals.loc[j,'required_agents'])
        # assigned agents covering this interval
        assigned_agents_covering = []
        if not schedule_df.empty:
            for _, row in schedule_df.iterrows():
                d = row['date']; s = int(row['shift_index'])
                if j in coverage_map.get((d, s), []):
                    assigned_agents_covering.append(row)
        total_effective_agent_fraction = 0.0
        for agent_row in assigned_agents_covering:
            agent_id = agent_row['agent_id']
            df_agent_breaks = break_detail_df[(break_detail_df['agent_id'] == agent_id) & (break_detail_df['interval_index'] == j)]
            br_minutes = int(df_agent_breaks['break_minutes'].sum()) if not df_agent_breaks.empty else 0
            active_frac = max(0.0, (interval_seconds/60.0 - br_minutes) / (interval_seconds/60.0))
            total_effective_agent_fraction += active_frac
        capacity_calls = total_effective_agent_fraction * (float(interval_seconds) / float(max(1.0, aht_sec)))
        handled_calls = min(calls, capacity_calls)
        covered_agents = len(assigned_agents_covering)
        interval_rows.append({
            'ds': intervals.loc[j,'ds'],
            'date': intervals.loc[j,'date'],
            'calls': calls,
            'required_agents': req,
            'covered_agents': covered_agents,
            'handled_calls_est': handled_calls,
            'shortfall_agents': max(0, req - covered_agents),
            'surplus_agents': max(0, covered_agents - req)
        })

    interval_summary = pd.DataFrame(interval_rows)

    feasible_flag = (res == cp_model.OPTIMAL or res == cp_model.FEASIBLE)
    solver_status = res if isinstance(res, int) else ("OPTIMAL" if feasible_flag else "UNKNOWN")

    return schedule_df, break_detail_df, interval_summary, solver_status, feasible_flag

# -------------------------
# Streamlit UI (lado cliente)
# -------------------------
with st.sidebar:
    st.header("Parámetros")
    aht_sec = st.number_input("TMO / AHT (segundos)", min_value=1, value=300, step=5)
    service_level_target = st.number_input("Service level objetivo (0-1)", min_value=0.0, max_value=1.0, value=0.8, step=0.01)
    asa = st.number_input("ASA (segundos)", min_value=1, value=20, step=1)
    absenteeism_pct = st.number_input("Ausentismo / Shrinkage (%)", min_value=0.0, max_value=0.9, value=0.15, step=0.01)
    weekly_hours = st.number_input("Horas semanales por agente (horas)", min_value=1, value=44)
    agents_pool_input = st.number_input("Pool agentes (0 = auto)", min_value=0, value=0)
    interval_seconds = st.number_input("Segundos por intervalo", min_value=60, value=1800, step=60)
    time_limit_seconds = st.number_input("Time limit solver (s)", min_value=10, value=120, step=10)
    days_to_optimize = st.number_input(f"Días a optimizar ({MIN_DAYS_HORIZON}..{MAX_DAYS_HORIZON})", min_value=MIN_DAYS_HORIZON, max_value=MAX_DAYS_HORIZON, value=MIN_DAYS_HORIZON)
    coverage_target_pct = st.slider("Coverage objetivo para cálculo mínimo de agentes (por llamadas) (%)", min_value=0.5, max_value=1.0, value=0.95, step=0.01)
    max_slots_override = st.number_input("Max slots para CP (override, 0=auto)", min_value=0, value=0)
    st.markdown("---")
    st.write("Carga tus archivos Mtr_Turnos y Input (Input puede incluir columna 'Festivo' con Si/No).")

col_left, col_right = st.columns([2,1])

with col_left:
    turns_file = st.file_uploader("Subir Mtr_Turnos (xls/xlsx/csv/xlsb)", type=["xlsx", "csv", "xls", "xlsb"])
    input_file = st.file_uploader("Subir Input (Forecast) (xls/xlsx/csv/xlsb)", type=["xlsx", "csv", "xls", "xlsb"])
    use_local = False
    if turns_file is None and input_file is None:
        possible_turns = ["Mtr_Turnos.xlsx", "Mtr_Turnos.xls", "Mtr_Turnos.xlsb", "Mtr_Turnos.csv"]
        possible_input = ["Input.xlsx", "Input.xls", "Input.xlsb", "Input.csv"]
        local_turns = None
        local_input = None
        for p in possible_turns:
            if os.path.exists(p):
                local_turns = p
                break
        for p in possible_input:
            if os.path.exists(p):
                local_input = p
                break
        if local_turns and local_input:
            if st.button("Usar archivos locales detectados"):
                turns_file = local_turns
                input_file = local_input
                use_local = True

# main flow: load, preview, run
if (turns_file is not None) and (input_file is not None):
    if not use_local:
        raw_turns, err_turns = validate_file(turns_file, "Mtr_Turnos (subido)")
        raw_input_df, err_input = validate_file(input_file, "Input (subido)")
    else:
        raw_turns, err_turns = validate_file(local_turns, "Mtr_Turnos (local)")
        raw_input_df, err_input = validate_file(local_input, "Input (local)")

    if err_turns:
        st.error(err_turns); st.stop()
    if err_input:
        st.error(err_input); st.stop()

    st.subheader("Preview: Maestra de Turnos")
    st.dataframe(raw_turns.head(10))
    st.subheader("Preview: Input (Forecast)")
    st.dataframe(raw_input_df.head(10))

    # manual mapping UI
    st.markdown("#### (Opcional) Mapeo manual de columnas")
    c1, c2 = st.columns(2)
    with c1:
        manual_start_col = st.selectbox("Columna inicio (maestra)", options=list(raw_turns.columns), index=0)
        manual_end_col = st.selectbox("Columna fin (maestra)", options=list(raw_turns.columns), index=1)
    with c2:
        manual_calls_col = st.selectbox("Columna llamadas (input)", options=list(raw_input_df.columns), index=0)
        possible_dates = [c for c in raw_input_df.columns if 'fecha' in normalize(c) or 'date' in normalize(c)]
        possible_times = [c for c in raw_input_df.columns if 'hora' in normalize(c) or 'interval' in normalize(c) or 'time' in normalize(c)]
        if possible_dates:
            manual_date_col = st.selectbox("Columna Fecha (input)", options=raw_input_df.columns, index=list(raw_input_df.columns).index(possible_dates[0]))
        else:
            manual_date_col = st.selectbox("Columna Fecha (input)", options=raw_input_df.columns)
        if possible_times:
            manual_time_col = st.selectbox("Columna Intervalo/Hora (input)", options=raw_input_df.columns, index=list(raw_input_df.columns).index(possible_times[0]))
        else:
            manual_time_col = st.selectbox("Columna Intervalo/Hora (input)", options=raw_input_df.columns)

    preview_checkbox = st.checkbox("Hacer preview rápido (Erlang) antes de optimizar", value=True)
    preview_days = st.slider("Días para preview (1..7)", min_value=1, max_value=7, value=3)

    run_button = st.button("Ejecutar optimización CP (puede tardar)")

    try:
        temp_turns = raw_turns.copy()
        turns_df = load_master_turns_from_df(temp_turns)
    except Exception as e:
        st.error(f"Error parseando maestra: {e}"); st.stop()

    try:
        temp_input = raw_input_df.copy()
        if manual_date_col in temp_input.columns and manual_time_col in temp_input.columns and manual_calls_col in temp_input.columns:
            temp_input2 = temp_input.rename(columns={manual_date_col: 'fecha', manual_time_col: 'intervalo', manual_calls_col: 'calls'})
            forecast_df = load_forecast_from_df(temp_input2)
        else:
            forecast_df = load_forecast_from_df(temp_input)
    except Exception as e:
        st.error(f"Error parseando forecast: {e}"); st.stop()

    # Preview rápido (Erlang)
    if preview_checkbox:
        try:
            forecast = forecast_df.copy()
            if 'festivo' not in forecast.columns:
                forecast['festivo'] = False
            forecast['date'] = forecast['ds'].dt.date
            unique_days_preview = sorted(forecast['date'].unique())[:preview_days]
            intervals_preview = forecast[forecast['date'].isin(unique_days_preview)].reset_index(drop=True)
            intervals_preview.attrs['interval_seconds'] = int(interval_seconds)
            intervals_preview.attrs['aht_sec'] = int(aht_sec)
            required_preview = []
            for idx, row in intervals_preview.iterrows():
                calls = float(row['calls'])
                req = required_agents_for_interval(calls=calls, aht_sec=int(aht_sec), service_level_target=float(service_level_target), interval_sec=int(interval_seconds), asa=int(asa))
                if (1 - float(absenteeism_pct)) > 0:
                    req = math.ceil(req / (1 - float(absenteeism_pct)))
                required_preview.append(int(req))
            intervals_preview['required_agents'] = required_preview
            st.subheader(f"Preview rápido ({preview_days} días) — Erlang")
            st.dataframe(intervals_preview.head(200))
            try:
                fig1, ax1 = plt.subplots(figsize=(10,2.5))
                ax1.plot(intervals_preview['ds'], intervals_preview['required_agents'], label='Requeridos')
                ax1.plot(intervals_preview['ds'], intervals_preview['calls'], label='Calls')
                ax1.legend(); ax1.grid(True); st.pyplot(fig1)
            except Exception:
                pass
        except Exception as e:
            st.warning(f"Preview falló: {e}")

    if run_button:
        if agents_pool_input and agents_pool_input > 0:
            agents_pool = int(agents_pool_input)
        else:
            try:
                temp_reqs = []
                for _, r in forecast_df.iterrows():
                    temp_reqs.append(required_agents_for_interval(float(r['calls']), int(aht_sec), float(service_level_target), int(interval_seconds), asa=int(asa)))
                est = int(max(temp_reqs)) if temp_reqs else 40
                agents_pool = max(40, est + 10)
            except Exception:
                agents_pool = 40

        st.info(f"Lanzando CP-SAT con pool={agents_pool}, days={days_to_optimize}, time_limit={time_limit_seconds}s ... (sin greedy)")

        try:
            schedule_df, break_detail_df, interval_summary, solver_status, feasible_flag = optimize_roster(
                turns_df=turns_df,
                forecast_df=forecast_df,
                agents_pool=agents_pool,
                aht_sec=int(aht_sec),
                absenteeism_pct=float(absenteeism_pct),
                weekly_hours=float(weekly_hours),
                service_level_target=float(service_level_target),
                interval_seconds=int(interval_seconds),
                asa=int(asa),
                time_limit_seconds=int(time_limit_seconds),
                days_to_optimize=int(days_to_optimize),
                max_slots_for_cp_override=(None if int(max_slots_override)==0 else int(max_slots_override))
            )
        except Exception as e:
            st.error(f"Error durante optimización: {e}"); st.stop()

        if solver_status == "UNKNOWN":
            st.warning("Solver terminó sin solución óptima clara (UNKNOWN). Revisa time_limit y tamaño del problema.")
        else:
            st.success(f"Optimización finalizada — estado solver: {solver_status} — factible: {feasible_flag}")

        total_calls = float(interval_summary['calls'].sum()) if not interval_summary.empty else 0.0
        total_handled = float(interval_summary['handled_calls_est'].sum()) if not interval_summary.empty else 0.0
        cumplimiento = (total_handled / total_calls) if total_calls > 0 else 0.0

        min_agents_for_target = compute_min_agents_for_coverage(interval_summary, coverage_target_pct, aht_sec, absenteeism_pct, int(interval_seconds), int(asa), service_level_target)
        min_agents_for_full = compute_min_agents_for_coverage(interval_summary, 1.0, aht_sec, absenteeism_pct, int(interval_seconds), int(asa), service_level_target)

        scheduled_agents = schedule_df['agent_id'].nunique() if (schedule_df is not None and not schedule_df.empty) else 0

        if scheduled_agents < min_agents_for_target:
            agentes_faltantes_para_target = int(min_agents_for_target - scheduled_agents)
            agentes_sobrantes_vs_target = 0
        else:
            agentes_faltantes_para_target = 0
            agentes_sobrantes_vs_target = int(scheduled_agents - min_agents_for_target)

        if scheduled_agents < min_agents_for_full:
            agentes_faltantes_para_full = int(min_agents_for_full - scheduled_agents)
            agentes_sobrantes_vs_full = 0
        else:
            agentes_faltantes_para_full = 0
            agentes_sobrantes_vs_full = int(scheduled_agents - min_agents_for_full)

        left_col, right_col = st.columns([2,1])
        with left_col:
            st.subheader("Interval summary")
            st.dataframe(interval_summary.head(300))
            st.subheader("Schedule (incluye columna breaks_summary)")
            st.dataframe(schedule_df.head(300))
            st.subheader("Break detail (por intervalo)")
            st.dataframe(break_detail_df.head(300))

            try:
                fig1, ax1 = plt.subplots(figsize=(12,3))
                ax1.plot(interval_summary['ds'], interval_summary['required_agents'], label='Requeridos')
                ax1.plot(interval_summary['ds'], interval_summary['covered_agents'], label='Conectados (aj. pausas)')
                ax1.legend(); ax1.grid(True)
                st.pyplot(fig1)
            except Exception as e:
                st.write("Plot Requeridos/Conectados error:", e)

            try:
                fig2, ax2 = plt.subplots(figsize=(12,3))
                ax2.plot(interval_summary['ds'], interval_summary['calls'], label='Pronosticadas')
                ax2.plot(interval_summary['ds'], interval_summary['handled_calls_est'], label='Atendidas Est. (aj. pausas)')
                ax2.legend(); ax2.grid(True)
                st.pyplot(fig2)
            except Exception as e:
                st.write("Plot calls error:", e)

        with right_col:
            st.subheader("KPIs")
            total_short = int(interval_summary['shortfall_agents'].sum()) if not interval_summary.empty else 0
            total_surplus = int(interval_summary['surplus_agents'].sum()) if not interval_summary.empty else 0

            st.metric("Total faltantes (sum intervalos)", total_short)
            st.metric("Total sobrantes (sum intervalos)", total_surplus)
            st.metric("Llamadas pronosticadas (suma)", int(round(total_calls)))
            st.metric("Llamadas estimadas a atender", int(round(total_handled)))
            st.metric("Cumplimiento estimado (%)", f"{cumplimiento*100:.2f}%")
            st.markdown("---")
            st.metric("Pool agentes (input)", agents_pool)
            st.metric("Agentes programados (IDs usados)", int(scheduled_agents))
            st.markdown("**Mínimos teóricos**")
            st.write(f"- Mínimo agentes para {int(coverage_target_pct*100)}% cobertura: **{min_agents_for_target}**")
            if agentes_faltantes_para_target > 0:
                st.write(f"  - *Necesitas* **+{agentes_faltantes_para_target}** agentes para alcanzar ese objetivo (según Erlang).")
            else:
                st.write(f"  - *Sobrantes vs objetivo*: **{agentes_sobrantes_vs_target}**")

            st.write(f"- Mínimo agentes para 100% cobertura: **{min_agents_for_full}**")
            if agentes_faltantes_para_full > 0:
                st.write(f"  - *Necesitas* **+{agentes_faltantes_para_full}** agentes para 100% cobertura.")
            else:
                st.write(f"  - *Sobrantes vs 100%*: **{agentes_sobrantes_vs_full}**")

            # --------------------------
            # EXPORTS: guardo en session_state el excel (varias hojas) y CSV individuales
            # así el usuario puede descargar múltiples veces sin que el app re-ejecute el optimizador
            # --------------------------
            # prepare excel with 3 sheets: schedule, breaks, intervals
            try:
                # write to BytesIO and keep bytes in session_state
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    schedule_df.to_excel(writer, sheet_name='schedule', index=False)
                    break_detail_df.to_excel(writer, sheet_name='break_detail', index=False)
                    interval_summary.to_excel(writer, sheet_name='interval_summary', index=False)
                buf.seek(0)
                st.session_state['last_export_bytes'] = buf.getvalue()
                # also store individual CSVs bytes
                csv_schedule = schedule_df.to_csv(index=False).encode('utf-8')
                csv_breaks = break_detail_df.to_csv(index=False).encode('utf-8')
                csv_intervals = interval_summary.to_csv(index=False).encode('utf-8')
                st.session_state['csv_schedule'] = csv_schedule
                st.session_state['csv_breaks'] = csv_breaks
                st.session_state['csv_intervals'] = csv_intervals
            except Exception as e:
                st.write("Error preparando archivos para descarga:", e)

            # Buttons: read from session_state so pressing them no vuelve a ejecutar optimize
            if 'last_export_bytes' in st.session_state:
                st.download_button("Descargar Excel (todas las hojas)", data=st.session_state['last_export_bytes'],
                                   file_name=f"export_schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="dl_all_excel")
            if 'csv_schedule' in st.session_state:
                st.download_button("Descargar Schedule (CSV)", data=st.session_state['csv_schedule'],
                                   file_name=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                   mime="text/csv", key="dl_schedule_csv")
            if 'csv_breaks' in st.session_state:
                st.download_button("Descargar Break Detail (CSV)", data=st.session_state['csv_breaks'],
                                   file_name=f"breaks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                   mime="text/csv", key="dl_breaks_csv")
            if 'csv_intervals' in st.session_state:
                st.download_button("Descargar Interval Summary (CSV)", data=st.session_state['csv_intervals'],
                                   file_name=f"intervals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                   mime="text/csv", key="dl_intervals_csv")

else:
    st.info("Carga ambos archivos (Mtr_Turnos y Input) en la interfaz lateral para iniciar.")
