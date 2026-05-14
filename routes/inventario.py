from flask import Blueprint, render_template, redirect, url_for, session, request
from database import get_db_connection, get_nombre_sucursal
from datetime import date

inventario_bp = Blueprint('inventario', __name__)

ROLES_SUCURSAL = ('Farmaceutico', 'Gerente')


@inventario_bp.route('/inventario')
def ver_inventario():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Filtros desde query params
    filtro_producto  = request.args.get('producto', '').strip()
    filtro_lote      = request.args.get('lote', '').strip()
    filtro_sucursal  = request.args.get('sucursal', '').strip()
    filtro_stock     = request.args.get('stock', '').strip()   # 'critico' | 'ok'
    filtro_caducidad = request.args.get('caducidad', '').strip()  # 'vencido' | 'proximo' | 'ok'

    conn = get_db_connection()
    cur = conn.cursor()

    base_query = """
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE 1=1
    """
    params = []

    if session.get('rol') == 'Administrador':
        sucursal_f = session.get('sucursal_seleccionada', 'General')
        if sucursal_f != 'General':
            base_query += " AND s.nombre_sucursal ILIKE %s"
            params.append(f"%{sucursal_f}%")
    else:
        sucursal_f = get_nombre_sucursal(session['id_sucursal_user'])
        base_query += " AND l.id_sucursal = %s"
        params.append(session['id_sucursal_user'])

    # Aplicar filtros
    if filtro_producto:
        base_query += " AND p.nombre ILIKE %s"
        params.append(f"%{filtro_producto}%")
    if filtro_lote:
        base_query += " AND l.codigo_lote ILIKE %s"
        params.append(f"%{filtro_lote}%")
    if filtro_sucursal and session.get('rol') == 'Administrador' and sucursal_f == 'General':
        base_query += " AND s.nombre_sucursal ILIKE %s"
        params.append(f"%{filtro_sucursal}%")
    if filtro_stock == 'critico':
        base_query += " AND l.stock_actual < 10"
    elif filtro_stock == 'ok':
        base_query += " AND l.stock_actual >= 10"

    hoy = date.today()
    if filtro_caducidad == 'vencido':
        base_query += " AND l.fecha_caducidad < %s"
        params.append(hoy)
    elif filtro_caducidad == 'proximo':
        base_query += " AND l.fecha_caducidad BETWEEN %s AND %s"
        params.extend([hoy, hoy.replace(month=hoy.month % 12 + 1, day=1) if hoy.month < 12
                        else hoy.replace(year=hoy.year + 1, month=1, day=1)])
    elif filtro_caducidad == 'ok':
        base_query += " AND l.fecha_caducidad > %s"
        params.append(hoy)

    base_query += " ORDER BY s.nombre_sucursal ASC, l.fecha_caducidad ASC"
    cur.execute(base_query, params)
    productos = cur.fetchall()
    total_dinero = sum(p[1] * p[4] for p in productos)

    cur.execute("SELECT nombre_sucursal FROM sucursales ORDER BY nombre_sucursal")
    lista_sucursales = [s[0] for s in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('inventario_visual.html',
                           productos=productos,
                           sucursal=sucursal_f,
                           total_dinero=total_dinero,
                           hoy=hoy,
                           lista_sucursales=lista_sucursales)