from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse

import pandas as pd
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio
from contexto_helper import (
    obtener_valores_promedio_mercado_por_llave,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_indicador,
    obtener_bloqueos_ruta_por_id,
)

# Importación robusta del set_modo_viaje (si no está, no rompe)
try:
    from contexto_helper import set_modo_viaje
except ImportError:
    def set_modo_viaje(_):
        return None

app = FastAPI(title="API SICETAC", version="1.5")


class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202512
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    contexto: str = "No"  # ✅ NUEVO CAMPO: por defecto es "No"

    # LEGACY: sigue existiendo para no romper nada
    horas_logisticas: float | None = None  # override "duro" del modelo (antes)

    # NUEVO: tiempo logístico que pide el usuario (cargue/descargue total)
    horas_logisticas_personalizadas: float | None = None

    # NUEVO: tarifa de stand by por hora > 8h (se usa solo si decides usarlo desde el front)
    tarifa_standby: float = 150000.0  # COP por hora de stand by

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0
    modo_viaje: str = "CARGADO"  # "CARGADO" | "VACIO"

    # Modo escenarios de tiempos logísticos (puedes ignorarlo desde ATICA si no lo usas)
    modo_tiempos_logisticos: bool = False  # 0h / 4–8h / personalizado


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
df_indicadores = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")


