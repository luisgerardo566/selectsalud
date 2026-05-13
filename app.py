from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import config
from routes.auth      import auth_bp
from routes.admin     import admin_bp
from routes.ventas    import ventas_bp
from routes.inventario import inventario_bp
from routes.catalogo  import catalogo_bp
from routes.usuarios import usuarios_bp

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.permanent_session_lifetime = config.PERMANENT_SESSION_LIFETIME

# Rate limiter
limiter = Limiter(key_func=get_remote_address, app=app)
limiter.limit("5 per 5 minute")(auth_bp)  # aplica solo al blueprint de auth

# Registrar blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ventas_bp)
app.register_blueprint(inventario_bp)
app.register_blueprint(catalogo_bp)
app.register_blueprint(usuarios_bp)

if __name__ == '__main__':
    app.run(debug=True)