from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd
import logging

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio

from mercado_helper import obtener_serie_mercado_rndc, traducir_config_a_analisis

logger = logging.getLogger("api")

# =========================
# APP
# =========================
app = FastAPI(
    title="API SICETAC (ATICA)",
    version="2.1.5",
    description=(
        "API para cálculo de costos SICETAC en Colombia. "
        "Por defecto usa origen+destino (id_ruta solo si se envía explícitamente). "
        "Calcula escenarios 0/2/8 horas logísticas y retorna Mercado RNDC (si está disponible). "
        "Estadísticas y contexto avanzado se dejan fuera por ahora."
    ),
)

# Handler global (para que los 500 digan qué pasó en Render)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("❌ Error no controlado en API")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error interno: {type(exc).__name__}: {str(exc)}"},
    )

# =========================
# INPUT
# =========================
class ConsultaInput(BaseModel):
    # Solo si el usuario lo da explícitamente se usa.
    id_ruta: str | None = None

    origen: str | None = None
    destino: str | None = None

    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

    modo_viaje: str = "CARGADO"  # CARGADO | VACIO


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

# Cargar matrices SICETAC (core)
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])


# =========================
# UTILS
# =========================
def _clean_optional_str(x: str | None) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"null", "none", "nan"}:
        return None
    return s

def _norm_modo_viaje(x: str | None) -> str:
    if x is None:
        return "CARGADO"
    s = str(x).strip().upper()
    return "VACIO" if s in {"VACIO", "VACÍO"} else "CARGADO"

def convertir_nativos(obj):
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

def _sum_km(dist_dict: dict) -> float:
    return float(
        (dist_dict.get("km_plano") or 0)
        + (dist_dict.get("km_ondulado") or 0)
        + (dist_dict.get("km_montañoso") or 0)
        + (dist_dict.get("km_urbano") or 0)
        + (dist_dict.get("km_despavimentado") or 0)
    )

def _safe_total_viaje(res: dict) -> float | None:
    if not isinstance(res, dict):
        return None
    for k in ["total_viaje", "total_viaje_vacio", "TOTAL_VIAJE", "TOTAL_VIAJE_VACIO"]:
        if k in res and res[k] is not None:
            try:
                return float(res[k])
            except Exception:
                return None
    return None

def _build_info_ruta_uniforme(
    *,
    metodo_busqueda: str,
    ruta_id_usada: str | None,
    id_principal: str | None,
    ids_alternativos: list[str],
    distancias: dict,
    mensaje: str,
    recomendacion: str | None,
) -> dict:
    return {
        "metodo_busqueda": metodo_busqueda,  # "por_origen_destino" | "directo_por_id"
        "ruta_id_usada": ruta_id_usada,
        "id_principal": id_principal,
        "ids_alternativos": ids_alternativos,
        "distancias": {**distancias, "km_total": _sum_km(distancias)},
        "mensaje": mensaje,
        "recomendacion": recomendacion,
    }


# =========================
# ENDPOINTS
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

    # Requiere que SICETACHelper tenga buscar_todas_las_rutas(...)
    lista_rutas, info = helper.buscar_todas_las_rutas(origen, destino, df_rutas)
    if not lista_rutas:
        raise HTTPException(status_code=404, detail=info.get("mensaje", "No se encontraron rutas"))

    return JSONResponse(
        content={
            "origen": info.get("origen_nombre"),
            "destino": info.get("destino_nombre"),
            "codigo_origen": info.get("origen_codigo"),
            "codigo_destino": info.get("destino_codigo"),
            "total_rutas": info.get("total_rutas"),
            "id_principal": info.get("id_principal"),
            "ids_alternativos": info.get("ids_alternativos", []),
            "rutas": lista_rutas,
        }
    )


