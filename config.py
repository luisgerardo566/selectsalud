from datetime import timedelta
from dotenv import load_dotenv
import os

load_dotenv()  # Carga las variables desde .env

# ── App ───────────────────────────────────────────────────────
SECRET_KEY = os.getenv('SECRET_KEY')
PERMANENT_SESSION_LIFETIME = timedelta(hours=1)

# ── Sucursal configurada en esta instalación ──────────────────
# Cambia este número según la sucursal donde está corriendo la app.
# El Administrador ignora este valor y puede acceder a todo.
SUCURSAL_ID = 3

# ── Conexión a la DB ──────────────────────────────────────────
# La app usa un solo usuario postgres. El control de acceso
# se maneja por rol de la tabla usuarios en Flask.
# Los roles rol_monitoreo y rol_desarrollador están disponibles
# para conectarse directamente desde DBeaver/pgAdmin.
DB_CONN_STR = (
    f"host='{os.getenv('DB_HOST')}' "
    f"port='{os.getenv('DB_PORT')}' "
    f"dbname='{os.getenv('DB_NAME')}' "
    f"user='{os.getenv('DB_USER')}' "
    f"password='{os.getenv('DB_PASSWORD')}'"
)