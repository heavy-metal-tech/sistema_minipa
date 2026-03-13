from app import app, db, User, OrdemServico, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Limpando banco de dados...")
    db.drop_all()
    db.create_all()
    
    # Criar você como Admin
    pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=pw, nome_completo='Will - Admin', is_admin=True)
    db.session.add(admin)
    
    # OS de teste para popular o dashboard
    teste = OrdemServico(
        cliente="Minipa Matriz", equipamento="ET-2042E", 
        serie="SN100200", garantia="Não", valor="180.00", tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("Sucesso! Banco de dados reiniciado e padronizado.")
