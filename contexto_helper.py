# contexto_helper.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import math
import pandas as pd
import unicodedata

from depto_helper import DeptoHelper
from estadisticas_helper import (
    obtener_evolucion_viajes_y_toneladas,
    obtener_top_mercancias_ruta,
    obtener_top_destinos,
    obtener_top_origenes,
    obtener_distribucion_vehiculos_ruta,
)

BASE_DIR = Path(__file__).resolve().parent

# Archivos actuales (según tu repo)
FILE_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"
FILE_TIEMPOS = "indice_cargue_descargue_resumen_mensual.xlsx"
FILE_COMPETITIVIDAD = "competitividad_rutas_2025.xlsx"
FILE_CONFIG_VEH = "CONFIGURACION_VEHICULAR_LIMPIO.xlsx"
FILE_MUNICIPIOS = "municipios.xlsx"

FILE_DEPTO_RUTAS = "DEPARTAMENTOS EN RUTAS SICE.xlsx"
FILE_BLOQUEOS = "BLOQUEOS EN VIAS COLFECAR.xlsx"

# Cache lazy
_DF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}
_MAP_CACHE: Dict[str, Any] = {}

# Modo global (si lo sigues usando)
_modo_viaje_global = "CARGADO"


def set_modo_viaje(modo: str):
    global _modo_viaje_global
    _modo_viaje_global = str(modo).upper().strip()


def get_modo_viaje() -> str:
    return _modo_viaje_global


def _path(name: str) -> Path:
    return BASE_DIR / name


def _safe_read_excel(name: str) -> Optional[pd.DataFrame]:
    if name in _DF_CACHE:
        return _DF_CACHE[name]

    p = _path(name)
    if not p.exists():
        _DF_CACHE[name] = None
        return None

    df = pd.read_excel(p)
    df.columns = [str(c).strip().upper() for c in df.columns]
    _DF_CACHE[name] = df
    return df


def _norm_text(s: Any) -> str:
    s = str(s).strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s


def limpiar_nan_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: limpiar_nan_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpiar_nan_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


# =========================================================
# Mapeo de configuración vehicular -> CONFIGURACION_ANALISIS
# =========================================================
def _get_mapeo_config() -> Dict[str, str]:
    if "mapeo_config" in _MAP_CACHE:
        return _MAP_CACHE["mapeo_config"]

    df = _safe_read_excel(FILE_CONFIG_VEH)
    if df is None:
        _MAP_CACHE["mapeo_config"] = {}
        return {}

    # Esperadas: TIPO_VEHICULO, CONFIGURACION_ANALISIS
    if "TIPO_VEHICULO" not in df.columns or "CONFIGURACION_ANALISIS" not in df.columns:
        _MAP_CACHE["mapeo_config"] = {}
        return {}

    df = df.copy()
    df["TIPO_VEHICULO"] = df["TIPO_VEHICULO"].astype(str).str.strip().str.upper()
    df["CONFIGURACION_ANALISIS"] = df["CONFIGURACION_ANALISIS"].astype(str).str.strip().str.upper()

    m = dict(zip(df["TIPO_VEHICULO"], df["CONFIGURACION_ANALISIS"]))
    _MAP_CACHE["mapeo_config"] = m
    return m


def traducir_config(config: str) -> str:
    """Traduce configuración con el mapeo si aplica; si no, devuelve la misma."""
    config = str(config).strip().upper()
    m = _get_mapeo_config()
    return m.get(config, config)


# =========================================================
# 1) VALORES PROMEDIO (mercado / valpagados)
#    Usa VALORES_CONSOLIDADOS_2025.xlsx
# =========================================================
def obtener_valores_promedio_mercado_por_llave(ruta_config: str) -> List[Dict[str, Any]]:
    """
    Espera que el excel tenga columna:
      - RUTA_CONFIGURACION
      - MES
      - VALOR_PROMEDIO_VALPAGADOS (si existe)
      - (opcional) VALOR_PROMEDIO_MERCADO
    Retorna series mensual ordenada.
    """
    df = _safe_read_excel(FILE_VALORES)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_VALORES}"}]

    if "RUTA_CONFIGURACION" not in df.columns or "MES" not in df.columns:
        return [{"warning": f"Columnas esperadas no existen en {FILE_VALORES} (RUTA_CONFIGURACION, MES)"}]

    ruta_config = str(ruta_config).strip().upper()
    dfr = df.copy()
    dfr["RUTA_CONFIGURACION"] = dfr["RUTA_CONFIGURACION"].astype(str).str.strip().str.upper()

    out_cols = ["MES"]
    if "VALOR_PROMEDIO_VALPAGADOS" in dfr.columns:
        dfr["VALOR_PROMEDIO_VALPAGADOS"] = pd.to_numeric(dfr["VALOR_PROMEDIO_VALPAGADOS"], errors="coerce")
        out_cols.append("VALOR_PROMEDIO_VALPAGADOS")
    if "VALOR_PROMEDIO_MERCADO" in dfr.columns:
        dfr["VALOR_PROMEDIO_MERCADO"] = pd.to_numeric(dfr["VALOR_PROMEDIO_MERCADO"], errors="coerce")
        out_cols.append("VALOR_PROMEDIO_MERCADO")

    dff = dfr[dfr["RUTA_CONFIGURACION"] == ruta_config]
    if dff.empty:
        return []

    dff = dff.sort_values("MES")
    return dff[out_cols].to_dict(orient="records")


