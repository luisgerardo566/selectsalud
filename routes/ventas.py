from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
from database import get_db_connection, get_nombre_sucursal
from datetime import date, timedelta
from collections import defaultdict

ventas_bp = Blueprint('ventas', __name__)

ROLES_SUCURSAL = ('Farmaceutico', 'Gerente')
DIAS_BLOQUEO_CADUCIDAD = 30


# ── Helpers ───────────────────────────────────────────────────

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


def _clasificar_productos(productos, hoy):
    limite_bloqueo = hoy + timedelta(days=DIAS_BLOQUEO_CADUCIDAD)

    grupos = defaultdict(list)
    for p in productos:
        grupos[p[0]].append(p)

    # Lote preferente: caducidad primero, stock como desempate
    preferente_por_producto = {}
    for nombre, lotes in grupos.items():
        candidatos = [l for l in lotes if l[4] > limite_bloqueo]
        if candidatos:
            preferente_por_producto[nombre] = min(candidatos, key=lambda x: (x[4], x[1]))[3]

    resultado = []
    for p in productos:
        nombre, stock, sucursal, id_lote, fecha_cad, precio, cod_lote = p
        dias = (fecha_cad - hoy).days

        if fecha_cad <= limite_bloqueo:
            estado     = 'bloqueado'
            razon      = f'Caduca en {dias} dia(s) - no apto para venta'
            pref_id    = preferente_por_producto.get(nombre)
            sugerencia = next((x[6] for x in grupos[nombre] if x[3] == pref_id), '') if pref_id else ''

        elif id_lote != preferente_por_producto.get(nombre) and nombre in preferente_por_producto:
            pref_id   = preferente_por_producto[nombre]
            pref_lote = next((x for x in grupos[nombre] if x[3] == pref_id), None)
            sug_cod   = pref_lote[6] if pref_lote else ''

            if pref_lote and pref_lote[4] < fecha_cad:
                dias_diff = (fecha_cad - pref_lote[4]).days
                if dias_diff >= 7:
                    razon = f'El lote #{sug_cod} caduca {dias_diff} dia(s) antes - venderlo primero'
                else:
                    razon = f'El lote #{sug_cod} caduca antes - venderlo primero'
            else:
                razon = f'El lote #{sug_cod} tiene menos stock - agotarlo primero'

            estado     = 'advertencia'
            sugerencia = sug_cod

        else:
            estado     = 'preferente'
            razon      = ''
            sugerencia = ''

        resultado.append(p + (estado, razon, sugerencia))

    orden = {'preferente': 0, 'advertencia': 1, 'bloqueado': 2}
    resultado.sort(key=lambda x: (x[0], orden[x[7]], x[1]))
    return resultado


# ── Rutas ─────────────────────────────────────────────────────

@ventas_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cur  = conn.cursor()

    base_query = '''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE l.stock_actual > 0
    '''

    sucursal_f, productos_raw = _sucursal_label_y_query_venta(cur, base_query)
    cur.close()
    conn.close()

    hoy      = date.today()
    productos = _clasificar_productos(productos_raw, hoy)

    return render_template('index.html',
                           productos=productos,
                           sucursal=sucursal_f,
                           nombre=session.get('nombre'),
                           hoy=hoy,
                           dias_bloqueo=DIAS_BLOQUEO_CADUCIDAD)


