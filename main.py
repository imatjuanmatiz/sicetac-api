# main.py
from __future__ import annotations

import logging

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio
from contexto_helper import obtener_valores_promedio_mercado_por_llave

# Importación robusta del set_modo_viaje (si existe)
try:
    from contexto_helper import set_modo_viaje
except ImportError:
    def set_modo_viaje(_):
        return None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="API SICETAC LIGHT", version="1.1")


class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    # Campos legacy (no usados en light para horas): siempre 0,2,8
    horas_logisticas: float | None = None
    horas_logisticas_personalizadas: float | None = None
    tarifa_standby: float = 150000.0

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0
    modo_viaje: str = "CARGADO"  # "CARGADO" | "VACIO"

    modo_tiempos_logisticos: bool = False  # ignorado en versión light


ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx",
}

# Carga fija
helper = SICETACHelper(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])


def convertir_nativos(d):
    if isinstance(d, dict):
        return {k: convertir_nativos(v) for k, v in d.items()}
    if isinstance(d, list):
        return [convertir_nativos(v) for v in d]
    if hasattr(d, "item"):
        try:
            return d.item()
        except Exception:
            return d
    return d


def inferir_distancia_total(resultado: dict | None) -> float | None:
    if not resultado:
        return None
    # Busca claves con "dist" y "km"
    for key in resultado.keys():
        kl = str(key).lower()
        if "dist" in kl and "km" in kl:
            try:
                return float(resultado[key])
            except Exception:
                continue
    # fallback por nombres comunes
    for nombre in ["distancia_total_km", "dist_total_km", "km_totales"]:
        if nombre in resultado:
            try:
                return float(resultado[nombre])
            except Exception:
                pass
    return None


def inferir_total_peajes(resultado: dict | None) -> float | None:
    if not resultado:
        return None
    for key in resultado.keys():
        kl = str(key).lower()
        if "peaje" in kl and ("total" in kl or "costo" in kl):
            try:
                return float(resultado[key])
            except Exception:
                continue
    for nombre in ["total_peajes", "costo_peajes"]:
        if nombre in resultado:
            try:
                return float(resultado[nombre])
            except Exception:
                pass
    return None


def extraer_total_viaje(resultado: dict | None) -> float | None:
    if not resultado:
        return None
    if "total_viaje" in resultado:
        try:
            return float(resultado["total_viaje"])
        except Exception:
            return None
    if "total_viaje_vacio" in resultado:
        try:
            return float(resultado["total_viaje_vacio"])
        except Exception:
            return None
    return None


def _vehiculo_analisis_sin_c(v: str) -> str:
    # Para llaves mercado: config sin 'C' (ej: C3S3 -> 3S3)
    return str(v).strip().upper().replace(" ", "").replace("C", "")


def _calcular_sicetac_base(data: ConsultaInput, horas_logisticas_modelo: float):
    # Buscar municipios
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]

    # Buscar ruta (aprox)
    fila_ruta, info_aprox = helper.buscar_ruta_con_aproximacion(
        data.origen,
        data.destino,
        df_rutas,
    )

    if fila_ruta is None:
        # Ruta no encontrada: usar distancias manuales si las hay
        if any([data.km_plano, data.km_ondulado, data.km_montañoso, data.km_urbano, data.km_despavimentado]):
            distancias = {
                "KM_PLANO": data.km_plano,
                "KM_ONDULADO": data.km_ondulado,
                "KM_MONTAÑOSO": data.km_montañoso,
                "KM_URBANO": data.km_urbano,
                "KM_DESPAVIMENTADO": data.km_despavimentado,
            }
        else:
            motivo = (info_aprox.get("motivo", "") if isinstance(info_aprox, dict) else "")
            raise HTTPException(
                status_code=404,
                detail=("Ruta no registrada en SICETAC y sin distancias manuales. " f"Detalle: {motivo}"),
            )
    else:
        distancias = {
            "KM_PLANO": fila_ruta.get("KM_PLANO", 0),
            "KM_ONDULADO": fila_ruta.get("KM_ONDULADO", 0),
            "KM_MONTAÑOSO": fila_ruta.get("KM_MONTAÑOSO", 0),
            "KM_URBANO": fila_ruta.get("KM_URBANO", 0),
            "KM_DESPAVIMENTADO": fila_ruta.get("KM_DESPAVIMENTADO", 0),
        }

    # Validar vehículo y mes
    vehiculo_upper = _vehiculo_analisis_sin_c(data.vehiculo)
    vehiculos_validos = (
        df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().str.replace(" ", "").str.replace("C", "").unique()
    )
    if vehiculo_upper not in vehiculos_validos:
        raise HTTPException(
            status_code=400,
            detail=(f"Vehículo '{data.vehiculo}' no encontrado. Opciones válidas: {', '.join(vehiculos_validos)}"),
        )

    meses_validos = df_parametros["MES"].unique().tolist()
    if int(data.mes) not in meses_validos:
        raise HTTPException(status_code=400, detail=f"Mes '{data.mes}' no válido. Debe ser uno de: {meses_validos}")

    set_modo_viaje(data.modo_viaje)

    # Ejecutar el modelo
    if str(data.modo_viaje).strip().upper() in {"VACIO", "VACÍO"}:
        resultado = calcular_modelo_sicetac_extendido_vacio(
            origen=data.origen,
            destino=data.destino,
            configuracion=data.vehiculo,
            serie=int(data.mes),
            distancias=distancias,
            valor_peaje_manual=data.valor_peaje_manual,
            matriz_parametros=df_parametros,
            matriz_costos_fijos=df_costos_fijos,
            matriz_vehicular=df_vehiculos,
            rutas_df=df_rutas,
            peajes_df=df_peajes,
            carroceria_especial=data.carroceria,
            ruta_oficial=fila_ruta,
            horas_logisticas=horas_logisticas_modelo,
        )
    else:
        resultado = calcular_modelo_sicetac_extendido(
            origen=data.origen,
            destino=data.destino,
            configuracion=data.vehiculo,
            serie=int(data.mes),
            distancias=distancias,
            valor_peaje_manual=data.valor_peaje_manual,
            matriz_parametros=df_parametros,
            matriz_costos_fijos=df_costos_fijos,
            matriz_vehicular=df_vehiculos,
            rutas_df=df_rutas,
            peajes_df=df_peajes,
            carroceria_especial=data.carroceria,
            ruta_oficial=fila_ruta,
            horas_logisticas=horas_logisticas_modelo,
        )

    # Normalizar total_viaje si viene como total_viaje_vacio
    if isinstance(resultado, dict) and "total_viaje" not in resultado and "total_viaje_vacio" in resultado:
        resultado["total_viaje"] = resultado["total_viaje_vacio"]

    return {
        "resultado": resultado,
        "cod_origen": cod_origen,
        "cod_destino": cod_destino,
        "origen_info": origen_info,
        "destino_info": destino_info,
    }


