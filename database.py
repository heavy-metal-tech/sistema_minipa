from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    is_gerente = db.Column(db.Boolean, default=False)

class TabelaPreco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo_servico = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)

class PecaOS(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordem_servico.id'), nullable=False)
    codigo = db.Column(db.String(50))
    descricao = db.Column(db.String(200))
    quantidade = db.Column(db.Integer, default=1)
    observacoes = db.Column(db.Text)
    foto = db.Column(db.String(300))  # Caminho da foto da peça

class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default='Aberta')

    # Dados do Cliente
    cliente = db.Column(db.String(150))           # Nome / Razão Social
    cpf_cnpj = db.Column(db.String(20))
    tipo_pessoa = db.Column(db.String(3), default='PF')  # PF ou PJ
    nome_fantasia = db.Column(db.String(150))
    inscricao_estadual = db.Column(db.String(30))
    inscricao_municipal = db.Column(db.String(30))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    endereco = db.Column(db.String(200))
    numero = db.Column(db.String(10))
    complemento = db.Column(db.String(100))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))

    # Dados do Equipamento
    marca = db.Column(db.String(100))
    equipamento = db.Column(db.String(100), nullable=False)
    serie = db.Column(db.String(50), nullable=False)
    nota_fiscal = db.Column(db.String(50))
    data_nf = db.Column(db.String(20))
    garantia = db.Column(db.String(3), default='Não')

    # Defeito e Serviço
    defeito = db.Column(db.Text)
    fotos_defeito = db.Column(db.Text)  # JSON com lista de caminhos das fotos
    tipo_servico = db.Column(db.String(100))
    valor = db.Column(db.String(20))

    tecnico = db.Column(db.String(100))
    pecas = db.relationship('PecaOS', backref='ordem', lazy=True, cascade='all, delete-orphan')

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    posicao = db.Column(db.String(50))
