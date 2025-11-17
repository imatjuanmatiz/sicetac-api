import type { NextApiRequest, NextApiResponse } from "next";
import OpenAI from "openai";

// Requiere en Vercel/Local:
// OPENAI_API_KEY=
// ATICA_FASTAPI_URL=https://sicetac-api.onrender.com
// ATICA_FASTAPI_TOKEN=

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

// Prompt de sistema (resumen del comportamiento de ATICA)
const SYSTEM_PROMPT = `
Tu nombre es ATICA. Eres un asistente especializado en transporte de carga por carretera en Colombia.
Calculas costos de viajes usando la API SICETAC (Imétrica) con parámetros oficiales.
Valores por defecto si faltan datos: vehiculo=C3S3, carroceria=GENERAL, modo_viaje=CARGADO, mes=202510.
Devuelve SIEMPRE un JSON con: costo_total, moneda, desglose {combustible, peajes, costo_fijo_general, otros}.
No expongas URLs internas ni repos privados; usa "base de contexto imetrica" como fuente genérica.
` as const;

// Esquema de salida fijo (Structured Outputs)
const structuredSchema = {
  type: "object",
  properties: {
    costo_total: { type: "number" },
    moneda: { type: "string" },
    desglose: {
      type: "object",
      properties: {
        combustible: { type: "number" },
        peajes: { type: "number" },
        costo_fijo_general: { type: "number" },
        otros: { type: "number" }
      },
      required: ["combustible", "peajes", "costo_fijo_general"]
    }
  },
  required: ["costo_total", "moneda", "desglose"]
} as const;

// 1 tool mínima: pedir costo a tu FastAPI
const tools = [
  {
    type: "function",
    name: "get_sicetac_cost",
    description: "Calcula el costo para una ruta y vehículo usando el backend FastAPI de ATICA.",
    parameters: {
      type: "object",
      properties: {
        origen: { type: "string", description: "Municipio origen" },
        destino: { type: "string", description: "Municipio destino" },
        vehiculo: { type: "string", description: "Ej. C3S3" },
        mes: { type: "number", description: "YYYYMM, ej. 202510 (número)" },
        carroceria: { type: "string", description: "Ej. GENERAL" },
        valor_peaje_manual: { type: "number" },
        horas_logisticas: { type: "number" },
        km_plano: { type: "number" },
        km_ondulado: { type: "number" },
        km_montañoso: { type: "number" },
        km_urbano: { type: "number" },
        km_despavimentado: { type: "number" },
        modo_viaje: { type: "string", enum: ["CARGADO", "VACIO"] }
      },
      required: ["origen", "destino"]
    }
  }
] as const;


async function callFastAPI(args: any) {
  const base = process.env.ATICA_FASTAPI_URL;
  if (!base) throw new Error("ATICA_FASTAPI_URL no configurado");
const url = `${base}/consulta`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(process.env.ATICA_FASTAPI_TOKEN
        ? { Authorization: `Bearer ${process.env.ATICA_FASTAPI_TOKEN}` }
        : {})
    },
    body: JSON.stringify(args)
  });
  if (!res.ok) throw new Error(`FastAPI error ${res.status}`);
  return await res.json();
}

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  try {
    const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const pregunta: string = body.pregunta || "";

    // 1) Primer run: el modelo decide si necesita la tool
    let run = await client.responses.create({
      model: "gpt-4o-mini",
      input: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: pregunta }
      ],
      tools,
      response_format: { type: "json_schema", json_schema: { name: "atica_output", schema: structuredSchema, strict: true } }
    });

    // 2) Si pidió la tool, la ejecutamos y cerramos el ciclo
    const toolCalls = run.output?.filter(p => p.type === "tool_call") || [];
    if (toolCalls.length > 0) {
      const tool_outputs: Array<{ tool_call_id: string; output: string }> = [];
      for (const tc of toolCalls) {
        if (tc.type !== "tool_call" || tc.name !== "get_sicetac_cost") continue;
        const args = JSON.parse(tc.arguments ?? "{}");
        const apiResult = await callFastAPI({
          // Rellenamos defaults si faltan
          vehiculo: "C3S3",
          carroceria: "GENERAL",
          modo_viaje: "CARGADO",
          mes: "202510",
          ...args
        });
        tool_outputs.push({ tool_call_id: tc.id!, output: JSON.stringify(apiResult) });
      }

      run = await client.responses.create({
        model: "gpt-4o-mini",
        input: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: pregunta }
        ],
        tools,
        tool_choice: "none",
        tool_outputs,
        response_format: { type: "json_schema", json_schema: { name: "atica_output", schema: structuredSchema, strict: true } }
      });
    }

    // 3) Devolvemos el JSON estructurado
    const out = run.output?.find(p => p.type === "output_text");
    const payload = out ? JSON.parse(out.text ?? "{}") : {};
    return res.status(200).json(payload);
  } catch (err: any) {
    console.error(err);
    return res.status(500).json({ error: err.message ?? "Error" });
  }
}