@ventas_bp.route('/buscar_lote')
def buscar_lote():
    if 'user_id' not in session:
        return jsonify({'error': 'no auth'}), 401

    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])

    hoy    = date.today()
    limite = hoy + timedelta(days=DIAS_BLOQUEO_CADUCIDAD)

    extra  = ''
    params = [limite, f'%{q}%', f'%{q}%']

    if session.get('rol') != 'Administrador':
        extra = 'AND l.id_sucursal = %s'
        params.append(session['id_sucursal_user'])
    elif session.get('sucursal_seleccionada', 'General') != 'General':
        extra = 'AND s.nombre_sucursal ILIKE %s'
        params.append(f"%{session['sucursal_seleccionada']}%")

    conn = get_db_connection()
    cur  = conn.cursor()

    # Obtener los lotes que coinciden con la busqueda (excluye bloqueados)
    cur.execute(f'''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE l.stock_actual > 0
          AND l.fecha_caducidad > %s
          AND (l.codigo_lote ILIKE %s OR p.nombre ILIKE %s)
          {extra}
        ORDER BY l.stock_actual ASC
        LIMIT 10
    ''', params)
    rows_busqueda = cur.fetchall()

    # Obtener todos los lotes activos del mismo contexto para calcular preferentes
    extra_todos = extra.replace('AND l.id_sucursal = %s', 'AND l.id_sucursal = %s')
    cur.execute(f'''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE l.stock_actual > 0
          {extra_todos}
    ''', params[3:])
    todos = cur.fetchall()
    cur.close()
    conn.close()

    # Construir grupos y preferentes para clasificar cada lote encontrado
    grupos = defaultdict(list)
    for t in todos:
        grupos[t[0]].append(t)

    preferente_por_producto = {}
    for nombre_p, lotes_p in grupos.items():
        candidatos = [l for l in lotes_p if l[4] > limite]
        if candidatos:
            preferente_por_producto[nombre_p] = min(candidatos, key=lambda x: (x[4], x[1]))[3]

    resultado = []
    for r in rows_busqueda:
        nombre_r, stock_r, suc_r, id_lote_r, fecha_cad_r, precio_r, cod_r = r
        dias_r = (fecha_cad_r - hoy).days

        # Clasificar estado del lote encontrado
        pref_id = preferente_por_producto.get(nombre_r)
        if id_lote_r == pref_id or pref_id is None:
            estado_r, razon_r, sug_r = 'preferente', '', ''
        else:
            pref_lote = next((x for x in grupos[nombre_r] if x[3] == pref_id), None)
            sug_cod   = pref_lote[6] if pref_lote else ''
            if pref_lote and pref_lote[4] < fecha_cad_r:
                dias_diff = (fecha_cad_r - pref_lote[4]).days
                razon_r = f'El lote #{sug_cod} caduca {dias_diff} dia(s) antes - venderlo primero' if dias_diff >= 7                           else f'El lote #{sug_cod} caduca antes - venderlo primero'
            else:
                razon_r = f'El lote #{sug_cod} tiene menos stock - agotarlo primero'
            estado_r, sug_r = 'advertencia', sug_cod

        resultado.append({
            'nombre':     nombre_r,
            'stock':      stock_r,
            'sucursal':   suc_r,
            'id_lote':    id_lote_r,
            'caducidad':  fecha_cad_r.isoformat(),
            'precio':     float(precio_r),
            'codigo':     cod_r,
            'estado':     estado_r,
            'razon':      razon_r,
            'sugerencia': sug_r,
        })

    return jsonify(resultado)


