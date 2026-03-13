from app import app, db, User, Estoque
from werkzeug.security import generate_password_hash

with app.app_context():
    db.drop_all() # Cuidado: Isso limpa o banco para garantir o novo padrão
    db.create_all()
    
    # Usuário Padrão
    pw = generate_password_hash('123', method='pbkdf2:sha256')
    db.session.add(User(username='will', password=pw, nome_completo='Will - Técnico Master'))
    
    # Estoque Padrão
    db.session.add(Estoque(item='Ponta de Prova MTL-1', quantidade=10))
    db.session.commit()
    print("Banco de dados padronizado e pronto!")
