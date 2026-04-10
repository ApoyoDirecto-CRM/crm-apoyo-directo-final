from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from flask_login import login_user, logout_user, login_required, current_user 
from .models import db, Usuario, Cliente, Gestion, Jornada 
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import func, or_, text
from sqlalchemy.orm import joinedload # <--- HERRAMIENTA CRÍTICA DE RENDIMIENTO
import pandas as pd
import io
import requests
import hashlib
import hmac
import base64
import urllib.parse
from flask import jsonify

main = Blueprint('main', __name__)

# ==============================================================
# 0. ACTUALIZACIÓN DE RAÍZ: REGISTRO DE ACTIVIDAD (PULSO)
# ==============================================================
@main.before_request
def actualizar_pulso():
    if current_user.is_authenticated:
        current_user.ultima_actividad = datetime.utcnow()
        db.session.commit()

# ==========================================
# FASE 1: GESTIÓN DE ACCESO Y SEGURIDAD
# ==========================================

@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        p_word = request.form.get('password')

        u = Usuario.query.filter_by(usuario=usuario).first()

        if u and check_password_hash(u.password_hash, p_word):
            login_user(u) 
            u.ultimo_login = datetime.utcnow()
            db.session.commit()
            
            flash(f"Bienvenido de nuevo, {u.nombre}.", "success")
            return redirect(url_for('main.dashboard'))
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    # TRUCO QUIRÚRGICO: Retrocedemos su reloj 10 minutos para forzar inactividad
    current_user.ultima_actividad = datetime.utcnow() - timedelta(minutes=10)
    
    j = Jornada.query.filter_by(usuario_id=current_user.id, fin=None).first()
    if j: 
        j.fin = datetime.utcnow()
        
    db.session.commit()
    logout_user() 
    session.clear()
    
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for('main.login'))

# ==========================================
# FASE 2 Y 4: ADMINISTRACIÓN Y MÉTRICAS
# ==========================================

@main.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    u = current_user
    es_mando = u.rol in ['GERENTE', 'SUPERVISOR']

    if request.method == 'POST':
        q_cuenta = request.form.get('busqueda_cuenta', '').strip()
        q_nombre = request.form.get('busqueda_nombre', '').strip()
        q_telefono = request.form.get('busqueda_telefono', '').strip()

        query = Cliente.query
        if q_cuenta: query = query.filter(Cliente.numero_cuenta.ilike(f'%{q_cuenta}%'))
        if q_nombre: query = query.filter(Cliente.nombre.ilike(f'%{q_nombre}%'))
        if q_telefono: query = query.filter(Cliente.telefono.ilike(f'%{q_telefono}%'))
        
        resultado = query.first()
        if resultado:
            return redirect(url_for('main.gestionar_cliente', cliente_id=resultado.id))
        else:
            flash("No se encontró ninguna cuenta con esos datos.", "warning")

    limite_activo = datetime.utcnow() - timedelta(minutes=5)
    todos_asesores = Usuario.query.filter_by(rol='ASESOR').all()
    
    for a in todos_asesores:
        if a.ultima_actividad and a.ultima_actividad > limite_activo:
            a.status_label = "ACTIVO"
            a.status_color = "success"
        else:
            a.status_label = "INACTIVO"
            a.status_color = "secondary"

    return render_template('dashboard.html', u=u, es_mando=es_mando, conectados=todos_asesores)

