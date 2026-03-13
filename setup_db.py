from app import app, db, User, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    db.drop_all() # Reset para aplicar a nova coluna 'is_admin'
    db.create_all()
    
    # Criando VOCÊ como ADMINISTRADOR
    admin_pw = generate_password_hash('123', method='pbkdf2:sha256')
    admin = User(
        username='will', 
        password=admin_pw, 
        nome_completo='Will - Administrador Master',
        is_admin=True # VOCÊ TEM O PODER TOTAL
    )
    db.session.add(admin)
    
    # Estoque inicial
    db.session.add(Estoque(item='Pilha 9V Alcalina', quantidade=10))
    
    db.session.commit()
    print("Banco de dados pronto! Usuário Will definido como Admin.")
