import psycopg2
from config import DB_CONN_STR


def get_db_connection():
    try:
        conn = psycopg2.connect(DB_CONN_STR)
        conn.set_client_encoding('UTF8')
        return conn
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None


def get_nombre_sucursal(id_sucursal):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nombre_sucursal FROM sucursales WHERE id_sucursal = %s", (id_sucursal,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else 'Sucursal'