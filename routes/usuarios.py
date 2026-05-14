from flask import Blueprint, render_template, redirect, url_for, session, request
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
from utils.decorators import roles_required

usuarios_bp = Blueprint('usuarios', __name__)


# ── Helpers internos ──────────────────────────────────────────

def _get_usuario(cur, id_usuario):
    """Devuelve (rol, id_sucursal) del usuario o None."""
    cur.execute("SELECT rol, id_sucursal FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    return cur.fetchone()

def _gerente_puede_modificar(target, id_sucursal_gerente):
    """Verifica que el Gerente solo toque Farmacéuticos de su sucursal."""
    return target and target[0] == 'Farmaceutico' and target[1] == id_sucursal_gerente

def _verificar_password_sesion(password_ingresada):
    """Devuelve True si la contraseña coincide con la del usuario en sesión."""
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT password_hash FROM usuarios WHERE id_usuario = %s", (session['user_id'],))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return bool(row and check_password_hash(row[0], password_ingresada))

def _aplicar_edicion(id_usuario, rol_nuevo, id_suc, nueva_pw=None):
    """Actualiza rol, sucursal y opcionalmente la contraseña de un usuario."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE usuarios SET rol = %s, id_sucursal = %s WHERE id_usuario = %s",
            (rol_nuevo, id_suc, id_usuario)
        )
        if nueva_pw:
            hashed = generate_password_hash(nueva_pw, method='scrypt')
            cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                (hashed, id_usuario)
            )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al editar usuario: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


# ── Rutas ─────────────────────────────────────────────────────

@usuarios_bp.route('/usuarios')
@roles_required('Administrador', 'Gerente')
def ver_usuarios():
    rol    = session.get('rol')
    id_suc = session.get('id_sucursal_user')

    conn = get_db_connection()
    cur = conn.cursor()

    if rol == 'Gerente':
        cur.execute('''
            SELECT u.id_usuario, u.nombre_usuario, u.rol, s.nombre_sucursal, u.id_sucursal
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id_sucursal
            WHERE u.rol IN ('Farmaceutico','Gerente') AND u.id_sucursal = %s
            ORDER BY u.nombre_usuario ASC
        ''', (id_suc,))
    else:
        cur.execute('''
            SELECT u.id_usuario, u.nombre_usuario, u.rol, s.nombre_sucursal, u.id_sucursal
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id_sucursal
            ORDER BY u.rol ASC, u.nombre_usuario ASC
        ''')
    lista_usuarios = cur.fetchall()

    if rol == 'Gerente':
        cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales WHERE id_sucursal = %s", (id_suc,))
    else:
        cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales ORDER BY nombre_sucursal ASC")
    lista_sucursales = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('usuarios.html',
                           lista_usuarios=lista_usuarios,
                           lista_sucursales=lista_sucursales,
                           es_gerente=(rol == 'Gerente'))


@usuarios_bp.route('/agregar_usuario', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def agregar_usuario():
    rol_sesion = session.get('rol')
    nombre     = request.form.get('nombre_usuario', '').strip()
    password   = request.form.get('password', '').strip()
    rol_nuevo  = request.form.get('rol', '').strip()
    id_suc     = request.form.get('id_sucursal', '').strip()

    # Gerente solo puede crear Farmacéuticos en su sucursal
    if rol_sesion == 'Gerente':
        rol_nuevo = 'Farmaceutico'
        id_suc    = str(session.get('id_sucursal_user'))

    if not all([nombre, password, rol_nuevo, id_suc]):
        return redirect(url_for('usuarios.ver_usuarios'))

    hashed = generate_password_hash(password, method='scrypt')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO usuarios (nombre_usuario, password_hash, rol, id_sucursal) VALUES (%s, %s, %s, %s)",
            (nombre, hashed, rol_nuevo, id_suc)
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al agregar usuario: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('usuarios.ver_usuarios'))


@usuarios_bp.route('/editar_usuario/<int:id_usuario>', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def editar_usuario(id_usuario):
    rol_sesion = session.get('rol')
    rol_nuevo  = request.form.get('rol', '').strip()
    id_suc     = request.form.get('id_sucursal', '').strip()
    nueva_pw   = request.form.get('nueva_password', '').strip()

    if rol_sesion == 'Gerente':
        rol_nuevo = 'Farmaceutico'
        id_suc    = str(session.get('id_sucursal_user'))
        conn = get_db_connection()
        cur  = conn.cursor()
        target = _get_usuario(cur, id_usuario)
        cur.close()
        conn.close()
        if not _gerente_puede_modificar(target, session.get('id_sucursal_user')):
            return redirect(url_for('usuarios.ver_usuarios'))

    if not all([rol_nuevo, id_suc]):
        return redirect(url_for('usuarios.ver_usuarios'))

    # Si viene nueva contraseña, requiere verificación por la ruta verificar_password_actual
    _aplicar_edicion(id_usuario, rol_nuevo, id_suc, nueva_pw or None)
    return redirect(url_for('usuarios.ver_usuarios'))


@usuarios_bp.route('/verificar_password_actual', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def verificar_password_actual():
    """Valida la contraseña del usuario en sesión antes de aplicar cambio de contraseña."""
    pw_actual  = request.form.get('pw_actual', '').strip()
    id_destino = request.form.get('id_usuario_destino', '').strip()
    rol_nuevo  = request.form.get('rol', '').strip()
    id_suc     = request.form.get('id_sucursal', '').strip()
    nueva_pw   = request.form.get('nueva_password', '').strip()

    if not _verificar_password_sesion(pw_actual):
        return redirect(url_for('usuarios.ver_usuarios', error_pw='1', target=id_destino))

    rol_sesion = session.get('rol')
    if rol_sesion == 'Gerente':
        rol_nuevo = 'Farmaceutico'
        id_suc    = str(session.get('id_sucursal_user'))

    _aplicar_edicion(id_destino, rol_nuevo, id_suc, nueva_pw or None)
    return redirect(url_for('usuarios.ver_usuarios', exito_pw='1'))


@usuarios_bp.route('/verificar_password_eliminar/<int:id_usuario>', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def verificar_password_eliminar(id_usuario):
    if id_usuario == session.get('user_id'):
        return redirect(url_for('usuarios.ver_usuarios'))

    pw_actual = request.form.get('pw_actual_eliminar', '').strip()
    if not _verificar_password_sesion(pw_actual):
        return redirect(url_for('usuarios.ver_usuarios', error_eliminar='1'))

    if session.get('rol') == 'Gerente':
        conn = get_db_connection()
        cur  = conn.cursor()
        target = _get_usuario(cur, id_usuario)
        cur.close()
        conn.close()
        if not _gerente_puede_modificar(target, session.get('id_sucursal_user')):
            return redirect(url_for('usuarios.ver_usuarios'))

    _eliminar_usuario_db(id_usuario)
    return redirect(url_for('usuarios.ver_usuarios', exito_eliminar='1'))


@usuarios_bp.route('/eliminar_usuario/<int:id_usuario>', methods=['POST'])
@roles_required('Administrador', 'Gerente')
def eliminar_usuario(id_usuario):
    if id_usuario == session.get('user_id'):
        return redirect(url_for('usuarios.ver_usuarios'))

    if session.get('rol') == 'Gerente':
        conn = get_db_connection()
        cur  = conn.cursor()
        target = _get_usuario(cur, id_usuario)
        cur.close()
        conn.close()
        if not _gerente_puede_modificar(target, session.get('id_sucursal_user')):
            return redirect(url_for('usuarios.ver_usuarios'))

    _eliminar_usuario_db(id_usuario)
    return redirect(url_for('usuarios.ver_usuarios'))


def _eliminar_usuario_db(id_usuario):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        conn.commit()
    except Exception as e:
        print(f"❌ Error al eliminar usuario: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()