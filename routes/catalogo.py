from flask import Blueprint, render_template, redirect, url_for, session, request
from database import get_db_connection
from utils.decorators import roles_required

catalogo_bp = Blueprint('catalogo', __name__)


# ── Catálogo ──────────────────────────────────────────────────

@catalogo_bp.route('/catalogo')
@roles_required('Administrador', 'Gerente')
def ver_catalogo():
    rol    = session.get('rol')
    id_suc = session.get('id_sucursal_user')

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id_categoria, nombre_categoria FROM categorias ORDER BY nombre_categoria ASC")
    lista_categorias = cur.fetchall()

    cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales ORDER BY nombre_sucursal ASC")
    lista_sucursales = cur.fetchall()

    cur.execute("SELECT id_producto, nombre FROM productos ORDER BY nombre ASC")
    lista_productos = cur.fetchall()

    # Alertas: Gerente solo ve las de su sucursal
    if rol == 'Gerente':
        cur.execute("""
            SELECT a.mensaje, a.fecha_alerta
            FROM alertas_inventario a
            JOIN lotes l ON a.id_lote = l.id_lote
            WHERE l.id_sucursal = %s
            ORDER BY a.fecha_alerta DESC LIMIT 5
        """, (id_suc,))
    else:
        cur.execute("SELECT mensaje, fecha_alerta FROM alertas_inventario ORDER BY fecha_alerta DESC LIMIT 5")
    alertas = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('catalogo.html',
                           lista_categorias=lista_categorias,
                           lista_sucursales=lista_sucursales,
                           lista_productos=lista_productos,
                           alertas=alertas,
                           es_gerente=(rol == 'Gerente'))


# ── Agregar producto (solo Admin) ─────────────────────────────

@catalogo_bp.route('/agregar_producto', methods=['POST'])
@roles_required('Administrador')
def agregar_producto():
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


# ── Agregar lote ──────────────────────────────────────────────

@catalogo_bp.route('/agregar_lote', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def agregar_lote():
    rol    = session.get('rol')
    id_suc = request.form.get('id_sucursal')

    # Gerente: forzar que el lote sea de su sucursal
    if rol == 'Gerente':
        id_suc = str(session.get('id_sucursal_user'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO lotes (id_producto, id_sucursal, codigo_lote, fecha_caducidad, stock_actual, precio_compra, fecha_entrega)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                request.form.get('id_producto'),
                id_suc,
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