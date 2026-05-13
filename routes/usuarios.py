from flask import Blueprint, render_template, redirect, url_for, session, request
from werkzeug.security import generate_password_hash
from database import get_db_connection

usuarios_bp = Blueprint('usuarios', __name__)


def _acceso_usuarios():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if session.get('rol') not in ('Administrador', 'Gerente'):
        return redirect(url_for('ventas.index'))
    return None


@usuarios_bp.route('/usuarios')
def ver_usuarios():
    redir = _acceso_usuarios()
    if redir: return redir

    rol    = session.get('rol')
    id_suc = session.get('id_sucursal_user')

    conn = get_db_connection()
    cur = conn.cursor()

    if rol == 'Gerente':
        # Solo Farmacéuticos de su sucursal
        cur.execute('''
            SELECT u.id_usuario, u.nombre_usuario, u.rol, s.nombre_sucursal, u.id_sucursal
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id_sucursal
            WHERE u.rol = 'Farmaceutico' AND u.id_sucursal = %s
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
        # Gerente solo puede asignar a su propia sucursal
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
def agregar_usuario():
    redir = _acceso_usuarios()
    if redir: return redir

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
def editar_usuario(id_usuario):
    redir = _acceso_usuarios()
    if redir: return redir

    rol_sesion = session.get('rol')
    rol_nuevo  = request.form.get('rol', '').strip()
    id_suc     = request.form.get('id_sucursal', '').strip()
    nueva_pw   = request.form.get('nueva_password', '').strip()

    # Gerente: forzar que solo edite Farmacéuticos de su sucursal
    if rol_sesion == 'Gerente':
        rol_nuevo = 'Farmaceutico'
        id_suc    = str(session.get('id_sucursal_user'))

        # Verificar que el usuario a editar pertenece a su sucursal
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT rol, id_sucursal FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        target = cur.fetchone()
        cur.close()
        conn.close()
        if not target or target[0] != 'Farmaceutico' or target[1] != session.get('id_sucursal_user'):
            return redirect(url_for('usuarios.ver_usuarios'))

    if not all([rol_nuevo, id_suc]):
        return redirect(url_for('usuarios.ver_usuarios'))

    conn = get_db_connection()
    cur = conn.cursor()
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

    return redirect(url_for('usuarios.ver_usuarios'))


@usuarios_bp.route('/eliminar_usuario/<int:id_usuario>', methods=['POST'])
def eliminar_usuario(id_usuario):
    redir = _acceso_usuarios()
    if redir: return redir

    if id_usuario == session.get('user_id'):
        return redirect(url_for('usuarios.ver_usuarios'))

    rol_sesion = session.get('rol')

    # Gerente: verificar que el usuario a eliminar sea Farmacéutico de su sucursal
    if rol_sesion == 'Gerente':
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT rol, id_sucursal FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        target = cur.fetchone()
        cur.close()
        conn.close()
        if not target or target[0] != 'Farmaceutico' or target[1] != session.get('id_sucursal_user'):
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