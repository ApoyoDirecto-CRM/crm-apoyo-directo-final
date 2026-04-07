from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager # <--- PIEZA MAESTRA DE SEGURIDAD
from .models import db, Usuario      # <--- IMPORTAMOS EL MODELO PARA EL LOADER
from config import Config

def create_app():
    app = Flask(__name__)
    # Carga la configuración (Base de Datos, Secret Key, etc.)
    app.config.from_object(Config) 
    
    # 1. Inicialización de la Base de Datos
    db.init_app(app)
    
    # 2. CONFIGURACIÓN DEL MOTOR DE SEGURIDAD (Flask-Login)
    login_manager = LoginManager()
    login_manager.login_view = 'main.login' # Define a dónde mandar a alguien si no tiene permiso
    login_manager.init_app(app)

    # El "Cargador de Usuarios": Esta función le permite al sistema 
    # "recordar" al asesor mientras navega por las pestañas.
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))
    
    # 3. Extensiones de Jinja (Para lógica interna en los HTML)
    app.jinja_env.add_extension('jinja2.ext.do')
    
    # 4. Registro de Blueprints (Tus rutas)
    from .routes import main
    app.register_blueprint(main)
    
    return app