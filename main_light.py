from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse

import pandas as pd
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio
from contexto_helper import obtener_valores_promedio_mercado_por_llave

# Importación robusta del set_modo_viaje
try:
    from contexto_helper import set_modo_viaje
except ImportError:
    def set_modo_viaje(_):
        return None

app = FastAPI(title="API SICETAC LIGHT", version="1.0")


class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    # Campos legacy, pero aquí NO usamos horas del usuario: siempre 0, 2, 8
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

# Carga fija (igual que en el main completo)
helper = SICETACHelper(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])


def convertir_nativos(d):
    if isinstance(d, dict):
        return {k: convertir_nativos(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convertir_nativos(v) for v in d]
    elif hasattr(d, "item"):
        return d.item()
    else:
        return d


# ----------------- Helpers para extraer campos clave -----------------

def inferir_distancia_total(resultado: dict | None) -> float | None:
    """Intenta encontrar la distancia total en km en el resultado SICETAC."""
    if not resultado:
        return None

    # Intenta claves típicas
    for key in resultado.keys():
        kl = key.lower()
        if "dist" in kl and "km" in kl:
            try:
                return float(resultado[key])
            except Exception:
                continue

    # Si tienes el nombre exacto (por ejemplo 'distancia_total_km'), puedes forzarlo:
    for nombre in ["distancia_total_km", "dist_total_km", "km_totales"]:
        if nombre in resultado:
            try:
                return float(resultado[nombre])
            except Exception:
                pass

    return None


def inferir_total_peajes(resultado: dict | None) -> float | None:
    """Intenta encontrar el total de peajes en el resultado SICETAC."""
    if not resultado:
        return None

    for key in resultado.keys():
        kl = key.lower()
        if "peaje" in kl and ("total" in kl or "costo" in kl):
            try:
                return float(resultado[key])
            except Exception:
                continue

    # Si conoces el nombre exacto, ponlo aquí
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


# ----------------- Núcleo de cálculo para una sola corrida -----------------

def _calcular_sicetac_base(data: ConsultaInput, horas_logisticas_modelo: float):
    """
    Ejecuta el modelo SICETAC (cargado o vacío) para un valor dado de horas_logisticas.
    Devuelve el dict completo del modelo y datos básicos de la ruta.
    """
    # Buscar municipios
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]

    # Buscar ruta
    fila_ruta, info_aprox = helper.buscar_ruta_con_aproximacion(
        data.origen,
        data.destino,
        df_rutas,
    )

    if fila_ruta is None:
        # Ruta no encontrada: usar distancias manuales si las hay
        if any(
            [
                data.km_plano,
                data.km_ondulado,
                data.km_montañoso,
                data.km_urbano,
                data.km_despavimentado,
            ]
        ):
            distancias = {
                "KM_PLANO": data.km_plano,
                "KM_ONDULADO": data.km_ondulado,
                "KM_MONTAÑOSO": data.km_montañoso,
                "KM_URBANO": data.km_urbano,
                "KM_DESPAVIMENTADO": data.km_despavimentado,
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Ruta no registrada en SICETAC y sin distancias manuales. "
                    f"Detalle: {info_aprox.get('motivo', '') if info_aprox else ''}"
                ),
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
    vehiculo_upper = data.vehiculo.strip().upper().replace("C", "")
    vehiculos_validos = (
        df_vehiculos["TIPO_VEHICULO"]
        .astype(str)
        .str.upper()
        .str.replace("C", "")
        .unique()
    )
    if vehiculo_upper not in vehiculos_validos:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Vehículo '{data.vehiculo}' no encontrado. "
                f"Opciones válidas: {', '.join(vehiculos_validos)}"
            ),
        )

    meses_validos = df_parametros["MES"].unique().tolist()
    if int(data.mes) not in meses_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Mes '{data.mes}' no válido. Debe ser uno de: {meses_validos}",
        )

    set_modo_viaje(data.modo_viaje)

    # Ejecutar el modelo
    if data.modo_viaje.upper() == "VACIO":
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

    if resultado is not None and "total_viaje" not in resultado and "total_viaje_vacio" in resultado:
        resultado["total_viaje"] = resultado["total_viaje_vacio"]

    return {
        "resultado": resultado,
        "cod_origen": cod_origen,
        "cod_destino": cod_destino,
        "origen_info": origen_info,
        "destino_info": destino_info,
    }


# ----------------- Endpoint LIGHT principal -----------------

@app.post("/consulta")
def calcular_sicetac_light(data: ConsultaInput):
    """
    Versión LIGHT:
    - Ejecuta SICETAC con 0h, 2h y 8h de horas_logisticas.
    - Devuelve:
        * distancia total
        * total de peajes
        * total del viaje para cada escenario
        * último valor de mercado disponible
    """
    try:
        # Tres corridas: 0h, 2h, 8h
        core_0 = _calcular_sicetac_base(data, horas_logisticas_modelo=0.0)
        core_2 = _calcular_sicetac_base(data, horas_logisticas_modelo=2.0)
        core_8 = _calcular_sicetac_base(data, horas_logisticas_modelo=8.0)

        res_0 = core_0["resultado"]
        res_2 = core_2["resultado"]
        res_8 = core_8["resultado"]

        # Distancia y peajes: tomamos los del escenario de 2h (para no usar 0h vacío)
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

        # Costos totales por escenario
        costos = {
            "H0": {
                "horas_logisticas": 0,
                "total_viaje": extraer_total_viaje(res_0),
            },
            "H2": {
                "horas_logisticas": 2,
                "total_viaje": extraer_total_viaje(res_2),
            },
            "H8": {
                "horas_logisticas": 8,
                "total_viaje": extraer_total_viaje(res_8),
            },
        }

        # Último dato de mercado
        cod_origen = core_0["cod_origen"]
        cod_destino = core_0["cod_destino"]
        vehiculo_upper = data.vehiculo.strip().upper().replace("C", "")
        ruta_config = f"{cod_origen}-{cod_destino}-{vehiculo_upper}"

        try:
            historico_mercado = obtener_valores_promedio_mercado_por_llave(
                ruta_config
            )
        except Exception:
            historico_mercado = None

        mercado_ultimo = None
        if historico_mercado:
            # Si es lista, tomamos el último elemento
            if isinstance(historico_mercado, list):
                mercado_ultimo = convertir_nativos(historico_mercado[-1])
            else:
                # Si es dict o algo similar, lo devolvemos completo
                mercado_ultimo = convertir_nativos(historico_mercado)

        respuesta = {
            "ruta": convertir_nativos(ruta),
            "costos": convertir_nativos(costos),
            "mercado_ultimo": mercado_ultimo,
        }

        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
