from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Filial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    ativa = db.Column(db.Boolean, default=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome_completo = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    is_gerente = db.Column(db.Boolean, default=False)
    filial_id = db.Column(db.Integer, db.ForeignKey('filial.id'), nullable=True)
    filial = db.relationship('Filial', backref='usuarios')

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

class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    componente = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    posicao = db.Column(db.String(50))

# ── BGA AI Soldering Module ───────────────────────────────────────────────────

class BGAPerfil(db.Model):
    """Temperature reflow profile for a BGA package type."""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200))
    tipo_solda = db.Column(db.String(20), default='SAC305')  # SAC305, SnPb, etc.
    # Preheat stage
    temp_preheat = db.Column(db.Float, default=150.0)   # °C target
    tempo_preheat = db.Column(db.Integer, default=90)   # seconds
    # Soak stage
    temp_soak = db.Column(db.Float, default=183.0)      # °C target
    tempo_soak = db.Column(db.Integer, default=90)      # seconds
    # Reflow stage
    temp_reflow = db.Column(db.Float, default=245.0)    # °C peak
    tempo_reflow = db.Column(db.Integer, default=60)    # seconds to peak
    tempo_acima_liquidus = db.Column(db.Integer, default=40)  # seconds TAL
    # Cooling
    taxa_resfriamento = db.Column(db.Float, default=2.0)  # °C/second max
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    operacoes = db.relationship('BGAOperacao', backref='perfil', lazy=True)

class BGAMaquina(db.Model):
    """Represents a physical BGA rework station."""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    modelo = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Ociosa')  # Ociosa, Em operação, Manutenção
    temperatura_atual = db.Column(db.Float, default=25.0)
    ultima_calibracao = db.Column(db.DateTime)
    filial_id = db.Column(db.Integer, db.ForeignKey('filial.id'), nullable=True)
    filial = db.relationship('Filial', backref='maquinas_bga')
    operacoes = db.relationship('BGAOperacao', backref='maquina', lazy=True)

class BGAOperacao(db.Model):
    """A single BGA soldering/rework operation."""
    id = db.Column(db.Integer, primary_key=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordem_servico.id'), nullable=True)
    os = db.relationship('OrdemServico', backref='operacoes_bga')
    maquina_id = db.Column(db.Integer, db.ForeignKey('b_g_a_maquina.id'), nullable=True)
    perfil_id = db.Column(db.Integer, db.ForeignKey('b_g_a_perfil.id'), nullable=True)
    componente = db.Column(db.String(150), nullable=False)   # e.g. "Intel i7-8700K BGA1151"
    descricao = db.Column(db.Text)
    status = db.Column(db.String(20), default='Aguardando')  # Aguardando, Em andamento, Concluída, Falha
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_inicio = db.Column(db.DateTime)
    data_fim = db.Column(db.DateTime)
    tecnico = db.Column(db.String(100))
    filial_id = db.Column(db.Integer, db.ForeignKey('filial.id'), nullable=True)
    filial = db.relationship('Filial', backref='operacoes_bga')
    # Photos
    foto_antes = db.Column(db.String(400))   # Cloudinary URL
    foto_depois = db.Column(db.String(400))  # Cloudinary URL
    # AI results
    perfil_ia_json = db.Column(db.Text)      # AI-recommended profile JSON
    resultado_ia = db.Column(db.Text)        # AI inspection result JSON
    qualidade_ia = db.Column(db.Integer)     # 0-100 quality score
    aprovado_ia = db.Column(db.Boolean)
    # Temperature log
    log_temperatura = db.Column(db.Text)     # JSON array [{t, temp}]
    observacoes = db.Column(db.Text)
