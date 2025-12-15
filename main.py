from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

# Contexto y estadísticas (solo se usan si contexto = "Sí")
from contexto_helper import (
    obtener_valores_promedio_mercado_por_llave,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_indicador,
    obtener_estadisticas_completas
)

app = FastAPI(title="API SICETAC", version="1.6.0")

# =========================
# MODELO DE ENTRADA
# =========================
class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202512
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    horas_logisticas: float | None = None
    horas_logisticas_personalizadas: float | None = None
    tarifa_standby: float = 150000
    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0
    modo_viaje: str = "CARGADO"
    modo_tiempos_logisticos: bool = False
    contexto: str = "No"   # 🔑 CLAVE


# =========================
# CARGA DE ARCHIVOS BASE
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

# Indicadores cargue / descargue
df_indicadores = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")


# =========================
# UTILIDAD
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
# ENDPOINT PRINCIPAL
# =========================
@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):

    # -------------------------
    # Buscar municipios
    # -------------------------
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]
    vehiculo_upper = data.vehiculo.strip().upper()

    # -------------------------
    # Buscar ruta oficial
    # -------------------------
    ruta_df = df_rutas[
        (df_rutas["codigo_dane_origen"] == cod_origen) &
        (df_rutas["codigo_dane_destino"] == cod_destino)
    ]

    ruta_invertida = False
    if ruta_df.empty:
        ruta_df = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_destino) &
            (df_rutas["codigo_dane_destino"] == cod_origen)
        ]
        ruta_invertida = not ruta_df.empty

    info_ruta_aproximada = None

    if ruta_df.empty:
        if any([
            data.km_plano, data.km_ondulado, data.km_montañoso,
            data.km_urbano, data.km_despavimentado
        ]):
            fila_ruta = None
            distancias = {
                "KM_PLANO": data.km_plano,
                "KM_ONDULADO": data.km_ondulado,
                "KM_MONTAÑOSO": data.km_montañoso,
                "KM_URBANO": data.km_urbano,
                "KM_DESPAVIMENTADO": data.km_despavimentado,
            }
            info_ruta_aproximada = {
                "mensaje": "Ruta no registrada en SICETAC. Se calcula con distancias aproximadas."
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Ruta no registrada y no se proporcionaron distancias manuales"
            )
    else:
        fila_ruta = ruta_df.iloc[0]
        distancias = {
            "KM_PLANO": fila_ruta.get("KM_PLANO", 0),
            "KM_ONDULADO": fila_ruta.get("KM_ONDULADO", 0),
            "KM_MONTAÑOSO": fila_ruta.get("KM_MONTAÑOSO", 0),
            "KM_URBANO": fila_ruta.get("KM_URBANO", 0),
            "KM_DESPAVIMENTADO": fila_ruta.get("KM_DESPAVIMENTADO", 0),
        }

    # -------------------------
    # Cálculo SICETAC
    # -------------------------
    resultado = calcular_modelo_sicetac_extendido(
        origen=data.origen,
        destino=data.destino,
        configuracion=vehiculo_upper,
        serie=data.mes,
        distancias=distancias,
        valor_peaje_manual=data.valor_peaje_manual,
        matriz_parametros=df_parametros,
        matriz_costos_fijos=df_costos_fijos,
        matriz_vehicular=df_vehiculos,
        rutas_df=df_rutas,
        peajes_df=df_peajes,
        carroceria_especial=data.carroceria,
        ruta_oficial=fila_ruta,
        horas_logisticas=data.horas_logisticas_personalizadas,
        modo_viaje=data.modo_viaje
    )

    resultado_convertido = convertir_nativos(resultado)

    # =========================
    # RESPUESTA BASE (SIEMPRE)
    # =========================
    respuesta = {
        "SICETAC": resultado_convertido,
        "MODO_VIAJE": data.modo_viaje.upper(),
        "INFO_RUTA_APROXIMADA": info_ruta_aproximada,
        "HISTORICO_VALOR_MERCADO": obtener_valores_promedio_mercado_por_llave(llave_mercado)
    }

    # =========================
    # CONTEXTO (SOLO SI SE PIDE)
    # =========================
    if data.contexto.strip().lower() == "sí":

        llave_mercado = f"{cod_origen}-{cod_destino}-{vehiculo_upper}"

        respuesta.update({
            "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo_upper),
            "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo_upper),
            "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo_upper),
            "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(
                df_indicadores, cod_origen, vehiculo_upper
            ),
            "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(
                df_indicadores, cod_destino, vehiculo_upper
            ),
            "ESTADISTICAS": obtener_estadisticas_completas(
                origen=data.origen,
                destino=data.destino,
                cod_origen=cod_origen,
                cod_destino=cod_destino
            )
        })

    return JSONResponse(content=respuesta)
