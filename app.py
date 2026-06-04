import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader

# ==========================================
# 1. CONFIGURACIÓN DEL ENTORNO Y SEGURIDAD
# ==========================================

# Carga las variables de entorno desde el archivo oculto `.env` a la memoria del sistema
load_dotenv()

# Recupera la clave secreta de la API de Groq de forma segura
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Validación preventiva en consola por si el usuario olvidó configurar su token
if not GROQ_API_KEY or "tu_clave_aqui" in GROQ_API_KEY:
    print("\n[ALERTA] No se ha detectado una clave válida en el archivo .env\n")

# Inicializa el cliente oficial de Groq utilizando la API Key del entorno seguro
client = Groq(api_key=GROQ_API_KEY)


# ==========================================
# 2. FUNCIÓN DE EXTRACCIÓN RAG (LECTOR PDF)
# ==========================================
def extraer_texto_pdf(ruta_pdf: str) -> str:
    """
    Función RAG (Retrieval-Augmented Generation).
    Abre un archivo PDF local, extrae el texto de todas sus páginas
    y añade delimitadores visuales para que la IA sepa el origen de los datos.
    """
    # Verifica si el archivo físico realmente existe en la ruta especificada
    if not os.path.exists(ruta_pdf):
        print(f"\n[ERROR] No se encontró el archivo '{ruta_pdf}' en la carpeta del proyecto.\n")
        return ""
    
    try:
        # Instancia el lector de PDFs con la ruta del archivo
        lector = PdfReader(ruta_pdf)
        texto_completo = ""
        
        # Itera sobre cada página del documento, indexándolas desde el número 1
        for numero_pagina, pagina in enumerate(lector.pages, start=1):
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                # Inyecta etiquetas de metadatos de página para que la IA pueda citar las fuentes correctamente
                texto_completo += f"\n--- INICIO PÁGINA {numero_pagina} ---\n"
                texto_completo += texto_pagina
                texto_completo += f"\n--- FIN PÁGINA {numero_pagina} ---\n"
                
        print(f"[RAG exitoso] Se han leído {len(lector.pages)} páginas desde '{ruta_pdf}'.")
        return texto_completo
    except Exception as e:
        print(f"[ERROR] No se pudo leer el archivo PDF: {str(e)}")
        return ""

# Carga global del texto del PDF en memoria al momento de inicializar el servidor
ARCHIVO_PDF = "base_conocimiento_becas.pdf"
TEXTO_PDF_REGLAMENTO = extraer_texto_pdf(ARCHIVO_PDF)


# ==========================================
# 3. CAPA DE DATOS / SIMULACIÓN DE TOOLS
# ==========================================

# Simulación de una Base de Datos relacional de la universidad (Expedientes Estudiantiles)
DB_ALUMNOS = {
    "2024001": {"nombre": "Juan Pérez", "gpa": 5.4, "reprobados": 1, "decil": 3},
    "2024002": {"nombre": "María López", "gpa": 4.9, "reprobados": 2, "decil": 8}
}

def tool_consultar_historial(numero_matricula: str):
    """
    TOOL OFICIAL: NOMBRE_DE_TU_TOOL.
    Simula una función de negocio o API interna que busca el registro académico 
    de un estudiante utilizando su número de matrícula único como llave.
    """
    return DB_ALUMNOS.get(numero_matricula, None)


# ==========================================
# 4. CONFIGURACIÓN DE LA API (FASTAPI)
# ==========================================

# Instancia la aplicación FastAPI que expondrá los servicios web
app = FastAPI(title="Backend Chatbot Universitario por Matrícula")

# Configuración del Middleware de CORS (Cross-Origin Resource Sharing)
# Esto permite que tu archivo index.html local (origen diferente) pueda hacer peticiones HTTP a esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Permite peticiones desde cualquier origen
    allow_credentials=True,
    allow_methods=["*"],       # Permite todos los métodos HTTP (GET, POST, etc.)
    allow_headers=["*"],       # Permite todas las cabeceras HTTP
)

# Modelo de datos Pydantic para validar la estructura del JSON recibido en el cuerpo del POST
class ChatRequest(BaseModel):
    numero_matricula: str     # Cadena de texto obligatoria con la matrícula
    mensaje: str              # Cadena de texto obligatoria con la pregunta del usuario


