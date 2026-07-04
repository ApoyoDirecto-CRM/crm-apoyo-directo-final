from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, Usuario, VentaBait
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import func
import pandas as pd
import io

main = Blueprint('main', __name__)


# ==========================================
# PULSO DE ACTIVIDAD
# ==========================================

@main.before_request
def actualizar_pulso():
    if current_user.is_authenticated:
        current_user.ultima_actividad = datetime.utcnow()
        db.session.commit()


# ==========================================
# AUTENTICACIÓN
# ==========================================

@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        u = Usuario.query.filter_by(usuario=usuario).first()
        if u and check_password_hash(u.password_hash, password):
            login_user(u)
            u.ultimo_login = datetime.utcnow()
            db.session.commit()
            flash(f"Bienvenido, {u.nombre}.", "success")
            return redirect(url_for('main.dashboard'))
        flash("Usuario o contraseña incorrectos", "error")
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    current_user.ultima_actividad = datetime.utcnow() - timedelta(minutes=10)
    db.session.commit()
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for('main.login'))


# ==========================================
# DASHBOARD
# ==========================================

@main.route('/dashboard')
@login_required
def dashboard():
    es_admin = current_user.rol in ['GERENTE', 'SUPERVISOR']

    if es_admin:
        ventas = VentaBait.query.order_by(VentaBait.fecha_venta.desc()).all()
        total_ventas = len(ventas)
        ventas_hoy = VentaBait.query.filter(VentaBait.fecha_venta == datetime.today().date()).count()
        agentes = Usuario.query.filter_by(rol='ASESOR').count()

        ventas_por_agente = db.session.query(
            Usuario.nombre, func.count(VentaBait.id)
        ).join(VentaBait, VentaBait.asesor_id == Usuario.id, isouter=True
        ).group_by(Usuario.id, Usuario.nombre).all()

        ventas_por_tipo = db.session.query(
            VentaBait.tipo_venta, func.count(VentaBait.id)
        ).group_by(VentaBait.tipo_venta).all()

        return render_template('dashboard.html', ventas=ventas, total_ventas=total_ventas,
                               ventas_hoy=ventas_hoy, agentes=agentes,
                               ventas_por_agente=ventas_por_agente, ventas_por_tipo=ventas_por_tipo)
    else:
        ventas = VentaBait.query.filter_by(asesor_id=current_user.id).order_by(VentaBait.fecha_venta.desc()).all()
        return render_template('dashboard.html', ventas=ventas)


# ==========================================
# GESTIÓN DE VENTAS
# ==========================================

@main.route('/registrar_venta', methods=['GET', 'POST'])
@login_required
def registrar_venta():
    if request.method == 'POST':
        try:
            fecha_venta = datetime.strptime(request.form['fecha_venta'], '%Y-%m-%d').date()
        except (ValueError, KeyError):
            fecha_venta = datetime.today().date()

        vigencia = None
        if request.form.get('vigencia_nip'):
            vigencia = datetime.strptime(request.form['vigencia_nip'], '%Y-%m-%d').date()

        venta = VentaBait(
            asesor_id=current_user.id if current_user.rol == 'ASESOR' else None,
            fecha_venta=fecha_venta,
            numero=request.form['numero'],
            imei=request.form['imei'],
            ni=request.form['ni'],
            cliente_nombre=request.form['cliente_nombre'],
            cliente_apellidos=request.form['cliente_apellidos'],
            metodo_contactacion=request.form['metodo_contactacion'],
            vigencia_nip=vigencia,
            tipo_venta=request.form['tipo_venta']
        )

        if current_user.rol in ['GERENTE', 'SUPERVISOR'] and request.form.get('asesor_id'):
            venta.asesor_id = int(request.form['asesor_id'])

        db.session.add(venta)
        db.session.commit()
        flash("Venta registrada con éxito.", "success")
        return redirect(url_for('main.dashboard'))

    agentes = Usuario.query.filter_by(rol='ASESOR').all() if current_user.rol in ['GERENTE', 'SUPERVISOR'] else []
    return render_template('registrar_venta.html', agentes=agentes, hoy=datetime.today().strftime('%Y-%m-%d'))