@app.get("/ruta/{id_ruta}")
def obtener_ruta_por_id(id_ruta: str):
    id_ruta = _clean_optional_str(id_ruta)
    if not id_ruta:
        raise HTTPException(status_code=400, detail="id_ruta inválido.")

    fila_ruta, info = helper.buscar_ruta_por_id(id_ruta, df_rutas)
    if fila_ruta is None:
        raise HTTPException(status_code=404, detail=info.get("error", "Ruta no encontrada"))

    dist = {
        "km_plano": float(fila_ruta.get("KM_PLANO", 0) or 0),
        "km_ondulado": float(fila_ruta.get("KM_ONDULADO", 0) or 0),
        "km_montañoso": float(fila_ruta.get("KM_MONTAÑOSO", 0) or 0),
        "km_urbano": float(fila_ruta.get("KM_URBANO", 0) or 0),
        "km_despavimentado": float(fila_ruta.get("KM_DESPAVIMENTADO", 0) or 0),
    }

    return JSONResponse(
        content={
            "id_ruta": info.get("id_sice"),
            "origen": info.get("origen"),
            "destino": info.get("destino"),
            "ruta": info.get("ruta"),
            "via": info.get("via"),
            "nombre_sice": info.get("nombre_sice"),
            "km_total": _sum_km(dist),
            "distancias": dist,
        }
    )


