# Del comentario a la acción: documentación técnica

> ### ▶ [Ver el video de presentación del proyecto](https://drive.google.com/file/d/13jAl6B3QxX9jNCTdNayvoRyPstJ2E_jt/view)
> Arquitectura, modelo y métricas, instalación y demostración de la aplicación (unos 20 minutos).

Sistema de análisis de comentarios de evaluación docente en español. Proyecto final de Sistemas Inteligentes de
Sergio Ponce, Andrés Acosta, José David Ruano y Felipe Moncada.

Las cifras completas están en [`docs/resultados.md`](docs/resultados.md) y la arquitectura en
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## Qué hace

Para cada comentario entrega la polaridad (negativo, neutro o positivo) con sus probabilidades, el conjunto de clases
que no puede descartar al 90 % de confianza (predicción conformal), la decisión de clasificarlo solo o enviarlo a
revisión humana, y los aspectos del curso que menciona (9 grupos) con su sentimiento. Con un CSV arma, por curso, un
ranking de qué corregir primero, la lista filtrable de comentarios y un mapa de calor comparativo.

## Cómo probarlo

El modelo entrenado `models/v001` viene en el repositorio.

```bash
# Con Docker
export UID
docker compose up --build -d
bash scripts/smoke_docker.sh          # última línea: SMOKE OK

# Sin Docker
uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m ml.representations --download
.venv/bin/python -m ml.artifact verify v001      # verified=v001
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Abrir http://127.0.0.1:8000: pestaña **Comentario individual** para un texto, **Carga por lotes** con
`Dataset/feedback_curso_universitario.csv` (193 comentarios, unos 30 s) y **Cola de revisión**.

```bash
curl -s -X POST http://127.0.0.1:8000/predict -H 'content-type: application/json' \
  -d '{"text":"El contenido fue interesante, pero el horario de las clases fue muy incómodo."}'