# =========================================================
# 2) INDICADORES (índice cargue/descargue)
#    indice_cargue_descargue_resumen_mensual.xlsx
# =========================================================
def obtener_indicadores(municipio_dane: Union[int, str], configuracion: str) -> Optional[Dict[str, Any]]:
    df = _safe_read_excel(FILE_TIEMPOS)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_TIEMPOS}"}

    config = traducir_config(configuracion)

    # columnas esperadas (mínimo):
    # CODIGO_OBJETIVO, CONFIGURACION, INDICE_CARGUE_DESCARGUE, VEHICULOS_CARGUE, VEHICULOS_DESCARGUE
    if "CODIGO_OBJETIVO" not in df.columns or "CONFIGURACION" not in df.columns:
        return {"warning": f"Columnas esperadas no existen en {FILE_TIEMPOS} (CODIGO_OBJETIVO, CONFIGURACION)"}

    dfr = df.copy()
    dfr["CONFIGURACION"] = dfr["CONFIGURACION"].astype(str).str.upper().str.strip()

    filt = (dfr["CODIGO_OBJETIVO"] == int(municipio_dane)) & (dfr["CONFIGURACION"] == str(config).upper())
    if not filt.any():
        return None

    fila = dfr.loc[filt].iloc[0].to_dict()

    idx = fila.get("INDICE_CARGUE_DESCARGUE")
    try:
        idx_num = float(idx) if idx is not None else None
    except Exception:
        idx_num = None

    interpretacion = None
    if idx_num is not None:
        interpretacion = (
            "Exceso de oferta (salen más vehículos de los que llegan)"
            if idx_num > 1
            else "Mayor recepción de vehículos (entran más de los que salen)"
        )

    return limpiar_nan_json(
        {
            "configuracion": fila.get("CONFIGURACION"),
            "vehiculos_cargue": fila.get("VEHICULOS_CARGUE"),
            "vehiculos_descargue": fila.get("VEHICULOS_DESCARGUE"),
            "indice_cargue_descargue": fila.get("INDICE_CARGUE_DESCARGUE"),
            "interpretacion": interpretacion,
        }
    )


# =========================================================
# 3) COMPETITIVIDAD POR RUTA
#    competitividad_rutas_2025.xlsx
# =========================================================
def evaluar_competitividad(origen: Union[int, str], destino: Union[int, str], configuracion: str) -> Optional[Dict[str, Any]]:
    df = _safe_read_excel(FILE_COMPETITIVIDAD)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_COMPETITIVIDAD}"}

    config = traducir_config(configuracion)

    needed = {"CODIGO_ORIGEN", "CODIGO_DESTINO", "CONFIGURACION"}
    if not needed.issubset(set(df.columns)):
        return {"warning": f"Faltan columnas esperadas en {FILE_COMPETITIVIDAD}: {sorted(list(needed - set(df.columns)))}"}

    dfr = df.copy()
    dfr["CONFIGURACION"] = dfr["CONFIGURACION"].astype(str).str.upper().str.strip()

    fila = dfr[
        (dfr["CODIGO_ORIGEN"] == int(origen)) &
        (dfr["CODIGO_DESTINO"] == int(destino)) &
        (dfr["CONFIGURACION"] == str(config).upper())
    ]

    if fila.empty:
        return None

    return limpiar_nan_json(fila.iloc[0].to_dict())


# =========================================================
# 4) MESES DISPONIBLES PARA INDICADORES (si lo necesitas)
# =========================================================
def obtener_meses_disponibles_indicador(
    df: Optional[pd.DataFrame] = None,
    codigo_objetivo: Optional[Union[int, str]] = None,
    configuracion: Optional[str] = None
) -> List[int]:
    """
    Compatible con usos anteriores:
    - si no pasas df, usa FILE_TIEMPOS
    - si no pasas filtro, devuelve todos los meses únicos que encuentre
    """
    if df is None:
        df = _safe_read_excel(FILE_TIEMPOS)

    if df is None:
        return []

    if "AÑOMES" not in df.columns:
        return []

    dfr = df.copy()

    if codigo_objetivo is not None and "CODIGO_OBJETIVO" in dfr.columns:
        dfr = dfr[dfr["CODIGO_OBJETIVO"] == int(codigo_objetivo)]

    if configuracion is not None and "CONFIGURACION" in dfr.columns:
        config = traducir_config(configuracion)
        dfr["CONFIGURACION"] = dfr["CONFIGURACION"].astype(str).str.upper().str.strip()
        dfr = dfr[dfr["CONFIGURACION"] == str(config).upper()]

    meses = dfr["AÑOMES"].dropna().unique().tolist()
    out = []
    for m in meses:
        try:
            out.append(int(m))
        except Exception:
            pass
    return sorted(list(set(out)))


