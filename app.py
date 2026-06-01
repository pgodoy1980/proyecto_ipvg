"""
Backend del Chatbot Universitario Multi-RAG.

Este módulo expone un endpoint HTTP que:
1) Obtiene datos académicos y socioeconómicos de un alumno desde SQLite.
2) Enruta semánticamente la consulta para elegir el PDF correcto (Becas o Prácticas).
3) Construye un prompt con contexto mixto (RAG + datos relacionales).
4) Solicita la respuesta a un LLM vía Groq y la devuelve al frontend.
"""

import os
import sqlite3
from typing import Any, Dict, Optional, TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader

# ==========================================
# 1. CARGA DE CONFIGURACIONES Y CREDENCIALES
# ==========================================
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY or "tu_clave_aqui" in GROQ_API_KEY:
    print("\n[ALERTA] No se ha detectado una clave válida en el archivo .env\n")

# Inicialización del cliente oficial de Groq
client = Groq(api_key=GROQ_API_KEY)

# Definición de las constantes de archivos físicos
DB_FILE = "universidad.db"
PDF_BECAS = "base_conocimiento_becas.pdf"
PDF_PRACTICAS = "base_conocimiento_practica_titulacion.pdf"

class HistorialAlumno(TypedDict):
    """Estructura tipada para los datos generales del alumno."""

    nombre: str
    gpa: float
    reprobados: int
    decil: int


class AvanceCurricular(TypedDict):
    """Estructura tipada para los datos de progreso académico."""

    asignaturas_totales: int
    asignaturas_aprobadas: int
    porcentaje_avance: float
    cumple_requisito_80_poriento: bool


# ==========================================
# 2. PROCESAMIENTO RAG (EXTRACCIÓN DE TEXTO)
# ==========================================
def extraer_texto_pdf(ruta_pdf: str) -> str:
    """
    Lee dinámicamente un archivo PDF página por página, anexando marcadores
    de origen para que el LLM pueda citar las fuentes de manera fidedigna.
    """
    if not os.path.exists(ruta_pdf):
        print(f"[RAG ERROR] No se encuentra el archivo: {ruta_pdf}")
        return ""
    try:
        lector = PdfReader(ruta_pdf)
        texto_completo = ""
        for numero_pagina, pagina in enumerate(lector.pages, start=1):
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto_completo += f"\n--- INICIO PÁGINA {numero_pagina} ---\n"
                texto_completo += texto_pagina
                texto_completo += f"\n--- FIN PÁGINA {numero_pagina} ---\n"
        return texto_completo
    except Exception as e:
        print(f"[RAG ERROR] Falló la extracción en {ruta_pdf}: {str(e)}")
        return ""


# ==========================================
# 3. CAPA DE HERRAMIENTAS (SQLITE TOOLS)
# ==========================================
def tool_consultar_historial(numero_matricula: str) -> Optional[HistorialAlumno]:
    """
    TOOL 1: tool_consultar_historial.
    Extrae la información socioeconómica y calificaciones generales del estudiante.

    Args:
        numero_matricula: Identificador único del alumno.

    Returns:
        dict | None: Datos del alumno si existe, o None si no se encuentra
        la matrícula o no existe la base de datos.
    """
    if not os.path.exists(DB_FILE):
        print("[DB ERROR] La base de datos no existe al consultar historial.")
        return None

    try:
        with sqlite3.connect(DB_FILE) as conexion:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT nombre, gpa, reprobados, decil FROM alumnos WHERE matricula = ?",
                (numero_matricula,),
            )
            resultado = cursor.fetchone()
    except sqlite3.Error as exc:
        print(f"[DB ERROR] Falló la consulta de historial: {exc}")
        return None

    if not resultado:
        return None

    return {
        "nombre": str(resultado[0]),
        "gpa": float(resultado[1]),
        "reprobados": int(resultado[2]),
        "decil": int(resultado[3]),
    }