# predicted: negative · conformal_set: [negative, neutral] · decision: review
# aspects: content (neutral), organization_schedule (negative)
```

## Datos

- 618 comentarios en 3 CSV: 205 negativos, 259 neutros y 154 positivos. Diagnóstico completo en
  [`docs/analysis.md`](docs/analysis.md): encabezados repetidos, 9 variantes de etiqueta, textos de plantilla,
  ruido de etiquetas y deriva entre archivos.
- Limpieza en `ml/data.py`: se eliminan encabezados repetidos y BOM, se normalizan las etiquetas a 3 clases y los
  22 nombres de aspecto a 9 grupos. El texto solo se normaliza a Unicode NFC y espacios; tildes, emojis e
  intensificadores se conservan porque llevan sentimiento. El dataset queda versionado por su SHA-256.
- Partición sin fuga (`ml/split.py`): como no hay columna de autor, los comentarios casi idénticos se agrupan por
  plantilla (380 grupos) y cada grupo queda de un solo lado; validación estratificada y agrupada de 5 pliegues.
  494 para entrenar y 124 para probar ([ADR-001](docs/adr/ADR-001-grouped-split-by-template-clusters.md)).

## Modelo

| Paso | Detalle | Código |
|---|---|---|
| Representaciones | TF-IDF, TF-IDF + SVD y embeddings `paraphrase-multilingual-MiniLM-L12-v2` (revisión fijada), ajustadas solo con entrenamiento dentro de un `Pipeline` | `ml/representations.py` |
| Clasificadores | Dummy, regresión logística, SVM lineal, Naive Bayes, Random Forest, Extra Trees, kNN y SGD: 24 candidatos | `ml/selection.py` |
| Ajuste | `GridSearchCV` sobre la validación agrupada, métrica macro-F1 | `ml/selection.py` |
| Elegido | Embeddings + Extra Trees (el mejor con probabilidades, que la parte conformal necesita) | `models/v001/manifest.json` |
| Prueba | Macro-F1 0,733 · accuracy 0,726 · matriz de confusión en [`docs/resultados.md`](docs/resultados.md) | `ml/evaluation.py` |
| Incertidumbre | Conformal cruzado (MAPIE) al 90 %: cobertura medida 0,952; curva de riesgo y cobertura | `ml/conformal.py`, [ADR-002](docs/adr/ADR-002-cross-conformal-and-expected-utility-abstention.md) |
| Decisión | Revisión si el conjunto no es de una clase o si el costo esperado de error supera al de revisión (5 a 1) | `api/domain/decision.py` |
| Aspectos | Multietiqueta TF-IDF + regresión logística, umbral por aspecto; sentimiento por cláusula; macro-F1 0,48 | `ml/aspects.py`, `api/domain/clauses.py` |

## Artefacto y versiones

- `python -m ml.train` ejecuta todo el pipeline y escribe una versión inmutable `models/vNNN/`: el bundle joblib
  (pipeline de polaridad, conformal, aspectos y temas), un manifiesto con métricas, hiperparámetros, semilla, SHA-256
  del dataset y del bundle, versión de Python (3.12.14) y de 9 librerías, y predicciones de control.
- `models/registry.json` guarda el historial: `python -m ml.artifact activate vNNN` y `python -m ml.artifact rollback`
  ([ADR-003](docs/adr/ADR-003-verified-joblib-bundles-with-registry.md)).
- `python -m ml.artifact verify v001` comprueba el hash, las versiones y que el modelo reproduzca sus predicciones de
  control con tolerancia 1e-9.

## Servicio e interfaz

- API FastAPI (`api/`) que nunca entrena: carga la versión activa y responde. `POST /predict` (clase,
  probabilidades, conjunto conformal, decisión, aspectos y palabras influyentes), `POST /predict-batch` (CSV),
  `POST /drift`, `GET /metrics`, `GET /model`, `GET /health`.
- Arquitectura limpia: dominio puro, puertos como protocolos, casos de uso y adaptadores; una prueba revisa que
  ninguna capa importe una que no debe.
- Interfaz web servida por la misma API (`web/`,
  [ADR-004](docs/adr/ADR-004-static-web-ui-served-by-fastapi.md)): comentario individual, carga de CSV con
  explorador por curso, mapa de calor y cola de revisión exportable.
- Entradas inválidas (texto vacío, CSV mal formado, archivo grande) responden con un error controlado; los
  comentarios ambiguos van a revisión (`tests/unit/test_routes.py`, `tests/unit/domain/test_decision.py`).

## Operación

- Latencia (CPU, `docs/benchmark-v001.json`): `/predict` p50 0,52 s; `/predict-batch` de 100 filas p50 5,9 s.
- Deriva: `reference_stats.json` guarda la distribución de longitudes y clases del entrenamiento y la tasa de
  palabras fuera de vocabulario; `/drift` compara un lote nuevo y `/metrics` muestra el último reporte.
- Contenedor (`Dockerfile`, `docker-compose.yml`): imagen Python 3.12.14 fijada por digest, solo dependencias de
  ejecución, embeddings descargados al construir, sin red al ejecutarse, usuario no root, sistema de archivos de solo
  lectura y puerto publicado solo en `127.0.0.1`. Funciona en local; la misma imagen sirve para cualquier plataforma
  de contenedores.
- `bash scripts/verify_clean_env.sh` reconstruye un entorno desde el commit, corre las pruebas y verifica el modelo
  (`CLEAN ENV OK`).

## Seguridad y privacidad

- El modelo solo se deserializa si su SHA-256 coincide con el manifiesto y las versiones de scikit-learn, numpy,
  joblib y MAPIE son las del entrenamiento; se rechazan enlaces simbólicos y rutas fuera de `models/`.
- Anonimización antes de mostrar comentarios: expresiones regulares para correos, teléfonos y documentos, y spaCy
  para nombres propios. Si el anonimizador no carga, el servicio no arranca.
- El servicio no guarda nada, no hace llamadas de red al ejecutarse ni usa LLM, y sus registros no contienen texto de
  comentarios. Las respuestas llevan Content-Security-Policy y otras cabeceras de seguridad.
- La etiqueta es una sugerencia; los casos dudosos los decide una persona en la cola de revisión.
- Reglas completas en [`security-rules.md`](security-rules.md).

## Calidad

| Comando | Resultado |
|---|---|
| `bash scripts/gate.sh` | Formato, lint, `mypy --strict`, pruebas de arquitectura, 814 pruebas unitarias (98 % de cobertura), escaneo de seguridad y auditoría de dependencias → `GATE OK` |
| `.venv/bin/pytest -q -m integration` | 18 pruebas sobre el dataset real y los embeddings |
| `bash scripts/verify_clean_env.sh` | `CLEAN ENV OK` |
| `bash scripts/smoke_docker.sh` | `SMOKE OK` |

El desarrollo se organizó en 31 especificaciones (`specs/`) con criterios de aceptación y pruebas escritas antes del
código, integradas por pull request con revisión.

## Limitaciones conocidas

- Datos sintéticos con plantillas y etiquetas con ruido: los resultados no se trasladan directamente a comentarios
  reales.
- Sin columna de autor: la partición agrupa por plantilla de texto.
- Las etiquetas de aspectos están incompletas, así que sus métricas penalizan algunos aciertos.
- El sistema es conservador: cerca del 70 % del CSV de ejemplo va a revisión (ajustable en `config/app.json`).
- Hay herramientas para validar con dos anotadores y kappa de Cohen (`ml.gold`, `gold/guidelines.md`); las hojas no
  se han etiquetado.

## Mapa del repositorio

| Ruta | Contenido |
|---|---|
| `ml/` | Entrenamiento: limpieza, split, representaciones, selección, conformal, aspectos, temas, artefacto y registro |
| `api/` | Servicio: dominio, puertos, aplicación, adaptadores y rutas |
| `web/`, `web-src/` | Interfaz web y compilación de estilos |
| `models/v001/` | Modelo entrenado, manifiesto, reporte y estadísticas de referencia |
| `Dataset/` | Los 3 CSV |
| `docs/` | Análisis, resultados, contratos, ADR, benchmark y material del curso |
| `specs/` | Las 31 especificaciones |
| `tests/` | Pruebas unitarias, de integración y de arquitectura |
| `scripts/` | Gate, seguridad, benchmark, Docker y entorno limpio |
