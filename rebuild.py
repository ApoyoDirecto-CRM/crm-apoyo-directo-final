from app import create_app
from app.models import db, Usuario
from werkzeug.security import generate_password_hash
import os

os.environ['DATABASE_URL'] = 'postgresql://base_crm_apoyo_user:eR6WgWR0tst2BZ3ueeSH9NAyrzHVMurZ@dpg-d70c9694tr6s73e3ej7g-a.oregon-postgres.render.com/base_crm_apoyo'

app = create_app()

def rebuild_total():
    with app.app_context():
        print("Destruyendo estructura antigua...")
        db.drop_all()   # Borra tablas y columnas obsoletas
        db.create_all() # Crea la estructura limpia con 'saldo_total' y 'producto'
        print("Estructura física actualizada con éxito.")

        print("[2/3] Generando credenciales maestras...")
        gerente = Usuario(
            nombre="Elias Alejandro Lira Arellano",
            usuario="ELIALIRA",
            password_hash=generate_password_hash("admin"), # <--- El cambio clave
            rol="GERENTE"
        )
        db.session.add(gerente)
        db.session.commit()
        print("      ✓ Perfil Administrativo (GERENTE) creado.")

        print("[3/3] Sistema listo para operar.")

if __name__ == '__main__':
    rebuild_total()