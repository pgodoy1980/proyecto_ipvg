"""
Chatbot Universitario · RAG + Tools (function calling)
======================================================
Flujo:
  1) Prompt + definición de tools + reglamento PDF (RAG)
  2) El modelo responde con tool_calls si necesita datos del alumno
  3) Python ejecuta la función real y devuelve el resultado
  4) El modelo redacta la respuesta final cruzando tool + reglamento
"""

import json
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
    "2024001": {"nombre": "Juan Pérez", "gpa": 5.4, "reprobadas": 1, "decil": 3},
    "2024002": {"nombre": "María López", "gpa": 4.9, "reprobadas": 2, "decil": 2},
}

ORIGENES_CORS_DEFECTO = [
    "http://127.0.0.1", "http://localhost",
    "http://127.0.0.1:8000", "http://localhost:8000",
    "http://127.0.0.1:8080", "http://localhost:8080",
    "http://127.0.0.1:5500", "http://localhost:5500",
]
REGEX_CORS_LOCAL = r"http://(127\.0\.0\.1|localhost)(:\d+)?"

KW_REGLAMENTO = (
    "beca", "reglamento", "apel", "requisit", "arancel institucional",
    "aliment", "bau", "bai", "beneficio estudiantil", "plazo", "días hábil",
    "tutor", "bienestar", "subsidio", "cobertura", "renovación", "renovacion",
    "ubsm", "ptap",
)
KW_HISTORIAL = (
    "mi gpa", "mi promedio", "mis notas", "mi decil", "mi historial",
    "mi estado académico", "mi estado academico", "mi rendimiento",
    "mi situación académica", "mi situacion academica", "mis reprobad",
    "cumplo los", "cumplo con", "puedo postular", "podría postular",
    "según mi gpa", "con mi gpa", "con mi promedio", "con mi decil",
)
KW_FUERA_ALCANCE = (
    "deporte", "deportes", "biblioteca", "intercambio", "vacacion", "vacaciones",
    "estacionamiento", "gimnasio", "horario de atención del departamento",
)
KW_RESPUESTA_SIN_DATO = (
    "no encontré esa información en el reglamento",
    "sin coincidencia para esta consulta",
)

client = Groq(api_key=GROQ_API_KEY)
TEXTO_PDF: str = ""


# ======================================================================
# 1. Funciones reales (las ejecuta tu código, no el modelo)
# ======================================================================
def tool_consultar_historial(numero_matricula: str) -> dict:
    """Consulta el historial académico del alumno en el sistema universitario."""
    alumno = DB_ALUMNOS.get(numero_matricula)
    if not alumno:
        return {"error": MSG_SIN_MATRICULA}
    reprobadas = alumno["reprobadas"]
    return {
        "numero_matricula": numero_matricula,
        "nombre": alumno["nombre"],
        "gpa": alumno["gpa"],
        "reprobadas": reprobadas,
        "decil": alumno["decil"],
        "cumple_renovacion_reprobadas": reprobadas <= 1,
    }


DISPATCH = {
    "tool_consultar_historial": tool_consultar_historial,
}


# ======================================================================
# 2. Definición de tools (esto es lo que el modelo "ve")
# ======================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tool_consultar_historial",
            "description": (
                "Obtiene el historial académico del estudiante: nombre, GPA, "
                "asignaturas reprobadas en el semestre anterior y decil socioeconómico. "
                "Usar cuando la consulta requiera datos personales o evaluar postulación/renovación."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "numero_matricula": {
                        "type": "string",
                        "description": "Número de matrícula del estudiante",
                    }
                },
                "required": ["numero_matricula"],
            },
        },
    },
]


# ======================================================================
# 3. RAG, utilidades y fuentes
# ======================================================================
def _contiene(texto: str, *palabras: str) -> bool:
    return any(p in texto.lower() for p in palabras)


def configuracion_cors() -> dict:
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


def requiere_historial(mensaje: str) -> bool:
    m = mensaje.lower()
    return _contiene(m, *KW_HISTORIAL) or (
        "renov" in m and _contiene(m, "cumplo", "mi rendimiento", "mi promedio", "mi gpa")
    )


def clasificar_consulta(mensaje: str) -> dict:
    return {
        "reglamento": _contiene(mensaje, *KW_REGLAMENTO),
        "fuera_alcance": _contiene(mensaje, *KW_FUERA_ALCANCE),
    }


def extraer_paginas_citadas(texto: str) -> list[str]:
    return sorted(set(re.findall(r"P[aá]gina\s+(\d+)", texto, re.I)), key=int)


def construir_fuentes(
    mensaje: str, matricula: str, respuesta: str, tools_usadas: list[str]
) -> list[dict]:
    c = clasificar_consulta(mensaje)
    sin_dato = _contiene(respuesta, *KW_RESPUESTA_SIN_DATO)
    paginas = extraer_paginas_citadas(respuesta)
    fuentes = []

    if "tool_consultar_historial" in tools_usadas:
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