@main.route('/editar_venta/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_venta(id):
    venta = VentaBait.query.get_or_404(id)
    if current_user.rol == 'ASESOR' and venta.asesor_id != current_user.id:
        flash("No tienes permiso para editar esta venta.", "error")
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        try:
            venta.fecha_venta = datetime.strptime(request.form['fecha_venta'], '%Y-%m-%d').date()
        except (ValueError, KeyError):
            pass
        venta.numero = request.form['numero']
        venta.imei = request.form['imei']
        venta.ni = request.form['ni']
        venta.cliente_nombre = request.form['cliente_nombre']
        venta.cliente_apellidos = request.form['cliente_apellidos']
        venta.metodo_contactacion = request.form['metodo_contactacion']
        if request.form.get('vigencia_nip'):
            venta.vigencia_nip = datetime.strptime(request.form['vigencia_nip'], '%Y-%m-%d').date()
        else:
            venta.vigencia_nip = None
        venta.tipo_venta = request.form['tipo_venta']

        if current_user.rol in ['GERENTE', 'SUPERVISOR'] and request.form.get('asesor_id'):
            venta.asesor_id = int(request.form['asesor_id'])

        db.session.commit()
        flash("Venta actualizada con éxito.", "success")
        return redirect(url_for('main.dashboard'))

    agentes = Usuario.query.filter_by(rol='ASESOR').all() if current_user.rol in ['GERENTE', 'SUPERVISOR'] else []
    return render_template('editar_venta.html', venta=venta, agentes=agentes)


@main.route('/eliminar_venta/<int:id>', methods=['POST'])
@login_required
def eliminar_venta(id):
    venta = VentaBait.query.get_or_404(id)
    if current_user.rol == 'ASESOR' and venta.asesor_id != current_user.id:
        flash("No tienes permiso para eliminar esta venta.", "error")
        return redirect(url_for('main.dashboard'))
    db.session.delete(venta)
    db.session.commit()
    flash("Venta eliminada.", "info")
    return redirect(url_for('main.dashboard'))


# ==========================================
# MÉTRICAS DE PRODUCTIVIDAD
# ==========================================

@main.route('/metricas')
@login_required
def metricas():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    ahora = datetime.utcnow()
    hoy = ahora.date()

    # Todas las ventas del día (en UTC-6 como en el original)
    ventas_hoy = VentaBait.query.filter(
        VentaBait.fecha_venta == hoy
    ).all()

    reporte = {}
    totales_asesor = {}

    for v in ventas_hoy:
        asesor_nombre = v.asesor.nombre if v.asesor else 'SIN ASIGNAR'
        hora = v.created_at.strftime('%H:00') if v.created_at else '00:00'

        if hora not in reporte:
            reporte[hora] = {}
        if asesor_nombre not in reporte[hora]:
            reporte[hora][asesor_nombre] = {'tipos': {}, 'subtotal': 0}
        if asesor_nombre not in totales_asesor:
            totales_asesor[asesor_nombre] = {'total': 0}

        t = v.tipo_venta
        reporte[hora][asesor_nombre]['tipos'][t] = reporte[hora][asesor_nombre]['tipos'].get(t, 0) + 1
        reporte[hora][asesor_nombre]['subtotal'] += 1
        totales_asesor[asesor_nombre]['total'] += 1

    asesores_lista = sorted(set(
        [v.asesor.nombre for v in ventas_hoy if v.asesor] + ['SIN ASIGNAR']
    ))
    for a in asesores_lista:
        if a not in totales_asesor:
            totales_asesor[a] = {'total': 0}
    reporte_ordenado = dict(sorted(reporte.items()))

    asesores_objetos = Usuario.query.filter_by(rol='ASESOR').all()
    limite_activo = ahora - timedelta(minutes=5)
    for a in asesores_objetos:
        a.is_online = bool(a.ultima_actividad and a.ultima_actividad > limite_activo)
        a.login_cdmx = a.ultimo_login - timedelta(hours=6) if a.ultimo_login else None

    return render_template('metricas.html',
                           reporte=reporte_ordenado,
                           asesores=asesores_lista,
                           totales=totales_asesor,
                           asesores_reales=asesores_objetos,
                           hoy=hoy)


# ==========================================
# DESCARGA DE REPORTE EXCEL
# ==========================================

@main.route('/descargar_reporte')
@login_required
def descargar_reporte():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        flash("No tienes permisos para descargar reportes.", "error")
        return redirect(url_for('main.dashboard'))

    ventas = VentaBait.query.order_by(VentaBait.fecha_venta.desc()).all()

    datos = []
    for v in ventas:
        datos.append({
            'ID': v.id,
            'Fecha_Venta': v.fecha_venta.strftime('%d/%m/%Y'),
            'Cliente_Nombre': v.cliente_nombre,
            'Cliente_Apellidos': v.cliente_apellidos,
            'Numero': v.numero,
            'IMEI': v.imei,
            'NI': v.ni,
            'Metodo_Contactacion': v.metodo_contactacion,
            'Vigencia_NIP': v.vigencia_nip.strftime('%d/%m/%Y') if v.vigencia_nip else '',
            'Tipo_Venta': v.tipo_venta,
            'Asesor': v.asesor.nombre if v.asesor else 'SIN ASIGNAR',
            'Fecha_Registro': v.created_at.strftime('%d/%m/%Y %H:%M') if v.created_at else ''
        })

    df = pd.DataFrame(datos)
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl', sheet_name='Ventas_BAIT')
    output.seek(0)

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        output,
        download_name=f"Reporte_Ventas_BAIT_{fecha_str}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ==========================================
# VISOR GLOBAL DE VENTAS
# ==========================================

@main.route('/visor_ventas')
@login_required
def visor_ventas():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    filtro = request.args.get('filtro', 'todas')
    query = VentaBait.query

    if filtro == 'hoy':
        query = query.filter(VentaBait.fecha_venta == datetime.today().date())
    elif filtro == 'agente':
        asesor_id = request.args.get('asesor_id', type=int)
        if asesor_id:
            query = query.filter(VentaBait.asesor_id == asesor_id)

    ventas = query.order_by(VentaBait.fecha_venta.desc(), VentaBait.created_at.desc()).all()
    agentes = Usuario.query.filter_by(rol='ASESOR').all()

    return render_template('visor_ventas.html', ventas=ventas, agentes=agentes, filtro_actual=filtro)


# ==========================================
# ADMINISTRACIÓN DE USUARIOS
# ==========================================

@main.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
def admin_usuarios():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST' and 'eliminar_id' in request.form:
        user_id = int(request.form['eliminar_id'])
        if user_id != current_user.id:
            db.session.delete(Usuario.query.get(user_id))
            db.session.commit()
            flash("Usuario eliminado.", "success")
        return redirect(url_for('main.admin_usuarios'))

    if request.method == 'POST' and 'cambiar_pass_id' in request.form:
        user_id = int(request.form['cambiar_pass_id'])
        nueva_pass = request.form['nueva_password']
        usuario = Usuario.query.get(user_id)
        if usuario and nueva_pass:
            usuario.password_hash = generate_password_hash(nueva_pass)
            db.session.commit()
            flash(f"Contraseña actualizada para {usuario.usuario}.", "success")
        return redirect(url_for('main.admin_usuarios'))

    usuarios = Usuario.query.order_by(Usuario.rol.asc(), Usuario.nombre.asc()).all()
    return render_template('admin_usuarios.html', usuarios=usuarios)


def generar_username(nombre):
    import re
    base = nombre.lower().strip()
    base = base.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    base = base.replace('ñ', 'n')
    base = re.sub(r'[^a-z0-9\s]', '', base)
    partes = [p for p in base.split() if p]
    if not partes:
        return 'usuario'

    first = partes[0][:4]
    if len(partes) == 1:
        username = first
    elif len(partes) == 2:
        username = first + partes[1][:4]
    else:
        username = first + partes[-2][:4]

    original = username
    contador = 1
    while Usuario.query.filter_by(usuario=username).first():
        username = f"{original}{contador}"
        contador += 1
    return username


@main.route('/admin/crear_asesor', methods=['GET', 'POST'])
@login_required
def crear_asesor():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        password = request.form['password']
        rol = request.form['rol']

        usuario = generar_username(nombre)

        nuevo = Usuario(
            nombre=nombre,
            usuario=usuario,
            password_hash=generate_password_hash(password),
            rol=rol
        )
        db.session.add(nuevo)
        db.session.commit()
        flash(f"Usuario '{usuario}' ({rol}) creado con éxito.", "success")
        return render_template('usuario_creado.html', nombre=nombre, usuario=usuario, password=password, rol=rol)

    return render_template('crear_asesor.html')


# ==========================================
# API
# ==========================================

@main.route('/api/preview_username')
@login_required
def api_preview_username():
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'username': '', 'exists': False})
    import re
    base = nombre.lower().strip()
    base = base.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    base = base.replace('ñ', 'n')
    base = re.sub(r'[^a-z0-9\s]', '', base)
    partes = [p for p in base.split() if p]
    if not partes:
        return jsonify({'username': '', 'exists': False})

    first = partes[0][:4]
    if len(partes) == 1:
        username = first
    elif len(partes) == 2:
        username = first + partes[1][:4]
    else:
        username = first + partes[-2][:4]

    original = username
    contador = 1
    exists = bool(Usuario.query.filter_by(usuario=username).first())
    while Usuario.query.filter_by(usuario=username).first():
        username = f"{original}{contador}"
        contador += 1
    return jsonify({'username': username, 'exists': exists})


