from flask import Blueprint, render_template, redirect, url_for, session
from database import get_db_connection, get_nombre_sucursal
from datetime import date

inventario_bp = Blueprint('inventario', __name__)

ROLES_SUCURSAL = ('Farmaceutico', 'Gerente')


@inventario_bp.route('/inventario')
def ver_inventario():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cur = conn.cursor()

    base_query = '''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal,
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
    '''

    if session.get('rol') == 'Administrador':
        sucursal_f = session.get('sucursal_seleccionada', 'General')
        if sucursal_f == 'General':
            cur.execute(base_query + " ORDER BY s.nombre_sucursal ASC")
        else:
            cur.execute(
                base_query + " WHERE s.nombre_sucursal ILIKE %s ORDER BY s.nombre_sucursal ASC",
                (f"%{sucursal_f}%",)
            )
    else:
        # Farmacéutico y Gerente: solo su sucursal
        sucursal_f = get_nombre_sucursal(session['id_sucursal_user'])
        cur.execute(base_query + " WHERE l.id_sucursal = %s", (session['id_sucursal_user'],))

    productos = cur.fetchall()
    total_dinero = sum(p[1] * p[4] for p in productos)

    cur.close()
    conn.close()

    return render_template('inventario_visual.html',
                           productos=productos,
                           sucursal=sucursal_f,
                           total_dinero=total_dinero,
                           hoy=date.today())