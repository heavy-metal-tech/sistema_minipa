import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash
from database import db, User, OrdemServico

# Inicialização Quântica do App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_will_tech'

# Configuração de Caminho Absoluto (Evita erro 500 no Render)
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'minipa_os.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Vinculando o Banco e o Login
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS DO SISTEMA ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username').strip().lower()).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos. Tente novamente.')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Busca todas as OS por ordem de chegada (mais recentes primeiro)
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    return render_template('dashboard.html', ordens=ordens)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        try:
            nova = OrdemServico(
                cliente=request.form.get('cliente'),
                equipamento=request.form.get('equipamento'),
                serie=request.form.get('serie'),
                nota_fiscal=request.form.get('nota_fiscal'),
                garantia=request.form.get('garantia'),
                valor=request.form.get('valor'),
                defeito=request.form.get('defeito'),
                tecnico=current_user.nome_completo # Salva o nome de quem está logado
            )
            db.session.add(nova)
            db.session.commit()
            flash('Ordem de Serviço cadastrada com sucesso!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar: {str(e)}')
            
    return render_template('nova_os.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# Comando para rodar localmente se precisar
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
