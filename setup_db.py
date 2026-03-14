from app import app
from database import db, User, TabelaPreco
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Resetando banco de dados...")
    db.drop_all()
    db.create_all()

    admin = User(
        username='will',
        password=generate_password_hash('123', method='pbkdf2:sha256'),
        nome_completo='Will Admin',
        is_admin=True
    )
    db.session.add(admin)

    for tipo, valor in [
        ('Reparo com PCI', 180.00),
        ('Reparo Geral', 120.00),
        ('Calibração', 90.00),
        ('Diagnóstico', 60.00),
    ]:
        db.session.add(TabelaPreco(tipo_servico=tipo, valor=valor))

    db.session.commit()
    print("Banco resetado com sucesso! Usuário: will / Senha: 123")
