from flask import Blueprint, render_template, redirect, url_for, session, request
from werkzeug.security import generate_password_hash
from database import get_db_connection

usuarios_bp = Blueprint('usuarios', __name__)


def _solo_admin():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if session.get('rol') != 'Administrador':
        return redirect(url_for('ventas.index'))
    return None


@usuarios_bp.route('/usuarios')
def ver_usuarios():
    redir = _solo_admin()
    if redir: return redir

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        SELECT u.id_usuario, u.nombre_usuario, u.rol, s.nombre_sucursal
        FROM usuarios u
        JOIN sucursales s ON u.id_sucursal = s.id_sucursal
        ORDER BY u.rol ASC, u.nombre_usuario ASC
    ''')
    lista_usuarios = cur.fetchall()

    cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales ORDER BY nombre_sucursal ASC")
    lista_sucursales = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('usuarios.html',
                           lista_usuarios=lista_usuarios,
                           lista_sucursales=lista_sucursales)


@usuarios_bp.route('/agregar_usuario', methods=['POST'])
def agregar_usuario():
    redir = _solo_admin()
    if redir: return redir

    nombre   = request.form.get('nombre_usuario', '').strip()
    password = request.form.get('password', '').strip()
    rol      = request.form.get('rol', '').strip()
    id_suc   = request.form.get('id_sucursal', '').strip()

    if not all([nombre, password, rol, id_suc]):
        return redirect(url_for('usuarios.ver_usuarios'))

    hashed = generate_password_hash(password, method='scrypt')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO usuarios (nombre_usuario, password_hash, rol, id_sucursal) VALUES (%s, %s, %s, %s)",
            (nombre, hashed, rol, id_suc)
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al agregar usuario: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('usuarios.ver_usuarios'))


@usuarios_bp.route('/eliminar_usuario/<int:id_usuario>', methods=['POST'])
def eliminar_usuario(id_usuario):
    redir = _solo_admin()
    if redir: return redir

    # Evitar que el admin se elimine a sí mismo
    if id_usuario == session.get('user_id'):
        return redirect(url_for('usuarios.ver_usuarios'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        conn.commit()
    except Exception as e:
        print(f"❌ Error al eliminar usuario: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('usuarios.ver_usuarios'))


@usuarios_bp.route('/cambiar_password/<int:id_usuario>', methods=['POST'])
def cambiar_password(id_usuario):
    redir = _solo_admin()
    if redir: return redir

    nueva = request.form.get('nueva_password', '').strip()
    if not nueva:
        return redirect(url_for('usuarios.ver_usuarios'))

    hashed = generate_password_hash(nueva, method='scrypt')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
            (hashed, id_usuario)
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error al cambiar contraseña: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('usuarios.ver_usuarios'))