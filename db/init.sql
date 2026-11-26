CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    documento   TEXT NOT NULL,
    titulo      TEXT,
    capitulo    TEXT,
    articulo    TEXT,
    chunk_index INT  NOT NULL DEFAULT 0,
    contenido   TEXT NOT NULL,
    embedding   vector(768) NOT NULL,
    UNIQUE (documento, articulo, chunk_index)
);