# ======================================================================
# 4. Conversación (function calling)
# ======================================================================
def construir_system_prompt(nombre_pila: str, matricula: str, texto_pdf: str) -> str:
    return f"""Eres asistente universitario del {NOMBRE_REGLAMENTO}.
Saluda a {nombre_pila} por su nombre de pila.

Reglas:
1. Reglamento oficial:
--- PDF ---
{texto_pdf}
--- FIN PDF ---
2. Usa tool_consultar_historial SOLO si necesitas GPA, reprobadas o decil del alumno
   (postulación, renovación o elegibilidad personalizada). Preguntas generales del
   reglamento (plazos, requisitos, apelación, documentación) se responden solo con el PDF.
3. En postulación o renovación de BAI/BAU, aplica **Página 2**: máximo 1 reprobada.
   Si reprobadas >= 2, concluye que NO puede postular ni mantener el beneficio.
   Menciona reprobadas, GPA y decil. No digas que no tienes acceso si ya usaste la tool.
4. Cita la página del PDF (ej: **Página 2**).
5. Si no está en el PDF, responde exactamente: "{MSG_SIN_REGLAMENTO}"
6. Español formal. Markdown: **negritas**, listas con *.
No incluyas sección "Fuentes consultadas"."""


def _mensaje_asistente(message) -> dict:
    """Convierte la respuesta del modelo (con tool_calls) al formato del historial."""
    msg = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return msg


def ejecutar_tool_calls(mensajes: list, tool_calls, matricula: str) -> list[str]:
    """Ejecuta cada tool_call y agrega los resultados al historial."""
    tools_usadas: list[str] = []
    for tc in tool_calls:
        nombre = tc.function.name
        args = json.loads(tc.function.arguments)
        if nombre == "tool_consultar_historial":
            args["numero_matricula"] = matricula  # seguridad: matrícula de la sesión

        fn = DISPATCH.get(nombre)
        resultado = fn(**args) if fn else {"error": f"Tool desconocida: {nombre}"}
        if nombre in DISPATCH:
            tools_usadas.append(nombre)

        mensajes.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(resultado, ensure_ascii=False),
        })
    return tools_usadas


def generar_respuesta(
    matricula: str, mensaje: str, nombre_pila: str, texto_pdf: str
) -> tuple[str, list[str]]:
    mensajes = [
        {"role": "system", "content": construir_system_prompt(nombre_pila, matricula, texto_pdf)},
        {"role": "user", "content": mensaje},
    ]

    # --- Solo RAG: sin tools disponibles ---
    if not requiere_historial(mensaje):
        respuesta = client.chat.completions.create(
            model=MODELO_LLM,
            messages=mensajes,
            temperature=0.2,
        )
        return respuesta.choices[0].message.content or "", []

    # --- Con historial: primera llamada obliga la tool ---
    primera = client.chat.completions.create(
        model=MODELO_LLM,
        messages=mensajes,
        tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "tool_consultar_historial"}},
        temperature=0.2,
    )
    mensaje_modelo = primera.choices[0].message
    mensajes.append(_mensaje_asistente(mensaje_modelo))

    if not mensaje_modelo.tool_calls:
        return mensaje_modelo.content or "", []

    # --- Ejecutar tools y devolver resultados al modelo ---
    tools_usadas = ejecutar_tool_calls(mensajes, mensaje_modelo.tool_calls, matricula)

    # --- Segunda llamada: respuesta final con datos de la tool ---
    final = client.chat.completions.create(
        model=MODELO_LLM,
        messages=mensajes,
        temperature=0.2,
    )
    return final.choices[0].message.content or "", tools_usadas


# ======================================================================
# 5. API
# ======================================================================
app = FastAPI(title="Chatbot Universitario")
app.add_middleware(CORSMiddleware, **configuracion_cors())


class ChatRequest(BaseModel):
    numero_matricula: str
    mensaje: str


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    alumno = DB_ALUMNOS.get(req.numero_matricula)
    if not alumno:
        return {"respuesta": MSG_SIN_MATRICULA, "fuentes": []}

    try:
        respuesta, tools_usadas = generar_respuesta(
            req.numero_matricula,
            req.mensaje,
            alumno["nombre"].split()[0],
            cargar_pdf(),
        )
        return {
            "respuesta": respuesta,
            "fuentes": construir_fuentes(
                req.mensaje, req.numero_matricula, respuesta, tools_usadas
            ),
        }
    except Exception as e:
        return {
            "respuesta": f"Error al conectar con Groq (revisa .env): {e}",
            "fuentes": [],
        }


TEXTO_PDF = extraer_texto_pdf(ARCHIVO_PDF)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