# =========================================================
# 5) RESOLVER CÓDIGOS DANE desde nombre (para estadísticas)
# =========================================================
def _resolver_codigo_dane(municipio: Union[int, str]) -> Optional[int]:
    # Si ya es número, úsalo
    try:
        if isinstance(municipio, (int, float)):
            return int(municipio)
        s = str(municipio).strip()
        if s.isdigit():
            return int(s)
    except Exception:
        pass

    # Resolver por nombre con municipios.xlsx (match exacto normalizado)
    df = _safe_read_excel(FILE_MUNICIPIOS)
    if df is None:
        return None

    # esperadas: nombre_oficial / codigo_dane (en tu excel real suele venir con esos nombres en minúscula;
    # aquí normalizamos a mayúsculas al cargar)
    # Intentamos varias alternativas:
    posibles_nombre = [c for c in df.columns if c in {"NOMBRE_OFICIAL", "NOMBRE", "MUNICIPIO"}]
    posibles_codigo = [c for c in df.columns if c in {"CODIGO_DANE", "CODIGO", "DANE"}]

    if not posibles_nombre or not posibles_codigo:
        return None

    col_nombre = posibles_nombre[0]
    col_codigo = posibles_codigo[0]

    objetivo = _norm_text(municipio)
    aux = df.copy()
    aux[col_nombre] = aux[col_nombre].astype(str).map(_norm_text)

    hit = aux[aux[col_nombre] == objetivo]
    if hit.empty:
        return None

    try:
        return int(hit.iloc[0][col_codigo])
    except Exception:
        return None


# =========================================================
# 6) ESTADÍSTICAS COMPLETAS (lo que pide ATICA)
# =========================================================
def obtener_estadisticas_completas(origen: Union[int, str], destino: Union[int, str]) -> Dict[str, Any]:
    """
    Usa los 6 excels de estadísticas actuales:
    - consolidacion_rutas_2024 / 2025 (evolución por mes/naturaleza)
    - consolidacion_anual_mercancia_top20_2025 (top mercancías ruta)
    - red_top20_destinos_origen_2025 (top destinos del origen)
    - red_top20_origenes_por_destino_2025 (top orígenes del destino)
    - consolidacion_rutas_vehiculo_2025 (distribución vehículos ruta)
    """
    cod_origen = _resolver_codigo_dane(origen)
    cod_destino = _resolver_codigo_dane(destino)

    if cod_origen is None or cod_destino is None:
        return limpiar_nan_json(
            {
                "warning": "No se pudieron resolver códigos DANE para origen/destino. "
                           "Pasa códigos directamente o asegúrate de que el nombre coincida con municipios.xlsx",
                "origen": origen,
                "destino": destino,
                "codigo_origen": cod_origen,
                "codigo_destino": cod_destino,
            }
        )

    evol = obtener_evolucion_viajes_y_toneladas(cod_origen, cod_destino)
    merc = obtener_top_mercancias_ruta(cod_origen, cod_destino, top_n=20)
    top_dest = obtener_top_destinos(cod_origen, top_n=20)
    top_org = obtener_top_origenes(cod_destino, top_n=20)
    veh = obtener_distribucion_vehiculos_ruta(cod_origen, cod_destino)

    return limpiar_nan_json(
        {
            "codigo_origen": cod_origen,
            "codigo_destino": cod_destino,
            "evolucion_viajes_toneladas": evol,
            "top_mercancias_ruta_2025": merc,
            "top_destinos_origen_2025": top_dest,
            "top_origenes_destino_2025": top_org,
            "distribucion_vehiculos_ruta_2025": veh,
        }
    )


