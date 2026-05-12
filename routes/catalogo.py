from flask import Blueprint, render_template, redirect, url_for, session, request
from database import get_db_connection

catalogo_bp = Blueprint('catalogo', __name__)


def _solo_admin():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if session.get('rol') != 'Administrador':
        return redirect(url_for('ventas.index'))
    return None


@catalogo_bp.route('/catalogo')
def ver_catalogo():
    redir = _solo_admin()
    if redir: return redir

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id_categoria, nombre_categoria FROM categorias ORDER BY nombre_categoria ASC")
    lista_categorias = cur.fetchall()

    cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales ORDER BY nombre_sucursal ASC")
    lista_sucursales = cur.fetchall()

    cur.execute("SELECT id_producto, nombre FROM productos ORDER BY nombre ASC")
    lista_productos = cur.fetchall()

    cur.execute("SELECT mensaje, fecha_alerta FROM alertas_inventario ORDER BY fecha_alerta DESC LIMIT 5")
    alertas = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('catalogo.html',
                           lista_categorias=lista_categorias,
                           lista_sucursales=lista_sucursales,
                           lista_productos=lista_productos,
                           alertas=alertas)


@catalogo_bp.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    redir = _solo_admin()
    if redir: return redir

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO productos (id_categoria, nombre, formula, precio_venta) VALUES (%s, %s, %s, %s)",
            (
                request.form.get('id_categoria'),
                request.form.get('nombre'),
                request.form.get('formula'),
                request.form.get('precio_venta'),
            )
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al insertar producto: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('catalogo.ver_catalogo'))


@catalogo_bp.route('/agregar_lote', methods=['POST'])
def agregar_lote():
    redir = _solo_admin()
    if redir: return redir

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO lotes (id_producto, id_sucursal, codigo_lote, fecha_caducidad, stock_actual, precio_compra, fecha_entrega)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                request.form.get('id_producto'),
                request.form.get('id_sucursal'),
                request.form.get('codigo'),
                request.form.get('fecha_caducidad'),
                request.form.get('cantidad'),
                request.form.get('precio'),
                request.form.get('fecha_entrega'),
            )
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al insertar lote: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('catalogo.ver_catalogo'))
