import os, io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_full_report'

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
if not os.path.exists(instance_dir): os.makedirs(instance_dir)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'minipa_os.db')
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
    cliente = db.Column(db.String(100))
    equipamento = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    nota_fiscal = db.Column(db.String(50))
    garantia = db.Column(db.String(10))
    valor = db.Column(db.String(20))
    defeito = db.Column(db.Text)
    tecnico = db.Column(db.String(100))
    data = db.Column(db.DateTime, default=db.func.current_timestamp())

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    posicao = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- ROTAS DE PDF (PARA MATRIZ) ---

@app.route('/imprimir_os/<int:id>')
@login_required
def imprimir_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setTitle(f"OS_{os_data.id}_Minipa")
    
    # Cabeçalho Azul Precision
    p.setFillColorRGB(0.05, 0.28, 0.63)
    p.rect(0, 750, 600, 100, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, "MINIPA PRECISION - ORDEM DE SERVIÇO")
    
    # Conteúdo
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 720, f"Nº OS: {os_data.id}")
    p.setFont("Helvetica", 11)
    p.drawString(50, 700, f"Cliente: {os_data.cliente}")
    p.drawString(50, 680, f"Equipamento: {os_data.equipamento}")
    p.drawString(50, 660, f"Série: {os_data.serie}")
    p.drawString(50, 640, f"Técnico: {os_data.tecnico}")
    p.line(50, 630, 550, 630)
    
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, 610, "Defeito/Observações:")
    p.setFont("Helvetica", 10)
    p.drawString(50, 590, f"{os_data.defeito}")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"OS_{os_data.id}.pdf", mimetype='application/pdf')

@app.route('/relatorio_estoque')
@login_required
def relatorio_estoque():
    itens = Estoque.query.all()
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 800, "RELATÓRIO DE ESTOQUE DE BANCADA - MINIPA")
    p.line(50, 790, 550, 790)
    
    y = 760
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Componente")
    p.drawString(300, y, "Posição")
    p.drawString(450, y, "Qtd Atual")
    y -= 20
    
    p.setFont("Helvetica", 10)
    for item in itens:
        p.drawString(50, y, item.componente)
        p.drawString(300, y, item.posicao)
        p.drawString(450, y, str(item.quantidade))
        y -= 15
        if y < 50: p.showPage(); y = 800
        
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="relatorio_estoque_minipa.pdf", mimetype='application/pdf')

# --- RESTANTE DAS ROTAS (DASHBOARD, LOGIN, ETC) ---
# ... (Manter as mesmas rotas de login, dashboard, nova_os e estoque do código anterior)

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    estoque = Estoque.query.all()
    return render_template('dashboard.html', ordens=ordens, estoque=estoque)

# (Lembre de incluir as rotas novo_usuario, update_estoque e novo_item_estoque enviadas antes)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        db.session.add(User(username='will', password=generate_password_hash('123'), nome_completo='Will Admin', is_admin=True))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
