# Gold-set annotation guidelines

You label student comments about university courses. Your sheet is compared with a second annotator's sheet to
measure how reliable the labels are.

## Independence

- Annotate alone. Never compare, discuss or share sheets before `python -m ml.gold agreement` has run.
- Annotator A fills `gold/sheet_a.csv`. Annotator B fills `gold/sheet_b.csv`.
- Do not edit `gold_id`, `row_key` or `text`, and do not reorder or rename the columns.

## Polarity

Fill `polarity` for every row with one of `negative`, `positive` or `neutral`, judging the whole comment.

- `neutral` means the comment has no evaluation, or praise and criticism of equal weight.
- Never leave `polarity` empty: the tool rejects the sheet.

## Aspects

Each `aspect_<group>` column covers one group of topics.

- Leave the cell empty when the comment does not mention that group.
- Otherwise write the sentiment of that mention: `negative`, `neutral` or `positive`.

| Column | Original labels of the dataset |
|---|---|
| `aspect_content` | `contenidos`, `Contenido y pertinencia`, `cantidad de temasrepaso al inicio del curso` |
| `aspect_assessment` | `parciales`, `dificultad de las preguntas en los parciales`, `Diseño de la evaluación y criterios` |
| `aspect_feedback` | `retroalimentación de los examenes`, `Retroalimentación recibida`, `comentarios del profesor` |
| `aspect_methodology_clarity` | `metodología del profesor`, `Actividades y metodología`, `Claridad de exposición` |
| `aspect_materials` | `material de clase`, `diseño de las diapositivas` |
| `aspect_organization_schedule` | `organización del curso y su planeación`, `horario` |
| `aspect_platform` | `disponibilidad de los recursos en el aula digital`, `Soporte técnico y plataforma` |
| `aspect_communication_climate` | `respuesta oportuna a los correos`, `Clima de aula e interacción` |
| `aspect_workload_pace` | `carga_académica`, `Ritmo y carga de trabajo` |

## Saving

- Save the file as CSV, UTF-8, with a comma as separator.
- Keep the same file name and folder; do not add columns or rows.
