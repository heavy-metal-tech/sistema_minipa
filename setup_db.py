from app import app
from database import db, User, OrdemServico
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Executando Colapso Quântico: Limpando tudo...")
    db.drop_all()
    db.create_all()
    
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(username='will', password=admin_pw, nome_completo='Will - Master', is_admin=True)
    db.session.add(admin)
    
    db.session.commit()
    print("SISTEMA RESETADO E LIMPO!")
