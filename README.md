# RAG sobre la Constitución Política de Colombia de 1991

Sistema RAG (Retrieval-Augmented Generation) sencillo que responde preguntas en lenguaje natural sobre la Constitución Política de Colombia y **cita los artículos** de donde obtiene la respuesta. Si los fragmentos recuperados no contienen la respuesta, lo dice explícitamente en vez de inventar.

- **Integrantes:** Juan Andres Cardenas, Adrian Reyes, Brayan Camilo Riascos
- **Asignatura / docente:** Inteligencia Artificial - Nicolas Narvaez

**Stack:** PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) · embeddings `gemini-embedding-001` (768 dimensiones) · modelo generativo de la API gratuita de Gemini · Python 3.12 · Docker Compose.

## Cómo funciona

```
 PDF de la Constitución
        │  limpieza + fragmentación por artículo        (src/procesar.py)
        ▼
 fragmentos + metadatos (título, capítulo, artículo)
        │  embeddings con Gemini → PostgreSQL/pgvector  (src/ingesta.py)
        ▼
 tabla chunks (texto, metadatos, vector(768))

 Pregunta ──► embedding ──► top-5 por distancia coseno ──► prompt aumentado ──► Gemini ──► respuesta con [Art. N]
              (src/busqueda.py)                            (src/rag.py)        (src/llm.py)
```

## Inicio rápido

