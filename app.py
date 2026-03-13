import os, io
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_will_precision'

# Caminho do Banco de Dados
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

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    posicao = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- ROTAS PRINCIPAIS ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username').strip().lower()).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Login inválido.')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    itens_estoque = Estoque.query.all()
    return render_template('dashboard.html', ordens=ordens, estoque=itens_estoque)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        nova = OrdemServico(
            cliente=request.form.get('cliente'), equipamento=request.form.get('equipamento'),
            serie=request.form.get('serie'), nota_fiscal=request.form.get('nota_fiscal'),
            garantia=request.form.get('garantia'), valor=request.form.get('valor'),
            defeito=request.form.get('defeito'), tecnico=current_user.nome_completo
        )
        db.session.add(nova)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('nova_os.html')

# --- ROTAS DE ESTOQUE ---
@app.route('/estoque/novo', methods=['POST'])
@login_required
def novo_item_estoque():
    novo_item = Estoque(
        componente=request.form.get('componente'),
        quantidade=int(request.form.get('quantidade') or 0),
        posicao=request.form.get('posicao')
    )
    db.session.add(novo_item)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/estoque/update/<int:id>', methods=['POST'])
@login_required
def update_estoque(id):
    item = Estoque.query.get_or_404(id)
    item.quantidade = request.form.get('nova_quantidade')
    db.session.commit()
    return redirect(url_for('dashboard'))

# --- ROTA DE IMPRESSÃO PDF ---
@app.route('/imprimir/<int:id>')
@login_required
def imprimir_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFillColorRGB(0.05, 0.28, 0.63) # Azul Minipa
    p.rect(0, 750, 600, 100, fill=1)
    p.setFillColorRGB(1, 1, 1)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, 800, "MINIPA PRECISION - ORDEM DE SERVIÇO #" + str(os_data.id))
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica", 12)
    p.drawString(50, 720, f"Cliente: {os_data.cliente}")
    p.drawString(50, 700, f"Equipamento: {os_data.equipamento}")
    p.drawString(50, 680, f"Nº Série: {os_data.serie}")
    p.drawString(50, 660, f"Técnico: {os_data.tecnico}")
    p.drawString(50, 620, "Defeito:")
    p.drawString(70, 600, f"{os_data.defeito}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"OS_{os_data.id}.pdf", mimetype='application/pdf')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- AUTO-SETUP ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        db.session.add(User(username='will', password=generate_password_hash('123'), nome_completo='Will Admin', is_admin=True))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
