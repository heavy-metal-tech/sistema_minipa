from app import app, db, User

with app.app_context():
    db.create_all()
    # Criar Chefe
    if not User.query.filter_by(username='chefe').first():
        admin = User(username='chefe', password='minipa_admin_2026', cargo='admin')
        db.session.add(admin)
    # Criar Seu Acesso
    if not User.query.filter_by(username='will').first():
        will = User(username='will', password='123', cargo='tecnico')
        db.session.add(will)
    db.session.commit()
    print("Usuários de teste criados!")