from functools import wraps
from flask import session, redirect, url_for


def login_required(f):
    """Redirige a login si no hay sesión activa."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def roles_required(*roles, redirect_to='ventas.index'):
    """
    Verifica que el usuario tenga uno de los roles indicados.
    Si no hay sesión → login. Si no tiene el rol → redirect_to.

    Uso:
        @roles_required('Administrador')
        @roles_required('Administrador', 'Gerente')
        @roles_required('Gerente', redirect_to='auth.login')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if session.get('rol') not in roles:
                return redirect(url_for(redirect_to))
            return f(*args, **kwargs)
        return decorated
    return decorator