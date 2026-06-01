# Proyecto: Chatbot Universitario Multi-RAG (Becas y Prácticas)

Este proyecto implementa una plataforma local tipo *chat* para atender consultas estudiantiles sobre:
- **Reglamento de Becas y Apoyo Estudiantil**
- **Reglamento de Prácticas Profesionales y Titulación**

Además, valida la consulta con información del estudiante desde una base **SQLite** (historial socioeconómico/notas y progreso curricular) y responde con contexto proveniente de los documentos oficiales (RAG).

## ¿De qué se trata?

La interfaz web (`index.html`) permite al estudiante ingresar su **número de matrícula** y escribir una pregunta.
El navegador envía la solicitud al backend (`app.py`) a través del endpoint:

`POST http://127.0.0.1:8000/api/chat`

El backend:
1. Busca datos del alumno en **SQLite** (tools relacionales).
2. Usa un **router semántico** (LLM) para decidir qué documento PDF cargar:
   - Becas
   - Prácticas y Titulación
3. Extrae texto del PDF seleccionado (RAG) usando marcadores por página.
4. Construye un *system prompt* con:
   - Información oficial del documento (RAG)
   - Datos dinámicos del alumno (SQLite tools)
5. Genera la respuesta usando **Groq** (modelo Llama) en español.

## Tecnologías utilizadas

### Backend (Python)
- **FastAPI**: API HTTP del servidor.
- **Uvicorn**: servidor ASGI para ejecutar FastAPI.
- **Pydantic**: validación del payload de entrada (`numero_matricula`, `mensaje`).
- **groq** (SDK): acceso al LLM mediante la API de Groq.
- **python-dotenv**: carga de variables desde `.env`.
- **pypdf**: extracción de texto desde los PDFs para RAG.
- **sqlite3** (nativo de Python): base de datos local para información del estudiante.

### Frontend (Web)
- **HTML/CSS/JavaScript**: interfaz del chat.
- **CSS propio**: estilos en `css/chat.css`.
- **Google Fonts (Inter)**: tipografía para una UI moderna.

## Características principales

- **Multi-RAG con router semántico**: selecciona dinámicamente el PDF relevante (Becas vs Prácticas) según la pregunta.
- **RAG basado en extracción por páginas**: el texto del PDF incluye marcadores `INICIO/FIN PÁGINA` para facilitar citas.
- **Integración con datos del estudiante** (SQLite):
  - `alumnos`: nombre, GPA, reprobados, decil.
  - `progreso_curricular`: totales/aprobadas para calcular porcentaje de avance.
- **Cálculo de requisito mínimo (80%)** para práctica: `porcentaje_avance >= 80.0`.
- **Prompt estricto y formato Markdown**: la salida se estructura usando Markdown (negritas, listas, saltos de línea).
- **CORS habilitado** para permitir consumo desde el frontend local.
- **UI con UX mejorada**: burbujas, scroll, indicador de “escribiendo”, botón con estado, etc.

## Estructura de archivos (resumen)

- `app.py`: backend FastAPI (endpoint `/api/chat`, herramientas SQLite, extracción PDF y generación con Groq).
- `index.html`: frontend del chat (envía `numero_matricula` y `mensaje`).
- `css/chat.css`: estilos de la interfaz.
- `init_db.py`: crea y/o inicializa `universidad.db` con datos de ejemplo.
- `base_conocimiento_becas.pdf`: reglamento para becas.
- `base_conocimiento_practica_titulacion.pdf` (o el nombre del archivo que uses): reglamento para prácticas/titulación.
  - Nota: el nombre **debe coincidir** con la constante `PDF_PRACTICAS` en `app.py`.
- `INSTRUCCIONES.txt`: guía de despliegue local.
- `.env`: credenciales (por ejemplo `GROQ_API_KEY`).

## Requisitos

Instala dependencias con:

```bash
pip install -r requerimientos.txt
```

## Despliegue local (rápido)

1. Configura `.env` con tu clave:
   - `GROQ_API_KEY=...`
2. Inicializa la base SQLite:
   - `python init_db.py`
3. Ejecuta el backend:
   - `python app.py`
4. Abre el frontend:
   - `index.html`

Para más detalles, revisa `INSTRUCCIONES.txt`.