**Requisitos:** Docker Desktop (o Docker Engine con Compose v2) **abierto y en ejecución**, y una API key gratuita de [Google AI Studio](https://aistudio.google.com). La clave se crea en un par de minutos y no se incluye en el repositorio por seguridad.

```bash
git clone https://github.com/JuanAnd-coder/rag-constitucion.git
cd rag-constitucion
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
notepad .env # Edita .env y pega tu clave en GEMINI_API_KEY
docker compose run --rm --build app #comando que levanta y ejecuta el sistema.
```

El último es el único comando de despliegue: construye la imagen, levanta PostgreSQL con pgvector, procesa el PDF, genera los embeddings y los guarda (solo trabaja lo que falte), y abre una sesión interactiva de preguntas.

**Tiempos:** la primera vez tarda unos 10 minutos por los límites de la capa gratuita de la API. Mientras corre la ingesta la terminal no muestra texto; para ver el avance, abre otra terminal en la misma carpeta y ejecuta `docker compose logs -f ingesta`. Si se interrumpe, al volver a ejecutar continúa donde quedó. Las siguientes veces arranca en unos segundos: vuelve a leer el PDF pero no llama a la API, porque los vectores quedan guardados en el volumen `pgdata`.

**Salir y detener:** en el chat, presiona Enter con la pregunta vacía. La base de datos sigue corriendo en segundo plano; para detenerla usa `docker compose down` (conserva los datos).

## Uso

```bash
# Chat interactivo
docker compose run --rm app

# Una sola pregunta, mostrando el texto completo de los fragmentos recuperados
docker compose run --rm app python -m src.rag "¿Qué es la acción de tutela?" --completo

# Solo la búsqueda (sin generar respuesta), comparando las métricas coseno, L2 y producto interno
docker compose run --rm app python -m src.busqueda "¿Qué es la acción de tutela?"

# Conjunto de evaluación (genera data/resultados_eval_<etiqueta>.md)
docker compose run --rm app python -m src.evaluar v3

# Ver qué modelos de Gemini funcionan con tu clave
docker compose run --rm app python -m src.probar_modelos
```

Ejemplo de salida: la respuesta con citas, seguida de los fragmentos recuperados con su distancia coseno (menor = más parecido).

### Consultar la base directamente

```bash
docker compose exec db psql -U rag -d constitucion_rag -c "SELECT count(*) AS fragmentos, count(DISTINCT articulo) AS articulos FROM chunks;"
```

### Empezar de cero

```bash
docker compose down -v      # borra los contenedores Y los datos guardados
```

## Decisiones de diseño

| Decisión | Valor | Justificación |
|---|---|---|
| Fragmentación | Un fragmento por artículo; si supera 1500 caracteres, ventanas de 1500 con solape de 200 | La Constitución es jerárquica y el artículo es la unidad natural para citar. 1500 caracteres (≈350-400 tokens) cubren casi todos los artículos completos; los muy largos mezclan temas en un solo vector y empeoran la búsqueda. El solape (~13 %) evita perder una idea que caiga justo en el corte. |
| Contexto en el vector | Se antepone título y capítulo al texto antes de generar el embedding | Permite que "De los derechos fundamentales" también pese en la búsqueda. |
| Embeddings | `gemini-embedding-001`, 768 dimensiones, `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`, vectores normalizados | 768 es una de las dimensiones recomendadas, ocupa 4 veces menos que 3072 y es suficiente para ~500 fragmentos. |
| Métrica de distancia | Coseno (`<=>`) | Estándar para embeddings de texto. Con vectores normalizados coseno, L2 y producto interno dan el mismo ranking (L2 = √(2 · distancia coseno)); `src/busqueda.py` lo muestra con las tres. |
| Índice | Ninguno (búsqueda exacta) | Son ~500 vectores. HNSW e IVFFlat son aproximados y solo compensan con cientos de miles de vectores; la búsqueda exacta garantiza el mejor resultado. |
| Fragmentos recuperados (k) | 5 | ≈2000 tokens de contexto: alcanza para preguntas que combinan varios artículos sin llenar el prompt de ruido. |
| Prompt | Instrucciones de sistema + fragmentos numerados + pregunta; temperatura 0,2 | Reglas explícitas: responder solo con los fragmentos, citar `[Art. N]`, permitir comparar o sintetizar fragmentos, y abstenerse con una frase fija cuando no hay información útil. |
| Abstención | Decidida por el modelo, no por un umbral de distancia | En la evaluación, las distancias de preguntas con respuesta (0,25–0,36) y sin respuesta (0,34–0,51) se traslapan, así que un umbral fijo no separa bien los casos. |
| Límites de la API | Lotes de 10 fragmentos, pausa de 8 s entre lotes, reintentos con espera creciente (10 s, 20 s, 40 s…) ante errores 429/500/503 y cortes de conexión | Respeta la capa gratuita. La ingesta es reanudable: solo procesa fragmentos nuevos o cambiados y borra los obsoletos. |
| Secretos | La clave está en `.env` (no se sube a Git); `.env.example` es la plantilla | Requisito de seguridad. |

## Evaluación

El conjunto de evaluación (`src/evaluar.py`) tiene **15 preguntas**: directas, combinadas (necesitan varios artículos), sin respuesta en el corpus y difíciles. Los informes completos, con las respuestas, los fragmentos recuperados y la valoración, están en `data/`:

- `resultados_eval_v1.md`: primera versión del prompt.
- `resultados_eval_v2.md`: tras corregir el prompt.

Resumen de la v2 (preguntas con respuesta, n = 11): el artículo esperado quedó en la posición 1 en 11/11; todos los artículos esperados estuvieron en el top-5 en 10/11; abstención correcta en 4/4 preguntas sin respuesta.

**Hallazgos principales**

- **Falso "no hay contexto" (v1):** en la pregunta "¿Cuál es la diferencia entre la acción de tutela y la de cumplimiento?" la recuperación fue perfecta (artículos 86 y 87), pero el modelo se abstuvo porque ningún fragmento compara explícitamente. Era un error de generación, no de búsqueda. Se corrigió permitiendo comparar y sintetizar fragmentos, y se verificó que las abstenciones correctas se mantuvieron.
- **Corpus desactualizado:** a "¿Puede el Presidente ser reelegido?" responde con el texto del PDF (reelección con un límite de dos períodos), que no incluye el Acto Legislativo 2 de 2015, el cual eliminó la reelección. Un RAG es tan actual como su corpus.
- **Cobertura en preguntas vagas:** a "¿Qué pasa si el Presidente comete un delito?" no recuperó los artículos 174 y 175 (juicio en el Senado), por lo que la respuesta es correcta pero incompleta.

## Limitaciones conocidas

- La edición del PDF incluye los actos legislativos hasta 2010 y no incluye las reformas constitucionales posteriores.
- El texto incluye notas editoriales ("Modificado por el Acto Legislativo…") que quedan dentro de los fragmentos.
- Los artículos muy largos se parten por número de caracteres, y un fragmento puede empezar a mitad de un numeral. Una mejora posible es cortar en los límites de numerales.
- El top-k se cuenta en fragmentos, no en artículos distintos: varios fragmentos del mismo artículo pueden ocupar el top-5.
- No hay búsqueda híbrida (palabras clave + vectores) ni reformulación de la pregunta; la búsqueda por número de artículo depende de que el número esté en el texto del fragmento.
- La evaluación es pequeña y las preguntas fueron escritas por el mismo equipo, así que sus métricas son orientativas.

## Privacidad

Con la capa gratuita de la API de Gemini, Google puede usar los datos enviados para mejorar sus servicios (verificar los términos vigentes). Por eso este proyecto solo envía **documentos públicos** (el texto de la Constitución) y las preguntas de prueba.

## Estructura del repositorio

```
├── docker-compose.yml     # PostgreSQL+pgvector, ingesta y aplicación
├── Dockerfile
├── requirements.txt
├── .env.example           # plantilla de variables (copiar a .env)
├── db/init.sql            # activa pgvector y crea la tabla chunks
├── data/
│   ├── constitucion.pdf   # corpus (documento público)
│   ├── resultados_eval_v1.md / resultados_eval_v2.md
│   └── chunks.json        # generado por src/procesar.py (no se versiona)
└── src/
    ├── config.py          # parámetros y variables de entorno
    ├── procesar.py        # PDF → texto limpio → artículos → fragmentos
    ├── embeddings.py      # embeddings de Gemini con reintentos
    ├── ingesta.py         # sincroniza chunks.json con PostgreSQL
    ├── busqueda.py        # búsqueda por similitud con pgvector
    ├── llm.py             # llamada al modelo generativo con reintentos
    ├── rag.py             # pipeline completo (prompt aumentado)
    ├── evaluar.py         # conjunto de evaluación
    ├── modelos.py / probar_modelos.py   # utilidades para elegir el modelo
    └── revisar.py         # utilidad de diagnóstico del texto extraído
```

## Desarrollo local (sin contenedor de aplicación)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d db
python -m src.procesar && python -m src.ingesta
python -m src.rag
```

## Solución de problemas

- **`API key not valid`:** revisa `GEMINI_API_KEY` en `.env` (sin comillas ni espacios) y que no haya una variable de entorno del sistema con el mismo nombre.
- **Error 404 del modelo:** el modelo de `GEMINI_MODEL` no está disponible para tu clave. Ejecuta `docker compose run --rm app python -m src.probar_modelos` y cambia el valor en `.env`.
- **Errores 429 o 503:** son límites o picos de demanda de la capa gratuita. Los scripts reintentan solos. Si la ingesta se detiene con un mensaje de límite agotado, vuelve a ejecutar el comando: continúa donde quedó. Los límites diarios se reinician a la medianoche (hora del Pacífico) y se aplican por proyecto de Google, no por clave; puedes ver tu consumo en [AI Studio](https://aistudio.google.com/rate-limit).
- **`service "ingesta" didn't complete successfully`:** mira el motivo con `docker compose logs ingesta`.
- **Puerto 5432 ocupado** (por ejemplo, si ya tienes PostgreSQL instalado): agrega `POSTGRES_PORT=5433` a tu `.env`. Solo cambia el puerto visible desde tu máquina; la aplicación dentro de Docker no se ve afectada.