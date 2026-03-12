import os
from app import app, db, User

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')

with app.app_context():
    # Garante que a pasta instance existe
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
    
    db.create_all()
    
    # Adiciona usuários se não existirem
    if not User.query.filter_by(username='chefe').first():
        admin = User(username='chefe', password='minipa_admin_2026', cargo='admin')
        db.session.add(admin)
    
    if not User.query.filter_by(username='will').first():
        will = User(username='will', password='123', cargo='tecnico')
        db.session.add(will)
    
    db.session.commit()
    print("Banco de dados e usuários criados com sucesso!")
