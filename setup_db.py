from app import app, db, User, OrdemServico, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Sincronizando Realidade Quântica (Reset do Banco)...")
    db.drop_all()
    db.create_all()
    
    # Criar teu perfil Admin
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=admin_pw, nome_completo='Will - Master', is_admin=True)
    db.session.add(admin)
    
    # OS de teste para popular o Dashboard imediatamente
    teste = OrdemServico(
        cliente="Laboratório Minipa", equipamento="ET-2042E", 
        serie="SN-2026", garantia="Sim", valor="0.00", tecnico="Will"
    )
    db.session.add(teste)
    
    db.session.commit()
    print("--- SISTEMA RECONSTRUÍDO COM SUCESSO ---")
