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
 
 
def embeber(client, textos, tarea="RETRIEVAL_DOCUMENT"):
    """Devuelve una matriz (len(textos), EMBEDDING_DIM) con vectores normalizados.
 
    tarea: "RETRIEVAL_DOCUMENT" para los fragmentos que se guardan,
           "RETRIEVAL_QUERY" para la pregunta del usuario.
    Reintenta con espera creciente si la API responde con límite de uso (429)
    o con un error temporal del servidor (500/503).
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
        except errors.APIError as e:
            if e.code in (429, 500, 503) and intento < REINTENTOS:
                print(f"  Error {e.code}: reintento {intento}/{REINTENTOS} en {espera}s")
                time.sleep(espera)
                espera *= 2
            else:
                raise
 
