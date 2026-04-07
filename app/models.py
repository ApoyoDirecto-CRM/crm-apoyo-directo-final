from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    ultimo_login = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actividad = db.Column(db.DateTime, default=datetime.utcnow)
    
    clientes = db.relationship('Cliente', backref='asesor', lazy=True, foreign_keys="Cliente.asesor_id")
    gestiones = db.relationship('Gestion', backref='usuario', lazy=True)
    jornadas = db.relationship('Jornada', backref='usuario', lazy=True)


class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    pago_minimo = db.Column(db.Float, default=0.0)
    pago_vencido = db.Column(db.Float, default=0.0) 
    dias_de_mora = db.Column(db.Integer, default=0) 
    numero_cuenta = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    
    # CORRECCIÓN: Se eliminó el campo 'telefono' duplicado
    telefono = db.Column(db.String(20), nullable=True)
    telefono_2 = db.Column(db.String(20), nullable=True) 
    telefono_3 = db.Column(db.String(20), nullable=True) 
    correo = db.Column(db.String(100), nullable=True)
    direccion = db.Column(db.Text, nullable=True) 
    saldo_total = db.Column(db.Float, default=0.0) 
    producto = db.Column(db.String(50), nullable=True)
    estatus = db.Column(db.String(20), default='Pendiente')
    
    # Se añade ondelete='SET NULL' para que si borras al asesor, el cliente pase a la bandeja grupal automáticamente
    asesor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    bloqueado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    bloqueado_hasta = db.Column(db.DateTime, nullable=True)
    
    gestiones_h = db.relationship('Gestion', backref='cliente', lazy=True, cascade="all, delete-orphan")

class Gestion(db.Model):
    __tablename__ = 'gestiones'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='CASCADE'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    resultado = db.Column(db.String(50), nullable=False)
    comentario = db.Column(db.Text, nullable=True)
    
    monto_promesa = db.Column(db.Float, nullable=True) # <--- NUEVO CAMPO
    fecha_promesa = db.Column(db.Date, nullable=True)  # <--- NUEVO CAMPO
    
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def fecha_local(self):
        from datetime import timedelta
        return self.fecha - timedelta(hours=6) if self.fecha else None

class Jornada(db.Model):
    __tablename__ = 'jornadas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    inicio = db.Column(db.DateTime, default=datetime.utcnow)
    fin = db.Column(db.DateTime, nullable=True)