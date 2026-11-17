/**
 * Internationalization dictionaries (EN / ES) for the web UI.
 */

export const STRINGS = {
  en: {
    appTitle: "From comment to action",
    appIntro: "Analyze Spanish course-evaluation comments. Each result shows the likely polarity, the classes the model cannot rule out, and whether a person should review the comment. The service stores nothing you enter.",
    tabSingle: "Single comment",
    tabBatch: "Batch upload",
    tabReview: "Review queue",
    singleTitle: "Analyze one comment",
    singleEmpty: "Paste a comment and select Analyze.",
    commentLabel: "Comment",
    analyzeBtn: "Analyze",
    analyzing: "Analyzing\u2026",
    examplesLabel: "Examples to try:",
    exPositive: "Positive",
    exMixed: "Mixed (Needs review)",
    exNegative: "Negative",
    resultTitle: "Result",
    predicted: "Predicted:",
    decisionClassify: "Decision: classify",
    decisionReview: "Decision:",
    needsReview: "Needs review",
    predSet: "Prediction set at",
    noClass: "no class",
    classProbs: "Class probabilities",
    aspectsTitle: "Aspects",
    noAspects: "No aspect detected in this comment.",
    influencesTitle: "Words that changed the prediction most",
    noInfluences: "No single word changed the prediction.",
    influencesCaption: "Each value is the drop in the probability of the predicted class when the word is removed. A negative value means the word pulled against it.",
    modelPrefix: "Model",
    batchTitle: "Analyze a CSV file",
    batchEmpty: "Upload a CSV file to see the course heatmap.",
    dropzoneText: "Drop a CSV file here or choose a file",
    chooseFileBtn: "Choose file",
    hintText: "UTF-8 CSV with columns feedback and curso, up to 2 MB and 5,000 rows",
    sampleCsvHint: "Tip: You can use Dataset/feedback_curso_universitario3.csv from the project.",
    noFileSelected: "No file selected.",
    analyzeFileBtn: "Analyze file",
    reviewTitle: "Review queue",
    reviewEmpty: "Upload a CSV file in Batch upload to fill the review queue.",
    exportBtn: "Export CSV",
    reviewCaption: "Decisions are saved in this browser only. Export the queue to share them.",
    accept: "Accept",
    relabel: "Relabel",
    showMore: "Show more",
    showLess: "Show less",
    langToggle: "Español",
  },
  es: {
    appTitle: "Del comentario a la acción",
    appIntro: "Analiza comentarios de evaluación docente en español. Cada resultado muestra la polaridad probable, las clases que el modelo no puede descartar y si una persona debe revisar el comentario. El servicio no almacena nada.",
    tabSingle: "Comentario individual",
    tabBatch: "Carga por lotes",
    tabReview: "Cola de revisión",
    singleTitle: "Analizar un comentario",
    singleEmpty: "Pega un comentario y selecciona Analizar.",
    commentLabel: "Comentario",
    analyzeBtn: "Analizar",
    analyzing: "Analizando\u2026",
    examplesLabel: "Ejemplos para probar:",
    exPositive: "Positivo",
    exMixed: "Mixto (Requiere revisión)",
    exNegative: "Negativo",
    resultTitle: "Resultado",
    predicted: "Predicho:",
    decisionClassify: "Decisión: clasificar",
    decisionReview: "Decisión:",
    needsReview: "Requiere revisión",
    predSet: "Conjunto conformal al",
    noClass: "ninguna clase",
    classProbs: "Probabilidades por clase",
    aspectsTitle: "Aspectos detectados",
    noAspects: "No se detectó ningún aspecto en este comentario.",
    influencesTitle: "Palabras que más influyeron en la predicción",
    noInfluences: "Ninguna palabra individual alteró la predicción.",
    influencesCaption: "Cada valor es la caída en la probabilidad de la clase predicha al omitir la palabra. Un valor negativo indica que la palabra empujaba en sentido contrario.",
    modelPrefix: "Modelo",
    batchTitle: "Analizar un archivo CSV",
    batchEmpty: "Sube un archivo CSV para ver el mapa de calor del curso.",
    dropzoneText: "Arrastra un archivo CSV aquí o selecciona un archivo",
    chooseFileBtn: "Elegir archivo",
    hintText: "CSV en UTF-8 con columnas feedback y curso, hasta 2 MB y 5.000 filas",
    sampleCsvHint: "Tip: Puedes usar Dataset/feedback_curso_universitario3.csv del repositorio.",
    noFileSelected: "Ningún archivo seleccionado.",
    analyzeFileBtn: "Analizar archivo",
    reviewTitle: "Cola de revisión",
    reviewEmpty: "Sube un archivo CSV en Carga por lotes para poblar la cola de revisión.",
    exportBtn: "Exportar CSV",
    reviewCaption: "Las decisiones se guardan únicamente en este navegador. Exporta la cola para compartirlas.",
    accept: "Aceptar",
    relabel: "Reetiquetar",
    showMore: "Ver más",
    showLess: "Ver menos",
    langToggle: "English",
  },
};

let currentLang = "es";

export function getLang() {
  return currentLang;
}

export function setLang(lang) {
  if (STRINGS[lang]) {
    currentLang = lang;
  }
}

export function t(key) {
  return STRINGS[currentLang][key] || STRINGS.en[key] || key;
}

export const SAMPLE_COMMENTS = Object.freeze({
  positive: "Las explicaciones del profesor fueron muy claras, las clases excelentes y el material didáctico estuvo completo.",
  mixed: "El contenido fue muy claro y los temas interesantes, pero los exámenes parciales fueron difíciles e injustos.",
  negative: "La carga académica fue desmedida, las evaluaciones no correspondían a lo visto y la retroalimentación nunca llegó.",
});
