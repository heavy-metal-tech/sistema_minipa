import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_seguro'

basedir = os.path.abspath(os.path.dirname(__file__))
# Usando v7 para garantir que o banco seja criado com as colunas certas do zero
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'minipa_v7.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100), default="Técnico Minipa")

class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(100), nullable=False)
    equipamento = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.String(20), default="0,00")
    status = db.Column(db.String(30), default='Aberta')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Pega os dados do formulário
        user = User.query.filter_by(username=request.form.get('username')).first()
        password = request.form.get('password')
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Usuário ou senha inválidos!')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.all()
    return render_template('dashboard.html', ordens=ordens, estoque=[])

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- CRIAÇÃO DO USUÁRIO ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='will').first():
        db.session.add(User(
            username='will', 
            password=generate_password_hash('123'),
            nome_completo="Willian Técnico"
        ))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
