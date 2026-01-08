# estadisticas_helper.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import unicodedata

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

# =========================
# Archivos (nombres esperados)
# =========================
FILE_RUTAS_2024 = "consolidacion_rutas_2024.xlsx"
FILE_RUTAS_2025 = "consolidacion_rutas_2025.xlsx"
FILE_RUTAS_VEH_2025 = "consolidacion_rutas_vehiculo_2025.xlsx"
FILE_MERCANCIAS_TOP20_2025 = "consolidacion_anual_mercancia_top20_2025.xlsx"
FILE_TOP_DESTINOS_ORIGEN_2025 = "red_top20_destinos_origen_2025.xlsx"
FILE_TOP_ORIGENES_DESTINO_2025 = "red_top20_origenes_por_destino_2025.xlsx"

# Cache: lectura lazy (mejor para Render)
_DF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


# =========================
# Utilidades
# =========================
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")


def _norm_col(c: Any) -> str:
    c = str(c).strip().upper()
    c = _strip_accents(c)            # AÑOMES -> ANOMES
    c = c.replace("\u00a0", " ")     # NBSP
    c = " ".join(c.split())
    return c


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_norm_col(c) for c in df.columns]
    return df


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
    df = _normalize_df(df)
    _DF_CACHE[name] = df
    return df


def _route_key(cod_origen: Union[int, str], cod_destino: Union[int, str]) -> str:
    return f"{int(cod_origen)}-{int(cod_destino)}"


def _filter_by_route(df: pd.DataFrame, cod_origen: int, cod_destino: int) -> pd.DataFrame:
    """
    Filtra SOLO sentido directo por:
      - RUTA == "cod_origen-cod_destino"
    o fallback:
      - CODIGO_ORIGEN == cod_origen y CODIGO_DESTINO == cod_destino
    """
    if df is None or df.empty:
        return df.iloc[0:0]

    clave = _route_key(cod_origen, cod_destino)
    cols = set(df.columns)

    if "RUTA" in cols:
        dfr = df[df["RUTA"].astype(str).str.strip() == clave]
        if not dfr.empty:
            return dfr

    if "CODIGO_ORIGEN" in cols and "CODIGO_DESTINO" in cols:
        dfr = df[(df["CODIGO_ORIGEN"] == int(cod_origen)) & (df["CODIGO_DESTINO"] == int(cod_destino))]
        if not dfr.empty:
            return dfr

    return df.iloc[0:0]


