"""Genera embeddings con la API de Gemini (reutilizado en la ingesta y en las consultas)."""
import time

import numpy as np
from google import genai
from google.genai import errors, types

import src.config as config

REINTENTOS = 6
ESPERA_INICIAL = 10  # segundos; se duplica en cada reintento


def crear_cliente():
    if not config.GEMINI_API_KEY:
        raise SystemExit("Falta GEMINI_API_KEY en el archivo .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def es_error_de_red(e):
    """Cortes de conexión temporales (el servidor cerró la conexión, timeout...)."""
    modulo = type(e).__module__
    return isinstance(e, (ConnectionError, TimeoutError)) or modulo.startswith(("httpx", "httpcore"))


def es_error_temporal(e):
    """Errores que conviene reintentar: límite de uso (429), fallos del servidor y cortes de red."""
    if isinstance(e, errors.APIError):
        return e.code in (429, 500, 503)
    return es_error_de_red(e)


MENSAJE_LIMITE = (
    "Se agotó el límite de uso de la API (error 429) después de varios reintentos.\n"
    "Si es el límite diario, se reinicia a la medianoche (hora del Pacífico); los límites son por\n"
    "proyecto de Google, no por clave. Vuelve a ejecutar: la ingesta continúa donde quedó."
)


def embeber(client, textos, tarea="RETRIEVAL_DOCUMENT"):
    """Devuelve una matriz (len(textos), EMBEDDING_DIM) con vectores normalizados.

    tarea: "RETRIEVAL_DOCUMENT" para los fragmentos que se guardan,
           "RETRIEVAL_QUERY" para la pregunta del usuario.
    Reintenta con espera creciente ante límite de uso (429), errores temporales
    del servidor (500/503) y cortes de conexión.
    """
    espera = ESPERA_INICIAL
    for intento in range(1, REINTENTOS + 1):
        try:
            resp = client.models.embed_content(
                model=config.EMBEDDING_MODEL,
                contents=textos,
                config=types.EmbedContentConfig(
                    task_type=tarea,
                    output_dimensionality=config.EMBEDDING_DIM,
                ),
            )
            vectores = np.array([e.values for e in resp.embeddings], dtype=np.float32)
            # Con dimensiones menores a la original los vectores no vienen
            # normalizados; los normalizamos (con coseno no cambia el ranking).
            vectores /= np.linalg.norm(vectores, axis=1, keepdims=True)
            return vectores
        except Exception as e:
            if es_error_temporal(e) and intento < REINTENTOS:
                motivo = e.code if isinstance(e, errors.APIError) else type(e).__name__
                print(f"  Error {motivo}: reintento {intento}/{REINTENTOS} en {espera}s")
                time.sleep(espera)
                espera *= 2
                continue
            if isinstance(e, errors.APIError) and e.code == 429:
                raise SystemExit(MENSAJE_LIMITE)
            raise