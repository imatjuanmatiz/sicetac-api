tafrom fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

from contexto_helper import (
    obtener_valores_promedio_mercado_por_llave,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_indicador,
    obtener_estadisticas_completas
)

# =========================
# APP
# =========================
app = FastAPI(title="API SICETAC", version="1.7.0")

# =========================
# MODELO INPUT
# =========================
class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202512
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    horas_logisticas_personalizadas: float | None = None
    tarifa_standby: float = 150000

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

    modo_viaje: str = "CARGADO"
    modo_tiempos_logisticos: bool = True

    estadistica: str = "Sí"


# =========================
# NORMALIZAR ESTADISTICAS
# =========================
def estadistica_activado(valor):
    if valor is None:
        return False
    return str(valor).strip().lower().replace("í", "i") in ["si", "sí", "true", "1"]


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
df_indicadores = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")


# =========================
# UTIL
# =========================
def convertir_nativos(obj):
    if isinstance(obj, dict):
        return {k: convertir_nativos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convertir_nativos(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


# =========================
# ENDPOINT
# =========================
@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):

    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]
    vehiculo = data.vehiculo.strip().upper()

    # =========================
    # CALCULO SICETAC (ESCENARIOS)
    # =========================
    resultado = calcular_modelo_sicetac_extendido(
        origen=data.origen,
        destino=data.destino,
        configuracion=vehiculo,
        serie=data.mes,
        valor_peaje_manual=data.valor_peaje_manual,
        matriz_parametros=df_parametros,
        matriz_costos_fijos=df_costos_fijos,
        matriz_vehicular=df_vehiculos,
        rutas_df=df_rutas,
        peajes_df=df_peajes,
        carroceria_especial=data.carroceria,
        horas_logisticas=data.horas_logisticas_personalizadas,
        modo_viaje=data.modo_viaje,
        modo_tiempos_logisticos=data.modo_tiempos_logisticos
    )

    resultado = convertir_nativos(resultado)

    # =========================
    # SICETAC
    # =========================
    llave_mercado = f"{cod_origen}-{cod_destino}-{vehiculo}"
    valor_mercado = obtener_valores_promedio_mercado_por_llave(llave_mercado)

    respuesta = {
        "SICETAC": resultado,
        "MODO_VIAJE": data.modo_viaje,
        "VALOR_MERCADO_RNDC": valor_mercado
    }

    # =========================
    #  ESTADISTICAS
    # =========================
    if estadistica_activado(data.estadistica):

        respuesta.update({
            "ESTADISTICAS": obtener_estadisticas_completas(
                origen=data.origen,
                destino=data.destino,
                cod_origen=cod_origen,
                cod_destino=cod_destino
            )
            "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo),
            "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo),
            "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo),
            "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(
                df_indicadores, cod_origen, vehiculo
            ),
            "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(
                df_indicadores, cod_destino, vehiculo
            ),
            
        })

    return JSONResponse(content=respuesta)
