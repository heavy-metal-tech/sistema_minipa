import os, io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_assistencia_2026'

# Configuração do Banco
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
if not os.path.exists(instance_dir): os.makedirs(instance_dir)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'minipa_oficial.db')
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
    is_admin = db.Column(db.Boolean, default=False)

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

# --- ROTAS (Ajustadas para evitar Erro 405 e 404) ---

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST']) # AQUI ESTÁ A CORREÇÃO DO ERRO 405
def login():
    if request.method == 'POST':
        username = request.form.get('username').lower()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login ou senha incorretos.')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    # Dados para o gráfico
    stats = {
        'total': len(ordens),
        'abertas': OrdemServico.query.filter_by(status='Aberta').count(),
        'analise': OrdemServico.query.filter_by(status='Em análise').count()
    }
    return render_template('dashboard.html', ordens=ordens, stats=stats)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        try:
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
        except Exception as e:
            flash(f'Erro ao salvar: {e}')
    return render_template('nova_os.html')

@app.route('/imprimir/<int:id>')
@login_required
def imprimir_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    # Cabeçalho Blue Precision
    p.setFillColorRGB(0.05, 0.28, 0.63)
    p.rect(0, 750, 600, 100, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, f"MINIPA PRECISION - OS #{os_data.id}")
    # Conteúdo
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 12)
    p.drawString(50, 700, f"Cliente: {os_data.cliente_nome}")
    p.drawString(50, 680, f"Equipamento: {os_data.modelo}")
    p.drawString(50, 660, f"Série: {os_data.serie}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"OS_Minipa_{os_data.id}.pdf")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- CRIAÇÃO DO BANCO E ADMIN ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        hashed_pw = generate_password_hash('123')
        db.session.add(User(username='will', password=hashed_pw, nome_completo='Willian Técnico', is_admin=True))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
