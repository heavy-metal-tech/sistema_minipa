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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'assistencia_v1.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELO COMPLETO (CONFORME ESCOPO DO CHEFE) ---
class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_abertura = db.Column(db.DateTime, default=db.func.current_timestamp())
    status = db.Column(db.String(30), default='Aberta') # Aberta, Em análise, Aguardando peça, Concluída
    
    # Cliente
    cliente_nome = db.Column(db.String(100), nullable=False)
    cliente_cpf_cnpj = db.Column(db.String(20))
    cliente_tel = db.Column(db.String(20))
    cliente_email = db.Column(db.String(100))
    
    # Equipamento
    modelo = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    nf_garantia = db.Column(db.String(50))
    em_garantia = db.Column(db.String(5)) # Sim / Não
    
    # Técnico e Financeiro
    defeito = db.Column(db.Text)
    pecas_solicitadas = db.Column(db.Text) # Códigos e descrições
    valor_servico = db.Column(db.String(20))
    tecnico_resp = db.Column(db.String(100))

# ... (Manter User, login_manager e outras rotas)

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    # Métricas para os gráficos (Contagem por status)
    status_counts = {
        'abertas': OrdemServico.query.filter_by(status='Aberta').count(),
        'analise': OrdemServico.query.filter_by(status='Em análise').count(),
        'concluidas': OrdemServico.query.filter_by(status='Concluída').count()
    }
    return render_template('dashboard.html', ordens=ordens, stats=status_counts)

# Iniciar Banco
with app.app_context():
    db.create_all()
