from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# Many-to-many: supervisor ↔ autorizadas
supervisor_autorizadas = db.Table('supervisor_autorizadas',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('filial_id', db.Integer, db.ForeignKey('filial.id'), primary_key=True)
)

class Filial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    email = db.Column(db.String(150))
    ativa = db.Column(db.Boolean, default=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    is_gerente = db.Column(db.Boolean, default=False)
    is_supervisor = db.Column(db.Boolean, default=False)
    filial_id = db.Column(db.Integer, db.ForeignKey('filial.id'), nullable=True)
    filial = db.relationship('Filial', backref='usuarios')
    must_change_password = db.Column(db.Boolean, default=False)
    autorizadas_supervisionadas = db.relationship('Filial', secondary=supervisor_autorizadas,
                                                  backref='supervisores')

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
    filial_id = db.Column(db.Integer, db.ForeignKey('filial.id'), nullable=True)
    filial = db.relationship('Filial', backref='ordens')
    pecas = db.relationship('PecaOS', backref='ordem', lazy=True, cascade='all, delete-orphan')
    logs = db.relationship('LogOS', backref='ordem', lazy=True, cascade='all, delete-orphan', order_by='LogOS.data')

class LogOS(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordem_servico.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.Column(db.String(100))
    tipo = db.Column(db.String(50))   # 'status', 'peca_solicitada', 'peca_enviada', 'edicao'
    descricao = db.Column(db.Text)

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    posicao = db.Column(db.String(50))