def tool_calcular_porcentaje_avance(numero_matricula: str) -> Optional[AvanceCurricular]:
    """
    TOOL 2: tool_calcular_porcentaje_avance.
    Calcula dinámicamente el progreso académico y contrasta contra la regla del 80%.

    Args:
        numero_matricula: Identificador único del alumno.

    Returns:
        dict | None: Estructura con totales, aprobadas, porcentaje y bandera
        de cumplimiento del 80%, o None si no hay registro.
    """
    if not os.path.exists(DB_FILE):
        print("[DB ERROR] La base de datos no existe al calcular avance.")
        return None

    try:
        with sqlite3.connect(DB_FILE) as conexion:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT asignaturas_totales, asignaturas_aprobadas FROM progreso_curricular WHERE matricula = ?",
                (numero_matricula,),
            )
            resultado = cursor.fetchone()
    except sqlite3.Error as exc:
        print(f"[DB ERROR] Falló la consulta de avance curricular: {exc}")
        return None

    if not resultado:
        return None

    totales = int(resultado[0])
    aprobadas = int(resultado[1])
    if totales <= 0:
        print(f"[DB ERROR] Total de asignaturas inválido para matrícula {numero_matricula}: {totales}")
        return None

    porcentaje = round((aprobadas / totales) * 100, 1)
    return {
        "asignaturas_totales": totales,
        "asignaturas_aprobadas": aprobadas,
        "porcentaje_avance": porcentaje,
        "cumple_requisito_80_poriento": porcentaje >= 80.0,
    }