@main.route('/crear_asesor', methods=['GET', 'POST'])
@login_required
def crear_asesor():
    # BLINDAJE: Usar current_user en lugar de session
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        nombre = request.form.get('nombre').strip()
        usuario = request.form.get('usuario').strip()
        p_word = request.form.get('password')
        rol = request.form.get('rol')

        if Usuario.query.filter_by(usuario=usuario).first():
            flash("Ese nombre de usuario ya está en uso. Elige otro.", "error")
            return redirect(url_for('main.crear_asesor'))

        nuevo_usuario = Usuario(
            nombre=nombre,
            usuario=usuario,
            password_hash=generate_password_hash(p_word),
            rol=rol
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        flash(f"Usuario {usuario} ({rol}) creado con éxito.", "success")
        return redirect(url_for('main.administrar_usuarios')) 

    return render_template('crear_asesor.html')

@main.route('/carga_masiva', methods=['GET', 'POST'])
@login_required
def carga_masiva():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        file = request.files.get('archivo_excel')
        
        if not file or file.filename == '':
            flash("No se seleccionó ningún archivo.")
            return redirect(request.url)

        try:
            df = pd.read_excel(file)
            df = df.fillna('')
            df.columns = df.columns.str.strip().str.lower()
            
            intentos_nuevos = intentos_actualizados = errores = 0

            for _, row in df.iterrows():
                try:
                    num_cuenta_limpio = str(row.get('numero_cuenta', '')).strip()
                    if not num_cuenta_limpio:
                        continue
                    
                    nombre_input = str(row.get('asesor_usuario', '')).strip()
                    if nombre_input.upper() == 'GRUPAL' or nombre_input == '':
                        id_final = None  
                    else:
                        asesor = Usuario.query.filter_by(usuario=nombre_input).first()
                        id_final = asesor.id if asesor else None

                    saldo_str = row.get('saldo_total', 0.0)
                    minimo_str = row.get('pago_minimo', 0.0)
                    vencido_str = row.get('pago_vencido', 0.0) 
                    mora_str = row.get('dias_de_mora', 0)      
                    
                    nuevo_saldo = float(saldo_str) if saldo_str != '' else 0.0
                    nuevo_minimo = float(minimo_str) if minimo_str != '' else 0.0
                    nuevo_vencido = float(vencido_str) if vencido_str != '' else 0.0 
                    nuevos_dias = int(mora_str) if mora_str != '' else 0             
                    
                    producto_str = str(row.get('producto', '')).strip()
                    direccion_str = str(row.get('direccion', '')).strip()
                    correo_str = str(row.get('correo', '')).strip().lower()

                    cliente_existente = Cliente.query.filter_by(numero_cuenta=num_cuenta_limpio).first()
                    
                    if cliente_existente:
                        cliente_existente.saldo_total = nuevo_saldo
                        cliente_existente.pago_minimo = nuevo_minimo
                        cliente_existente.pago_vencido = nuevo_vencido
                        cliente_existente.dias_de_mora = nuevos_dias
                        
                        if producto_str: cliente_existente.producto = producto_str
                        if direccion_str: cliente_existente.direccion = direccion_str
                        if correo_str: cliente_existente.correo = correo_str
                        
                        if id_final is not None or nombre_input.upper() == 'GRUPAL':
                            cliente_existente.asesor_id = id_final
                            
                        intentos_actualizados += 1
                        db.session.flush() 
                    else:
                        nuevo_cliente = Cliente(
                            numero_cuenta=num_cuenta_limpio,
                            nombre=str(row.get('nombre', '')),
                            telefono=str(row.get('telefono', '')),
                            correo=correo_str,          
                            direccion=direccion_str,    
                            producto=producto_str,      
                            saldo_total=nuevo_saldo,
                            pago_minimo=nuevo_minimo,
                            pago_vencido=nuevo_vencido, 
                            dias_de_mora=nuevos_dias,   
                            asesor_id=id_final, 
                            estatus='Pendiente'
                        )
                        db.session.add(nuevo_cliente)
                        intentos_nuevos += 1
                        db.session.flush()
                        
                except Exception as e:
                    db.session.rollback()
                    print(f"Error técnico en fila {row.get('numero_cuenta')}: {e}")
                    errores += 1
            
            db.session.commit()
            flash(f"Actualización Exitosa. {intentos_nuevos} cuentas nuevas. {intentos_actualizados} actualizadas. {errores} errores.", "success")
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            flash("Error crítico al leer Excel. Asegúrate de que el formato sea correcto.", "danger")
            return redirect(request.url)

    return render_template('carga_masiva.html')

# ==========================================
# FASE 3: OPERACIÓN DE COBRANZA
# ==========================================

@main.route('/gestionar/<int:cliente_id>', methods=['GET', 'POST'])
@login_required
def gestionar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # BLINDAJE DE PRIVACIDAD: Evita que un asesor abra la cuenta de otro
    if current_user.rol == 'ASESOR':
        if cliente.asesor_id is not None and cliente.asesor_id != current_user.id:
            flash("Acceso denegado: Esta cuenta pertenece a otro asesor.", "danger")
            return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        resultado = request.form.get('estatus')
        comentario = request.form.get('comentario')
        
        monto_str = request.form.get('monto_promesa', '').strip()
        fecha_str = request.form.get('fecha_promesa', '').strip()
        tel_2 = request.form.get('telefono_2', '').strip()
        tel_3 = request.form.get('telefono_3', '').strip()
        
        if tel_2: cliente.telefono_2 = tel_2
        if tel_3: cliente.telefono_3 = tel_3
        
        monto_val = float(monto_str) if monto_str else None
        fecha_val = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else None
        
        nueva_gestion = Gestion(
            cliente_id=cliente.id,
            usuario_id=current_user.id,
            resultado=resultado,
            comentario=comentario,
            monto_promesa=monto_val,   
            fecha_promesa=fecha_val,   
            fecha=datetime.utcnow()
        )
        db.session.add(nueva_gestion)
        
        cliente.estatus = resultado
        cliente.bloqueado_por = None
        cliente.bloqueado_hasta = None
        
        db.session.commit()
        flash("Gestión registrada con éxito.", "success")
        return redirect(url_for('main.gestionar_cliente', cliente_id=cliente.id))

    historial = Gestion.query.filter_by(cliente_id=cliente.id).order_by(Gestion.fecha.desc()).all()
    return render_template('gestionar_cliente.html', cliente=cliente, historial=historial)

@main.route('/detalle_cliente/<int:id>')
@login_required
def detalle_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    historial = Gestion.query.filter_by(cliente_id=id).order_by(Gestion.fecha.desc()).all()
    return render_template('detalle_cliente.html', cliente=cliente, historial=historial)

@main.route('/siguiente_cliente')
@main.route('/siguiente_cliente/<int:actual_id>')
@login_required
def siguiente_cliente(actual_id=0):
    query = Cliente.query.filter_by(asesor_id=current_user.id).filter(Cliente.estatus != 'Liquidada')

    if actual_id > 0:
        siguiente = query.filter(Cliente.id > actual_id).order_by(Cliente.id.asc()).first()
        if siguiente:
            return redirect(url_for('main.gestionar_cliente', cliente_id=siguiente.id))
        else:
            primer = query.order_by(Cliente.id.asc()).first()
            if primer and primer.id != actual_id:
                flash("Has llegado al final de tu lista. Volviendo al inicio.", "info")
                return redirect(url_for('main.gestionar_cliente', cliente_id=primer.id))
            elif primer and primer.id == actual_id:
                flash("Esta es la única cuenta activa que tienes asignada.", "warning")
                return redirect(url_for('main.gestionar_cliente', cliente_id=primer.id))
            else:
                flash("Has barrido toda tu cartera. ¡Excelente trabajo!", "success")
                return redirect(url_for('main.dashboard'))
    else:
        mi_cliente = query.order_by(Cliente.id.asc()).first()
        if mi_cliente:
            return redirect(url_for('main.gestionar_cliente', cliente_id=mi_cliente.id))
        else:
            flash("No tienes cuentas asignadas en tu cartera PERSONAL.", "success")
            return redirect(url_for('main.dashboard'))

@main.route('/siguiente_cliente_grupal')
@main.route('/siguiente_cliente_grupal/<int:actual_id>')
@login_required
def siguiente_cliente_grupal(actual_id=0):
    query = Cliente.query.filter_by(asesor_id=None).filter(Cliente.estatus != 'Liquidada')
    
    if actual_id > 0:
        siguiente = query.filter(Cliente.id > actual_id).order_by(Cliente.id.asc()).first()
        if siguiente:
            return redirect(url_for('main.gestionar_cliente', cliente_id=siguiente.id))
        else:
            primer = query.order_by(Cliente.id.asc()).first()
            if primer and primer.id != actual_id:
                flash("Fin de la bandeja grupal. Volviendo a la primera cuenta.", "info")
                return redirect(url_for('main.gestionar_cliente', cliente_id=primer.id))
            elif primer and primer.id == actual_id:
                flash("Esta es la única cuenta activa en la bandeja GRUPAL.", "warning")
                return redirect(url_for('main.gestionar_cliente', cliente_id=primer.id))
            else:
                flash("Excelente trabajo en equipo. Bandeja GRUPAL limpia.", "success")
                return redirect(url_for('main.dashboard'))
    else:
        cliente_grupal = query.order_by(Cliente.id.asc()).first()
        if cliente_grupal:
            return redirect(url_for('main.gestionar_cliente', cliente_id=cliente_grupal.id))
        else:
            flash("Excelente trabajo en equipo. La bandeja GRUPAL está en ceros.", "success")
            return redirect(url_for('main.dashboard'))
        
@main.route('/descargar_reporte')
@login_required
def descargar_reporte():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        flash("No tienes permisos para descargar reportes.", "danger")
        return redirect(url_for('main.dashboard'))

    # BLINDAJE DE RENDIMIENTO CRÍTICO (Subqueries y JoinedLoad)
    clientes = Cliente.query.options(joinedload(Cliente.asesor)).filter(Cliente.estatus != 'Liquidada').order_by(Cliente.nombre.asc()).all()

    subq = db.session.query(
        Gestion.cliente_id,
        func.max(Gestion.fecha).label('max_fecha')
    ).group_by(Gestion.cliente_id).subquery()
    
    ultimas_gestiones_obj = db.session.query(Gestion).join(
        subq, db.and_(Gestion.cliente_id == subq.c.cliente_id, Gestion.fecha == subq.c.max_fecha)
    ).all()
    
    diccionario_gestiones = {g.cliente_id: g for g in ultimas_gestiones_obj}

    datos_reporte = []
    
    for c in clientes:
        ultima_gestion = diccionario_gestiones.get(c.id)
        
        monto_prom = ultima_gestion.monto_promesa if ultima_gestion and ultima_gestion.monto_promesa else 0.0
        fecha_prom = ultima_gestion.fecha_promesa.strftime('%d/%m/%Y') if ultima_gestion and ultima_gestion.fecha_promesa else 'N/A'
        fecha_llamada = ultima_gestion.fecha_local.strftime('%d/%m/%Y %H:%M') if ultima_gestion else 'Sin Gestión'
        comentario = ultima_gestion.comentario if ultima_gestion else 'N/A'
        
        asesor_nombre = c.asesor.nombre if c.asesor else 'BANDEJA GRUPAL'

        datos_reporte.append({
            'Numero_Cuenta': c.numero_cuenta,
            'Nombre_Titular': c.nombre,
            'Producto': c.producto or 'N/A',
            'Estatus_Actual': c.estatus,
            'Saldo_Total': c.saldo_total,
            'Pago_Vencido': c.pago_vencido, 
            'Dias_de_Mora': c.dias_de_mora, 
            'Pago_Minimo': c.pago_minimo,
            'Monto_Promesa': monto_prom,
            'Fecha_Promesa': fecha_prom,
            'Telefono_1': c.telefono or 'N/A',
            'Telefono_2': c.telefono_2 or 'N/A',
            'Telefono_3': c.telefono_3 or 'N/A',
            'Correo_Electronico': c.correo or 'N/A',
            'Direccion': c.direccion or 'N/A',
            'Asesor_Asignado': asesor_nombre,
            'Ultima_Gestion_Fecha': fecha_llamada,
            'Ultimo_Comentario': comentario
        })

    df = pd.DataFrame(datos_reporte)
    output = io.BytesIO()
    
    df.to_excel(output, index=False, engine='openpyxl', sheet_name='Cartera_Activa')
    output.seek(0)
    
    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        output, 
        download_name=f"Reporte_Operacion_{fecha_str}.xlsx", 
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@main.route('/productividad')
@login_required
def productividad():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))
    
    ahora_local = datetime.utcnow() - timedelta(hours=6)
    hoy = ahora_local.date()

    gestiones_hoy = Gestion.query.filter(
        func.date(Gestion.fecha - text("interval '6 hours'")) == hoy
    ).all()

    reporte = {}
    asesores_set = set()
    totales_asesor = {} 

    for g in gestiones_hoy:
        asesor_nombre = g.usuario.nombre
        asesores_set.add(asesor_nombre)
        
        hora = g.fecha_local.strftime('%H:00') 

        if hora not in reporte:
            reporte[hora] = {}
        if asesor_nombre not in reporte[hora]:
            reporte[hora][asesor_nombre] = {'resultados': {}, 'subtotal_llamadas': 0, 'monto_hora': 0.0}
        
        if asesor_nombre not in totales_asesor:
            totales_asesor[asesor_nombre] = {'total_llamadas': 0, 'total_monto': 0.0}

        res = g.resultado
        reporte[hora][asesor_nombre]['resultados'][res] = reporte[hora][asesor_nombre]['resultados'].get(res, 0) + 1
        reporte[hora][asesor_nombre]['subtotal_llamadas'] += 1
        totales_asesor[asesor_nombre]['total_llamadas'] += 1

        if res == 'Promesa de Pago' and g.monto_promesa:
            reporte[hora][asesor_nombre]['monto_hora'] += g.monto_promesa
            totales_asesor[asesor_nombre]['total_monto'] += g.monto_promesa

    asesores_lista = sorted(list(asesores_set))
    reporte_ordenado = dict(sorted(reporte.items()))
    
    asesores_objetos = Usuario.query.filter_by(rol='ASESOR').all()
    limite_activo = datetime.utcnow() - timedelta(minutes=5)

    for a in asesores_objetos:
        a.is_online = bool(a.ultima_actividad and a.ultima_actividad > limite_activo)
        a.login_cdmx = a.ultimo_login - timedelta(hours=6) if a.ultimo_login else None

    return render_template('productividad.html', 
                           reporte=reporte_ordenado, 
                           asesores=asesores_lista, 
                           totales=totales_asesor,
                           asesores_reales=asesores_objetos)

