"""Paso 5: recuperación de los fragmentos más similares con pgvector.

Probar solo la búsqueda (sin generar respuesta), comparando las 3 métricas:
    python -m src.busqueda "¿Qué es la acción de tutela?"
"""
import sys

import psycopg
from pgvector.psycopg import register_vector

import src.config as config
from src.embeddings import crear_cliente, embeber

# Operadores de pgvector. En los tres, MENOR valor = MÁS parecido.
OPERADORES = {
    "coseno": "<=>",   # distancia coseno (la que usamos)
    "l2": "<->",       # distancia euclidiana
    "ip": "<#>",       # producto interno NEGATIVO
}


def conectar():
    conn = psycopg.connect(**config.DB_CONFIG)
    register_vector(conn)
    return conn


def buscar_por_vector(conn, vector, k=config.TOP_K, metrica="coseno"):
    """Devuelve los k fragmentos más cercanos al vector, con su distancia."""
    op = OPERADORES[metrica]  # sale de un diccionario fijo, no del usuario
    sql = f"""
        SELECT articulo, titulo, capitulo, chunk_index, contenido,
               embedding {op} %(vec)s AS distancia
        FROM chunks
        WHERE documento = %(doc)s
        ORDER BY embedding {op} %(vec)s
        LIMIT %(k)s
    """
    filas = conn.execute(sql, {"vec": vector, "doc": config.DOCUMENTO, "k": k}).fetchall()
    return [
        {
            "articulo": f[0], "titulo": f[1], "capitulo": f[2],
            "chunk_index": f[3], "contenido": f[4], "distancia": float(f[5]),
        }
        for f in filas
    ]


def buscar(conn, client, pregunta, k=config.TOP_K, metrica="coseno"):
    """Convierte la pregunta en vector (tarea RETRIEVAL_QUERY) y busca."""
    vector = embeber(client, [pregunta], tarea="RETRIEVAL_QUERY")[0]
    return buscar_por_vector(conn, vector, k, metrica)


if __name__ == "__main__":
    pregunta = " ".join(sys.argv[1:]) or "¿Qué es la acción de tutela?"
    client = crear_cliente()
    vector = embeber(client, [pregunta], tarea="RETRIEVAL_QUERY")[0]
    print(f"Pregunta: {pregunta}")
    with conectar() as conn:
        for metrica in OPERADORES:
            print(f"\n--- métrica: {metrica} ---")
            for i, r in enumerate(buscar_por_vector(conn, vector, metrica=metrica), 1):
                print(f"{i}. dist={r['distancia']:.4f}  Art. {r['articulo']:<14} {r['titulo'][:50]}")