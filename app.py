import os
import io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_corp_precision_2026'

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
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False) # Define se é admin ou técnico

class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(100))
    equipamento = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    nota_fiscal = db.Column(db.String(50))
    garantia = db.Column(db.String(10))
    defeito = db.Column(db.Text)
    tecnico = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pendente')

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

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

@app.route('/dashboard')
@login_required
def dashboard():
    # O Admin vê tudo, o técnico vê apenas as OS que ele abriu (opcional)
    if current_user.is_admin:
        ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    else:
        ordens = OrdemServico.query.filter_by(tecnico=current_user.nome_completo).all()
    
    pecas = Estoque.query.all()
    return render_template('dashboard.html', ordens=ordens, pecas=pecas)

@app.route('/cadastrar_tecnico', methods=['GET', 'POST'])
@login_required
def cadastrar_tecnico():
    # Apenas o Admin (você) pode cadastrar novos técnicos
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem cadastrar técnicos.")
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        novo_tecnico = User(
            username=request.form.get('username'),
            password=hashed_pw,
            nome_completo=request.form.get('nome'),
            is_admin=False # Sempre criado como técnico comum
        )
        db.session.add(novo_tecnico)
        db.session.commit()
        flash('Técnico cadastrado com sucesso!')
        return redirect(url_for('dashboard'))
    return render_template('cadastrar_tecnico.html')

# (Manter rotas de nova_os, gerar_pdf e ajustar_estoque conforme as anteriores)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
