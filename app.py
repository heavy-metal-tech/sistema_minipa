import os, io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_oficial_2026'

# Configuração do Banco de Dados
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
if not os.path.exists(instance_dir): os.makedirs(instance_dir)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'assistencia_v2.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS (Banco de Dados) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100))

class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_abertura = db.Column(db.DateTime, default=db.func.current_timestamp())
    status = db.Column(db.String(30), default='Aberta')
    cliente_nome = db.Column(db.String(100), nullable=False)
    cliente_cpf_cnpj = db.Column(db.String(20))
    modelo = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    nf_garantia = db.Column(db.String(50))
    em_garantia = db.Column(db.String(5)) # Sim / Não
    defeito = db.Column(db.Text)
    valor_servico = db.Column(db.String(20))
    tecnico_resp = db.Column(db.String(100))

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    # Garante que ao abrir o site ele sempre vá para o lugar certo
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST']) # AQUI ESTÁ A CORREÇÃO DO ERRO 405
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username').lower()).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos!')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    # Dados fictícios para o gráfico não ficar vazio no início
    stats = {'abertas': OrdemServico.query.filter_by(status='Aberta').count()}
    return render_template('dashboard.html', ordens=ordens, stats=stats)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        nova = OrdemServico(
            cliente_nome=request.form.get('cliente'),
            cliente_cpf_cnpj=request.form.get('cpf_cnpj'),
            modelo=request.form.get('modelo'),
            serie=request.form.get('serie'),
            nf_garantia=request.form.get('nf'),
            em_garantia=request.form.get('garantia'),
            defeito=request.form.get('defeito'),
            valor_servico=request.form.get('valor'),
            tecnico_resp=current_user.nome_completo
        )
        db.session.add(nova)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('nova_os.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- INICIALIZAÇÃO DO BANCO E TÉCNICO ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        hashed_pw = generate_password_hash('123')
        db.session.add(User(username='will', password=hashed_pw, nome_completo='Willian Admin'))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
