from app import app, db, User, Estoque

with app.app_context():
    db.create_all()
    
    # Usuário Will
    if not User.query.filter_by(username='will').first():
        db.session.add(User(username='will', password='123'))
    
    # Itens de Estoque para demonstração
    if not Estoque.query.first():
        itens = [
            Estoque(item='Fusível Cerâmico 10A', quantidade=2, minimo=5),
            Estoque(item='Pilha 9V Alcalina', quantidade=20, minimo=5),
            Estoque(item='Garra Jacaré Preta', quantidade=3, minimo=10)
        ]
        db.session.add_all(itens)
    
    db.session.commit()
    print("Sistema pronto e estoque inicializado!")
