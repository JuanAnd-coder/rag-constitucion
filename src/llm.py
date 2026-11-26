"""Llamada al modelo generativo de Gemini, con reintentos ante límites de uso."""
import time

from google.genai import errors, types

import src.config as config

REINTENTOS = 5
ESPERA_INICIAL = 10  # segundos; se duplica en cada reintento


def generar(client, prompt, instrucciones):
    espera = ESPERA_INICIAL
    for intento in range(1, REINTENTOS + 1):
        try:
            resp = client.models.generate_content(
                model=config.GENERATION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.2,  # baja: queremos respuestas fieles al contexto, no creativas
                ),
            )
            return resp.text or "(El modelo no devolvió texto; la respuesta pudo ser bloqueada.)"
        except errors.APIError as e:
            if e.code == 404:
                detalle = str(getattr(e, "message", e))[:200]
                raise SystemExit(
                    f"El modelo '{config.GENERATION_MODEL}' no respondió (404). Detalle: {detalle}\n"
                    "Ejecuta 'python -m src.probar_modelos' para ver cuáles funcionan con tu clave "
                    "y ponlo en GEMINI_MODEL (.env)."
                )
            if e.code in (429, 500, 503) and intento < REINTENTOS:
                print(f"  Error {e.code}: reintento {intento}/{REINTENTOS} en {espera}s")
                time.sleep(espera)
                espera *= 2
            else:
                raise