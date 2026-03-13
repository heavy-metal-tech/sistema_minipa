import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_will'

# Configuração de Caminho Absoluto
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'minipa_os.db')
if not os.path.exists(os.path.dirname(db_path)):
    os.makedirs(os.path.dirname(db_path))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
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
    valor = db.Column(db.String(20))
    defeito = db.Column(db.Text)
    tecnico = db.Column(db.String(100))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username').strip().lower()).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Erro de login.')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    return render_template('dashboard.html', ordens=ordens)

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

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# Inicialização do Banco Automática para o Render
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        pw = generate_password_hash('123', method='pbkdf2:sha256')
        admin = User(username='will', password=pw, nome_completo='Will Admin')
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
