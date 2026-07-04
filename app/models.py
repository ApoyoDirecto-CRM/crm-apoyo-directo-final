from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

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

    ventas = db.relationship('VentaBait', backref='asesor', lazy=True)


class VentaBait(db.Model):
    __tablename__ = 'ventas_bait'
    id = db.Column(db.Integer, primary_key=True)
    asesor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    fecha_venta = db.Column(db.Date, nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    imei = db.Column(db.String(50), nullable=False)
    ni = db.Column(db.String(50), nullable=False)
    cliente_nombre = db.Column(db.String(100), nullable=False)
    cliente_apellidos = db.Column(db.String(100), nullable=False)
    metodo_contactacion = db.Column(db.String(50), nullable=False)
    vigencia_nip = db.Column(db.Date, nullable=True)
    tipo_venta = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
