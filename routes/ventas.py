from flask import Blueprint, render_template, redirect, url_for, session, request
from database import get_db_connection, get_nombre_sucursal
from datetime import date, timedelta

ventas_bp = Blueprint('ventas', __name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sucursal_label_y_query_venta(cur, base_query):
    if session.get('rol') == 'Administrador':
        sucursal_f = session.get('sucursal_seleccionada', 'General')
        if sucursal_f == 'General':
            cur.execute(base_query + " ORDER BY s.nombre_sucursal ASC")
        else:
            cur.execute(
                base_query + " AND s.nombre_sucursal ILIKE %s ORDER BY s.nombre_sucursal ASC",
                (f"%{sucursal_f}%",)
            )
    else:
        sucursal_f = get_nombre_sucursal(session['id_sucursal_user'])
        cur.execute(base_query + " AND l.id_sucursal = %s", (session['id_sucursal_user'],))

    return sucursal_f, cur.fetchall()


# ── Rutas ─────────────────────────────────────────────────────────────────────

@ventas_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cur = conn.cursor()

    base_query = '''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE l.stock_actual > 0
    '''

    sucursal_f, productos = _sucursal_label_y_query_venta(cur, base_query)
    cur.close()
    conn.close()

    return render_template('index.html',
                           productos=productos,
                           sucursal=sucursal_f,
                           nombre=session.get('nombre'),
                           hoy=date.today())


@ventas_bp.route('/agregar_carrito/<int:lote_id>', methods=['POST'])
def agregar_carrito(lote_id):
    if 'carrito' not in session:
        session['carrito'] = []

    carrito = session['carrito']
    sucursal_real_lote = request.form.get('sucursal_origen')
    cantidad_nueva = int(request.form.get('cantidad', 1))

    if carrito and carrito[0].get('sucursal_origen') != sucursal_real_lote:
        return redirect(url_for('ventas.index'))

    for item in carrito:
        if item['lote_id'] == lote_id:
            item['cantidad'] += cantidad_nueva
            session['carrito'] = carrito
            session.modified = True
            return redirect(url_for('ventas.index'))

    carrito.append({
        'lote_id':         lote_id,
        'nombre':          request.form.get('nombre'),
        'cantidad':        cantidad_nueva,
        'precio':          float(request.form.get('precio')),
        'sucursal_origen': sucursal_real_lote,
    })
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/actualizar_cantidad/<int:index>/<accion>')
def actualizar_cantidad(index, accion):
    carrito = session.get('carrito', [])
    if 0 <= index < len(carrito):
        if accion == 'mas':
            carrito[index]['cantidad'] += 1
        elif accion == 'menos':
            carrito[index]['cantidad'] -= 1
            if carrito[index]['cantidad'] <= 0:
                carrito.pop(index)
        session['carrito'] = carrito
        session.modified = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/eliminar_item/<int:index>')
def eliminar_item(index):
    carrito = session.get('carrito', [])
    if 0 <= index < len(carrito):
        carrito.pop(index)
        session['carrito'] = carrito
        session.modified = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/limpiar_carrito')
def limpiar_carrito():
    session['carrito'] = []
    session.modified = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/confirmar_venta', methods=['POST'])
def confirmar_venta():
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('ventas.index'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id_sucursal FROM sucursales WHERE nombre_sucursal = %s",
            (session.get('sucursal_seleccionada'),)
        )
        res = cur.fetchone()
        suc_id = res[0] if res else session['id_sucursal_user']

        total_v = sum(item['precio'] * item['cantidad'] for item in carrito)
        cur.execute(
            'INSERT INTO ventas (fecha_hora, id_usuario, id_sucursal, total) VALUES (CURRENT_TIMESTAMP, %s, %s, %s) RETURNING id_venta',
            (session['user_id'], suc_id, total_v)
        )
        id_v = cur.fetchone()[0]

        for item in carrito:
            cur.execute(
                'INSERT INTO detalle_ventas (id_venta, id_lote, cantidad, precio_unitario) VALUES (%s, %s, %s, %s)',
                (id_v, item['lote_id'], item['cantidad'], item['precio'])
            )
            cur.execute(
                'UPDATE lotes SET stock_actual = stock_actual - %s WHERE id_lote = %s',
                (item['cantidad'], item['lote_id'])
            )

        conn.commit()
        session.pop('carrito', None)
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en venta: {e}")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('ventas.index'))


@ventas_bp.route('/ventas')
def ver_ventas():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Filtros desde la URL
    ticket_filtro   = request.args.get('ticket', '').strip()
    producto_filtro = request.args.get('producto', '').strip()
    vendedor_filtro = request.args.get('vendedor', '').strip()
    sucursal_filtro = request.args.get('sucursal', '').strip()
    periodo_filtro  = request.args.get('periodo', '').strip()

    conn = get_db_connection()
    cur = conn.cursor()

    query = '''
        SELECT DISTINCT v.id_venta, v.fecha_hora, u.nombre_usuario, s.nombre_sucursal, v.total
        FROM ventas v
        JOIN usuarios u ON v.id_usuario = u.id_usuario
        JOIN sucursales s ON v.id_sucursal = s.id_sucursal
        LEFT JOIN detalle_ventas dv ON v.id_venta = dv.id_venta
        LEFT JOIN lotes l ON dv.id_lote = l.id_lote
        LEFT JOIN productos p ON l.id_producto = p.id_producto
        WHERE 1=1
    '''
    params = []

    # Restricción por rol
    if session.get('rol') != 'Administrador':
        query += " AND v.id_sucursal = %s"
        params.append(session['id_sucursal_user'])

    # Filtro por No. Ticket
    if ticket_filtro:
        query += " AND CAST(v.id_venta AS TEXT) ILIKE %s"
        params.append(f"%{ticket_filtro}%")

    # Filtro por producto
    if producto_filtro:
        query += " AND p.nombre ILIKE %s"
        params.append(f"%{producto_filtro}%")

    # Filtro por vendedor
    if vendedor_filtro:
        query += " AND u.nombre_usuario ILIKE %s"
        params.append(f"%{vendedor_filtro}%")

    # Filtro por sucursal (solo admin)
    if sucursal_filtro and session.get('rol') == 'Administrador':
        query += " AND s.nombre_sucursal ILIKE %s"
        params.append(f"%{sucursal_filtro}%")

    # Filtro por período
    hoy = date.today()
    if periodo_filtro == 'hoy':
        query += " AND v.fecha_hora::date = %s"
        params.append(hoy)
    elif periodo_filtro == 'ayer':
        query += " AND v.fecha_hora::date = %s"
        params.append(hoy - timedelta(days=1))
    elif periodo_filtro == 'semana':
        query += " AND v.fecha_hora::date >= %s"
        params.append(hoy - timedelta(days=7))
    elif periodo_filtro == 'mes':
        query += " AND v.fecha_hora::date >= %s"
        params.append(hoy.replace(day=1))
    elif periodo_filtro == 'trimestre':
        query += " AND v.fecha_hora::date >= %s"
        params.append(hoy - timedelta(days=90))

    query += " ORDER BY v.fecha_hora DESC"
    cur.execute(query, params)
    ventas_maestro = cur.fetchall()

    # Listado de sucursales y vendedores para los selects
    cur.execute("SELECT nombre_sucursal FROM sucursales ORDER BY nombre_sucursal")
    listado_sucursales = [s[0] for s in cur.fetchall()]

    cur.execute("SELECT DISTINCT nombre_usuario FROM usuarios ORDER BY nombre_usuario")
    listado_vendedores = [u[0] for u in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('ventas.html',
                           ventas=ventas_maestro,
                           sucursales=listado_sucursales,
                           vendedores=listado_vendedores)


@ventas_bp.route('/venta_detalle/<int:id_venta>')
def venta_detalle(id_venta):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT p.nombre, dv.cantidad, dv.precio_unitario,
               (dv.cantidad * dv.precio_unitario) AS subtotal, p.formula
        FROM detalle_ventas dv
        JOIN lotes l ON dv.id_lote = l.id_lote
        JOIN productos p ON l.id_producto = p.id_producto
        WHERE dv.id_venta = %s
    ''', (id_venta,))

    detalles = cur.fetchall()
    total_venta = sum(f[3] for f in detalles)

    cur.close()
    conn.close()
    return render_template('detalle_modal.html',
                           detalles=detalles,
                           id_venta=id_venta,
                           total_venta=total_venta)