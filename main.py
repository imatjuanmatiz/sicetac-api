from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel
import pandas as pd

from fastapi.responses import JSONResponse
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
app = FastAPI(title="API SICETAC", version="2.1.0")

# =========================
# MODELO INPUT
# =========================
class ConsultaInput(BaseModel):
    origen: str | None = None
    destino: str | None = None
    id_ruta: str | None = None

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
# CARGA BASE
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
# UTIL
# =========================
def estadistica_activado(valor):
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

    km_plano = float(fila_ruta.get("KM_PLANO", 0))
    km_ondulado = float(fila_ruta.get("KM_ONDULADO", 0))
    km_montañoso = float(fila_ruta.get("KM_MONTAÑOSO", 0))
    km_urbano = float(fila_ruta.get("KM_URBANO", 0))
    km_despav = float(fila_ruta.get("KM_DESPAVIMENTADO", 0))

    return (
        f"Plano: {km_plano} km | Ondulado: {km_ondulado} km | "
        f"Montañoso: {km_montañoso} km | Urbano: {km_urbano} km | "
        f"Despavimentado: {km_despav} km"
    )


# =========================
# ENDPOINTS: RUTAS
# =========================
@app.get("/rutas/disponibles")
def listar_rutas_disponibles(
    origen: str = Query(..., description="Nombre municipio origen"),
    destino: str = Query(..., description="Nombre municipio destino"),
):
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
    fila_ruta, info = helper.buscar_ruta_por_id(id_ruta, df_rutas)

    if fila_ruta is None:
        raise HTTPException(status_code=404, detail=info.get("error"))

    origen_muni = helper.obtener_municipio_por_codigo(info["origen"])
    destino_muni = helper.obtener_municipio_por_codigo(info["destino"])

    return JSONResponse(content={
        "id_ruta": info["id_sice"],
        "origen": {
            "codigo": info["origen"],
            "nombre": (origen_muni or {}).get("nombre_oficial")
        },
        "destino": {
            "codigo": info["destino"],
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
    # 0) Normalización base
    # -------------------------
    vehiculo_sicetac = (data.vehiculo or "C3S3").strip().upper().replace(" ", "")
    vehiculo_stats = traducir_vehiculo_a_stats(vehiculo_sicetac)

    # -------------------------
    # 1) Resolver ruta principal (por id_ruta o por origen/destino)
    # -------------------------
    fila_ruta = None
    info_ruta = {}

    if data.id_ruta:
        fila_ruta, info_ruta = helper.buscar_ruta_por_id(data.id_ruta, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró la ruta por ID"))
    else:
        if not data.origen or not data.destino:
            raise HTTPException(status_code=400, detail="Debe enviar 'origen' y 'destino' o 'id_ruta'.")

        fila_ruta, info_ruta = helper.buscar_ruta(data.origen, data.destino, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró ruta para origen/destino."))

    # -------------------------
    # 2) Extraer códigos origen/destino
    # -------------------------
    cod_origen = int(info_ruta.get("detalle_busqueda_id", {}).get("origen") or info_ruta.get("detalle_rutas", {}).get("origen"))
    cod_destino = int(info_ruta.get("detalle_busqueda_id", {}).get("destino") or info_ruta.get("detalle_rutas", {}).get("destino"))

    # si no existen por algún motivo (seguridad)
    if not cod_origen or not cod_destino:
        raise HTTPException(status_code=500, detail="No se pudieron resolver códigos DANE de origen/destino desde la ruta.")

    # -------------------------
    # 3) Construir distancias (usa fila_ruta + posibilidad de override manual)
    # -------------------------
    distancias = {
        "KM_PLANO": float(getattr(data, "km_plano", 0) or 0) if float(getattr(data, "km_plano", 0) or 0) > 0 else float(fila_ruta.get("KM_PLANO", 0)),
        "KM_ONDULADO": float(getattr(data, "km_ondulado", 0) or 0) if float(getattr(data, "km_ondulado", 0) or 0) > 0 else float(fila_ruta.get("KM_ONDULADO", 0)),
        "KM_MONTAÑOSO": float(getattr(data, "km_montañoso", 0) or 0) if float(getattr(data, "km_montañoso", 0) or 0) > 0 else float(fila_ruta.get("KM_MONTAÑOSO", 0)),
        "KM_URBANO": float(getattr(data, "km_urbano", 0) or 0) if float(getattr(data, "km_urbano", 0) or 0) > 0 else float(fila_ruta.get("KM_URBANO", 0)),
        "KM_DESPAVIMENTADO": float(getattr(data, "km_despavimentado", 0) or 0) if float(getattr(data, "km_despavimentado", 0) or 0) > 0 else float(fila_ruta.get("KM_DESPAVIMENTADO", 0)),
    }

    # -------------------------
    # 4) Calcular SICETAC
    # -------------------------
    try:
        resultado = calcular_modelo_sicetac_extendido(
            origen=data.origen,
            destino=data.destino,
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
        # ruta_configuración típica: "11001000-76001000_3S3" (según tu diseño previo)
        ruta_config = f"{cod_origen}-{cod_destino}_{vehiculo_stats}"
        valor_mercado = obtener_valores_promedio_mercado_por_llave(ruta_config)
    except Exception:
        valor_mercado = []

    # -------------------------
    # 4.2) Info ruta para respuesta
    # -------------------------
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
        "VEHICULO": {
            "sicetac": vehiculo_sicetac,
            "estadisticas": vehiculo_stats
        }
    }

    # -------------------------
    # 5) Estadísticas y Contexto (SEPARADOS)
    # -------------------------
    if estadistica_activado(data.estadistica):
        # 1) ESTADISTICAS (consolidados por ruta)
        try:
            respuesta["ESTADISTICAS"] = obtener_estadisticas_completas(
                cod_origen,
                cod_destino
            )
        except Exception as e:
            logger.exception("Fallo en estadisticas_helper")
            respuesta["ESTADISTICAS"] = {
                "warning": "No se pudieron generar estadísticas",
                "error": str(e)
            }

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
            respuesta["CONTEXTO"] = {
                "warning": "No se pudo generar contexto",
                "error": str(e),
                "vehiculo_stats": vehiculo_stats
            }

    return JSONResponse(content=respuesta)


# ✅ Render health-check puede usar HEAD / (evita 405)
@app.head("/")
def head_root():
    return Response(status_code=200)


@app.get("/")
def root():
    return {"message": "API SICETAC", "version": "2.1.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.1.0"}