def _to_num(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _norm_vehicle_no_c(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.strip().upper().replace(" ", "")
    # por seguridad, si viniera con C, la quitamos en estadísticas
    s = s.replace("C", "")
    return s


def _month_sort_key(anomes: Any) -> int:
    """
    ANOMES esperado como YYYYMM (ej 202501).
    Si viene como string, intenta convertir.
    """
    try:
        return int(str(anomes).strip())
    except Exception:
        return 0


# =========================================================
# 1) Comparativo mensual 2024 vs 2025 (por NATURALEZACARGA)
# =========================================================
def obtener_comparativo_mes_a_mes_2024_2025(
    codigo_origen: int,
    codigo_destino: int
) -> Dict[str, Any]:
    """
    Produce tabla comparativa:
    - llave: (ANOMES, NATURALEZACARGA)
    - métricas: viajes, toneladas, galones
    - variación: abs y %
    """
    df24 = _safe_read_excel(FILE_RUTAS_2024)
    df25 = _safe_read_excel(FILE_RUTAS_2025)

    if df24 is None or df25 is None:
        return {
            "warning": "Uno o más archivos no están disponibles",
            "archivos": {
                "2024": FILE_RUTAS_2024 if df24 is not None else None,
                "2025": FILE_RUTAS_2025 if df25 is not None else None,
            }
        }

    d24 = _filter_by_route(df24, codigo_origen, codigo_destino)
    d25 = _filter_by_route(df25, codigo_origen, codigo_destino)

    if d24.empty and d25.empty:
        return {"tabla": [], "mensaje": "No hay datos 2024 ni 2025 para la ruta."}

    # AÑOMES -> ANOMES por normalización de columnas
    needed = ["ANOMES", "NATURALEZACARGA", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TOTAL_GALONES"]

    # Si falta ANOMES pero existe MES o AÑO MES etc, intentamos mapear
    def ensure_anomes(d: pd.DataFrame) -> pd.DataFrame:
        if d.empty:
            return d
        cols = set(d.columns)
        if "ANOMES" in cols:
            return d
        # intentos de fallback
        for alt in ["AÑO MES", "ANO MES", "MES", "AÑOMES"]:
            alt_norm = _norm_col(alt)
            if alt_norm in cols:
                d = d.copy()
                d["ANOMES"] = d[alt_norm]
                return d
        return d

    d24 = ensure_anomes(d24)
    d25 = ensure_anomes(d25)

    # Normalizar numéricos + toneladas
    d24 = _to_num(d24, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TOTAL_GALONES"])
    d25 = _to_num(d25, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TOTAL_GALONES"])

    for d in (d24, d25):
        if not d.empty and "TOTAL_KILOGRAMOS" in d.columns:
            d["TONELADAS"] = d["TOTAL_KILOGRAMOS"] / 1000.0

    # Agrupar por mes + naturaleza (por si hay duplicados)
    def agg(d: pd.DataFrame, year: int) -> pd.DataFrame:
        if d.empty:
            return pd.DataFrame(columns=["ANOMES", "NATURALEZACARGA",
                                         f"VIAJES_{year}", f"TON_{year}", f"GAL_{year}"])
        # asegurar columnas
        base_cols = {"ANOMES", "NATURALEZACARGA", "TOTAL_VIAJES", "TONELADAS", "TOTAL_GALONES"}
        faltan = sorted(list(base_cols - set(d.columns)))
        if faltan:
            # devolvemos vacío pero sin romper
            return pd.DataFrame(columns=["ANOMES", "NATURALEZACARGA",
                                         f"VIAJES_{year}", f"TON_{year}", f"GAL_{year}"])

        x = d.copy()
        x["ANOMES"] = x["ANOMES"].map(_month_sort_key)
        x["NATURALEZACARGA"] = x["NATURALEZACARGA"].astype(str).str.upper().str.strip()
        g = x.groupby(["ANOMES", "NATURALEZACARGA"], as_index=False).agg(
            TOTAL_VIAJES=("TOTAL_VIAJES", "sum"),
            TONELADAS=("TONELADAS", "sum"),
            TOTAL_GALONES=("TOTAL_GALONES", "sum"),
        )
        g = g.rename(columns={
            "TOTAL_VIAJES": f"VIAJES_{year}",
            "TONELADAS": f"TON_{year}",
            "TOTAL_GALONES": f"GAL_{year}",
        })
        return g

    a24 = agg(d24, 2024)
    a25 = agg(d25, 2025)

    # Merge outer para comparar
    if a24.empty and not a25.empty:
        merged = a25.copy()
        merged["VIAJES_2024"] = 0
        merged["TON_2024"] = 0
        merged["GAL_2024"] = 0
    elif a25.empty and not a24.empty:
        merged = a24.copy()
        merged["VIAJES_2025"] = 0
        merged["TON_2025"] = 0
        merged["GAL_2025"] = 0
    else:
        merged = pd.merge(a24, a25, on=["ANOMES", "NATURALEZACARGA"], how="outer")

    merged = merged.fillna(0)

    # Variaciones
    merged["VAR_VIAJES_ABS"] = merged["VIAJES_2025"] - merged["VIAJES_2024"]
    merged["VAR_TON_ABS"] = merged["TON_2025"] - merged["TON_2024"]
    merged["VAR_GAL_ABS"] = merged["GAL_2025"] - merged["GAL_2024"]

    def pct(new, old):
        try:
            return (new - old) / old * 100.0 if old and old != 0 else None
        except Exception:
            return None

    merged["VAR_VIAJES_PCT"] = merged.apply(lambda r: pct(r["VIAJES_2025"], r["VIAJES_2024"]), axis=1)
    merged["VAR_TON_PCT"] = merged.apply(lambda r: pct(r["TON_2025"], r["TON_2024"]), axis=1)
    merged["VAR_GAL_PCT"] = merged.apply(lambda r: pct(r["GAL_2025"], r["GAL_2024"]), axis=1)

    merged = merged.sort_values(by=["ANOMES", "NATURALEZACARGA"], ascending=True)

    return {"tabla": merged.to_dict(orient="records")}


# =========================================================
# 2) Distribución anual 2025 por tipo de vehículo (COD_CONFIG_VEHICULO)
# =========================================================
def obtener_distribucion_vehiculos_2025(
    codigo_origen: int,
    codigo_destino: int
) -> Dict[str, Any]:
    df = _safe_read_excel(FILE_RUTAS_VEH_2025)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_RUTAS_VEH_2025}"}

    dfr = _filter_by_route(df, codigo_origen, codigo_destino)
    if dfr.empty:
        return {"tabla": [], "mensaje": "No hay datos de vehículos 2025 para la ruta."}

    required = {"COD_CONFIG_VEHICULO", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS"}
    if not required.issubset(set(dfr.columns)):
        return {"warning": f"Faltan columnas en {FILE_RUTAS_VEH_2025}", "faltantes": sorted(list(required - set(dfr.columns)))}

    dfr = dfr.copy()
    dfr["COD_CONFIG_VEHICULO"] = dfr["COD_CONFIG_VEHICULO"].map(_norm_vehicle_no_c)
    dfr = _to_num(dfr, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TOTAL_GALONES"])
    dfr["TONELADAS"] = dfr["TOTAL_KILOGRAMOS"] / 1000.0

    agg = dfr.groupby("COD_CONFIG_VEHICULO", as_index=False).agg(
        TOTAL_VIAJES=("TOTAL_VIAJES", "sum"),
        TOTAL_KILOGRAMOS=("TOTAL_KILOGRAMOS", "sum"),
        TONELADAS=("TONELADAS", "sum"),
        TOTAL_GALONES=("TOTAL_GALONES", "sum") if "TOTAL_GALONES" in dfr.columns else ("TOTAL_VIAJES", "size"),
    )

    total_viajes = float(agg["TOTAL_VIAJES"].sum()) if not agg.empty else 0.0
    total_ton = float(agg["TONELADAS"].sum()) if not agg.empty else 0.0

    agg["PCT_VIAJES"] = (agg["TOTAL_VIAJES"] / total_viajes * 100.0) if total_viajes > 0 else 0.0
    agg["PCT_TONELADAS"] = (agg["TONELADAS"] / total_ton * 100.0) if total_ton > 0 else 0.0

    agg = agg.sort_values(by="TOTAL_VIAJES", ascending=False)

    return {"tabla": agg.to_dict(orient="records")}


# =========================================================
# 3) Top 20 mercancías 2025 por ruta
# =========================================================
def obtener_top_mercancias_2025(
    codigo_origen: int,
    codigo_destino: int,
    top_n: int = 20
) -> Dict[str, Any]:
    df = _safe_read_excel(FILE_MERCANCIAS_TOP20_2025)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_MERCANCIAS_TOP20_2025}"}

    dfr = _filter_by_route(df, codigo_origen, codigo_destino)
    if dfr.empty:
        return {"tabla": [], "mensaje": "No hay mercancías top 2025 para la ruta."}

    # Normalizar numéricos relevantes
    dfr = _to_num(dfr, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "TONELADAS_RUTA", "PCT_PARTICIPACION"])

    # Orden preferido
    if "PCT_PARTICIPACION" in dfr.columns:
        dfr = dfr.sort_values("PCT_PARTICIPACION", ascending=False)
    elif "TONELADAS" in dfr.columns:
        dfr = dfr.sort_values("TONELADAS", ascending=False)
    elif "TOTAL_VIAJES" in dfr.columns:
        dfr = dfr.sort_values("TOTAL_VIAJES", ascending=False)

    cols = ["AÑO", "CODMERCANCIA", "MERCANCIA", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "PCT_PARTICIPACION"]
    cols = [c for c in cols if c in dfr.columns]

    return {"tabla": dfr[cols].head(top_n).to_dict(orient="records")}


# =========================================================
# 4) Red top 20 destinos por origen 2025
# =========================================================
def obtener_top_destinos_origen_2025(codigo_origen: int, top_n: int = 20) -> Dict[str, Any]:
    df = _safe_read_excel(FILE_TOP_DESTINOS_ORIGEN_2025)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_TOP_DESTINOS_ORIGEN_2025}"}

    if "CODIGO_ORIGEN" not in df.columns:
        return {"warning": f"Falta columna CODIGO_ORIGEN en {FILE_TOP_DESTINOS_ORIGEN_2025}"}

    dfr = df[df["CODIGO_ORIGEN"] == int(codigo_origen)].copy()
    if dfr.empty:
        return {"tabla": [], "mensaje": "No hay red top destinos para este origen (2025)."}

    dfr = _to_num(dfr, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"])
    sort_col = "TOTAL_VIAJES" if "TOTAL_VIAJES" in dfr.columns else ("TONELADAS" if "TONELADAS" in dfr.columns else None)
    if sort_col:
        dfr = dfr.sort_values(sort_col, ascending=False)

    cols = ["AÑO", "CODIGO_ORIGEN", "MUNICIPIO_ORIGEN", "CODIGO_DESTINO", "MUNICIPIO_DESTINO", "TOTAL_VIAJES", "TONELADAS"]
    cols = [c for c in cols if c in dfr.columns]
    return {"tabla": dfr[cols].head(top_n).to_dict(orient="records")}


# =========================================================
# 5) Red top 20 orígenes por destino 2025
# =========================================================
def obtener_top_origenes_destino_2025(codigo_destino: int, top_n: int = 20) -> Dict[str, Any]:
    df = _safe_read_excel(FILE_TOP_ORIGENES_DESTINO_2025)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_TOP_ORIGENES_DESTINO_2025}"}

    if "CODIGO_DESTINO" not in df.columns:
        return {"warning": f"Falta columna CODIGO_DESTINO en {FILE_TOP_ORIGENES_DESTINO_2025}"}

    dfr = df[df["CODIGO_DESTINO"] == int(codigo_destino)].copy()
    if dfr.empty:
        return {"tabla": [], "mensaje": "No hay red top orígenes para este destino (2025)."}

    dfr = _to_num(dfr, ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"])
    sort_col = "TOTAL_VIAJES" if "TOTAL_VIAJES" in dfr.columns else ("TONELADAS" if "TONELADAS" in dfr.columns else None)
    if sort_col:
        dfr = dfr.sort_values(sort_col, ascending=False)

    cols = ["AÑO", "CODIGO_DESTINO", "MUNICIPIO_DESTINO", "CODIGO_ORIGEN", "MUNICIPIO_ORIGEN", "TOTAL_VIAJES", "TONELADAS"]
    cols = [c for c in cols if c in dfr.columns]
    return {"tabla": dfr[cols].head(top_n).to_dict(orient="records")}


# =========================================================
# 6) Orquestador: todo junto
# =========================================================
def obtener_estadisticas_completas(codigo_origen: int, codigo_destino: int) -> Dict[str, Any]:
    return {
        "comparativo_mes_a_mes_2024_2025": obtener_comparativo_mes_a_mes_2024_2025(codigo_origen, codigo_destino),
        "distribucion_vehiculos_2025": obtener_distribucion_vehiculos_2025(codigo_origen, codigo_destino),
        "top_mercancias_2025": obtener_top_mercancias_2025(codigo_origen, codigo_destino, top_n=20),
        "red_top20_destinos_origen_2025": obtener_top_destinos_origen_2025(codigo_origen, top_n=20),
        "red_top20_origenes_destino_2025": obtener_top_origenes_destino_2025(codigo_destino, top_n=20),
    }
