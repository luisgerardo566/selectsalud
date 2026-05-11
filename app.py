from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, redirect, url_for, request, session
import psycopg2
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'select_salud_v2_2026_final'

# --- CONEXIÓN A DB ---
def get_db_connection():
    conn_str = "host='127.0.0.1' port='5432' dbname='db_selectSalud' user='postgres' password='123456'"
    try:
        conn = psycopg2.connect(conn_str)
        conn.set_client_encoding('UTF8')
        return conn
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None

# --- ACCESO (LOGIN) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard' if session['rol'] == 'Administrador' else 'index'))

    if request.method == 'POST':
        usuario_form = request.form.get('username')
        password_form = request.form.get('password')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id_usuario, nombre_usuario, password_hash, rol, id_sucursal FROM usuarios WHERE nombre_usuario = %s', (usuario_form,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[2].strip(), password_form):
            session.clear()
            session['user_id'] = user[0]
            session['nombre'] = user[1]
            session['rol'] = user[3]
            session['id_sucursal_user'] = user[4]
            session['carrito'] = []

            if session['rol'] == 'Administrador':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

# --- MENÚ PRINCIPAL (ADMIN) ---
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('login'))
    return render_template('admin.html', nombre=session['nombre'])

# --- SELECTOR DE SUCURSAL ---
@app.route('/selector/<tipo_flujo>')
def mostrar_selector(tipo_flujo):
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('seleccionar_sucursal.html', modo=tipo_flujo)

# --- MANEJADOR DE DIRECCIONAMIENTO ---
@app.route('/ir_a_tabla/<modo>/<sucursal>')
def ir_a_tabla(modo, sucursal):
    # 1. Guardamos la nueva sucursal seleccionada
    session['sucursal_seleccionada'] = sucursal
    
    # 2. LIMPIEZA: Vaciamos el carrito para que no se mezclen productos de sedes distintas
    session['carrito'] = [] 
    session.modified = True
    
    if modo == 'Venta':
        return redirect(url_for('index'))
    return redirect(url_for('ver_inventario'))
# --- VISTA DE PUNTO DE VENTA (Venta) ---
@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Recuperamos la sucursal del selector (por defecto 'General')
    sucursal_f = session.get('sucursal_seleccionada', 'General')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Base de la consulta
    query = '''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.id_lote, 
               l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
        WHERE l.stock_actual > 0
    '''
    
    # Si no es la vista General, filtramos por el nombre exacto de la DB
    # En la ruta de index (venta) y la de inventario, cambia el execute por esto:
    if sucursal_f == 'General':
        cur.execute(query + " ORDER BY s.nombre_sucursal ASC")
    else:
    # Usamos ILIKE y % para que encuentre el nombre aunque tenga espacios extra
        cur.execute(query + " AND s.nombre_sucursal ILIKE %s", (f"%{sucursal_f}%",))

    productos = cur.fetchall()
    cur.close()
    conn.close()
    
    # Pasamos 'productos' y 'sucursal' al HTML
    return render_template('index.html', 
                           productos=productos, 
                           sucursal=sucursal_f, 
                           nombre=session.get('nombre'), 
                           hoy=date.today())
# --- VISTA DE CONSULTA (Inventario) ---
@app.route('/inventario')
def ver_inventario():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    sucursal_f = session.get('sucursal_seleccionada', 'General')
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = '''
        SELECT p.nombre, l.stock_actual, s.nombre_sucursal, l.fecha_caducidad, p.precio_venta, l.codigo_lote
        FROM productos p
        JOIN lotes l ON p.id_producto = l.id_producto
        JOIN sucursales s ON l.id_sucursal = s.id_sucursal
    '''
    
    if sucursal_f == 'General':
        cur.execute(query + " ORDER BY s.nombre_sucursal ASC")
    else:
    # Usamos ILIKE y % para que encuentre el nombre aunque tenga espacios extra
        cur.execute(query + " AND s.nombre_sucursal ILIKE %s", (f"%{sucursal_f}%",))

    productos = cur.fetchall()
    
    # Calculamos el valor total para mostrarlo en el encabezado
    total_dinero = sum(p[1] * p[4] for p in productos)
    
    cur.close()
    conn.close()
    
    return render_template('inventario_visual.html', 
                           productos=productos, 
                           sucursal=sucursal_f, 
                           total_dinero=total_dinero, 
                           hoy=date.today())

