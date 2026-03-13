from app import app, db, User, OrdemServico, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Iniciando Colapso Quântico (Reset do Banco)...")
    db.drop_all()
    db.create_all()
    
    # Usuário Will (Admin)
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=admin_pw, nome_completo='Will - Master', is_admin=True)
    db.session.add(admin)
    
    # Inserindo dados iniciais para garantir que o Dashboard carregue
    item_teste = Estoque(item='Fusível 10A Minipa', quantidade=20)
    os_teste = OrdemServico(cliente="Laboratório Central", equipamento="ET-2042E", 
                            serie="SN2026-X", garantia="Sim", valor="0.00", tecnico="Will")
    
    db.session.add_all([item_teste, os_teste])
    db.session.commit()
    print("--- REALIDADE SINCRONIZADA: SISTEMA PRONTO ---")