# ==========================================
# 5. ENDPOINT PRINCIPAL (LÓGICA DEL CHAT)
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Ruta POST que procesa la consulta del chat.
    Recibe la matrícula y el mensaje, ejecuta la tool, compone el System Prompt 
    con técnica RAG y solicita la respuesta al modelo Llama 3.1 en Groq.
    """
    global TEXTO_PDF_REGLAMENTO
    # Mecanismo de resiliencia: Si por algún motivo el texto está vacío, reintenta leer el PDF
    if not TEXTO_PDF_REGLAMENTO:
        TEXTO_PDF_REGLAMENTO = extraer_texto_pdf(ARCHIVO_PDF)

    # EJECUCIÓN DE LA TOOL: Busca los datos personales/dinámicos en la base de datos simulada
    alumno_info = tool_consultar_historial(request.numero_matricula)
    
    # Si la matrícula no existe en el diccionario, corta la ejecución y retorna un error amigable
    if not alumno_info:
        return {"respuesta": "Lo siento, no encontré el número de matrícula ingresado en el sistema de la universidad."}
    
    # COMPOSTURA DEL SYSTEM PROMPT ESTRUCTURADO (RAG + TOOLS)
    system_prompt = f"""
    SYSTEM PROMPT

    Eres un asistente de la Universidad, especializado en responder consultas sobre el Reglamento de Becas y Apoyo Estudiantil Universitario (REG-BAE-2026).

    Tu público corresponde a los estudiantes regulares y postulantes de la universidad que buscan orientación sobre sus beneficios.

    Reglas de respuesta:
    1. Si la pregunta es sobre el reglamento de becas, utiliza la información oficial indexada del documento para consultar la información oficial:
    --- INICIO INFORMACIÓN OFICIAL DEL DOCUMENTO PDF ---
    {TEXTO_PDF_REGLAMENTO}
    --- FIN INFORMACIÓN OFICIAL DEL DOCUMENTO PDF ---

    2. Para datos personales o cálculos dinámicos, utiliza la información provista en tiempo real por la tool 'tool_consultar_historial':
    --- INICIO DATOS EN TIEMPO REAL DEL ALUMNO ---
    - Nombre del Alumno: {alumno_info['nombre']}
    - Número de Matrícula: {request.numero_matricula}
    - Promedio de Notas Actual (GPA): {alumno_info['gpa']}
    - Asignaturas Reprobadas este semestre: {alumno_info['reprobados']}
    - Nivel socioeconómico (Decil): {alumno_info['decil']}
    --- FIN DATOS EN TIEMPO REAL DEL ALUMNO ---

    3. Cita siempre la fuente (ej: Página 1, Página 2 o Página 3) cuando respondas con datos del documento.
    4. Si no encuentras la respuesta en la información oficial del documento, indica textualmente: "Lo siento, no encontré esa información en el reglamento oficial de la universidad. Te sugiero contactar directamente al Departamento de Bienestar Estudiantil." No inventes información.
    5. Responde en español, dirigiéndose al alumno por su nombre de pila, con un tono CERCANO pero estrictamente FORMAL.
       Utiliza formato Markdown de manera obligatoria para estructurar tu respuesta:
       - Usa **negritas** para estados importantes, notas o plazos.
       - Usa listas con viñetas (asteriscos) para separar los datos académicos del alumno o los requisitos del PDF.
       - Deja un salto de línea doble entre párrafos para evitar bloques densos de texto.
    """

    try:
        # LLAMADA AL GRAN MODELO DE LENGUAJE (LLM) EN GROQ
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Especifica el modelo de Meta optimizado de alta velocidad
            messages=[
                {"role": "system", "content": system_prompt}, # Envía el contexto y reglas del negocio
                {"role": "user", "content": request.mensaje}   # Envía la duda del estudiante
            ],
            temperature=0.2, # Temperatura baja para garantizar respuestas deterministas y basadas solo en el PDF
        )
        
        # Extrae el contenido de texto generado por la inteligencia artificial
        respuesta_ia = completion.choices[0].message.content
        return {"respuesta": respuesta_ia}

    except Exception as e:
        # Captura cualquier error de conexión o credenciales de la API de Groq
        return {"respuesta": f"Error al conectar con Groq (Revisa tu .env): {str(e)}"}

# Punto de entrada estándar de Python para ejecutar el servidor local mediante Uvicorn
if __name__ == "__main__":
    # Inicia la aplicación en el localhost (127.0.0.1) a través del puerto 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)