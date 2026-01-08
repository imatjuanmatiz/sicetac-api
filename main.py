from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import pandas as pd
import logging

logger = logging.getLogger("api")

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

from contexto_helper import (
    obtener_valores_promedio_mercado_por_llave,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_indicador,
)

from estadisticas_helper import obtener_estadisticas_completas


# =========================
# APP
# =========================
app = FastAPI(title="API SICETAC", version="2.1.1")


# =========================
# INPUT
# =========================
class ConsultaInput(BaseModel):
    # Por defecto, vacío (None). Solo si el usuario lo entrega explícitamente se usa.
    id_ruta: str | None = None

    # Solo se usan si NO hay id_ruta válido
    origen: str | None = None
    destino: str | None = None

    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    horas_logisticas_personalizadas: float | None = None

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

    modo_viaje: str = "CARGADO"
    estadistica: str = "Sí"


# =========================
# ARCHIVOS
# =========================
ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx",
}

helper = SICETACHelper(ARCHIVOS["municipios"])

df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])


# =========================
# UTILS
# =========================
def _clean_optional_str(x: str | None) -> str | None:
    """
    Convierte strings vacíos/ruidosos en None:
      "", "   ", "null", "none", "nan" -> None
    """
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    if s.lower() in {"null", "none", "nan"}:
        return None
    return s


def estadistica_activado(valor) -> bool:
    if valor is None:
        return False
    return str(valor).strip().lower().replace("í", "i") in ["si", "sí", "true", "1"]


def convertir_nativos(obj):
    """Convierte tipos numpy/pandas a tipos Python nativos para JSON."""
    if isinstance(obj, dict):
        return {k: convertir_nativos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convertir_nativos(v) for v in obj]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
    except Exception:
        pass
    return obj