# =========================================================
# 7) BLOQUEOS COLFECAR (opcional, robusto)
# =========================================================
def obtener_bloqueos_ruta_por_id(cod_origen: int, cod_destino: int, depto_helper_file: str = "DEPTO HELPER.xlsx") -> Dict[str, Any]:
    """
    No tumba el API si falta algún archivo/columna.
    """
    df_deptos = _safe_read_excel(FILE_DEPTO_RUTAS)
    df_bloq = _safe_read_excel(FILE_BLOQUEOS)

    if df_deptos is None or df_bloq is None:
        return limpiar_nan_json(
            {
                "warning": "Archivos de bloqueos no disponibles",
                "archivos": {"deptos": FILE_DEPTO_RUTAS, "bloqueos": FILE_BLOQUEOS},
                "fuente": "Datos proporcionados por Colfecar",
            }
        )

    # Normaliza columnas (sin tildes)
    def _clean_col(c: str) -> str:
        c = c.strip().upper()
        c = "".join(ch for ch in unicodedata.normalize("NFD", c) if unicodedata.category(ch) != "Mn")
        return c

    df_deptos.columns = [_clean_col(c) for c in df_deptos.columns]
    df_bloq.columns = [_clean_col(c) for c in df_bloq.columns]

    needed_dept = {"CODIGO_DANE_ORIGEN", "CODIGO_DANE_DESTINO", "ID DEPTO"}
    needed_bloq = {"ID DEPTO"}
    if not needed_dept.issubset(set(df_deptos.columns)) or not needed_bloq.issubset(set(df_bloq.columns)):
        return limpiar_nan_json(
            {
                "warning": "Columnas esperadas no están en archivos de bloqueos",
                "faltantes_deptos": sorted(list(needed_dept - set(df_deptos.columns))),
                "faltantes_bloqueos": sorted(list(needed_bloq - set(df_bloq.columns))),
                "fuente": "Datos proporcionados por Colfecar",
            }
        )

    # Asegura tipos
    df_deptos = df_deptos.copy()
    df_bloq = df_bloq.copy()
    df_deptos["CODIGO_DANE_ORIGEN"] = pd.to_numeric(df_deptos["CODIGO_DANE_ORIGEN"], errors="coerce")
    df_deptos["CODIGO_DANE_DESTINO"] = pd.to_numeric(df_deptos["CODIGO_DANE_DESTINO"], errors="coerce")
    df_deptos["ID DEPTO"] = pd.to_numeric(df_deptos["ID DEPTO"], errors="coerce")
    df_bloq["ID DEPTO"] = pd.to_numeric(df_bloq["ID DEPTO"], errors="coerce")

    if "EFECTO TOTAL HORAS" in df_bloq.columns:
        df_bloq["EFECTO TOTAL HORAS"] = pd.to_numeric(df_bloq["EFECTO TOTAL HORAS"], errors="coerce").fillna(0)
    else:
        df_bloq["EFECTO TOTAL HORAS"] = 0

    filt = df_deptos[
        ((df_deptos["CODIGO_DANE_ORIGEN"] == int(cod_origen)) & (df_deptos["CODIGO_DANE_DESTINO"] == int(cod_destino))) |
        ((df_deptos["CODIGO_DANE_ORIGEN"] == int(cod_destino)) & (df_deptos["CODIGO_DANE_DESTINO"] == int(cod_origen)))
    ]

    if filt.empty:
        return limpiar_nan_json(
            {
                "total_bloqueos": 0,
                "departamentos_ruta": [],
                "id_departamentos_ruta": [],
                "lista_bloqueos": [],
                "resumen_motivos": [],
                "total_efecto_horas": 0,
                "riesgo_bloqueos": 0,
                "fuente": "Datos proporcionados por Colfecar",
            }
        )

    id_deptos = filt["ID DEPTO"].dropna().astype(int).unique().tolist()

    # Mapear nombres de deptos (si existe el helper)
    nombres = []
    try:
        helper = DeptoHelper(depto_helper_file)
        nombres = [helper.buscar_nombre(x) or f"ID {x}" for x in id_deptos]
    except Exception:
        nombres = [f"ID {x}" for x in id_deptos]

    bloqueos = df_bloq[df_bloq["ID DEPTO"].isin(id_deptos)].copy()
    total_bloqueos = int(len(bloqueos))

    total_efecto = float(bloqueos["EFECTO TOTAL HORAS"].sum()) if not bloqueos.empty else 0.0
    riesgo = round((total_efecto / max(total_bloqueos, 1)), 2) if total_bloqueos > 0 else 0.0

    # Resumen motivos si existe columna MOTIVO
    resumen = []
    if "MOTIVO" in bloqueos.columns and not bloqueos.empty:
        tmp = bloqueos["MOTIVO"].astype(str).value_counts().head(10)
        resumen = [{"motivo": k, "conteo": int(v)} for k, v in tmp.items()]

    return limpiar_nan_json(
        {
            "total_bloqueos": total_bloqueos,
            "departamentos_ruta": nombres,
            "id_departamentos_ruta": id_deptos,
            "lista_bloqueos": bloqueos.head(200).to_dict(orient="records"),  # límite defensivo
            "resumen_motivos": resumen,
            "total_efecto_horas": total_efecto,
            "riesgo_bloqueos": riesgo,
            "fuente": "Datos proporcionados por Colfecar",
        }
    )
