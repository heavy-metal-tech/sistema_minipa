from app import app, db, User, OrdemServico, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Iniciando limpeza e criação do banco...")
    db.drop_all() 
    db.create_all()
    
    # Criar você como Administrador MASTER
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(
        username='will', 
        password=admin_pw, 
        nome_completo='Will - Administrador', 
        is_admin=True
    )
    db.session.add(admin)
    
    # Adicionar uma OS real para testar o Dashboard
    teste = OrdemServico(
        cliente="Minipa Matriz", 
        equipamento="ET-2042E", 
        serie="SN998877", 
        garantia="Não", 
        valor="150.00",
        tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("--- SISTEMA MINIPA PRONTO PARA FILIAIS ---")