# ==========================================
# 4. ENRUTADOR SEMÁNTICO (INTENT ROUTER)
# ==========================================
def enrutar_consulta_pdf(mensaje_usuario: str) -> str:
    """
    Clasifica en tiempo de ejecución la duda del estudiante para abrir
    únicamente el PDF requerido, optimizando la ventana de contexto.

    Args:
        mensaje_usuario: Consulta libre escrita por el estudiante.

    Returns:
        str: Ruta del PDF a utilizar como base RAG.
            - PDF_BECAS (por defecto ante error)
            - PDF_PRACTICAS
    """
    prompt_enrutador = f"""
    Eres un enrutador semántico de bases de conocimiento universitarias. Tu única tarea es clasificar la consulta en una de las dos opciones:
    - BECAS: Consultas de dinero, deciles, beca arancel, alimentación, apoyo psicológico o bienestar.
    - PRACTICAS: Consultas de horas de práctica, informes, comisiones, proyectos de tesis, egreso o examen de título.

    Consulta: "{mensaje_usuario}"
    Responde ÚNICAMENTE con 'BECAS' o 'PRACTICAS'. No añadas nada más.
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt_enrutador}],
            temperature=0.0,
        )
        decision = completion.choices[0].message.content.strip().upper()
        return PDF_PRACTICAS if "PRACTICAS" in decision else PDF_BECAS
    except Exception as exc:
        print(f"[ROUTER ERROR] Falló el enrutador semántico: {exc}")
        return PDF_BECAS


# ==========================================
# 5. ENDPOINT Y LÓGICA COGNITIVA ASÍNCRONA
# ==========================================
app = FastAPI(title="Backend Chatbot Universitario Multi-RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    """Esquema de entrada para el endpoint de chat."""

    numero_matricula: str
    mensaje: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint principal del chatbot.

    Flujo general:
    1. Valida que exista la base de datos local.
    2. Recupera datos del alumno y su avance curricular.
    3. Selecciona el documento normativo según la intención de la consulta.
    4. Inyecta contexto en un system prompt y consulta el modelo LLM.
    5. Retorna la respuesta procesada al cliente.

    Args:
        request: Cuerpo JSON con matrícula y mensaje del usuario.

    Returns:
        dict: Objeto con clave "respuesta" para renderizar en frontend.
    """
    # Verificación de existencia preventiva de la DB
    if not os.path.exists(DB_FILE):
        return {
            "respuesta": "Error interno: La base de datos no está inicializada localmente. Ejecuta init_db.py primero."
        }

    # 1. Consumo en paralelo de las dos Tools Relacionales
    alumno_info = tool_consultar_historial(request.numero_matricula)
    avance_info = tool_calcular_porcentaje_avance(request.numero_matricula)
    
    if not alumno_info or not avance_info:
        return {"respuesta": "Lo siento, no encontré el número de matrícula ingresado en los registros del sistema."}
    
    # 2. Ejecución del Router y carga selectiva de la base de conocimiento
    archivo_seleccionado = enrutar_consulta_pdf(request.mensaje)
    texto_conocimiento_rag = extraer_texto_pdf(archivo_seleccionado)
    if not texto_conocimiento_rag.strip():
        return {
            "respuesta": (
                f"Error interno: No fue posible cargar la base documental '{archivo_seleccionado}'. "
                "Verifica que el archivo exista y sea legible."
            )
        }
    
    nombre_doc = "Reglamento de Becas (REG-BAE-2026)" if archivo_seleccionado == PDF_BECAS else "Reglamento de Prácticas Profesionales y Titulación (REG-PPT-2026)"

    # 3. Configuración estricta del SYSTEM PROMPT estructurado.
    #    Aquí se combina el contexto estático (PDF) con el dinámico (SQLite).
    system_prompt = f"""
    SYSTEM PROMPT
    Eres un asistente de la Universidad, especializado en responder consultas sobre el {nombre_doc}.

    Reglas de respuesta:
    1. Si la pregunta es sobre el tema del documento, utiliza la información oficial indexada aquí:
    --- INICIO INFORMACIÓN OFICIAL DEL DOCUMENTO PDF ---
    {texto_conocimiento_rag}
    --- FIN INFORMACIÓN OFICIAL DEL DOCUMENTO PDF ---

    2. Para datos personales o cálculos dinámicos de becas y asignaturas, utiliza la información provista en tiempo real por las tools del sistema:
    --- INICIO DATOS EN TIEMPO REAL DEL ALUMNO (TOOL: tool_consultar_historial) ---
    - Nombre del Alumno: {alumno_info['nombre']}
    - Número de Matrícula: {request.numero_matricula}
    - Promedio de Notas Actual (GPA): {alumno_info['gpa']}
    - Asignaturas Reprobadas este semestre: {alumno_info['reprobados']}
    - Nivel socioeconómico (Decil): {alumno_info['decil']}
    --- FIN DATOS EN TIEMPO REAL DEL ALUMNO ---

    --- INICIO DATOS EN TIEMPO REAL DE AVANCE (TOOL: tool_calcular_porcentaje_avance) ---
    - Total de asignaturas de la carrera: {avance_info['asignaturas_totales']}
    - Asignaturas aprobadas a la fecha: {avance_info['asignaturas_aprobadas']}
    - Porcentaje de avance curricular real: {avance_info['porcentaje_avance']}%
    - ¿Cumple con el mínimo de 80% requerido para práctica?: {"SÍ cumple" if avance_info['cumple_requisito_80_poriento'] else "NO cumple"}
    --- FIN DATOS EN TIEMPO REAL DE AVANCE ---

    3. Cita siempre la fuente (ej: Página 1, Página 2 o Página 3) cuando respondas con datos del documento oficial en uso.
    4. Si no encuentras la respuesta en la información oficial del documento, indica textualmente: "Lo siento, no encontré esa información en el reglamento oficial de la universidad. Te sugiero contactar directamente al Departamento correspondiente." No inventes información.
    5. Responde en español, dirigiéndose al alumno por su nombre de pila, con un tono CERCANO pero estrictamente FORMAL.
       Utiliza formato Markdown de manera obligatoria para estructurar tu respuesta (negritas, listas y saltos de línea dobles).
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.mensaje}
            ],
            temperature=0.2,
        )
        return {"respuesta": completion.choices[0].message.content}
    except Exception as e:
        return {"respuesta": f"Error en los servidores de Groq: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)