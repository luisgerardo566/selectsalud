from flask import Blueprint, render_template, redirect, url_for, session

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin_dashboard')
def dashboard():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('auth.login'))
    return render_template('admin.html', nombre=session['nombre'])


@admin_bp.route('/selector/<tipo_flujo>')
def mostrar_selector(tipo_flujo):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Farmacéutico: saltar selector, ir directo a su sucursal
    if session.get('rol') != 'Administrador':
        session['carrito'] = []
        session.modified = True
        if tipo_flujo == 'Venta':
            return redirect(url_for('ventas.index'))
        return redirect(url_for('inventario.ver_inventario'))

    return render_template('seleccionar_sucursal.html', modo=tipo_flujo)


@admin_bp.route('/ir_a_tabla/<modo>/<sucursal>')
def ir_a_tabla(modo, sucursal):
    session['sucursal_seleccionada'] = sucursal
    session['carrito'] = []
    session.modified = True

    if modo == 'Venta':
        return redirect(url_for('ventas.index'))
    return redirect(url_for('inventario.ver_inventario'))
