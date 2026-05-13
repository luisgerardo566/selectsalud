from flask import Blueprint, render_template, redirect, url_for, session

admin_bp = Blueprint('admin', __name__)


def _requiere_admin():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('auth.login'))
    return None

def _requiere_admin_o_gerente():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if session.get('rol') not in ('Administrador', 'Gerente'):
        return redirect(url_for('ventas.index'))
    return None


# ── Dashboard Administrador ───────────────────────────────────

@admin_bp.route('/admin_dashboard')
def dashboard():
    redir = _requiere_admin()
    if redir: return redir
    return render_template('admin.html', nombre=session['nombre'])


# ── Dashboard Gerente ─────────────────────────────────────────

@admin_bp.route('/gerente_dashboard')
def gerente_dashboard():
    if 'user_id' not in session or session.get('rol') != 'Gerente':
        return redirect(url_for('auth.login'))
    return render_template('gerente.html', nombre=session['nombre'])


# ── Selector de sucursal (solo Administrador) ─────────────────

@admin_bp.route('/selector/<tipo_flujo>')
def mostrar_selector(tipo_flujo):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

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
def ir_a_tabla(modo, sucursal):
    redir = _requiere_admin()
    if redir: return redir

    session['sucursal_seleccionada'] = sucursal
    session['carrito'] = []
    session.modified = True

    if modo == 'Venta':
        return redirect(url_for('ventas.index'))
    return redirect(url_for('inventario.ver_inventario'))