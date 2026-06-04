import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader

# --- Configuración ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY or "tu_clave_aqui" in GROQ_API_KEY:
    print("\n[ALERTA] No se ha detectado una clave válida en el archivo .env\n")

ARCHIVO_PDF = "base_conocimiento_becas.pdf"
NOMBRE_REGLAMENTO = "REG-BAE-2026 — Reglamento de Becas y Apoyo Estudiantil"
MODELO_LLM = "llama-3.1-8b-instant"

MSG_SIN_MATRICULA = (
    "Lo siento, no encontré el número de matrícula ingresado en el sistema de la universidad."
)
MSG_SIN_REGLAMENTO = (
    "Lo siento, no encontré esa información en el reglamento oficial de la universidad. "
    "Te sugiero contactar directamente al Departamento de Bienestar Estudiantil."
)

DB_ALUMNOS = {
    "2024001": {"nombre": "Juan Pérez", "gpa": 5.4, "reprobados": 1, "decil": 3},
    "2024002": {"nombre": "María López", "gpa": 4.9, "reprobados": 2, "decil": 2},
}

ORIGENES_CORS_DEFECTO = [
    "http://127.0.0.1",
    "http://localhost",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
REGEX_CORS_LOCAL = r"http://(127\.0\.0\.1|localhost)(:\d+)?"

KW_REGLAMENTO = (
    "beca", "reglamento", "apel", "requisit", "arancel institucional",
    "aliment", "bau", "bai", "beneficio estudiantil", "plazo", "días hábil",
    "tutor", "bienestar", "subsidio", "cobertura", "renovación", "renovacion",
    "ubsm", "ptap",
)
KW_FUERA_ALCANCE = (
    "deporte", "deportes", "biblioteca", "intercambio", "vacacion", "vacaciones",
    "estacionamiento", "gimnasio", "horario de atención del departamento",
)
KW_EXPEDIENTE = (
    "mi gpa", "mi promedio", "mis notas", "mi decil", "mi historial",
    "mi estado académico", "mi estado academico", "mi rendimiento",
    "mi situación académica", "mi situacion academica", "mis reprobad",
    "cumplo los", "cumplo con", "puedo postular", "podría postular",
    "según mi gpa", "con mi gpa", "con mi promedio", "con mi decil",
)
KW_RESPUESTA_SIN_DATO = (
    "no encontré esa información en el reglamento",
    "sin coincidencia para esta consulta",
)

client = Groq(api_key=GROQ_API_KEY)
TEXTO_PDF: str = ""


def _contiene(texto: str, *palabras: str) -> bool:
    t = texto.lower()
    return any(p in t for p in palabras)


def configuracion_cors() -> dict:
    """CORS: lista explícita en .env o, por defecto, orígenes locales + regex de puertos."""
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    base = {
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if raw:
        base["allow_origins"] = [o.strip() for o in raw.split(",") if o.strip()]
        return base
    base["allow_origins"] = ORIGENES_CORS_DEFECTO
    base["allow_origin_regex"] = REGEX_CORS_LOCAL
    return base


def extraer_texto_pdf(ruta: str) -> str:
    if not os.path.exists(ruta):
        print(f"[ERROR] No se encontró '{ruta}'")
        return ""
    try:
        lector = PdfReader(ruta)
        partes = []
        for n, pagina in enumerate(lector.pages, start=1):
            texto = pagina.extract_text()
            if texto:
                partes.append(f"\n--- INICIO PÁGINA {n} ---\n{texto}\n--- FIN PÁGINA {n} ---\n")
        print(f"[RAG] {len(lector.pages)} páginas leídas desde '{ruta}'")
        return "".join(partes)
    except Exception as e:
        print(f"[ERROR] PDF: {e}")
        return ""


def cargar_pdf() -> str:
    global TEXTO_PDF
    if not TEXTO_PDF:
        TEXTO_PDF = extraer_texto_pdf(ARCHIVO_PDF)
    return TEXTO_PDF


def clasificar_consulta(mensaje: str) -> dict:
    m = mensaje.lower()
    personal = _contiene(m, *KW_EXPEDIENTE) or (
        "renov" in m and _contiene(m, "cumplo", "mi rendimiento", "mi promedio", "mi gpa")
    )
    return {
        "personal": personal,
        "reglamento": _contiene(m, *KW_REGLAMENTO),
        "fuera_alcance": _contiene(m, *KW_FUERA_ALCANCE),
    }


def extraer_paginas_citadas(texto: str) -> list[str]:
    return sorted(set(re.findall(r"P[aá]gina\s+(\d+)", texto, re.I)), key=int)


def construir_fuentes(mensaje: str, matricula: str, respuesta: str) -> list[dict]:
    c = clasificar_consulta(mensaje)
    sin_dato = _contiene(respuesta, *KW_RESPUESTA_SIN_DATO)
    paginas = extraer_paginas_citadas(respuesta)
    fuentes = []

    if c["personal"]:
        fuentes.append({
            "tipo": "tool",
            "titulo": "Datos académicos en tiempo real",
            "detalle": f"tool_consultar_historial — Matrícula {matricula}",
            "archivo": None,
        })

    usar_rag = not sin_dato and not c["fuera_alcance"] and (c["reglamento"] or paginas)
    if usar_rag:
        rag = {
            "tipo": "rag",
            "titulo": "Documento oficial (RAG)",
            "detalle": NOMBRE_REGLAMENTO,
            "archivo": ARCHIVO_PDF,
        }
        if paginas:
            rag["paginas"] = paginas
        fuentes.append(rag)
    elif sin_dato or c["fuera_alcance"]:
        fuentes = [f for f in fuentes if f["tipo"] != "rag"]

    if not fuentes and (sin_dato or c["fuera_alcance"]):
        fuentes.append({
            "tipo": "ninguna",
            "titulo": "Sin fuente en el reglamento",
            "detalle": (
                "Esta consulta no está cubierta por el REG-BAE-2026. "
                "Contacta al Departamento de Bienestar Estudiantil."
            ),
            "archivo": None,
        })
    return fuentes


def construir_system_prompt(alumno: dict, matricula: str, mensaje: str, texto_pdf: str) -> str:
    nombre = alumno["nombre"].split()[0]
    usa_tool = clasificar_consulta(mensaje)["personal"]

    if usa_tool:
        bloque_alumno = f"""
    2. Usa los datos de tool_consultar_historial:
    --- DATOS DEL ALUMNO ---
    Nombre: {alumno['nombre']} | Matrícula: {matricula}
    GPA: {alumno['gpa']} | Reprobadas: {alumno['reprobados']} | Decil: {alumno['decil']}
    --- FIN DATOS ---"""
        regla_datos = (
            "4. Si usas datos personales, indica que provienen del sistema académico."
        )
    else:
        bloque_alumno = (
            "\n    2. NO uses expediente (GPA, decil, reprobadas). Solo el reglamento PDF."
        )
        regla_datos = "4. No cites ni inventes datos del expediente académico."

    return f"""Eres asistente universitario del {NOMBRE_REGLAMENTO}.
Saluda a {nombre} por su nombre de pila.

Reglas:
1. Reglamento oficial:
--- PDF ---
{texto_pdf}
--- FIN PDF ---
{bloque_alumno}
3. Cita la página del PDF cuando corresponda (ej: **Página 2**).
{regla_datos}
5. Si no está en el PDF, responde exactamente: "{MSG_SIN_REGLAMENTO}"
6. Español formal y cercano. Markdown: **negritas**, listas con *, párrafos separados.
No incluyas sección "Fuentes consultadas" (la muestra la interfaz)."""


# --- API ---
app = FastAPI(title="Chatbot Universitario")
app.add_middleware(CORSMiddleware, **configuracion_cors())


class ChatRequest(BaseModel):
    numero_matricula: str
    mensaje: str


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    texto_pdf = cargar_pdf()
    alumno = DB_ALUMNOS.get(req.numero_matricula)

    if not alumno:
        return {"respuesta": MSG_SIN_MATRICULA, "fuentes": []}

    try:
        completion = client.chat.completions.create(
            model=MODELO_LLM,
            messages=[
                {
                    "role": "system",
                    "content": construir_system_prompt(
                        alumno, req.numero_matricula, req.mensaje, texto_pdf
                    ),
                },
                {"role": "user", "content": req.mensaje},
            ],
            temperature=0.2,
        )
        respuesta = completion.choices[0].message.content
        return {
            "respuesta": respuesta,
            "fuentes": construir_fuentes(req.mensaje, req.numero_matricula, respuesta),
        }
    except Exception as e:
        return {
            "respuesta": f"Error al conectar con Groq (revisa .env): {e}",
            "fuentes": [],
        }


# Carga del PDF al importar el módulo
TEXTO_PDF = extraer_texto_pdf(ARCHIVO_PDF)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