@main.route('/administrar_usuarios', methods=['GET', 'POST'])
@login_required
def administrar_usuarios():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST' and 'eliminar_id' in request.form:
        user_id = request.form.get('eliminar_id')
        usuario_a_eliminar = Usuario.query.get(user_id)
        if usuario_a_eliminar and usuario_a_eliminar.id != current_user.id: 
            db.session.delete(usuario_a_eliminar)
            db.session.commit()
            flash(f"Usuario {usuario_a_eliminar.usuario} eliminado con éxito.")
        return redirect(url_for('main.administrar_usuarios'))

    if request.method == 'POST' and 'cambiar_pass_id' in request.form:
        user_id = request.form.get('cambiar_pass_id')
        nueva_pass = request.form.get('nueva_password')
        usuario = Usuario.query.get(user_id)
        if usuario and nueva_pass:
            usuario.password_hash = generate_password_hash(nueva_pass)
            db.session.commit()
            flash(f"Contraseña actualizada para {usuario.usuario}.")
        return redirect(url_for('main.administrar_usuarios'))

    usuarios = Usuario.query.order_by(Usuario.rol.asc(), Usuario.nombre.asc()).all()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@main.route('/visor_cartera')
@login_required
def visor_cartera():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))
    
    filtro = request.args.get('filtro', 'todas')
    query = Cliente.query.filter(Cliente.estatus != 'Liquidada')
    
    if filtro == 'grupal':
        query = query.filter(Cliente.asesor_id == None)
    elif filtro == 'asignada':
        query = query.filter(Cliente.asesor_id != None)
        
    cuentas = query.order_by(Cliente.saldo_total.desc()).all()
    return render_template('visor_cartera.html', cuentas=cuentas, filtro_actual=filtro)

