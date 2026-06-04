# Pruebas del chatbot universitario

Guía para validar el comportamiento del asistente: **RAG** (PDF), **tool** (datos del alumno) y **respuesta cuando no hay información** en el reglamento.

## Requisitos previos

1. Instalar dependencias: `pip install -r requirements.txt`
2. Configurar `GROQ_API_KEY` en el archivo `.env`
3. Iniciar el backend: `python app.py` (puerto `8000`)
4. Abrir `index.html` en el navegador
5. Verificar que exista `base_conocimiento_becas.pdf` en la carpeta del proyecto

## Matrículas de prueba

| Matrícula | Alumno      | GPA | Reprobadas (semestre) | Decil |
|-----------|-------------|-----|------------------------|-------|
| `2024001` | Juan Pérez  | 5.4 | 1                      | 3     |
| `2024002` | María López | 4.9 | 2                      | 2     |

Cualquier otra matrícula debe responder: *"Lo siento, no encontré el número de matrícula ingresado en el sistema de la universidad."*

---

## Pregunta 1 — RAG (reglamento / PDF)

**Matrícula:** `2024001` (o `2024002`)

**Pregunta:**

> ¿Cuáles son los requisitos para postular a la Beca de Arancel Institucional (BAI)?

**Qué validar:**

- Respuesta basada en el PDF, no inventada.
- Debe mencionar, entre otros: alumno regular de pregrado, deciles 1–6, NEM ≥ 5.5 (primer año) o GPA ≥ 5.0 (cursos superiores), cobertura entre 30% y 70% del arancel.
- Debe **citar la fuente** (ej.: Página 1).
- Tono formal, en español, con formato Markdown (negritas, listas).

---

## Pregunta 2 — RAG (reglamento / PDF)

**Matrícula:** `2024001` (o `2024002`)

**Pregunta:**

> ¿Cuántos días hábiles tengo para apelar si pierdo mi beca por motivos académicos?

**Qué validar:**

- Debe indicar **10 días hábiles** desde la notificación de la pérdida.
- Puede mencionar causales (enfermedad, fuerza mayor, problemas familiares) y documentación (certificado médico, informe social, etc.).
- Debe **citar la fuente** (ej.: Página 2).

---

## Pregunta 3 — Tool (datos del alumno + reglamento)

**Matrícula:** `2024001` (Juan Pérez)

**Pregunta:**

> ¿Cumplo los criterios de renovación semestral de mi beca según mi rendimiento actual?

**Qué validar:**

- Usa datos de la tool: GPA **5.4**, **1** asignatura reprobada, nombre **Juan**.
- Cruza con el reglamento (Página 2): GPA ≥ 5.2, máximo 1 reprobación en el semestre anterior.
- Conclusión esperada: **sí cumple** renovación en GPA y en número de reprobadas.
- Debe dirigirse al alumno por su nombre y citar el reglamento cuando corresponda.

---

## Pregunta 4 — Tool (datos del alumno + reglamento)

**Matrícula:** `2024002` (María López)

**Pregunta:**

> Según mi decil y mi situación académica, ¿podría postular a la Beca de Alimentación Universitaria (BAU)?

**Qué validar:**

- Usa datos de la tool: decil **2**, GPA **4.9**, **2** reprobadas, nombre **María**.
- Decil 2: **sí** encaja en BAU (deciles 1–4 prioritarios; Página 1).
- Puede aclarar requisitos BAU: carga mínima de 3 asignaturas, subsidio 45.000 CLP, etc.
- Puede contrastar con BAI (GPA ≥ 5.0) o renovación (2+ reprobadas = pérdida de beneficio; Página 2).
- Respuesta personalizada, no genérica.

---

## Pregunta 5 — Sin información en el reglamento

**Matrícula:** `2024001` (o `2024002`)

**Pregunta:**

> ¿Cuál es el horario de atención del departamento de deportes universitario?

**Qué validar:**

- El PDF **no** contiene esa información (solo becas, renovación, apelación, bienestar mental y tutorías).
- Debe responder con el mensaje indicado en el system prompt, en esencia:
  - *"Lo siento, no encontré esa información en el reglamento oficial de la universidad. Te sugiero contactar directamente al Departamento de Bienestar Estudiantil."*
- **No** debe inventar horarios ni datos.

**Otras preguntas equivalentes** (fuera del reglamento):

- Fechas de vacaciones de verano
- Proceso de intercambio internacional
- Arancel de una carrera específica
- Horario de la biblioteca central

---

## Resumen rápido

| # | Tipo        | Matrícula  | Objetivo de la prueba                          |
|---|-------------|------------|------------------------------------------------|
| 1 | RAG         | Cualquiera | Requisitos BAI desde el PDF                    |
| 2 | RAG         | Cualquiera | Plazo de apelación (10 días hábiles)           |
| 3 | Tool + RAG  | `2024001`  | Renovación según GPA y reprobadas de Juan      |
| 4 | Tool + RAG  | `2024002`  | Elegibilidad BAU según decil y notas de María  |
| 5 | Sin respuesta | Cualquiera | Reconocer límite del reglamento (deportes)     |

---

## Checklist de ejecución

- [ ] Backend en ejecución sin errores de API Groq
- [ ] Pregunta 1: cita Página 1 y requisitos BAI correctos
- [ ] Pregunta 2: cita Página 2 y plazo de 10 días hábiles
- [ ] Pregunta 3: usa nombre y datos de `2024001`
- [ ] Pregunta 4: usa nombre y datos de `2024002`
- [ ] Pregunta 5: mensaje de “no encontré en el reglamento”, sin inventar
- [ ] Matrícula inválida: mensaje de matrícula no encontrada
