# API SICETAC - Versión Extendida

Esta API expone un modelo de cálculo de costos operativos bajo la metodología SICETAC (Ministerio de Transporte de Colombia), y lo complementa con datos de mercado y operación real derivados del RNDC.

## 🚀 Endpoints

### POST `/consulta`
Calcula el valor del viaje bajo el modelo SICETAC y devuelve contexto adicional de mercado y operación.

#### Body (JSON)
```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "valor_peaje_manual": 0.0,
  "horas_logisticas": null,
  "km_plano": 0,
  "km_ondulado": 0,
  "km_montañoso": 0,
  "km_urbano": 0,
  "km_despavimentado": 0
}
```

#### Respuesta (JSON)
```json
{
  "SICETAC": { ... },
  "VALOR_MERCADO_2025": "$3,050,000",
  "INDICADORES_ORIGEN": {
    "viajes_cargue": 620,
    "viajes_descargue": 410,
    "indice": 1.51
  },
  "INDICADORES_DESTINO": {
    "viajes_cargue": 290,
    "viajes_descargue": 612,
    "indice": 0.47
  },
  "COMPETITIVIDAD": {
    "nivel": "Media",
    "empresas": 14,
    "participacion": 38.2
  }
}
```

---

## 📊 Datos utilizados

| Archivo CSV | Descripción |
|-------------|-------------|
| `VALORES_CONSOLIDADOS_2025.csv` | Valor promedio por ruta y configuración (mercado 2025 consolidado) |
| `indice_cargue_descargue_consolidado_04.csv` | Indicadores de viajes originados/descargados por municipio |
| `competitividad_rutas_2025.csv` | Nivel de concentración empresarial por ruta/configuración |

---

## 💡 Ejemplo de uso (cURL)
```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "origen": "Bogotá",
        "destino": "Medellín",
        "vehiculo": "3S3",
        "mes": 202504
      }'
```

---

## 📦 Requisitos de entorno

- Python 3.9+
- `pandas`, `fastapi`, `uvicorn`, `openpyxl`

Instalación:
```bash
pip install -r requirements.txt
```

Ejecución local:
```bash
uvicorn main:app --reload
```

---

## 📚 Licencia y uso
Esta API fue desarrollada por IMETRICA para el análisis y simulación de costos de transporte terrestre en Colombia, integrando fuentes oficiales y datos de operación real.