def convertir_nativos(d):
    if isinstance(d, dict):
        return {k: convertir_nativos(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convertir_nativos(v) for v in d]
    elif hasattr(d, "item"):
        return d.item()
    else:
        return d


@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    try:
        # --- Buscar municipios de origen y destino ---
        origen_info = helper.buscar_municipio(data.origen)
        destino_info = helper.buscar_municipio(data.destino)

        if not origen_info or not destino_info:
            raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

        cod_origen = origen_info["codigo_dane"]
        cod_destino = destino_info["codigo_dane"]

        # --- Buscar ruta (exacta o aproximada con lat/long) ---
        info_ruta_aproximada = None

        fila_ruta, info_aprox = helper.buscar_ruta_con_aproximacion(
            data.origen,
            data.destino,
            df_rutas,
        )

        if fila_ruta is None:
            # No se encontró ni ruta exacta ni aproximada:
            # como último recurso, usar distancias manuales si el usuario las pasó
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
                info_ruta_aproximada = info_aprox
                fila_ruta = None
            else:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Ruta no registrada en SICETAC y no se encontraron "
                        f"aproximaciones razonables. Detalle: {info_aprox.get('motivo', '')}"
                    ),
                )
        else:
            # Tenemos una ruta (directa o aproximada) desde SICETAC
            distancias = {
                "KM_PLANO": fila_ruta.get("KM_PLANO", 0),
                "KM_ONDULADO": fila_ruta.get("KM_ONDULADO", 0),
                "KM_MONTAÑOSO": fila_ruta.get("KM_MONTAÑOSO", 0),
                "KM_URBANO": fila_ruta.get("KM_URBANO", 0),
                "KM_DESPAVIMENTADO": fila_ruta.get("KM_DESPAVIMENTADO", 0),
            }
            info_ruta_aproximada = info_aprox

        # --- Validaciones de vehículo y mes ---
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

        # --- Routing por modo de viaje (CARGADO / VACIO) ---
        set_modo_viaje(data.modo_viaje)

        # Helper interno para ejecutar el modelo correcto
        def _ejecutar_modelo(horas_logisticas_modelo: float | None):
            if data.modo_viaje.upper() == "VACIO":
                return calcular_modelo_sicetac_extendido_vacio(
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
                return calcular_modelo_sicetac_extendido(
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

        # Helper para normalizar el nombre del total en salidas de VACÍO
        def _normalizar_total(res: dict | None):
            if res is None:
                return None
            if "total_viaje" not in res and "total_viaje_vacio" in res:
                res["total_viaje"] = res["total_viaje_vacio"]
            return res

        # =============================
        # 1. Escenarios de tiempos logísticos (si decides usarlos)
        # =============================
        resultado = None
        escenarios_tiempos = None

        if data.modo_tiempos_logisticos:
            # Escenario movilización: 0 horas logísticas
            res_movilizacion = _normalizar_total(_ejecutar_modelo(0))

            # Escenario SICETAC por defecto (2 horas logisticas totales)
            res_sicetac = _normalizar_total(_ejecutar_modelo(None))

            # Escenario personalizado (si el usuario pasó horas_logisticas_personalizadas)
            res_personalizado = None
            if data.horas_logisticas_personalizadas is not None:
                horas_usuario = float(data.horas_logisticas_personalizadas)
                horas_base = min(horas_usuario, 8.0)
                horas_extra = max(horas_usuario - 8.0, 0.0)

                # Ejecuta el modelo con máximo 2h logísticas "normales"
                res_base = _normalizar_total(_ejecutar_modelo(horas_base))
                if res_base is not None:
                    res_personalizado = convertir_nativos(res_base)
                    costo_standby = round(
                        horas_extra * float(data.tarifa_standby), 2
                    )
                    total_viaje = float(res_personalizado.get("total_viaje", 0))
                    res_personalizado.update(
                        {
                            "horas_logisticas_usuario": horas_usuario,
                            "horas_logisticas_base": horas_base,
                            "horas_standby_adicionales": horas_extra,
                            "tarifa_standby": float(data.tarifa_standby),
                            "costo_standby": costo_standby,
                            "total_viaje_ajustado": round(
                                total_viaje + costo_standby, 2
                            ),
                        }
                    )

            escenarios_tiempos = {
                "MOVILIZACION": convertir_nativos(res_movilizacion)
                if res_movilizacion
                else None,
                "SICETAC_DEFECTO": convertir_nativos(res_sicetac)
                if res_sicetac
                else None,
                "PERSONALIZADO": res_personalizado,
            }

            # Por compatibilidad, dejamos como principal el escenario SICETAC por defecto
            resultado = res_sicetac or res_movilizacion or res_personalizado
        else:
            # =============================
            # 2. Comportamiento normal (sin escenarios)
            # =============================
            if data.horas_logisticas_personalizadas is not None:
                # Nuevo comportamiento: tiempo logístico definido por el usuario
                horas_usuario = float(data.horas_logisticas_personalizadas)
                horas_base = min(horas_usuario, 2.0)
                horas_extra = max(horas_usuario - 2.0, 0.0)

                res_base = _normalizar_total(_ejecutar_modelo(horas_base))
                resultado = res_base

                # Si hay horas extra, calculamos stand by
                if resultado is not None and horas_extra > 0:
                    resultado = convertir_nativos(resultado)
                    costo_standby = round(
                        horas_extra * float(data.tarifa_standby), 2
                    )
                    total_viaje = float(resultado.get("total_viaje", 0))
                    resultado.update(
                        {
                            "horas_logisticas_usuario": horas_usuario,
                            "horas_logisticas_base": horas_base,
                            "horas_standby_adicionales": horas_extra,
                            "tarifa_standby": float(data.tarifa_standby),
                            "costo_standby": costo_standby,
                            "total_viaje_ajustado": round(
                                total_viaje + costo_standby, 2
                            ),
                        }
                    )
            else:
                # Legacy: usa la lógica original
                # (horas_logisticas=None => 2 horas; o valor duro si viene en el JSON)
                resultado = _normalizar_total(_ejecutar_modelo(data.horas_logisticas))

        # Normalizar y convertir
        resultado = _normalizar_total(resultado)
        resultado_convertido = (
            convertir_nativos(resultado) if resultado is not None else None
        )

        # Helpers contextuales robustos
        try:
            ruta_config = f"{cod_origen}-{cod_destino}-{data.vehiculo.strip().upper().replace('C', '')}"
            historico_mercado = obtener_valores_promedio_mercado_por_llave(
                ruta_config
            )
        except Exception:
            historico_mercado = None

        try:
            indicadores_origen = obtener_indicadores(cod_origen, vehiculo_upper)
        except Exception:
            indicadores_origen = None

        try:
            indicadores_destino = obtener_indicadores(cod_destino, vehiculo_upper)
        except Exception:
            indicadores_destino = None

        try:
            competitividad = evaluar_competitividad(
                cod_origen, cod_destino, vehiculo_upper
            )
        except Exception:
            competitividad = None

        try:
            meses_indicadores_origen = obtener_meses_disponibles_indicador(
                df_indicadores, cod_origen, vehiculo_upper
            )
        except Exception:
            meses_indicadores_origen = None

        try:
            meses_indicadores_destino = obtener_meses_disponibles_indicador(
                df_indicadores, cod_destino, vehiculo_upper
            )
        except Exception:
            meses_indicadores_destino = None

       # Asegurar que INFO_RUTA_APROXIMADA también esté en tipos nativos (no numpy)
        info_ruta_aproximada_nativa = convertir_nativos(info_ruta_aproximada) if info_ruta_aproximada else None

        respuesta = {
            "SICETAC": resultado_convertido,
            "MODO_VIAJE": data.modo_viaje.upper(),
            "HISTORICO_VALOR_MERCADO": historico_mercado if historico_mercado else [],
            "INDICADORES_ORIGEN": indicadores_origen,
            "INDICADORES_DESTINO": indicadores_destino,
            "COMPETITIVIDAD": competitividad,
            "MESES_INDICADORES_ORIGEN": meses_indicadores_origen,
            "MESES_INDICADORES_DESTINO": meses_indicadores_destino,
            "INFO_RUTA_APROXIMADA": info_ruta_aproximada_nativa,
        }

        if escenarios_tiempos is not None:
            respuesta["MODO_TIEMPOS_LOGISTICOS"] = True
            respuesta["ESCENARIOS_TIEMPOS_LOGISTICOS"] = escenarios_tiempos
   
    # 🧠 Si se solicita contexto estadístico, se agrega
    if data.contexto.strip().lower() == "sí":
        respuesta["ESTADISTICAS"] = obtener_estadisticas_completas(
            origen=data.origen,
            destino=data.destino,
            cod_origen=cod_origen,
            cod_destino=cod_destino
        )
        

        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
