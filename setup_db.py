from app import app, db, User, OrdemServico
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Limpando banco de dados para eliminar erros 405/500...")
    db.drop_all()
    db.create_all()
    
    # Criar você como Admin
    pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=pw, nome_completo='Will - Admin')
    db.session.add(admin)
    
    # OS de teste para confirmar que o Dashboard carrega corretamente
    teste = OrdemServico(
        cliente="Minipa Matriz", equipamento="ET-2042E", 
        serie="SN-12345", garantia="Sim", valor="0.00", tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("--- SISTEMA SINCRONIZADO: USE 'will' E '123' ---")
