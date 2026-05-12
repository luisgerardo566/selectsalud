from flask import Blueprint, render_template, redirect, url_for, session, request
from werkzeug.security import check_password_hash
from werkzeug.exceptions import TooManyRequests
from database import get_db_connection

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('admin.dashboard') if session['rol'] == 'Administrador' else url_for('ventas.index'))

    if request.method == 'POST':
        usuario_form = request.form.get('username')
        password_form = request.form.get('password')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT id_usuario, nombre_usuario, password_hash, rol, id_sucursal FROM usuarios WHERE nombre_usuario = %s',
            (usuario_form,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[2].strip(), password_form):
            session.clear()
            session.permanent = True
            session['user_id'] = user[0]
            session['nombre']  = user[1]
            session['rol']     = user[3]
            session['id_sucursal_user'] = user[4]
            session['carrito'] = []

            if session['rol'] == 'Administrador':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('ventas.index'))

        return render_template('login.html', error="Usuario o contraseña incorrectos.")

    return render_template('login.html')


@auth_bp.errorhandler(429)
def rate_limit_handler(e):
    return render_template('login.html', rate_limited=True), 429


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))