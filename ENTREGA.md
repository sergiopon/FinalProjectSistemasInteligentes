# Entrega final: Del comentario a la acción

Proyecto final de **Sistemas Inteligentes**: clasificación de comentarios de evaluación docente en español.
Integrantes: Sergio Ponce, Andrés Acosta, José David Ruano y Felipe Moncada.

Este documento recorre cada requisito de la guía del curso (`docs/curso/CL12_26102026.pdf`) y dice dónde se cumple
y cómo comprobarlo. Las cifras completas están en [`docs/resultados.md`](docs/resultados.md).

## Qué hace el sistema

Lee comentarios de estudiantes y, para cada uno, entrega la polaridad (negativo, neutro o positivo) con sus
probabilidades, el conjunto de clases que no puede descartar al 90 % de confianza (predicción conformal), la
decisión de clasificarlo solo o enviarlo a revisión humana, y los aspectos del curso que menciona (9 grupos) con su
sentimiento. Con un CSV arma, por curso, un ranking de qué corregir primero, la lista filtrable de comentarios y un
mapa de calor comparativo.

## Cómo probarlo en 5 minutos

El modelo entrenado `models/v001` viene en el repositorio, así que no hace falta entrenar.

```bash
# Opción A: Docker (Linux; necesita Docker con Compose)
export UID
docker compose up --build -d
bash scripts/smoke_docker.sh          # última línea: SMOKE OK
# abrir http://127.0.0.1:8000

# Opción B: entorno local con uv
uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m ml.representations --download
.venv/bin/python -m ml.artifact verify v001      # verified=v001
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

En la página: pestaña **Comentario individual** para un texto, pestaña **Carga por lotes** con
`Dataset/feedback_curso_universitario.csv` (193 comentarios, unos 30 s), y pestaña **Cola de revisión**.

## Parte de IA: los 7 pasos de la guía

| # | Requisito | Cómo se cumple | Evidencia |
|---|---|---|---|
| 1 | Explorar el CSV: columnas, etiquetas, faltantes, duplicados, calidad | Diagnóstico completo: encabezados repetidos, 9 variantes de etiqueta, ruido de etiquetas (~50 % de acuerdo con aspectos), textos de plantilla, deriva entre archivos | `docs/analysis.md` §2 |
| 2 | Definir la tarea y preprocesar (normalización, emojis, intensificadores) | Polaridad en 3 clases + 9 aspectos. Normalización NFC y de espacios; se conservan tildes, emojis e intensificadores a propósito | `ml/data.py`, `docs/resultados.md` (Preprocesamiento) |
| 3 | Split 80/20 estratificado, sin fuga, agrupado por autor | Sin columna de autor: se agrupan comentarios de la misma plantilla (380 grupos) y se usa `StratifiedGroupKFold`. 494 / 124 | `ml/split.py`, `docs/adr/ADR-001-grouped-split-by-template-clusters.md` |
| 4 | Comparar TF-IDF vs. embeddings, ajustados solo con train | TF-IDF, TF-IDF + SVD y embeddings multilingües (revisión fijada), todos dentro de un `Pipeline` | `ml/representations.py`, `ml/selection.py` |
| 5 | Dummy + Regresión logística, SVM lineal, Naive Bayes, Random Forest | Los cinco, más Extra Trees, kNN y SGD: 24 candidatos | `docs/resultados.md` (Selección del modelo) |
| 6 | `Pipeline` + `GridSearchCV`, CV estratificada, selección por macro-F1 | Sí, con validación cruzada agrupada | `ml/selection.py` |
| 7 | Evaluación en test: accuracy, precision, recall, macro-F1, matriz de confusión | Macro-F1 0,733; accuracy 0,726; matriz de confusión incluida | `docs/resultados.md` (Evaluación en prueba), `models/v001/report.json` |

Además: predicción conformal con cobertura medida 0,952 (objetivo 0,90) y curva de riesgo y cobertura
(`ml/conformal.py`, `docs/adr/ADR-002-cross-conformal-and-expected-utility-abstention.md`).

## Productización: los 6 pasos de la guía

| # | Requisito | Cómo se cumple | Cómo comprobarlo |
|---|---|---|---|
| 1 | Seleccionar el mejor modelo y registrar métricas, parámetros y versión del dataset | `manifest.json` guarda modelo, representación, hiperparámetros, métricas, SHA-256 del dataset y semilla | `cat models/v001/manifest.json` |
| 2 | Guardar el `Pipeline` completo con joblib y las versiones de Python y dependencias | `bundle.joblib` con el pipeline de polaridad, el conformal, el de aspectos y el de temas; el manifiesto registra Python 3.12.14 y 9 librerías | `ml/artifact.py` |
| 3 | Cargar en un entorno limpio y probar textos vacíos, errores y comentarios ambiguos | `verify_clean_env.sh` crea un entorno nuevo desde el commit, corre las pruebas y verifica que el modelo reproduzca sus predicciones de control (tolerancia 1e-9). Vacíos y errores dan 422 con mensaje controlado; los ambiguos van a revisión | `bash scripts/verify_clean_env.sh` → `CLEAN ENV OK`; `tests/unit/test_routes.py` |
| 4 | API con FastAPI que devuelva clase y probabilidades | `POST /predict` y `POST /predict-batch` (CSV), además de `/health`, `/model`, `/drift`, `/metrics` | `api/routes.py`; ver ejemplo abajo |
| 5 | Interfaz para un comentario o un CSV | Página web servida por la misma API: comentario individual, carga por lotes con explorador por curso y mapa de calor, cola de revisión con exportación | `web/`, `docs/adr/ADR-004-static-web-ui-served-by-fastapi.md` |
| 6 | Medir tiempos, seguridad y calidad; desplegar; monitorear deriva | Benchmark de latencia; reglas de seguridad verificadas por script; 800+ pruebas; monitoreo con `/drift` y `/metrics`. **Despliegue:** contenerizado y listo; no se publicó en la nube para no generar costos en un proyecto académico | `docs/benchmark-v001.json`, `bash scripts/gate.sh`, `bash scripts/smoke_docker.sh` |

Ejemplo de `/predict`:

```bash
curl -s -X POST http://127.0.0.1:8000/predict -H 'content-type: application/json' \
  -d '{"text":"El contenido fue interesante, pero el horario de las clases fue muy incómodo."}'
