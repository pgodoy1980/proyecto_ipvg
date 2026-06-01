import sqlite3
import os

DB_FILE = "universidad.db"

def crear_e_inicializar_db():
    """
    Script independiente para la creación y población de la base de datos SQLite.
    Separa la persistencia de datos de la lógica del servidor FastAPI.
    """
    print(f"[*] Iniciando la creación de la base de datos en: '{DB_FILE}'...")
    
    # Establece conexión con el motor SQLite (si el archivo no existe, lo crea automáticamente)
    conexion = sqlite3.connect(DB_FILE)
    cursor = conexion.cursor()
    
    # 1. Creación de la Tabla 'alumnos' (Datos socioeconómicos y notas generales)
    print("[+] Creando tabla 'alumnos'...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alumnos (
            matricula TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            gpa REAL NOT NULL,
            reprobados INTEGER NOT NULL,
            decil INTEGER NOT NULL
        )
    """)
    
    # 2. Creación de la Tabla 'progreso_curricular' (Avance de asignaturas para procesos de práctica)
    print("[+] Creando tabla 'progreso_curricular'...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progreso_curricular (
            matricula TEXT PRIMARY KEY,
            asignaturas_totales INTEGER NOT NULL,
            asignaturas_aprobadas INTEGER NOT NULL,
            FOREIGN KEY(matricula) REFERENCES alumnos(matricula)
        )
    """)
    
    # 3. Población de datos de prueba (Solo si la base de datos está vacía)
    cursor.execute("SELECT COUNT(*) FROM alumnos")
    if cursor.fetchone()[0] == 0:
        print("[+] Insertando registros iniciales de prueba...")
        
        # Datos para la tabla de alumnos generales
        alumnos_iniciales = [
            ("2024001", "Juan Pérez", 5.4, 1, 3), # Alumno apto para becas y práctica (90% avance)
            ("2024002", "María López", 4.9, 2, 2) # Alumna en alerta por becas y práctica (70% avance)
        ]
        cursor.executemany("INSERT INTO alumnos VALUES (?, ?, ?, ?, ?)", alumnos_iniciales)
        
        # Datos para la tabla de progreso curricular
        progreso_inicial = [
            ("2024001", 40, 36), # 36/40 = 90.0% de avance
            ("2024002", 40, 28)  # 28/40 = 70.0% de avance
        ]
        cursor.executemany("INSERT INTO progreso_curricular VALUES (?, ?, ?)", progreso_inicial)
        
        # Confirma y guarda físicamente las transacciones en el archivo .db
        conexion.commit()
        print("[OK] Base de datos creada, estructurada y poblada exitosamente.")
    else:
        print("[!] La base de datos ya contiene registros. No se realizaron modificaciones.")
        
    # Cierra los descriptores de conexión para liberar el archivo en el sistema operativo
    conexion.close()

if __name__ == "__main__":
    crear_e_inicializar_db()