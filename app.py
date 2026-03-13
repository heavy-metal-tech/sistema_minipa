import os
import io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Bibliotecas para PDF e E-mail
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_corp_precision_2026'

# Configuração do Banco
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'minipa_os.db')
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
@app.route('/')
def login():
    return render_template('login.html') # Simplificado para o exemplo

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    pecas = Estoque.query.all()
    return render_template('dashboard.html', name=current_user.nome_completo, ordens=ordens, pecas=pecas)

@app.route('/gerar_pdf/<int:os_id>')
@login_required
def gerar_pdf(os_id):
    os_data = OrdemServico.query.get_or_404(os_id)
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Cabeçalho do PDF
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "RELATÓRIO DE ASSISTÊNCIA TÉCNICA - MINIPA")
    p.line(100, 790, 500, 790)
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 760, f"Ordem de Serviço: #{os_data.id}")
    p.drawString(100, 740, f"Cliente: {os_data.cliente}")
    p.drawString(100, 720, f"Equipamento: {os_data.equipamento}")
    p.drawString(100, 700, f"Nº de Série: {os_data.serie}")
    p.drawString(100, 680, f"Garantia: {os_data.garantia}")
    p.drawString(100, 660, f"Técnico: {os_data.tecnico}")
    
    p.drawString(100, 630, "Defeito/Serviço Realizado:")
    p.setFont("Helvetica-Oblique", 11)
    p.drawString(120, 610, f"{os_data.defeito}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"OS_{os_id}_Minipa.pdf", mimetype='application/pdf')

@app.route('/enviar_minipa/<int:os_id>')
@login_required
def enviar_minipa(os_id):
    # Lógica de integração com API de e-mail (Ex: SendGrid)
    flash(f"Relatório da OS #{os_id} enviado com sucesso para a Central Minipa!")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
