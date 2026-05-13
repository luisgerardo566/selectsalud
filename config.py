from datetime import timedelta

# ── App ───────────────────────────────────────────────────────
SECRET_KEY = 'select_salud_v2_2026_final'
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
    "host='aws-1-us-east-1.pooler.supabase.com' "
    "port='5432' "
    "dbname='postgres' "
    "user='postgres.rwvvlmzaoeglnwodgdql' "
    "password='Axvze7k7Op.'"
)