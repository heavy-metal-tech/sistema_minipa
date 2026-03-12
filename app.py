from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minipa_2026_tech'
# Caminho para o banco de dados na pasta do projeto
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///minipa_os.db'
db = SQLAlchemy(app)

# Configuração de Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id): self.id = id

@login_manager.user_loader
def load_user(user_id): return User(user_id)

# Modelo do Banco de Dados
class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_abertura = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='Aberta')
    cliente_nome = db.Column(db.String(100))
    equipamento_modelo = db.Column(db.String(50))
    num_serie = db.Column(db.String(50))
    nota_fiscal = db.Column(db.String(50))
    em_garantia = db.Column(db.String(10))
    defeito = db.Column(db.Text)
    valor = db.Column(db.Float)

# Rotas
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['usuario'] == 'tecnico' and request.form['senha'] == 'minipa123':
            login_user(User(1))
            return redirect(url_for('dashboard'))
        flash('Acesso negado!')
    return render_template('login.html')

@app.route('/')
@login_required
def dashboard():
    lista = OrdemServico.query.order_by(OrdemServico.id.desc()).all()
    return render_template('dashboard.html', ordens=lista)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    if request.method == 'POST':
        nova = OrdemServico(
            cliente_nome=request.form['cliente'],
            equipamento_modelo=request.form['modelo'],
            num_serie=request.form['serie'],
            nota_fiscal=request.form['nf'],
            em_garantia=request.form['garantia'],
            defeito=request.form['defeito'],
            valor=float(request.form['valor'])
        )
        db.session.add(nova)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('nova_os.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)