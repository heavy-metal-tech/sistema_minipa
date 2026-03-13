import os, io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'quantum_minipa_2026'

# Localização do Banco - Garantindo persistência no Render
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'minipa_os.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- ENTIDADES (Database) ---
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

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- PROCESSAMENTO DE ROTAS ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username').strip().lower()).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Acesso negado: Credenciais quânticas incorretas.')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Carregamento explícito de dados
    os_list = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    stock_list = Estoque.query.all()
    return render_template('dashboard.html', ordens=os_list, estoque=stock_list)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        nova = OrdemServico(
            cliente=request.form.get('cliente'),
            equipamento=request.form.get('equipamento'),
            serie=request.form.get('serie'),
            nota_fiscal=request.form.get('nota_fiscal'),
            garantia=request.form.get('garantia'),
            valor=request.form.get('valor'),
            defeito=request.form.get('defeito'),
            tecnico=current_user.nome_completo
        )
        db.session.add(nova)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('nova_os.html')

@app.route('/gerar_pdf/<int:os_id>')
@login_required
def gerar_pdf(os_id):
    os_data = OrdemServico.query.get_or_404(os_id)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "MINIPA - RELATÓRIO TÉCNICO DE BANCADA")
    p.setFont("Helvetica", 12)
    p.drawString(100, 770, f"OS: #{os_data.id} | Cliente: {os_data.cliente}")
    p.drawString(100, 750, f"Modelo: {os_data.equipamento} | S/N: {os_data.serie}")
    p.drawString(100, 730, f"Técnico: {os_data.tecnico}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"OS_{os_id}_Minipa.pdf")

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
