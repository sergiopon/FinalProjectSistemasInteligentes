# Resultados del modelo `v001`

Todas las cifras salen de `models/v001/report.json` y `models/v001/manifest.json`, generados por
`.venv/bin/python -m ml.train` el 2026-11-10 con semilla 42. Se pueden comprobar con
`.venv/bin/python -m ml.artifact verify v001`.

## Datos y partición

| Concepto | Valor |
|---|---|
| Comentarios | 618 en 3 archivos CSV (`Dataset/`) |
| Clases | negativo 205 · neutro 259 · positivo 154 |
| Huella del dataset (SHA-256) | `5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666` |
| Grupos de plantilla | 380 (clustering aglomerativo sobre TF-IDF de caracteres 3–5, distancia coseno, umbral 0,7) |
| Entrenamiento / prueba | 494 / 124, sin ningún grupo en ambos lados (`StratifiedGroupKFold`, 5 pliegues) |

El dataset no tiene columna de autor y sus textos salen de plantillas, así que la partición agrupa comentarios casi
idénticos para evitar fuga de información (`docs/adr/ADR-001-grouped-split-by-template-clusters.md`).

## Preprocesamiento

- Se eliminan los encabezados repetidos y la marca BOM de los CSV.
- Las 9 variantes de etiqueta de polaridad se normalizan a 3 clases y los 22 nombres de aspecto a 9 grupos.
- El texto solo se normaliza a Unicode NFC y se colapsan los espacios. Se conservan a propósito mayúsculas,
  tildes, puntuación, emojis e intensificadores ("muy", "bastante", "nada"), porque llevan sentimiento; los
  embeddings y el TF-IDF los aprovechan directamente.

## Selección del modelo

3 representaciones × 8 clasificadores = 24 candidatos. Cada uno con búsqueda de hiperparámetros
(`GridSearchCV`) sobre la validación cruzada agrupada y estratificada, con macro-F1 como métrica.

| Representación | Clasificador | Macro-F1 (CV) | Desv. |
|---|---|---|---|
| Embeddings | SVM lineal | 0,685 | 0,046 |
| **Embeddings** | **Extra Trees** (elegido) | **0,677** | 0,043 |
| Embeddings | Random Forest | 0,677 | 0,040 |
| Embeddings | Regresión logística | 0,675 | 0,050 |
| Embeddings | Naive Bayes | 0,665 | 0,038 |
| Embeddings | SGD (log loss) | 0,658 | 0,036 |
| Embeddings | kNN | 0,656 | 0,052 |
| TF-IDF | Extra Trees | 0,629 | 0,049 |
| TF-IDF | Regresión logística | 0,608 | 0,057 |
| TF-IDF + SVD | SVM lineal | 0,606 | 0,049 |
| TF-IDF | Naive Bayes | 0,605 | 0,057 |
| TF-IDF | SVM lineal | 0,604 | 0,076 |
| TF-IDF | Random Forest | 0,603 | 0,028 |
| TF-IDF | SGD (log loss) | 0,600 | 0,056 |
| TF-IDF + SVD | Regresión logística | 0,588 | 0,063 |
| TF-IDF + SVD | SGD (log loss) | 0,579 | 0,056 |
| TF-IDF + SVD | Random Forest | 0,531 | 0,048 |
| TF-IDF | kNN | 0,527 | 0,042 |
| TF-IDF + SVD | Extra Trees | 0,504 | 0,080 |
| TF-IDF + SVD | Naive Bayes | 0,498 | 0,051 |
| TF-IDF + SVD | kNN | 0,474 | 0,069 |
| Cualquiera | Dummy (clase mayoritaria) | 0,197 | 0,001 |

Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisión
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 dimensiones.

**Por qué Extra Trees y no SVM lineal:** la regla de selección solo admite modelos que entregan probabilidades
(`predict_proba`), porque la predicción conformal y el agente de decisión las necesitan. `LinearSVC` no las entrega;
Extra Trees es el mejor de los que sí (0,67749 frente a 0,67741 de Random Forest).

## Evaluación en prueba (124 comentarios no vistos)

| Métrica | Valor |
|---|---|
| Accuracy | 0,726 |
| Macro-precision | 0,731 |
| Macro-recall | 0,736 |
| **Macro-F1** | **0,733** |

| Clase | Precision | Recall | F1 | Soporte |
|---|---|---|---|---|
| Negativo | 0,711 | 0,780 | 0,744 | 41 |
| Neutro | 0,708 | 0,654 | 0,680 | 52 |
| Positivo | 0,774 | 0,774 | 0,774 | 31 |

Matriz de confusión (filas: clase real; columnas: clase predicha):

