import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_security_2026'

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path): os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'minipa_os.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # Hash para segurança
    nome_completo = db.Column(db.String(100))

class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    defeito = db.Column(db.String(200))
    tecnico_responsavel = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pendente')

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    minimo = db.Column(db.Integer, default=5)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos.')
    return render_template('login.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        novo_user = User(
            username=request.form.get('username'),
            password=hashed_pw,
            nome_completo=request.form.get('nome')
        )
        db.session.add(novo_user)
        db.session.commit()
        flash('Técnico cadastrado com sucesso!')
        return redirect(url_for('login'))
    return render_template('registrar.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.all()
    pecas = Estoque.query.filter(Estoque.quantidade <= Estoque.minimo).all()
    return render_template('dashboard.html', name=current_user.nome_completo, ordens=ordens, pecas=pecas)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        nova = OrdemServico(
            equipamento=request.form.get('equipamento'),
            serie=request.form.get('serie'),
            defeito=request.form.get('defeito'),
            tecnico_responsavel=current_user.nome_completo
        )
        db.session.add(nova)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('nova_os.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
