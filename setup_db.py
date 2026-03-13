from app import app, db, User, Estoque
from werkzeug.security import generate_password_hash

def inicializar_banco():
    with app.app_context():
        # 1. Cria todas as tabelas (Usuários, O.S. e Estoque)
        db.create_all()
        
        # 2. Cria o Usuário Administrador (Will)
        # Verificamos se já existe para não duplicar no deploy
        admin_user = User.query.filter_by(username='will').first()
        if not admin_user:
            # Geramos uma senha segura criptografada
            hashed_password = generate_password_hash('123', method='pbkdf2:sha256')
            admin = User(
                username='will', 
                password=hashed_password, 
                nome_completo='Will - Técnico Master'
            )
            db.session.add(admin)
            print("Usuário administrador criado com sucesso!")

        # 3. Inicializa o Estoque com itens padrão da Minipa
        # Isso ajuda a mostrar o funcionamento imediato para o dono
        if not Estoque.query.first():
            itens_iniciais = [
                Estoque(item='Fusível de Ação Rápida 10A/600V', quantidade=2, minimo=5),
                Estoque(item='Bateria 9V Alcalina (Multímetros)', quantidade=15, minimo=5),
                Estoque(item='Cabo de Ponta de Prova (Par)', quantidade=4, minimo=6),
                Estoque(item='Display LCD para ET-2042E', quantidade=1, minimo=2),
                Estoque(item='Garra Jacaré (Preta/Vermelha)', quantidade=10, minimo=12)
            ]
            db.session.add_all(itens_iniciais)
            print("Estoque inicial de peças cadastrado!")

        # 4. Salva tudo no banco de dados
        db.session.commit()
        print("--- BANCO DE DADOS DA FILIAL PRONTO PARA USO ---")

if __name__ == '__main__':
    inicializar_banco()