# predicted: negative · conformal_set: [negative, neutral] · decision: review
# aspects: content (neutral), organization_schedule (negative)
```

## Despliegue seguro: los 6 puntos de la guía

| # | Requisito | Cómo se cumple |
|---|---|---|
| 1 | Pipeline unificado | Vectorizador o embeddings y clasificador en un solo `Pipeline` dentro del bundle |
| 2 | No reentrenar al iniciar | El servicio solo carga la versión activa; entrenar es un comando aparte (`ml.train`) |
| 3 | Cargar solo joblib de confianza | Antes de `joblib.load` se verifica el SHA-256 del archivo contra el manifiesto; se rechazan enlaces simbólicos y rutas fuera de `models/` (`ml/artifact.py`, `api/adapters/model_store.py`) |
| 4 | Versiones compatibles entre entrenamiento y producción | Versiones exactas en `requirements.txt`; al cargar se comparan scikit-learn, numpy, joblib y MAPIE con el manifiesto y, si difieren, el servicio no arranca |
| 5 | Salida estructurada si hay nueve aspectos | `aspects`: lista de `{group, polarity, score}` con los 9 grupos posibles |
| 6 | Control y reversión de versiones | `models/registry.json` con historial; `python -m ml.artifact activate vNNN` y `python -m ml.artifact rollback` |

## Ética, privacidad y rol de los LLM

- **Anonimización:** antes de mostrar comentarios, expresiones regulares ocultan correos, teléfonos y documentos, y
  spaCy (`es_core_news_sm`) oculta nombres de persona. Solo se enmascaran entidades marcadas como nombre propio, para
  no tapar palabras comunes. Si el anonimizador no carga, el servicio no arranca.
- **Sin almacenamiento ni red:** el servicio procesa en memoria, no guarda nada, no hace llamadas de red al
  ejecutarse y los registros nunca contienen el texto de los comentarios.
- **Decisión humana:** la etiqueta es una sugerencia; los casos dudosos van a la cola de revisión.
- **LLM:** el producto no usa LLM ni envía comentarios a servicios externos.
- Reglas completas: [`security-rules.md`](security-rules.md).

## Lo que pide el video

| Punto | Dónde |
|---|---|
| Desarrollo, arquitectura y tecnologías | [`ARCHITECTURE.md`](ARCHITECTURE.md), `docs/adr/`, [`CONTEXT.md`](CONTEXT.md) |
| Modelo clasificador, métricas e integración | [`docs/resultados.md`](docs/resultados.md), `ml/`, `api/adapters/model_store.py` |
| Instalar, ejecutar y usar | Sección "Cómo probarlo" arriba y [`README.md`](README.md) |
| Subir un CSV o un comentario y ver la clasificación | Interfaz en http://127.0.0.1:8000 |

## Calidad y verificación

| Comando | Resultado esperado |
|---|---|
| `bash scripts/gate.sh` | Formato, lint, `mypy --strict`, pruebas de arquitectura, 814 pruebas unitarias con 98 % de cobertura, escaneo de seguridad y auditoría de dependencias → `GATE OK` |
| `.venv/bin/pytest -q -m integration` | 18 pruebas sobre el dataset real y los embeddings |
| `bash scripts/verify_clean_env.sh` | `CLEAN ENV OK` |
| `bash scripts/smoke_docker.sh` (con el contenedor arriba) | `SMOKE OK` |

Metodología: el sistema se dividió en 31 especificaciones (`specs/`) con criterios de aceptación y pruebas escritas
antes del código, integradas por pull request con revisión.

## Limitaciones y desviaciones declaradas

- **Despliegue:** local y contenerizado, sin servidor público (costos). La imagen Docker está lista para cualquier
  plataforma de contenedores.
- **Agrupación por autor:** el dataset no tiene autor; se agrupa por plantilla de texto.
- **Conjunto de oro:** las herramientas para que dos personas etiqueten y medir el kappa de Cohen existen
  (`ml.gold`, `ml.gold_eval`, `gold/guidelines.md`), pero las hojas no se etiquetaron.
- **Datos sintéticos y etiquetas con ruido:** los resultados no garantizan lo mismo con comentarios reales.
- **Revisión humana alta:** cerca del 70 % del CSV de ejemplo va a revisión, porque el sistema es conservador
  (equivocarse cuesta 5 veces más que revisar). Se ajusta en `config/app.json`.

## Mapa del repositorio

| Ruta | Contenido |
|---|---|
| `ml/` | Entrenamiento: limpieza, split, representaciones, selección, conformal, aspectos, temas, artefacto y registro |
| `api/` | Servicio: dominio, puertos, aplicación, adaptadores y rutas (arquitectura limpia) |
| `web/` | Interfaz web (`web-src/` compila los estilos) |
| `models/v001/` | Modelo entrenado, manifiesto, reporte y estadísticas de referencia |
| `Dataset/` | Los 3 CSV del curso |
| `docs/` | Análisis, resultados, contratos, ADR, benchmark y material del curso |
| `specs/` | Las 31 especificaciones del desarrollo |
| `tests/` | Pruebas unitarias, de integración y de arquitectura |
| `scripts/` | Gate, escaneo de seguridad, benchmark, Docker y entorno limpio |
