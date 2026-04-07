from app import create_app, db

app = create_app()

if __name__ == '__main__':
    # Esto asegura que las tablas existan antes de empezar (Fase 1/2)
    app.run(debug=True)