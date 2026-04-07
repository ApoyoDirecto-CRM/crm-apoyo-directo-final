import os

class Config:
    # 1. ESCUDO DE SESIONES
    # Intenta leer la clave de la nube; si no existe (estás en tu PC), usa una de respaldo.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'crm_secret_key_2026_local_segura'

    # 2. CONEXIÓN INTELIGENTE A BASE DE DATOS
    db_url = os.environ.get('DATABASE_URL') or 'postgresql://postgres:crm123@localhost:5432/cm_cobranza'
    
    # Parche quirúrgico para la nube: Proveedores como Render usan 'postgres://', 
    # pero las versiones modernas de SQLAlchemy exigen 'postgresql://'. Esto lo repara en automático.
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False