@ventas_bp.route('/agregar_carrito/<int:lote_id>', methods=['POST'])
def agregar_carrito(lote_id):
    if 'carrito' not in session:
        session['carrito'] = []

    conn = get_db_connection()
    cur  = conn.cursor()
    """PROTECCIÓN ANTE SANCIONES SANITARIAS"""
    cur.execute("SELECT fecha_caducidad FROM lotes WHERE id_lote = %s", (lote_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        dias = (row[0] - date.today()).days
        if dias <= DIAS_BLOQUEO_CADUCIDAD:
            return redirect(url_for('ventas.index'))

    carrito            = session['carrito']
    sucursal_real_lote = request.form.get('sucursal_origen')
    cantidad_nueva     = int(request.form.get('cantidad', 1))

    if carrito and carrito[0].get('sucursal_origen') != sucursal_real_lote:
        return redirect(url_for('ventas.index'))

    for item in carrito:
        if item['lote_id'] == lote_id:
            item['cantidad'] += cantidad_nueva
            session['carrito'] = carrito
            session.modified   = True
            return redirect(url_for('ventas.index'))

    carrito.append({
        'lote_id':         lote_id,
        'nombre':          request.form.get('nombre'),
        'cantidad':        cantidad_nueva,
        'precio':          float(request.form.get('precio')),
        'sucursal_origen': sucursal_real_lote,
    })
    session['carrito'] = carrito
    session.modified   = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/agregar_carrito_scan', methods=['POST'])
def agregar_carrito_scan():
    if 'user_id' not in session:
        return jsonify({'error': 'no auth'}), 401

    data     = request.get_json()
    lote_id  = data.get('id_lote')
    nombre   = data.get('nombre')
    precio   = float(data.get('precio', 0))
    sucursal = data.get('sucursal')
    cantidad = int(data.get('cantidad', 1))

    if 'carrito' not in session:
        session['carrito'] = []

    carrito = session['carrito']
    if carrito and carrito[0].get('sucursal_origen') != sucursal:
        return jsonify({'error': 'sucursal_mismatch'}), 400

    for item in carrito:
        if item['lote_id'] == lote_id:
            item['cantidad'] += cantidad
            session['carrito'] = carrito
            session.modified   = True
            return jsonify({'ok': True, 'cantidad': item['cantidad']})

    carrito.append({
        'lote_id':         lote_id,
        'nombre':          nombre,
        'cantidad':        cantidad,
        'precio':          precio,
        'sucursal_origen': sucursal,
    })
    session['carrito'] = carrito
    session.modified   = True
    return jsonify({'ok': True, 'cantidad': cantidad})


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
        session.modified   = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/eliminar_item/<int:index>')
def eliminar_item(index):
    carrito = session.get('carrito', [])
    if 0 <= index < len(carrito):
        carrito.pop(index)
        session['carrito'] = carrito
        session.modified   = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/limpiar_carrito')
def limpiar_carrito():
    session['carrito'] = []
    session.modified   = True
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/confirmar_venta', methods=['POST'])
def confirmar_venta():
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('ventas.index'))

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id_sucursal FROM sucursales WHERE nombre_sucursal = %s",
            (session.get('sucursal_seleccionada'),)
        )
        res    = cur.fetchone()
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
        print(f"Error en venta: {e}")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('ventas.index'))


@ventas_bp.route('/ventas')
def ver_ventas():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    ticket_filtro   = request.args.get('ticket', '').strip()
    producto_filtro = request.args.get('producto', '').strip()
    vendedor_filtro = request.args.get('vendedor', '').strip()
    sucursal_filtro = request.args.get('sucursal', '').strip()
    periodo_filtro  = request.args.get('periodo', '').strip()

    conn = get_db_connection()
    cur  = conn.cursor()

    """MÁS COMPLEJA"""
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

    if session.get('rol') in ROLES_SUCURSAL:
        query += " AND v.id_sucursal = %s"
        params.append(session['id_sucursal_user'])

    if ticket_filtro:
        query += " AND CAST(v.id_venta AS TEXT) ILIKE %s"
        params.append(f"%{ticket_filtro}%")
    if producto_filtro:
        query += " AND p.nombre ILIKE %s"
        params.append(f"%{producto_filtro}%")
    if vendedor_filtro:
        query += " AND u.nombre_usuario ILIKE %s"
        params.append(f"%{vendedor_filtro}%")
    if sucursal_filtro and session.get('rol') == 'Administrador':
        query += " AND s.nombre_sucursal ILIKE %s"
        params.append(f"%{sucursal_filtro}%")

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
    cur  = conn.cursor()
    cur.execute('''
        SELECT p.nombre, dv.cantidad, dv.precio_unitario,
               (dv.cantidad * dv.precio_unitario) AS subtotal, p.formula
        FROM detalle_ventas dv
        JOIN lotes l ON dv.id_lote = l.id_lote
        JOIN productos p ON l.id_producto = p.id_producto
        WHERE dv.id_venta = %s
    ''', (id_venta,))

    detalles    = cur.fetchall()
    total_venta = sum(f[3] for f in detalles)
    cur.close()
    conn.close()

    return render_template('detalle_modal.html',
                           detalles=detalles,
                           id_venta=id_venta,
                           total_venta=total_venta)