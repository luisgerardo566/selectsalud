from flask import Blueprint, render_template, redirect, url_for, session
from utils.decorators import login_required, roles_required

admin_bp = Blueprint('admin', __name__)


# ── Dashboard Administrador ───────────────────────────────────

@admin_bp.route('/admin_dashboard')
@roles_required('Administrador', redirect_to='auth.login')
def dashboard():
    return render_template('admin.html', nombre=session['nombre'])


# ── Dashboard Gerente ─────────────────────────────────────────

@admin_bp.route('/gerente_dashboard')
@roles_required('Gerente', redirect_to='auth.login')
def gerente_dashboard():
    return render_template('gerente.html', nombre=session['nombre'])


# ── Selector de sucursal ──────────────────────────────────────

@admin_bp.route('/selector/<tipo_flujo>')
@login_required
def mostrar_selector(tipo_flujo):
    rol = session.get('rol')

    # Farmacéutico y Gerente: saltar selector, ir directo
    if rol != 'Administrador':
        session['carrito'] = []
        session.modified = True
        if tipo_flujo == 'Venta':
            return redirect(url_for('ventas.index'))
        return redirect(url_for('inventario.ver_inventario'))

    return render_template('seleccionar_sucursal.html', modo=tipo_flujo)


@admin_bp.route('/ir_a_tabla/<modo>/<sucursal>')
@roles_required('Administrador', redirect_to='auth.login')
def ir_a_tabla(modo, sucursal):
    session['sucursal_seleccionada'] = sucursal
    session['carrito'] = []
    session.modified = True

    if modo == 'Venta':
        return redirect(url_for('ventas.index'))
    return redirect(url_for('inventario.ver_inventario'))