| | Negativo | Neutro | Positivo |
|---|---|---|---|
| **Negativo** | 32 | 8 | 1 |
| **Neutro** | 12 | 34 | 6 |
| **Positivo** | 1 | 6 | 24 |

Casi todos los errores son entre una clase extrema y neutro; los cruces negativo↔positivo son 2 de 124.

Macro-F1 por archivo de origen: `feedback_curso_universitario.csv` 0,693 · `feedback_curso_universitario2.csv` 0,707 ·
`feedback_curso_universitario3.csv` 0,222 (muy pocas filas de prueba; indica deriva entre archivos).

Con 124 filas el macro-F1 de prueba tiene varianza; el valor de validación cruzada (0,68) es la estimación más estable.

## Predicción conformal y abstención

MAPIE `CrossConformalClassifier` con nivel de confianza 0,90 (`config/app.json`, `conformal.alpha = 0.1`).

| Métrica | Valor |
|---|---|
| Cobertura empírica en prueba | **0,952** (objetivo 0,90) |
| Tamaño medio del conjunto | 1,76 clases |
| Conjuntos de una sola clase | 25,8 % |
| Conjuntos vacíos | 0 % |

Curva de riesgo y cobertura: si el sistema solo responde en los comentarios donde más confía, el error baja.

| Fracción respondida | Error en esa fracción |
|---|---|
| 25 % | 9,7 % |
| 50 % | 8,1 % |
| 75 % | 21,5 % |
| 100 % | 27,4 % |

Agente de decisión (`api/domain/decision.py`, ADR-002): manda a revisión si el conjunto está vacío, tiene más de
una clase o no contiene la clase más probable; si no, compara el costo esperado de error `(1 − p) × 5` con el costo
de revisión `1`. Solo clasifica solo cuando el conjunto tiene una clase y su probabilidad supera 0,80.

## Aspectos

Modelo multietiqueta: TF-IDF de 1–2 gramas con regresión logística uno contra todos (pesos balanceados). El umbral
de cada aspecto se eligió maximizando F1 sobre predicciones fuera de pliegue. Macro-F1 en prueba: **0,48**.

| Aspecto | Precision | Recall | F1 | Umbral |
|---|---|---|---|---|
| Comunicación y clima | 0,75 | 1,00 | 0,86 | 0,40 |
| Organización y horario | 0,77 | 0,83 | 0,80 | 0,40 |
| Contenido | 0,60 | 1,00 | 0,75 | 0,10 |
| Evaluación | 0,45 | 0,59 | 0,51 | 0,45 |
| Retroalimentación | 0,43 | 0,50 | 0,46 | 0,40 |
| Materiales | 0,28 | 0,41 | 0,33 | 0,40 |
| Ritmo y carga de trabajo | 0,21 | 0,75 | 0,33 | 0,30 |
| Plataforma | 0,14 | 0,33 | 0,20 | 0,40 |
| Metodología y claridad | 0,09 | 0,08 | 0,09 | 0,45 |

El sentimiento de cada aspecto se toma de la cláusula donde el aspecto tiene mayor puntaje (el comentario se divide
por puntuación y por conectores como "pero" o "aunque"). Las etiquetas de aspectos del dataset están incompletas, así
que estas cifras subestiman el modelo (ver `docs/analysis.md` §2).

## Tiempos de inferencia

Medido el 2026-11-27 con `.venv/bin/python -m scripts.benchmark` (CPU, en proceso, sin red; detalle en
`docs/benchmark-v001.json`).

| Ruta | p50 | p95 |
|---|---|---|
| `POST /predict` (un comentario, con explicación por palabras) | 0,52 s | 0,65 s |
| `POST /predict-batch` (100 filas, con anonimización y reporte por curso) | 5,9 s | 7,8 s |

## Monitoreo de deriva

`models/v001/reference_stats.json` guarda la distribución de longitudes y clases del entrenamiento y la tasa de
palabras fuera de vocabulario en prueba (0,589). `POST /drift` compara un CSV nuevo con esa referencia, y
`GET /metrics` muestra latencias, conteos de decisiones y el último reporte de deriva.

## Limitaciones

- Los datos son sintéticos y salen de plantillas; los resultados no se pueden extrapolar a comentarios reales.
- Las etiquetas tienen ruido: la polaridad global coincide con el sentimiento de sus aspectos en cerca del 50 % de
  las filas, y "neutro" suele marcar comentarios mixtos.
- No hay columna de autor: el split agrupa por plantilla, no por persona.
- El conjunto de oro (dos anotadores y kappa de Cohen) tiene herramientas listas (`ml.gold`, `ml.gold_eval`) pero
  no se etiquetó por falta de tiempo; sin él, las métricas se miden contra las etiquetas ruidosas del dataset.
