# main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

# Inicializar FastAPI
app = FastAPI(title="API SICETAC", version="1.0")

# Clase para definir el input esperado
class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str
    mes: str
    carroceria: str = None
    valor_peaje_manual: float = 0.0
    horas_logisticas: float = None

# Cargar todos los archivos una sola vez
ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx"
}

# Dataframes cargados
df_municipios = pd.read_excel(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])

# Inicializar ayudante
helper = SICETACHelper(ARCHIVOS["municipios"], ARCHIVOS["vehiculos"])

@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    # Validar municipios y ruta
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    # Buscar ruta oficial en tabla
    ruta = df_rutas[
        (df_rutas["COD_DANE_ORIGEN"] == origen_info["codigo_municipio"]) &
        (df_rutas["COD_DANE_DESTINO"] == destino_info["codigo_municipio"])
    ]

    if not ruta.empty:
        fila_ruta = ruta.iloc[0]
        distancias = {
            'KM_PLANO': fila_ruta.get("KM_PLANO", 0),
            'KM_ONDULADO': fila_ruta.get("KM_ONDULADO", 0),
            'KM_MONTAÑOSO': fila_ruta.get("KM_MONTAÑOSO", 0),
            'KM_URBANO': fila_ruta.get("KM_URBANO", 0),
            'KM_DESPAVIMENTADO': fila_ruta.get("KM_DESPAVIMENTADO", 0),
        }
        resultado = calcular_modelo_sicetac_extendido(
            origen=data.origen,
            destino=data.destino,
            configuracion=data.vehiculo,
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
            horas_logisticas=data.horas_logisticas
        )
    else:
        # Si no hay ruta oficial, devuelve error o puede aplicar lógica alternativa
        raise HTTPException(status_code=404, detail="Ruta no oficial. Implementa cálculo alternativo si lo deseas.")

    return resultado