@main.route('/api/ventas_por_agente')
@login_required
def api_ventas_por_agente():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return jsonify([])
    data = db.session.query(
        Usuario.nombre, func.count(VentaBait.id)
    ).join(VentaBait, VentaBait.asesor_id == Usuario.id, isouter=True
    ).group_by(Usuario.id, Usuario.nombre).all()
    return jsonify([{'label': n, 'value': v} for n, v in data])


@main.route('/api/ventas_por_tipo')
@login_required
def api_ventas_por_tipo():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return jsonify([])
    data = db.session.query(
        VentaBait.tipo_venta, func.count(VentaBait.id)
    ).group_by(VentaBait.tipo_venta).all()
    return jsonify([{'label': t, 'value': v} for t, v in data])


@main.route('/api/estado_asesores')
@login_required
def api_estado_asesores():
    if current_user.rol not in ['GERENTE', 'SUPERVISOR']:
        return jsonify({'error': 'No autorizado'}), 403

    limite = datetime.utcnow() - timedelta(minutes=5)
    asesores = Usuario.query.filter_by(rol='ASESOR').all()

    return jsonify([{
        'usuario': a.usuario,
        'nombre': a.nombre,
        'status_label': 'ACTIVO' if (a.ultima_actividad and a.ultima_actividad > limite) else 'INACTIVO',
        'status_color': 'success' if (a.ultima_actividad and a.ultima_actividad > limite) else 'secondary',
        'ultimo_login': a.ultimo_login.isoformat() if a.ultimo_login else None,
        'ultima_actividad': a.ultima_actividad.isoformat() if a.ultima_actividad else None
    } for a in asesores])