# --- HISTORIAL DE VENTAS (Corregido para admin.html) ---
@app.route('/ventas')
def ver_ventas():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Capturamos filtros de la URL (si existen)
    sucursal_filtro = request.args.get('sucursal', '')
    producto_filtro = request.args.get('producto', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # CONSULTA MAESTRO: Obtenemos una fila por cada ticket de venta
    # Usamos DISTINCT y JOINS para poder filtrar por producto si es necesario
    query = '''
        SELECT DISTINCT v.id_venta, v.fecha_hora, u.nombre_usuario, s.nombre_sucursal, v.total
        FROM ventas v
        JOIN usuarios u ON v.id_usuario = u.id_usuario
        JOIN sucursales s ON v.id_sucursal = s.id_sucursal
        LEFT JOIN detalle_ventas dv ON v.id_venta = dv.id_venta
        LEFT JOIN lotes l ON dv.id_lote = l.id_lote
        LEFT JOIN productos p ON l.id_producto = p.id_producto
        WHERE 1=1
    '''
    params = []
    if sucursal_filtro:
        query += " AND s.nombre_sucursal ILIKE %s"
        params.append(f"%{sucursal_filtro}%")
    if producto_filtro:
        query += " AND p.nombre ILIKE %s"
        params.append(f"%{producto_filtro}%")
        
    query += " ORDER BY v.fecha_hora DESC"
    cur.execute(query, params)
    ventas_maestro = cur.fetchall()
    
    # Listado para el buscador de sucursales
    cur.execute("SELECT nombre_sucursal FROM sucursales")
    listado_sucursales = [s[0] for s in cur.fetchall()]
    
    cur.close()
    conn.close()
    return render_template('ventas.html', ventas=ventas_maestro, sucursales=listado_sucursales)

@app.route('/venta_detalle/<int:id_venta>')
def venta_detalle(id_venta):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # CONSULTA DETALLE CORREGIDA:
    # Traemos Nombre[0], Cantidad[1], Precio[2], Subtotal[3] y Fórmula[4]
    cur.execute('''
        SELECT 
            p.nombre, 
            dv.cantidad, 
            dv.precio_unitario, 
            (dv.cantidad * dv.precio_unitario) as subtotal,
            p.formula
        FROM detalle_ventas dv
        JOIN lotes l ON dv.id_lote = l.id_lote
        JOIN productos p ON l.id_producto = p.id_producto
        WHERE dv.id_venta = %s
    ''', (id_venta,))
    
    detalles = cur.fetchall()
    
    # CALCULAMOS EL TOTAL: Sumamos el índice [3] de cada fila
    total_venta = sum(fila[3] for fila in detalles)
    
    cur.close()
    conn.close()
    
    # Enviamos 'detalles', 'id_venta' y el nuevo 'total_venta'
    return render_template('detalle_modal.html', 
                           detalles=detalles, 
                           id_venta=id_venta, 
                           total_venta=total_venta)
# --- GESTIÓN DE CARRITO ---
@app.route('/agregar_carrito/<int:lote_id>', methods=['POST'])
def agregar_carrito(lote_id):
    # 1. Asegurar que el carrito exista en la sesión
    if 'carrito' not in session:
        session['carrito'] = []
    
    carrito = session['carrito']
    
    # 2. Capturar los datos enviados desde el formulario (index.html)
    nombre_prod = request.form.get('nombre')
    precio_prod = float(request.form.get('precio'))
    cantidad_prod = int(request.form.get('cantidad'))
    # Esta es la sucursal real del lote, no la de la sesión
    sucursal_real_lote = request.form.get('sucursal_origen')

    # 3. VALIDACIÓN DE MEZCLA DE SUCURSALES
    if len(carrito) > 0:
        # Revisamos la sucursal del primer producto que ya está en el carrito
        sucursal_en_carrito = carrito[0].get('sucursal_origen')
        
        # Si la sucursal del nuevo producto es distinta a la que ya está dentro
        if sucursal_real_lote != sucursal_en_carrito:
            # Opción segura: No añadir y podrías enviar un mensaje de error
            # Si prefieres que se limpie el carrito automáticamente, usa: session['carrito'] = []
            return redirect(url_for('index')) 

    # 4. AÑADIR EL PRODUCTO AL CARRITO
    # Guardamos 'sucursal_origen' para que la tabla temporal muestre el nombre real
    carrito.append({
        'lote_id': lote_id,
        'nombre': nombre_prod,
        'cantidad': cantidad_prod,
        'precio': precio_prod,
        'sucursal_origen': sucursal_real_lote
    })
    
    session['carrito'] = carrito
    session.modified = True 
    
    return redirect(url_for('index'))

@app.route('/limpiar_carrito')
def limpiar_carrito():
    session['carrito'] = []
    session.modified = True
    return redirect(url_for('index'))

@app.route('/eliminar_item/<int:index>')
def eliminar_item(index):
    if 'carrito' in session:
        carrito = session['carrito']
        # Verificamos que el índice exista en el carrito
        if 0 <= index < len(carrito):
            carrito.pop(index)
            session['carrito'] = carrito
            session.modified = True
    return redirect(url_for('index'))

@app.route('/confirmar_venta', methods=['POST'])
def confirmar_venta():
    carrito = session.get('carrito', [])
    if not carrito: return redirect(url_for('index'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id_sucursal FROM sucursales WHERE nombre_sucursal = %s", (session.get('sucursal_seleccionada'),))
        res = cur.fetchone()
        suc_id = res[0] if res else session['id_sucursal_user']

        total_v = sum(item['precio'] * item['cantidad'] for item in carrito)
        cur.execute('INSERT INTO ventas (fecha_hora, id_usuario, id_sucursal, total) VALUES (CURRENT_TIMESTAMP, %s, %s, %s) RETURNING id_venta', 
                   (session['user_id'], suc_id, total_v))
        id_v = cur.fetchone()[0]
        
        for item in carrito:
            cur.execute('INSERT INTO detalle_ventas (id_venta, id_lote, cantidad, precio_unitario) VALUES (%s, %s, %s, %s)', 
                       (id_v, item['lote_id'], item['cantidad'], item['precio']))
            cur.execute('UPDATE lotes SET stock_actual = stock_actual - %s WHERE id_lote = %s', (item['cantidad'], item['lote_id']))
        
        conn.commit()
        session.pop('carrito', None)
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('index'))

# --- RUTA PARA VER EL CATÁLOGO ---
@app.route('/catalogo')
def ver_catalogo():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Traemos las categorías para el menú desplegable
    cur.execute("SELECT id_categoria, nombre_categoria FROM categorias ORDER BY nombre_categoria ASC")
    lista_categorias = cur.fetchall()
    
    # 2. Traemos las sucursales para el formulario de Lotes
    cur.execute("SELECT id_sucursal, nombre_sucursal FROM sucursales ORDER BY nombre_sucursal ASC")
    lista_sucursales = cur.fetchall()
    cur.execute("SELECT id_producto, nombre FROM productos ORDER BY nombre ASC")
    lista_productos = cur.fetchall()
    
    # 3. Traemos las alertas (Trigger)
    cur.execute("SELECT mensaje, fecha_alerta FROM alertas_inventario ORDER BY fecha_alerta DESC LIMIT 5")
    alertas = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('catalogo.html', 
                           lista_categorias=lista_categorias, 
                           lista_sucursales=lista_sucursales, 
                           lista_productos=lista_productos,
                           alertas=alertas)

# --- RUTA PARA GUARDAR EL PRODUCTO (INSERT) ---
@app.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Capturamos el ID numérico que viene del select
    id_categoria = request.form.get('id_categoria') 
    nombre = request.form.get('nombre')
    formula = request.form.get('formula')
    precio_v = request.form.get('precio_venta')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Usamos id_categoria en el INSERT
        cur.execute("""
            INSERT INTO productos (id_categoria, nombre, formula, precio_venta) 
            VALUES (%s, %s, %s, %s)
        """, (id_categoria, nombre, formula, precio_v))
        conn.commit()
    except Exception as e:
        print(f"Error al insertar: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()
        
    return redirect(url_for('ver_catalogo'))

@app.route('/agregar_lote', methods=['POST'])
def agregar_lote():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Capturamos todos los campos según la estructura de LTTT.PNG
    id_prod = request.form.get('id_producto')
    id_suc = request.form.get('id_sucursal')
    codigo = request.form.get('codigo')
    f_caducidad = request.form.get('fecha_caducidad')
    stock = request.form.get('cantidad')  # Se mapea a stock_actual
    p_compra = request.form.get('precio')
    f_entrega = request.form.get('fecha_entrega')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # INSERT exacto con los 7 campos de la tabla lotes
        cur.execute("""
            INSERT INTO lotes (id_producto, id_sucursal, codigo_lote, fecha_caducidad, stock_actual, precio_compra, fecha_entrega) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_prod, id_suc, codigo, f_caducidad, stock, p_compra, f_entrega))
        
        conn.commit()
    except Exception as e:
        print(f"Error al insertar lote: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()
        
    return redirect(url_for('ver_catalogo'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)