@app.post("/consulta")
def calcular_sicetac_light(data: ConsultaInput):
    """
    Versión LIGHT:
    - Ejecuta SICETAC con 0h, 2h y 8h de horas_logisticas.
    - Devuelve:
        * distancia total (si se puede inferir)
        * total peajes (si se puede inferir)
        * total del viaje para cada escenario
        * último valor de mercado disponible (si existe)
    """
    try:
        core_0 = _calcular_sicetac_base(data, horas_logisticas_modelo=0.0)
        core_2 = _calcular_sicetac_base(data, horas_logisticas_modelo=2.0)
        core_8 = _calcular_sicetac_base(data, horas_logisticas_modelo=8.0)

        res_0 = core_0["resultado"]
        res_2 = core_2["resultado"]
        res_8 = core_8["resultado"]

        distancia_total = inferir_distancia_total(res_2)
        total_peajes = inferir_total_peajes(res_2)

        origen_info = core_0["origen_info"]
        destino_info = core_0["destino_info"]

        ruta = {
            "origen": origen_info.get("municipio"),
            "destino": destino_info.get("municipio"),
            "distancia_total_km": distancia_total,
            "total_peajes": total_peajes,
        }

        costos = {
            "H0": {"horas_logisticas": 0, "total_viaje": extraer_total_viaje(res_0)},
            "H2": {"horas_logisticas": 2, "total_viaje": extraer_total_viaje(res_2)},
            "H8": {"horas_logisticas": 8, "total_viaje": extraer_total_viaje(res_8)},
        }

        # Mercado (NO puede tumbar el resultado)
        cod_origen = core_0["cod_origen"]
        cod_destino = core_0["cod_destino"]
        vehiculo_upper = _vehiculo_analisis_sin_c(data.vehiculo)
        ruta_config = f"{cod_origen}-{cod_destino}-{vehiculo_upper}"  # ✅ SIEMPRE '-'

        try:
            historico_mercado = obtener_valores_promedio_mercado_por_llave(ruta_config)
        except Exception as e:
            logger.warning(f"⚠️ Mercado falló para {ruta_config}: {e}")
            historico_mercado = []

        mercado_ultimo = None
        if historico_mercado and isinstance(historico_mercado, list):
            mercado_ultimo = convertir_nativos(historico_mercado[-1])

        respuesta = {
            "ruta": convertir_nativos(ruta),
            "costos": convertir_nativos(costos),
            "mercado_ultimo": mercado_ultimo,
        }
        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except Exception as e:
        logger.exception("❌ Error interno en /consulta")
        return JSONResponse(content={"error": str(e)}, status_code=500)


# --- Endpoints útiles para Render ---
@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/")
def root():
    return {"message": "API SICETAC LIGHT", "version": "1.1"}

@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.1"}