@main.route('/api/estado_asesores')
@login_required
def api_estado_asesores():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return jsonify({'error': 'No autorizado'}), 403

    limite_activo = datetime.utcnow() - timedelta(minutes=5)
    todos_asesores = Usuario.query.filter_by(rol='ASESOR').all()

    datos = []
    for a in todos_asesores:
        is_active = a.ultima_actividad and a.ultima_actividad > limite_activo
        datos.append({
            'usuario': a.usuario,
            'status_label': 'ACTIVO' if is_active else 'INACTIVO',
            'status_color': 'success' if is_active else 'secondary'
        })

    return jsonify(datos)

# --- INTEGRACIÓN ZADARMA (CLICK-TO-CALL) ---
ZADARMA_KEY = '25cc35a15328fa2f4b9d'
ZADARMA_SECRET = 'd4404402bd075b2dac13'

@main.route('/llamar/<telefono>')
def realizar_llamada(telefono):
    # 1. Filtro Quirúrgico: Limpiamos el número y le agregamos el '52' de México
    telefono = telefono.replace(" ", "").replace("-", "")
    if len(telefono) == 10:
        telefono = "52" + telefono
        
    # Parámetros básicos de la llamada (Extensión 100)
    params = {
        'from': '100', 
        'to': telefono
    }
    
    # 2. Preparar los parámetros en orden estricto
    sorted_params = dict(sorted(params.items()))
    params_string = urllib.parse.urlencode(sorted_params)
    
    # 3. Construir la firma de seguridad (HMAC-SHA1 + Base64)
    method = '/v1/request/callback/'
    md5hash = hashlib.md5(params_string.encode('utf8')).hexdigest()
    data = method + params_string + md5hash
    
    hmac_obj = hmac.new(ZADARMA_SECRET.encode('utf8'), data.encode('utf8'), hashlib.sha1)
    sign = base64.b64encode(hmac_obj.digest()).decode('utf8')
    
    headers = {'Authorization': f"{ZADARMA_KEY}:{sign}"}
    
    # 4. Disparar la orden al servidor
    url = f"https://api.zadarma.com{method}?{params_string}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Llamada conectada al " + telefono})
        else:
            return jsonify({"status": "error", "message": response.text})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})