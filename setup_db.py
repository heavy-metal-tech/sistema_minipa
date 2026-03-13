from app import app, db, User, OrdemServico
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Iniciando limpeza profunda...")
    db.drop_all()
    db.create_all()
    
    # Criando você como Admin
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=admin_pw, nome_completo='Will - Admin', is_admin=True)
    db.session.add(admin)
    
    # Adicionando OS de teste
    teste = OrdemServico(
        cliente="Laboratório Teste", equipamento="ET-2042E", 
        serie="SN-123", garantia="Sim", valor="0.00", tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("Sistema Minipa restaurado com sucesso!")
