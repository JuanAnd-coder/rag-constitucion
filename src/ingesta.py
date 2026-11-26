"""Paso 4: sincroniza data/chunks.json con la tabla chunks de PostgreSQL.
 
- Fragmentos nuevos o cuyo texto cambió -> se les genera embedding y se guardan.
- Fragmentos que ya no existen en chunks.json -> se borran de la base.
- Fragmentos idénticos a los ya guardados -> se saltan (no gastan cuota de la API).
 
Se puede interrumpir y volver a correr sin problema.
 
Uso (desde la raíz del proyecto):   python -m src.ingesta
"""
import json
import time
 
import psycopg
from pgvector.psycopg import register_vector
 
import src.config as config
from src.embeddings import crear_cliente, embeber
 
BATCH = 10   # fragmentos por llamada a la API (procesar por lotes)
PAUSA = 3    # segundos de espera entre lotes para respetar los límites de la capa gratuita
 
 
def texto_para_embedding(chunk):
    """Texto que se convierte en vector: incluye título y capítulo como contexto."""
    contexto = " | ".join(p for p in (chunk["titulo"], chunk["capitulo"]) if p)
    return f"{contexto}\n{chunk['contenido']}" if contexto else chunk["contenido"]
 
 
SQL_INSERT = """
INSERT INTO chunks (documento, titulo, capitulo, articulo, chunk_index, contenido, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (documento, articulo, chunk_index)
DO UPDATE SET titulo = EXCLUDED.titulo, capitulo = EXCLUDED.capitulo,
              contenido = EXCLUDED.contenido, embedding = EXCLUDED.embedding
"""
 
 
def main():
    chunks = json.loads(config.CHUNKS_PATH.read_text(encoding="utf-8"))
    client = crear_cliente()
 
    with psycopg.connect(**config.DB_CONFIG) as conn:
        register_vector(conn)
 
        # Lo que ya hay en la base: (articulo, chunk_index) -> (titulo, capitulo, contenido)
        en_base = {
            (f[0], f[1]): (f[2], f[3], f[4])
            for f in conn.execute(
                "SELECT articulo, chunk_index, titulo, capitulo, contenido "
                "FROM chunks WHERE documento = %s",
                (config.DOCUMENTO,),
            )
        }
        nuevos = {(c["articulo"], c["chunk_index"]) for c in chunks}
 
        # 1. Borrar lo que ya no existe en chunks.json
        obsoletos = [k for k in en_base if k not in nuevos]
        for articulo, idx in obsoletos:
            conn.execute(
                "DELETE FROM chunks WHERE documento = %s AND articulo = %s AND chunk_index = %s",
                (config.DOCUMENTO, articulo, idx),
            )
        conn.commit()
 
        # 2. Procesar solo lo nuevo o cambiado
        pendientes = [
            c for c in chunks
            if en_base.get((c["articulo"], c["chunk_index"]))
            != (c["titulo"], c["capitulo"], c["contenido"])
        ]
        print(f"En chunks.json: {len(chunks)} | borrados de la base: {len(obsoletos)} "
              f"| por procesar: {len(pendientes)}")
 
        for i in range(0, len(pendientes), BATCH):
            lote = pendientes[i : i + BATCH]
            vectores = embeber(client, [texto_para_embedding(c) for c in lote])
            for c, v in zip(lote, vectores):
                conn.execute(
                    SQL_INSERT,
                    (c["documento"], c["titulo"], c["capitulo"], c["articulo"],
                     c["chunk_index"], c["contenido"], v),
                )
            conn.commit()  # guardamos cada lote: si algo falla, no se pierde lo anterior
            print(f"  {min(i + BATCH, len(pendientes))}/{len(pendientes)} fragmentos guardados")
            time.sleep(PAUSA)
 
    print("Ingesta terminada.")
 
 
if __name__ == "__main__":
    main()
 
