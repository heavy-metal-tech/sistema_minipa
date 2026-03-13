from app import app, db, User, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    db.drop_all() # Limpa o erro 500 resetando as tabelas
    db.create_all()
    
    # Criar você como Administrador
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=admin_pw, 
                nome_completo='Will - Administrador', is_admin=True)
    db.session.add(admin)
    
    # Adicionar uma OS de teste para não vir vazio
    teste = OrdemServico(cliente="Minipa Matriz", equipamento="ET-2042E", 
                         serie="123456", garantia="Não", tecnico="Will")
    db.session.add(teste)
    
    db.session.commit()
    print("--- SISTEMA REINICIADO COM SUCESSO ---")
