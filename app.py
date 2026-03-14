import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_estavel'

basedir = os.path.abspath(os.path.dirname(__file__))
# Usando v5 para garantir que as tabelas de estoque e usuários reflitam o dashboard novo
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'minipa_v5.db')
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
    cliente = db.Column(db.String(100), nullable=False) # Ajustado para bater com o HTML
    equipamento = db.Column(db.String(100), nullable=False) # Ajustado para bater com o HTML
    serie = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.String(20), default="0,00") # Ajustado para bater com o HTML
    status = db.Column(db.String(30), default='Aberta')

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100))
    quantidade = db.Column(db.Integer)
    posicao = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Login inválido')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    ordens = OrdemServico.query.all()
    estoque = Estoque.query.all()
    return render_template('dashboard.html', ordens=ordens, estoque=estoque)

@app.route('/deletar/<int:id>')
@login_required
def deletar_os(id):
    os_para_deletar = OrdemServico.query.get_or_404(id)
    db.session.delete(os_para_deletar)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- BANCO DE DADOS ---
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