def traducir_vehiculo_a_stats(vehiculo_sicetac: str) -> str:
    """
    Traduce vehículo SICETAC (ej: C3S3) a configuración análisis (sin C, ej: 3S3)
    usando CONFIGURACION_VEHICULAR_LIMPIO.xlsx si existe mapeo.
    Fallback: quita 'C'.
    """
    v = (vehiculo_sicetac or "").strip().upper().replace(" ", "")
    if df_vehiculos is None or df_vehiculos.empty:
        return v.replace("C", "")

    tmp = df_vehiculos.copy()
    tmp.columns = [str(c).strip().upper() for c in tmp.columns]

    if "TIPO_VEHICULO" not in tmp.columns or "CONFIGURACION_ANALISIS" not in tmp.columns:
        return v.replace("C", "")

    tmp["TIPO_VEHICULO"] = tmp["TIPO_VEHICULO"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
    tmp["CONFIGURACION_ANALISIS"] = tmp["CONFIGURACION_ANALISIS"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)

    hit = tmp[tmp["TIPO_VEHICULO"] == v]
    if hit.empty:
        return v.replace("C", "")

    return str(hit.iloc[0]["CONFIGURACION_ANALISIS"]).strip().upper().replace(" ", "").replace("C", "")


def obtener_nombre_ruta(fila_ruta):
    if fila_ruta is None:
        return "Ruta no especificada"

    km_plano = float(fila_ruta.get("KM_PLANO", 0) or 0)
    km_ondulado = float(fila_ruta.get("KM_ONDULADO", 0) or 0)
    km_montañoso = float(fila_ruta.get("KM_MONTAÑOSO", 0) or 0)
    km_urbano = float(fila_ruta.get("KM_URBANO", 0) or 0)
    km_despav = float(fila_ruta.get("KM_DESPAVIMENTADO", 0) or 0)

    return (
        f"Plano: {km_plano} km | Ondulado: {km_ondulado} km | "
        f"Montañoso: {km_montañoso} km | Urbano: {km_urbano} km | "
        f"Despavimentado: {km_despav} km"
    )


def _first_not_none(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None


# =========================
# ENDPOINTS: RUTAS
# =========================
@app.get("/rutas/disponibles")
def listar_rutas_disponibles(
    origen: str = Query(..., description="Nombre municipio origen"),
    destino: str = Query(..., description="Nombre municipio destino"),
):
    origen = _clean_optional_str(origen)
    destino = _clean_optional_str(destino)

    if not origen or not destino:
        raise HTTPException(status_code=400, detail="Debe enviar origen y destino válidos.")

    lista_rutas, info = helper.buscar_todas_las_rutas(origen, destino, df_rutas)

    if not lista_rutas:
        raise HTTPException(status_code=404, detail=info.get("mensaje", "No se encontraron rutas"))

    return JSONResponse(content={
        "origen": info.get("origen_nombre"),
        "destino": info.get("destino_nombre"),
        "codigo_origen": info.get("origen_codigo"),
        "codigo_destino": info.get("destino_codigo"),
        "total_rutas": info.get("total_rutas"),
        "id_principal": info.get("id_principal"),
        "ids_alternativos": info.get("ids_alternativos", []),
        "rutas": lista_rutas
    })


@app.get("/ruta/{id_ruta}")
def obtener_ruta_por_id(id_ruta: str):
    id_ruta = _clean_optional_str(id_ruta)
    if not id_ruta:
        raise HTTPException(status_code=400, detail="id_ruta inválido.")

    fila_ruta, info = helper.buscar_ruta_por_id(id_ruta, df_rutas)

    if fila_ruta is None:
        raise HTTPException(status_code=404, detail=info.get("error"))

    origen_muni = helper.obtener_municipio_por_codigo(info.get("origen"))
    destino_muni = helper.obtener_municipio_por_codigo(info.get("destino"))

    return JSONResponse(content={
        "id_ruta": info.get("id_sice"),
        "origen": {
            "codigo": info.get("origen"),
            "nombre": (origen_muni or {}).get("nombre_oficial")
        },
        "destino": {
            "codigo": info.get("destino"),
            "nombre": (destino_muni or {}).get("nombre_oficial")
        },
        "ruta": info.get("ruta"),
        "via": info.get("via"),
        "nombre_sice": info.get("nombre_sice"),
        "km_total": info.get("km_total"),
    })


# =========================
# ENDPOINT: CONSULTA
# =========================
@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    # -------------------------
    # 0) Normalización de inputs
    # -------------------------
    id_ruta = _clean_optional_str(data.id_ruta)
    origen = _clean_optional_str(data.origen)
    destino = _clean_optional_str(data.destino)

    vehiculo_sicetac = _clean_optional_str(data.vehiculo) or "C3S3"
    vehiculo_sicetac = vehiculo_sicetac.strip().upper().replace(" ", "")
    vehiculo_stats = traducir_vehiculo_a_stats(vehiculo_sicetac)

    # -------------------------
    # 1) Resolver ruta (SOLO usa ID si viene explícito y válido)
    # -------------------------
    fila_ruta = None
    info_ruta = {}

    if id_ruta:
        fila_ruta, info_ruta = helper.buscar_ruta_por_id(id_ruta, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró la ruta por ID"))
    else:
        if not origen or not destino:
            raise HTTPException(status_code=400, detail="Debe enviar 'origen' y 'destino' o un 'id_ruta' válido.")
        fila_ruta, info_ruta = helper.buscar_ruta(origen, destino, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró ruta para origen/destino."))

    # -------------------------
    # 2) Extraer códigos origen/destino (robusto)
    # -------------------------
    if id_ruta:
        # buscar_ruta_por_id devuelve origen/destino directo en info_ruta
        cod_origen_raw = info_ruta.get("origen")
        cod_destino_raw = info_ruta.get("destino")
    else:
        # buscar_ruta devuelve dict con detalle_rutas/detalle_busqueda_id
        cod_origen_raw = _first_not_none(
            (info_ruta.get("detalle_busqueda_id") or {}).get("origen"),
            (info_ruta.get("detalle_rutas") or {}).get("origen"),
        )
        cod_destino_raw = _first_not_none(
            (info_ruta.get("detalle_busqueda_id") or {}).get("destino"),
            (info_ruta.get("detalle_rutas") or {}).get("destino"),
        )

    if cod_origen_raw is None or cod_destino_raw is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "No se pudieron resolver códigos DANE de origen/destino desde la ruta.",
                "id_ruta_usado": id_ruta,
                "info_ruta_keys": list(info_ruta.keys()),
                "info_ruta": info_ruta,
            },
        )

    cod_origen = int(cod_origen_raw)
    cod_destino = int(cod_destino_raw)

    # -------------------------
    # 3) Distancias (fila_ruta + override manual)
    # -------------------------
    distancias = {
        "KM_PLANO": float(data.km_plano or 0) if float(data.km_plano or 0) > 0 else float(fila_ruta.get("KM_PLANO", 0) or 0),
        "KM_ONDULADO": float(data.km_ondulado or 0) if float(data.km_ondulado or 0) > 0 else float(fila_ruta.get("KM_ONDULADO", 0) or 0),
        "KM_MONTAÑOSO": float(data.km_montañoso or 0) if float(data.km_montañoso or 0) > 0 else float(fila_ruta.get("KM_MONTAÑOSO", 0) or 0),
        "KM_URBANO": float(data.km_urbano or 0) if float(data.km_urbano or 0) > 0 else float(fila_ruta.get("KM_URBANO", 0) or 0),
        "KM_DESPAVIMENTADO": float(data.km_despavimentado or 0) if float(data.km_despavimentado or 0) > 0 else float(fila_ruta.get("KM_DESPAVIMENTADO", 0) or 0),
    }

    # -------------------------
    # 4) Calcular SICETAC
    # -------------------------
    try:
        resultado = calcular_modelo_sicetac_extendido(
            origen=origen,                     # puede ser None si usaste id_ruta; modelo debe tolerarlo o ignorarlo
            destino=destino,                   # idem
            configuracion=vehiculo_sicetac,
            serie=data.mes,
            distancias=distancias,
            matriz_parametros=df_parametros,
            matriz_costos_fijos=df_costos_fijos,
            matriz_vehicular=df_vehiculos,
            rutas_df=df_rutas,
            peajes_df=df_peajes,
            valor_peaje_manual=float(data.valor_peaje_manual or 0),
            carroceria_especial=data.carroceria,
            ruta_oficial=fila_ruta,
            modo_viaje=data.modo_viaje,
            horas_logisticas_personalizadas=data.horas_logisticas_personalizadas,
        )
        resultado = convertir_nativos(resultado)
    except Exception as e:
        logger.exception("Fallo cálculo SICETAC")
        raise HTTPException(status_code=500, detail=f"Error calculando SICETAC: {str(e)}")

    # -------------------------
    # 4.1) Valores mercado RNDC (si aplica)
    # -------------------------
    valor_mercado = []
    try:
        ruta_config = f"{cod_origen}-{cod_destino}_{vehiculo_stats}"
        valor_mercado = obtener_valores_promedio_mercado_por_llave(ruta_config)
    except Exception:
        valor_mercado = []

    # -------------------------
    # 4.2) Info ruta para respuesta
    # -------------------------
    if id_ruta:
        info_ruta_response = {
            "id_ruta_usado": id_ruta,
            "distancias_descriptivas": obtener_nombre_ruta(fila_ruta),
            "detalle": info_ruta,
        }
    else:
        info_ruta_response = {
            "ruta_principal": info_ruta.get("ruta_principal"),
            "rutas_alternativas": info_ruta.get("rutas_alternativas", []),
            "detalle": info_ruta.get("detalle_rutas") or info_ruta.get("detalle_busqueda_id"),
            "distancias_descriptivas": obtener_nombre_ruta(fila_ruta),
        }

    respuesta = {
        "SICETAC": resultado,
        "MODO_VIAJE": data.modo_viaje,
        "VALOR_MERCADO_RNDC": valor_mercado,
        "INFO_RUTA": info_ruta_response,
        "CODIGOS": {"origen": cod_origen, "destino": cod_destino},
        "VEHICULO": {"sicetac": vehiculo_sicetac, "estadisticas": vehiculo_stats},
    }

    # -------------------------
    # 5) Estadísticas y Contexto (SEPARADOS y a prueba de fallos)
    # -------------------------
    if estadistica_activado(data.estadistica):
        # 1) ESTADISTICAS (consolidados por ruta)
        try:
            respuesta["ESTADISTICAS"] = obtener_estadisticas_completas(cod_origen, cod_destino)
        except Exception as e:
            logger.exception("Fallo en estadisticas_helper")
            respuesta["ESTADISTICAS"] = {"warning": "No se pudieron generar estadísticas", "error": str(e)}

        # 2) CONTEXTO (indicadores + competitividad) - usa vehiculo_stats (sin C)
        try:
            respuesta["CONTEXTO"] = {
                "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo_stats),
                "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo_stats),
                "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo_stats),
                "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(None, cod_origen, vehiculo_stats),
                "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(None, cod_destino, vehiculo_stats),
            }
        except Exception as e:
            logger.exception("Fallo en contexto_helper")
            respuesta["CONTEXTO"] = {"warning": "No se pudo generar contexto", "error": str(e), "vehiculo_stats": vehiculo_stats}

    return JSONResponse(content=respuesta)


# =========================
# HEALTH
# =========================
@app.head("/")
def head_root():
    return Response(status_code=200)


@app.get("/")
def root():
    return {"message": "API SICETAC", "version": "2.1.1"}


@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.1.1"}
