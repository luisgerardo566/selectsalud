from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, redirect, url_for, request, session
import psycopg2
from datetime import datetime

app = Flask(__name__)
# Esta llave es necesaria para que las sesiones (carrito y login) funcionen
app.secret_key = 'clave_secreta'

# 1. CONFIGURACIÓN DE CONEXIÓN
def get_db_connection():
    conn_str = "host='127.0.0.1' port='5432' dbname='db_selectSalud' user='postgres' password='123456'"
    try:
        conn = psycopg2.connect(conn_str)
        conn.set_client_encoding('UTF8')
        return conn
    except Exception as e:
        print(f"❌ Error de conexión DB: {e}")
        return None

# 2. RUTA DE LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_form = request.form.get('username')
        password_form = request.form.get('password')
        
        conn = get_db_connection()
        if not conn: return "Error de conexión a la base de datos"
        
        cur = conn.cursor()
        # Asegúrate de que el orden sea este: 0:id, 1:nombre, 2:hash, 3:rol, 4:sucursal
        cur.execute('''
            SELECT id_usuario, nombre_usuario, password_hash, rol, id_sucursal 
            FROM usuarios 
            WHERE nombre_usuario = %s
        ''', (usuario_form,))
        
        user = cur.fetchone()
        cur.close()
        conn.close()

        # --- SECCIÓN DE DEBUG (Mira tu terminal de Python al intentar entrar) ---
        if user:
            # .strip() elimina espacios en blanco que pueda agregar el tipo de dato CHAR en Postgres
            hash_db = user[2].strip() 
            coincide = check_password_hash(hash_db, password_form)
            
            print(f"\n--- INTENTO DE LOGIN: {usuario_form} ---")
            print(f"Hash recuperado: {hash_db[:30]}...") # Solo imprimimos el inicio por seguridad
            print(f"¿La contraseña coincide?: {coincide}")
            print("------------------------------------\n")

            if coincide:
                session['user_id'] = user[0]
                session['nombre'] = user[1]
                session['rol'] = user[3]
                session['id_sucursal_user'] = user[4]
                return redirect(url_for('index'))
        
        # Si llegamos aquí, algo falló
        return "<h1>❌ Usuario o contraseña incorrectos</h1><p>Revisa la terminal para más detalles.</p><a href='/login'>Intentar de nuevo</a>"
            
    return render_template('login.html')
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 3. RUTA PRINCIPAL (INVENTARIO)
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Filtrado por Roles (RBAC)
    if session['rol'] == 'Administrador':
        query = '''
            SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote 
            FROM productos p
            LEFT JOIN lotes l ON p.id_producto = l.id_producto
            LEFT JOIN sucursales s ON l.id_sucursal = s.id_sucursal
            ORDER BY s.nombre_sucursal ASC;
        '''
        cur.execute(query)
    else:
        query = '''
            SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote 
            FROM productos p
            LEFT JOIN lotes l ON p.id_producto = l.id_producto
            LEFT JOIN sucursales s ON l.id_sucursal = s.id_sucursal
            WHERE s.id_sucursal = %s;
        '''
        cur.execute(query, (session['id_sucursal_user'],))

    productos_data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', productos=productos_data, nombre=session['nombre'], rol=session['rol'])

# 4. GESTIÓN DEL CARRITO (TABLA TEMPORAL EN PYTHON)
@app.route('/agregar_carrito/<int:lote_id>', methods=['POST'])
def agregar_carrito(lote_id):
    if 'carrito' not in session:
        session['carrito'] = []
    
    sucursal_nueva = request.form.get('sucursal')
    
    # Validación de Sucursal Única (Cola de consistencia)
    if session['carrito'] and session['carrito'][0]['sucursal'] != sucursal_nueva:
        return f"<h1>🚫 Error de Logística</h1><p>No puedes mezclar productos de {sucursal_nueva} con la sucursal actual.</p><a href='/'>Volver</a>"

    carrito = session['carrito']
    carrito.append({
        'lote_id': lote_id,
        'nombre': request.form.get('nombre'),
        'sucursal': sucursal_nueva,
        'cantidad': int(request.form.get('cantidad')),
        'precio': 100.00 # Precio base
    })
    session['carrito'] = carrito
    session.modified = True 
    return redirect(url_for('index'))

@app.route('/limpiar_carrito')
def limpiar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('index'))


# 5. CONFIRMAR VENTA (TRANSACCIÓN FINAL)
@app.route('/confirmar_venta', methods=['POST'])
def confirmar_venta():
    carrito = session.get('carrito', [])
    if not carrito: return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        total_v = sum(item['precio'] * item['cantidad'] for item in carrito)
        
        # --- PASO DINÁMICO: Obtenemos el ID real de la sucursal del primer producto ---
        nombre_sucursal_carrito = carrito[0]['sucursal']
        
        cur.execute('SELECT id_sucursal FROM sucursales WHERE nombre_sucursal = %s', (nombre_sucursal_carrito,))
        sucursal_encontrada = cur.fetchone()
        
        if sucursal_encontrada:
            id_sucursal_real = sucursal_encontrada[0]
        else:
            # Por si algo falla, usamos la sucursal del usuario logueado como respaldo
            id_sucursal_real = session.get('id_sucursal_user', 1)

        # A. Cabecera con el ID dinámico
        cur.execute('''
            INSERT INTO ventas (fecha_hora, id_usuario, id_sucursal, total) 
            VALUES (CURRENT_TIMESTAMP, %s, %s, %s) RETURNING id_venta;
        ''', (session['user_id'], id_sucursal_real, total_v))
        
        id_v = cur.fetchone()[0]

        # B. Detalles y Stock (Esto se queda igual)
        for item in carrito:
            cur.execute('''
                INSERT INTO detalle_ventas (id_venta, id_lote, cantidad, precio_unitario) 
                VALUES (%s, %s, %s, %s)
            ''', (id_v, item['lote_id'], item['cantidad'], item['precio']))
            
            cur.execute('''
                UPDATE lotes SET stock_actual = stock_actual - %s 
                WHERE id_lote = %s
            ''', (item['cantidad'], item['lote_id']))

        conn.commit()
        session.pop('carrito', None)
        print(f"✅ Venta {id_v} registrada en sucursal ID: {id_sucursal_real}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error en Venta: {e}")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('index'))

# 6. HISTORIAL DE VENTAS
@app.route('/ventas')
def ver_ventas():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT DISTINCT v.fecha_hora, p.nombre, dv.cantidad, dv.precio_unitario, u.nombre_usuario, s.nombre_sucursal
        FROM detalle_ventas dv
        JOIN ventas v ON dv.id_venta = v.id_venta
        JOIN lotes l ON dv.id_lote = l.id_lote
        JOIN productos p ON l.id_producto = p.id_producto
        JOIN usuarios u ON v.id_usuario = u.id_usuario
        JOIN sucursales s ON v.id_sucursal = s.id_sucursal
        ORDER BY v.fecha_hora DESC;
    ''')
    historial = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ventas.html', ventas=historial)

if __name__ == '__main__':
    app.run(debug=True)