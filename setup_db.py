from app import app, db, User, OrdemServico, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Efetuando limpeza de tabelas antigas...")
    db.drop_all()
    db.create_all()
    
    # Criar você como Admin Master
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(
        username='will', 
        password=admin_pw, 
        nome_completo='Will - Admin', 
        is_admin=True
    )
    db.session.add(admin)
    
    # OS de teste para confirmar que o Dashboard carrega
    teste = OrdemServico(
        cliente="Laboratório Central", 
        equipamento="ET-2042E", 
        serie="SN2026", 
        garantia="Não", 
        valor="150.00", 
        tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("SISTEMA RESTAURADO: Agora acesse o login com 'will' e '123'.")