@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    id_ruta = _clean_optional_str(data.id_ruta)
    origen = _clean_optional_str(data.origen)
    destino = _clean_optional_str(data.destino)

    modo_viaje = _norm_modo_viaje(data.modo_viaje)
    if modo_viaje not in {"CARGADO", "VACIO"}:
        raise HTTPException(status_code=400, detail="modo_viaje inválido. Use 'CARGADO' o 'VACIO'.")

    vehiculo_sicetac = (_clean_optional_str(data.vehiculo) or "C3S3").strip().upper().replace(" ", "")
    vehiculo_stats = traducir_config_a_analisis(vehiculo_sicetac)

    # 1) Resolver ruta
    fila_ruta = None
    info_ruta = {}

    if id_ruta:
        fila_ruta, info_ruta = helper.buscar_ruta_por_id(id_ruta, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró la ruta por ID"))
        metodo_busqueda = "directo_por_id"
    else:
        if not origen or not destino:
            raise HTTPException(status_code=400, detail="Debe enviar 'origen' y 'destino' o un 'id_ruta' válido.")
        fila_ruta, info_ruta = helper.buscar_ruta(origen, destino, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=info_ruta.get("error", "No se encontró ruta para origen/destino"))
        metodo_busqueda = "por_origen_destino"

    # 2) Códigos DANE
    cod_origen_raw = info_ruta.get("origen") or info_ruta.get("origen_codigo")
    cod_destino_raw = info_ruta.get("destino") or info_ruta.get("destino_codigo")
    if cod_origen_raw is None or cod_destino_raw is None:
        raise HTTPException(status_code=500, detail="No se pudieron resolver códigos DANE de origen/destino desde la ruta.")

    cod_origen = int(cod_origen_raw)
    cod_destino = int(cod_destino_raw)

    # 3) Distancias (ruta + overrides manuales si >0)
    distancias_modelo = {
        "KM_PLANO": float(data.km_plano or 0) if float(data.km_plano or 0) > 0 else float(fila_ruta.get("KM_PLANO", 0) or 0),
        "KM_ONDULADO": float(data.km_ondulado or 0) if float(data.km_ondulado or 0) > 0 else float(fila_ruta.get("KM_ONDULADO", 0) or 0),
        "KM_MONTAÑOSO": float(data.km_montañoso or 0) if float(data.km_montañoso or 0) > 0 else float(fila_ruta.get("KM_MONTAÑOSO", 0) or 0),
        "KM_URBANO": float(data.km_urbano or 0) if float(data.km_urbano or 0) > 0 else float(fila_ruta.get("KM_URBANO", 0) or 0),
        "KM_DESPAVIMENTADO": float(data.km_despavimentado or 0) if float(data.km_despavimentado or 0) > 0 else float(fila_ruta.get("KM_DESPAVIMENTADO", 0) or 0),
    }

    dist_respuesta = {
        "km_plano": float(distancias_modelo["KM_PLANO"]),
        "km_ondulado": float(distancias_modelo["KM_ONDULADO"]),
        "km_montañoso": float(distancias_modelo["KM_MONTAÑOSO"]),
        "km_urbano": float(distancias_modelo["KM_URBANO"]),
        "km_despavimentado": float(distancias_modelo["KM_DESPAVIMENTADO"]),
    }

    # 4) Calcular escenarios 0/2/8 horas
    escenarios = {"0_horas": 0, "2_horas": 2, "8_horas": 8}
    resultados_escenarios: dict = {}

    for nombre, horas in escenarios.items():
        if modo_viaje == "VACIO":
            res = calcular_modelo_sicetac_extendido_vacio(
                origen=origen,
                destino=destino,
                configuracion=vehiculo_sicetac,
                serie=data.mes,
                distancias=distancias_modelo,
                valor_peaje_manual=float(data.valor_peaje_manual or 0),
                matriz_parametros=df_parametros,
                matriz_costos_fijos=df_costos_fijos,
                matriz_vehicular=df_vehiculos,
                rutas_df=df_rutas,
                peajes_df=df_peajes,
                carroceria_especial=data.carroceria,
                ruta_oficial=fila_ruta,
                horas_logisticas=horas,
            )
        else:
            res = calcular_modelo_sicetac_extendido(
                origen=origen,
                destino=destino,
                configuracion=vehiculo_sicetac,
                serie=data.mes,
                distancias=distancias_modelo,
                valor_peaje_manual=float(data.valor_peaje_manual or 0),
                matriz_parametros=df_parametros,
                matriz_costos_fijos=df_costos_fijos,
                matriz_vehicular=df_vehiculos,
                rutas_df=df_rutas,
                peajes_df=df_peajes,
                carroceria_especial=data.carroceria,
                ruta_oficial=fila_ruta,
                horas_logisticas=horas,
            )

        resultados_escenarios[nombre] = convertir_nativos(res)

    t0 = _safe_total_viaje(resultados_escenarios.get("0_horas", {}))
    t2 = _safe_total_viaje(resultados_escenarios.get("2_horas", {}))
    t8 = _safe_total_viaje(resultados_escenarios.get("8_horas", {}))

    comparativo = {
        "total_0_horas": t0,
        "total_2_horas": t2,
        "total_8_horas": t8,
        "delta_0_a_2": (t2 - t0) if (t0 is not None and t2 is not None) else None,
        "delta_2_a_8": (t8 - t2) if (t8 is not None and t2 is not None) else None,
        "delta_0_a_8": (t8 - t0) if (t0 is not None and t8 is not None) else None,
    }

    # Principal por compatibilidad: el escenario 2 horas
    sicetac_principal = resultados_escenarios.get("2_horas") or resultados_escenarios.get("0_horas")

    # 5) Mercado RNDC (NO puede tumbar SICETAC)
    valor_mercado = obtener_serie_mercado_rndc(cod_origen, cod_destino, vehiculo_sicetac)

    # 6) INFO_RUTA (mensaje simple)
    ruta_id_usada = id_ruta if metodo_busqueda == "directo_por_id" else info_ruta.get("id_principal")
    ids_alternativos = info_ruta.get("ids_alternativos", []) if isinstance(info_ruta.get("ids_alternativos", []), list) else []
    id_principal = info_ruta.get("id_principal")

    if metodo_busqueda == "directo_por_id":
        mensaje = f"Se usó la ruta solicitada por ID ({id_ruta})."
        recomendacion = None
    else:
        if ids_alternativos:
            mensaje = f"Se usó la vía principal (ID {id_principal}). Hay {len(ids_alternativos)} rutas alternativas disponibles."
            recomendacion = "Si deseas forzar una vía específica, envía id_ruta en /consulta."
        else:
            mensaje = f"Se usó la vía principal (ID {id_principal})."
            recomendacion = None

    info_ruta_uniforme = _build_info_ruta_uniforme(
        metodo_busqueda=metodo_busqueda,
        ruta_id_usada=str(ruta_id_usada) if ruta_id_usada is not None else None,
        id_principal=str(id_principal) if id_principal is not None else None,
        ids_alternativos=[str(x) for x in ids_alternativos],
        distancias=dist_respuesta,
        mensaje=mensaje,
        recomendacion=recomendacion,
    )

    return JSONResponse(
        content={
            "SICETAC": sicetac_principal,
            "SICETAC_ESCENARIOS": resultados_escenarios,
            "COMPARATIVO_HORAS": comparativo,
            "MODO_VIAJE": modo_viaje,
            "INFO_RUTA": info_ruta_uniforme,
            "VALOR_MERCADO_RNDC": valor_mercado,  # ✅ si no hay, []
            "CODIGOS": {"origen": cod_origen, "destino": cod_destino},
            "VEHICULO": {"sicetac": vehiculo_sicetac, "analisis": vehiculo_stats},
        }
    )


# =========================
# HEALTH (Render)
# =========================
@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/")
def root():
    return {"message": "API SICETAC", "version": "2.1.5"}

@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.1.5"}
