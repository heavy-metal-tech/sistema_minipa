import os, io, smtplib, json, secrets
import cloudinary
import cloudinary.uploader
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import Flask, render_template, redirect, url_for, request, flash, send_file, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from database import db, User, OrdemServico, Estoque, TabelaPreco, PecaOS, Filial, supervisor_autorizadas, LogOS

app = Flask(__name__)
_secret = os.environ.get('SECRET_KEY')
if not _secret:
    _secret = secrets.token_hex(32)
    print('WARNING: SECRET_KEY not set. Sessions will reset on restart. Set SECRET_KEY env var.')
app.config['SECRET_KEY'] = _secret

_db_url = os.environ.get('DATABASE_URL', 'sqlite:///instance/minipa_v3.db')
# Render provides postgres:// but SQLAlchemy requires postgresql://
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 600,
    'connect_args': {'connect_timeout': 10},
}

# E-mail config (edite conforme seu servidor SMTP)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')
EMAIL_MINIPA = os.environ.get('EMAIL_MINIPA', 'assistencia@minipa.com.br')

db.init_app(app)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])

# Jinja filter para JSON
import json as _json
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return _json.loads(value) if value else []
    except:
        return []

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def check_must_change_password():
    if current_user.is_authenticated and getattr(current_user, 'must_change_password', False):
        if request.endpoint not in ('trocar_senha', 'logout', 'static'):
            return redirect(url_for('trocar_senha'))

@app.errorhandler(429)
def rate_limit_exceeded(e):
    flash('Muitas tentativas. Aguarde 1 minuto e tente novamente.', 'error')
    return render_template('login.html'), 429

# ── Helpers ──────────────────────────────────────────────────────────────────

def salvar_foto(foto):
    """Upload photo to Cloudinary if credentials are set, otherwise skip."""
    if not foto or not foto.filename:
        return None
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    if not (cloud_name and api_key and api_secret):
        return None
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
    result = cloudinary.uploader.upload(foto, folder='minipa_os')
    return result.get('secure_url')

STATUS_COLORS = {
    'Aberta': '#2563eb',
    'Em análise': '#d97706',
    'Aguardando peça': '#7c3aed',
    'Peça enviada': '#0891b2',
    'Manutenção concluída': '#059669',
    'Equipamento retirado pelo cliente': '#65a30d',
    'Concluída': '#16a34a',
    'Enviada para fabricante': '#6b7280',
}

def draw_pdf_os(os_data):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4

    # Cabeçalho
    p.setFillColorRGB(0.05, 0.28, 0.63)
    p.rect(0, H - 90, W, 90, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, H - 42, f"ORDEM DE SERVIÇO  Nº {os_data.id:05d}")
    p.setFont("Helvetica", 10)
    p.drawString(40, H - 60, "Minipa Precision — Assistência Técnica Autorizada")
    data_fmt = os_data.data_abertura.strftime('%d/%m/%Y %H:%M') if os_data.data_abertura else '—'
    p.drawString(40, H - 75, f"Data de Abertura: {data_fmt}     Status: {os_data.status}")

    y = H - 110

    def section(title):
        nonlocal y
        p.setFillColorRGB(0.93, 0.95, 0.98)
        p.rect(30, y - 4, W - 60, 18, fill=1, stroke=0)
        p.setFillColor(colors.HexColor('#0f1e4a'))
        p.setFont("Helvetica-Bold", 10)
        p.drawString(36, y + 2, title.upper())
        y -= 22

    def row(label, value, x=40, dx=150):
        nonlocal y
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.HexColor('#374151'))
        p.drawString(x, y, label)
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(x + dx, y, str(value or '—'))
        y -= 14

    def row2(l1, v1, l2, v2):
        nonlocal y
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.HexColor('#374151'))
        p.drawString(40, y, l1)
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(190, y, str(v1 or '—'))
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.HexColor('#374151'))
        p.drawString(310, y, l2)
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(460, y, str(v2 or '—'))
        y -= 14

    # Dados do cliente
    section("Dados do Cliente / Empresa")
    tipo = os_data.tipo_pessoa or 'PF'
    if tipo == 'PJ':
        row("Razão Social:", os_data.cliente)
        row2("Nome Fantasia:", os_data.nome_fantasia, "CNPJ:", os_data.cpf_cnpj)
        row2("Insc. Estadual:", os_data.inscricao_estadual, "Insc. Municipal:", os_data.inscricao_municipal)
    else:
        row("Nome:", os_data.cliente)
        row("CPF:", os_data.cpf_cnpj)
    row2("Telefone:", os_data.telefone, "E-mail:", os_data.email)
    end_full = f"{os_data.endereco or ''}, {os_data.numero or ''} {os_data.complemento or ''}".strip(', ')
    row("Endereço:", end_full)
    row2("Bairro:", os_data.bairro, "CEP:", os_data.cep)
    row2("Cidade:", os_data.cidade, "UF:", os_data.estado)
    y -= 6

    # Dados do equipamento
    section("Dados do Equipamento")
    row2("Marca:", os_data.marca, "Modelo:", os_data.equipamento)
    row2("Nº de Série:", os_data.serie, "Em Garantia:", os_data.garantia)
    row2("Nota Fiscal:", os_data.nota_fiscal, "Data NF:", os_data.data_nf)
    y -= 6

    # Defeito
    section("Defeito Informado pelo Cliente")
    p.setFont("Helvetica", 9)
    p.setFillColor(colors.black)
    defeito_text = os_data.defeito or '—'
    # Quebra de linha simples
    words = defeito_text.split()
    line = ''
    for word in words:
        if len(line + ' ' + word) > 90:
            p.drawString(40, y, line.strip())
            y -= 13
            line = word
        else:
            line += ' ' + word
    if line:
        p.drawString(40, y, line.strip())
        y -= 13
    y -= 6

    # Peças solicitadas
    section("Peças Solicitadas")
    if os_data.pecas:
        p.setFont("Helvetica-Bold", 8)
        p.setFillColor(colors.HexColor('#374151'))
        p.drawString(40, y, "Código")
        p.drawString(120, y, "Descrição")
        p.drawString(340, y, "Qtd")
        p.drawString(380, y, "Observações")
        y -= 12
        p.setFont("Helvetica", 8)
        p.setFillColor(colors.black)
        for peca in os_data.pecas:
            p.drawString(40, y, peca.codigo or '—')
            p.drawString(120, y, peca.descricao or '—')
            p.drawString(340, y, str(peca.quantidade))
            p.drawString(380, y, peca.observacoes or '—')
            y -= 12
    else:
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#9ca3af'))
        p.drawString(40, y, "Nenhuma peça solicitada.")
        y -= 14
    y -= 6

    # Serviço e Valor
    section("Serviço e Valor")
    row2("Valor Estimado:", f"R$ {os_data.valor or '0,00'}", "Técnico:", os_data.tecnico)
    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(colors.HexColor('#374151'))
    p.drawString(40, y, "Descrição do Serviço:")
    y -= 13
    p.setFont("Helvetica", 9)
    p.setFillColor(colors.black)
    servico_text = (os_data.tipo_servico or '—').replace('\r', '')
    for line in servico_text.split('\n')[:6]:
        words = line.split()
        cur = ''
        for word in words:
            if len(cur + ' ' + word) > 90:
                p.drawString(50, y, cur.strip())
                y -= 12
                cur = word
            else:
                cur += ' ' + word
        if cur.strip():
            p.drawString(50, y, cur.strip())
            y -= 12
    y -= 6

    # Rodapé
    p.setFillColorRGB(0.05, 0.28, 0.63)
    p.rect(0, 0, W, 30, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica", 8)
    p.drawString(40, 11, "Minipa Precision — Assistência Técnica Autorizada")
    p.drawRightString(W - 40, 11, f"OS #{os_data.id:05d} — {data_fmt}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# ── Rotas de PDF ──────────────────────────────────────────────────────────────

@app.route('/relatorio/os/<int:id>')
@login_required
def pdf_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    buffer = draw_pdf_os(os_data)
    return send_file(buffer, as_attachment=True, download_name=f"OS_{os_data.id:05d}.pdf", mimetype='application/pdf')

@app.route('/relatorio/estoque')
@login_required
def pdf_estoque():
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4
    p.setFillColorRGB(0.05, 0.28, 0.63)
    p.rect(0, H - 70, W, 70, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, H - 40, "RELATÓRIO DE INVENTÁRIO — MINIPA PRECISION")
    p.setFont("Helvetica", 10)
    p.drawString(40, H - 58, datetime.now().strftime('%d/%m/%Y %H:%M'))
    p.setFillColor(colors.black)
    y = H - 100
    p.setFont("Helvetica-Bold", 10)
    p.drawString(40, y, "Item")
    p.drawString(280, y, "Quantidade")
    p.drawString(400, y, "Posição")
    y -= 16
    p.setFont("Helvetica", 10)
    for item in Estoque.query.all():
        p.drawString(40, y, item.componente)
        p.drawString(280, y, str(item.quantidade))
        p.drawString(400, y, item.posicao or '—')
        y -= 14
        if y < 60:
            p.showPage()
            y = H - 40
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="estoque_minipa.pdf", mimetype='application/pdf')

# ── Envio de E-mail ───────────────────────────────────────────────────────────

@app.route('/enviar_email/<int:id>', methods=['POST'])
@login_required
def enviar_email(id):
    os_data = OrdemServico.query.get_or_404(id)
    # Usa o email da autorizada se cadastrado, caso contrário usa o email global da Minipa
    destino = (os_data.filial.email if os_data.filial and os_data.filial.email else None) or EMAIL_MINIPA
    try:
        pdf_buffer = draw_pdf_os(os_data)
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = destino
        msg['Subject'] = f"Solicitação de peças – OS nº {os_data.id:05d}"
        body = (f"Prezados,\n\nInformamos a abertura da Ordem de Serviço nº {os_data.id:05d} "
                f"referente ao equipamento modelo {os_data.equipamento} (S/N: {os_data.serie}).\n"
                f"Segue em anexo relatório contendo defeito apresentado e peças solicitadas.\n\n"
                f"Atenciosamente,\n{current_user.nome_completo}\nMinipa Precision — Assistência Técnica Autorizada")
        msg.attach(MIMEText(body, 'plain'))
        attachment = MIMEApplication(pdf_buffer.read(), _subtype='pdf')
        attachment.add_header('Content-Disposition', 'attachment', filename=f"OS_{os_data.id:05d}.pdf")
        msg.attach(attachment)
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        # Atualiza status
        os_data.status = 'Enviada para fabricante'
        db.session.commit()
        flash('E-mail enviado com sucesso para a Minipa!', 'success')
    except Exception as e:
        flash(f'Erro ao enviar e-mail: {str(e)}', 'error')
    return redirect(url_for('ver_os', id=id))

# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/tabela_precos')
@login_required
def api_tabela_precos():
    itens = TabelaPreco.query.all()
    return jsonify([{'id': i.id, 'tipo': i.tipo_servico, 'valor': i.valor} for i in itens])

# ── Navegação ─────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:50]
        password = request.form.get('password', '')[:200]
        if not username or not password:
            flash('Preencha usuário e senha.', 'error')
            return render_template('login.html')
        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/trocar_senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if not getattr(current_user, 'must_change_password', False):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nova = request.form.get('nova_senha', '')
        confirma = request.form.get('confirma_senha', '')
        if len(nova) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'error')
        elif nova != confirma:
            flash('As senhas não coincidem.', 'error')
        else:
            current_user.password = generate_password_hash(nova)
            current_user.must_change_password = False
            db.session.commit()
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('trocar_senha.html')

@app.route('/dashboard')
@login_required
def dashboard():
    from collections import defaultdict
    from datetime import datetime, timedelta
    from sqlalchemy import func

    q = request.args.get('q', '')
    status_filter = request.args.get('status', '')

    # Base query scoped to what this user can see
    base_q = OrdemServico.query
    if current_user.is_admin or current_user.is_gerente:
        pass
    elif current_user.is_supervisor:
        ids = [f.id for f in current_user.autorizadas_supervisionadas]
        base_q = base_q.filter(OrdemServico.filial_id.in_(ids)) if ids else base_q.filter(db.false())
    elif current_user.filial_id:
        base_q = base_q.filter_by(filial_id=current_user.filial_id)

    # OS list with search/filter on top of base
    query = base_q
    if q:
        query = query.filter(
            OrdemServico.cliente.ilike(f'%{q}%') |
            OrdemServico.equipamento.ilike(f'%{q}%')
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    ordens = query.order_by(OrdemServico.id.desc()).all()
    estoque = Estoque.query.all()

    # Stats scoped to base_q
    all_visible = base_q.all()
    stats = {
        'abertas': base_q.filter_by(status='Aberta').count(),
        'aguardando': base_q.filter_by(status='Aguardando peça').count(),
        'concluidas': base_q.filter_by(status='Concluída').count(),
        'total': base_q.count(),
        'faturamento': sum(float(o.valor.replace(',','.')) for o in all_visible if o.valor and o.valor.replace(',','.').replace('.','',1).isdigit()),
    }

    # Gráfico OS por mês (últimos 6 meses) — scoped
    meses = []
    os_por_mes = []
    for i in range(5, -1, -1):
        d = datetime.now().replace(day=1) - timedelta(days=i*28)
        count = base_q.filter(
            db.extract('month', OrdemServico.data_abertura) == d.month,
            db.extract('year', OrdemServico.data_abertura) == d.year
        ).count()
        meses.append(d.strftime('%b/%y'))
        os_por_mes.append(count)

    # Gráfico por status — scoped
    status_labels = ['Aberta', 'Em análise', 'Aguardando peça', 'Peça enviada', 'Manutenção concluída', 'Equipamento retirado pelo cliente', 'Concluída', 'Enviada para fabricante']
    status_data = [base_q.filter_by(status=s).count() for s in status_labels]

    # Top equipamentos — scoped
    top_equip = base_q.with_entities(OrdemServico.equipamento, func.count(OrdemServico.id).label('total'))\
        .group_by(OrdemServico.equipamento).order_by(func.count(OrdemServico.id).desc()).limit(5).all()

    usuarios = User.query.order_by(User.is_admin.desc(), User.nome_completo).all()
    return render_template('dashboard.html', ordens=ordens, estoque=estoque,
                           stats=stats, q=q, status_filter=status_filter,
                           STATUS_COLORS=STATUS_COLORS,
                           meses=meses, os_por_mes=os_por_mes,
                           status_labels=status_labels, status_data=status_data,
                           top_equip=top_equip, usuarios=usuarios)

@app.route('/nova_os', methods=['GET', 'POST'])
@login_required
def nova_os():
    tabela = TabelaPreco.query.all()
    filiais = Filial.query.filter_by(ativa=True).all()
    if request.method == 'POST':
        # Determine filial_id: admin/gerente/supervisor choose; técnico uses own filial
        if current_user.is_admin or current_user.is_gerente:
            filial_id = request.form.get('filial_id') or None
            filial_id = int(filial_id) if filial_id else None
        elif current_user.is_supervisor:
            filial_id = request.form.get('filial_id') or None
            filial_id = int(filial_id) if filial_id else None
        else:
            filial_id = current_user.filial_id
        nova = OrdemServico(
            status=request.form.get('status', 'Aberta'),
            tipo_pessoa=request.form.get('tipo_pessoa', 'PF'),
            cliente=request.form.get('cliente'),
            cpf_cnpj=request.form.get('cpf_cnpj'),
            nome_fantasia=request.form.get('nome_fantasia'),
            inscricao_estadual=request.form.get('inscricao_estadual'),
            inscricao_municipal=request.form.get('inscricao_municipal'),
            telefone=request.form.get('telefone'),
            email=request.form.get('email'),
            endereco=request.form.get('endereco'),
            numero=request.form.get('numero'),
            complemento=request.form.get('complemento'),
            bairro=request.form.get('bairro'),
            cidade=request.form.get('cidade'),
            estado=request.form.get('estado'),
            cep=request.form.get('cep'),
            marca=request.form.get('marca'),
            equipamento=request.form.get('equipamento'),
            serie=request.form.get('serie'),
            nota_fiscal=request.form.get('nota_fiscal'),
            data_nf=request.form.get('data_nf'),
            garantia=request.form.get('garantia', 'Não'),
            defeito=request.form.get('defeito'),
            tipo_servico=request.form.get('tipo_servico'),
            valor=request.form.get('valor'),
            tecnico=current_user.nome_completo,
            filial_id=filial_id,
        )
        db.session.add(nova)
        try:
            db.session.flush()
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar OS: {str(e)}', 'error')
            return render_template('nova_os.html', tabela=tabela, filiais=filiais)
        # Peças
        codigos = request.form.getlist('peca_codigo[]')
        descricoes = request.form.getlist('peca_descricao[]')
        quantidades = request.form.getlist('peca_quantidade[]')
        obs_list = request.form.getlist('peca_obs[]')
        for i in range(len(codigos)):
            if descricoes[i].strip():
                peca = PecaOS(os_id=nova.id, codigo=codigos[i],
                              descricao=descricoes[i], quantidade=int(quantidades[i] or 1),
                              observacoes=obs_list[i])
                db.session.add(peca)
        db.session.add(LogOS(os_id=nova.id, usuario=current_user.nome_completo,
                              tipo='criacao', descricao=f'OS criada com status "{nova.status}"'))
        try:
            db.session.commit()
            flash('Ordem de Serviço criada com sucesso!', 'success')
            return redirect(url_for('ver_os', id=nova.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar OS: {str(e)}', 'error')
            return render_template('nova_os.html', tabela=tabela, filiais=filiais)
    return render_template('nova_os.html', tabela=tabela, filiais=filiais)

@app.route('/os/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    tabela = TabelaPreco.query.all()
    if request.method == 'POST':
        status_anterior = os_data.status
        novo_status = request.form.get('status', os_data.status)
        os_data.status = novo_status
        os_data.tipo_pessoa = request.form.get('tipo_pessoa', os_data.tipo_pessoa)
        os_data.cliente = request.form.get('cliente', os_data.cliente)
        os_data.cpf_cnpj = request.form.get('cpf_cnpj', os_data.cpf_cnpj)
        os_data.nome_fantasia = request.form.get('nome_fantasia', os_data.nome_fantasia)
        os_data.inscricao_estadual = request.form.get('inscricao_estadual', os_data.inscricao_estadual)
        os_data.inscricao_municipal = request.form.get('inscricao_municipal', os_data.inscricao_municipal)
        os_data.telefone = request.form.get('telefone', os_data.telefone)
        os_data.email = request.form.get('email', os_data.email)
        os_data.endereco = request.form.get('endereco', os_data.endereco)
        os_data.numero = request.form.get('numero', os_data.numero)
        os_data.complemento = request.form.get('complemento', os_data.complemento)
        os_data.bairro = request.form.get('bairro', os_data.bairro)
        os_data.cidade = request.form.get('cidade', os_data.cidade)
        os_data.estado = request.form.get('estado', os_data.estado)
        os_data.cep = request.form.get('cep', os_data.cep)
        os_data.marca = request.form.get('marca', os_data.marca)
        os_data.equipamento = request.form.get('equipamento', os_data.equipamento)
        os_data.serie = request.form.get('serie', os_data.serie)
        os_data.nota_fiscal = request.form.get('nota_fiscal', os_data.nota_fiscal)
        os_data.data_nf = request.form.get('data_nf', os_data.data_nf)
        os_data.garantia = request.form.get('garantia', os_data.garantia)
        os_data.defeito = request.form.get('defeito', os_data.defeito)
        os_data.tipo_servico = request.form.get('tipo_servico', os_data.tipo_servico)
        os_data.valor = request.form.get('valor', os_data.valor)
        # Novas fotos do defeito
        novas_fotos = []
        for foto in request.files.getlist('fotos_defeito[]'):
            caminho = salvar_foto(foto)
            if caminho:
                novas_fotos.append(caminho)
        if novas_fotos:
            fotos_existentes = json.loads(os_data.fotos_defeito or '[]')
            fotos_existentes.extend(novas_fotos)
            os_data.fotos_defeito = json.dumps(fotos_existentes)
        if novo_status != status_anterior:
            tipo = 'peca_solicitada' if novo_status == 'Aguardando peça' else \
                   'peca_enviada' if novo_status == 'Peça enviada' else 'status'
            db.session.add(LogOS(os_id=os_data.id, usuario=current_user.nome_completo,
                                 tipo=tipo,
                                 descricao=f'Status alterado: "{status_anterior}" → "{novo_status}"'))
        else:
            db.session.add(LogOS(os_id=os_data.id, usuario=current_user.nome_completo,
                                 tipo='edicao', descricao='OS editada'))
        db.session.commit()
        flash('OS atualizada com sucesso!', 'success')
        return redirect(url_for('ver_os', id=id))
    return render_template('editar_os.html', os=os_data, tabela=tabela, STATUS_COLORS=STATUS_COLORS)

@app.route('/os/<int:id>')
@login_required
def ver_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    return render_template('ver_os.html', os=os_data, STATUS_COLORS=STATUS_COLORS)

@app.route('/os/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status(id):
    os_data = OrdemServico.query.get_or_404(id)
    status_anterior = os_data.status
    novo_status = request.form.get('status')
    os_data.status = novo_status
    # Determina o tipo do log pelo status
    tipo = 'status'
    if novo_status == 'Aguardando peça':
        tipo = 'peca_solicitada'
    elif novo_status == 'Peça enviada':
        tipo = 'peca_enviada'
    db.session.add(LogOS(os_id=id, usuario=current_user.nome_completo,
                         tipo=tipo,
                         descricao=f'Status alterado: "{status_anterior}" → "{novo_status}"'))
    db.session.commit()
    return redirect(url_for('ver_os', id=id))

@app.route('/estoque/add', methods=['POST'])
@login_required
def add_estoque():
    try:
        novo = Estoque(componente=request.form.get('componente'),
                       quantidade=int(request.form.get('quantidade', 0)),
                       posicao=request.form.get('posicao'))
        db.session.add(novo)
        db.session.commit()
        flash('Item adicionado ao estoque.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao adicionar item: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

@app.route('/os/<int:id>/delete', methods=['POST'])
@login_required
def delete_os(id):
    if not (current_user.is_admin or current_user.is_gerente):
        flash('Sem permissão para deletar OS.', 'error')
        return redirect(url_for('dashboard'))
    os_data = OrdemServico.query.get_or_404(id)
    db.session.delete(os_data)
    db.session.commit()
    flash(f'OS #{id:05d} deletada com sucesso.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/estoque/delete/<int:id>', methods=['POST'])
@login_required
def delete_estoque(id):
    item = Estoque.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Item removido do estoque.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/usuarios/delete/<int:id>', methods=['POST'])
@login_required
def delete_usuario(id):
    if not (current_user.is_admin or current_user.is_gerente):
        return redirect(url_for('dashboard'))
    if id == current_user.id:
        flash('Você não pode deletar seu próprio usuário.', 'error')
        return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    # Gerente não pode deletar admin
    if user.is_admin and not current_user.is_admin:
        flash('Sem permissão para deletar administradores.', 'error')
        return redirect(url_for('dashboard'))
    db.session.delete(user)
    db.session.commit()
    flash(f'Usuário {user.nome_completo} removido.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tabela_precos', methods=['GET', 'POST'])
@login_required
def tabela_precos():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            t = TabelaPreco(tipo_servico=request.form.get('tipo_servico'),
                            valor=float(request.form.get('valor', 0)))
            db.session.add(t)
        elif action == 'delete':
            t = TabelaPreco.query.get(int(request.form.get('id')))
            if t:
                db.session.delete(t)
        db.session.commit()
    tabela = TabelaPreco.query.all()
    return render_template('tabela_precos.html', tabela=tabela)

@app.route('/usuarios/novo', methods=['POST'])
@login_required
def novo_tecnico():
    if current_user.is_admin or current_user.is_gerente:
        username = request.form.get('username', '').strip()
        if not username:
            flash('Username é obrigatório.', 'error')
            return redirect(url_for('dashboard'))
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash(f'Username "{username}" já existe. Escolha outro.', 'error')
            return redirect(url_for('dashboard'))
        cargo = request.form.get('cargo', 'tecnico')
        u = User(
            username=username,
            password=generate_password_hash(request.form.get('password')),
            nome_completo=request.form.get('nome'),
            is_admin=(cargo == 'admin') and current_user.is_admin,
            is_gerente=(cargo == 'gerente'),
            is_supervisor=(cargo == 'supervisor'),
            must_change_password=True
        )
        db.session.add(u)
        try:
            db.session.commit()
            flash(f'Usuário {u.nome_completo} cadastrado com sucesso!', 'success')
        except Exception:
            db.session.rollback()
            flash('Erro ao cadastrar usuário. Verifique se o username já existe.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/autorizadas', methods=['GET', 'POST'])
@login_required
def autorizadas():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            f = Filial(nome=request.form.get('nome'),
                       cidade=request.form.get('cidade'),
                       estado=request.form.get('estado'),
                       email=request.form.get('email') or None)
            db.session.add(f)
            flash('Autorizada cadastrada!', 'success')
        elif action == 'set_email':
            f = Filial.query.get(int(request.form.get('id')))
            if f:
                f.email = request.form.get('email') or None
            flash('E-mail atualizado!', 'success')
        elif action == 'delete':
            f = Filial.query.get(int(request.form.get('id')))
            if f: db.session.delete(f)
            flash('Autorizada removida!', 'success')
        elif action == 'vincular':
            user = User.query.get(int(request.form.get('user_id')))
            filial_id = request.form.get('filial_id')
            if user:
                user.filial_id = int(filial_id) if filial_id else None
            flash('Usuário vinculado!', 'success')
        elif action == 'vincular_supervisor':
            user = User.query.get(int(request.form.get('supervisor_id')))
            filial_ids = request.form.getlist('supervisor_filiais[]')
            if user and user.is_supervisor:
                user.autorizadas_supervisionadas = [Filial.query.get(int(fid)) for fid in filial_ids if fid]
            flash('Supervisor atualizado!', 'success')
        db.session.commit()
    lista = Filial.query.all()
    usuarios = User.query.all()
    supervisores = User.query.filter_by(is_supervisor=True).all()
    return render_template('autorizadas.html', filiais=lista, usuarios=usuarios, supervisores=supervisores)

@app.route('/logs')
@login_required
def logs_global():
    if not (current_user.is_admin or current_user.is_gerente):
        return redirect(url_for('dashboard'))
    logs = LogOS.query.order_by(LogOS.data.desc()).limit(300).all()
    return render_template('logs.html', logs=logs)

@app.route('/ping')
def ping():
    return 'ok', 200

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# ── Init DB ───────────────────────────────────────────────────────────────────

def _init_db():
    import time
    from sqlalchemy import text
    migrations = [
        'ALTER TABLE ordem_servico ADD COLUMN IF NOT EXISTS fotos_defeito TEXT',
        'ALTER TABLE peca_os ADD COLUMN IF NOT EXISTS foto VARCHAR(300)',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_gerente BOOLEAN DEFAULT FALSE',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS filial_id INTEGER',
        'ALTER TABLE ordem_servico ADD COLUMN IF NOT EXISTS filial_id INTEGER',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_supervisor BOOLEAN DEFAULT FALSE',
        'ALTER TABLE filial ADD COLUMN IF NOT EXISTS email VARCHAR(150)',
        '''CREATE TABLE IF NOT EXISTS log_os (
            id SERIAL PRIMARY KEY,
            os_id INTEGER REFERENCES ordem_servico(id) ON DELETE CASCADE,
            data TIMESTAMP DEFAULT NOW(),
            usuario VARCHAR(100),
            tipo VARCHAR(50),
            descricao TEXT
        )''',
    ]
    for attempt in range(5):
        try:
            db.create_all()
            with db.engine.connect() as conn:
                for i, sql in enumerate(migrations):
                    try:
                        conn.execute(text(f"SAVEPOINT m{i}"))
                        conn.execute(text(sql))
                        conn.execute(text(f"RELEASE SAVEPOINT m{i}"))
                    except Exception:
                        try:
                            conn.execute(text(f"ROLLBACK TO SAVEPOINT m{i}"))
                        except Exception:
                            pass
                conn.commit()
            if not User.query.filter_by(username='will').first():
                db.session.add(User(username='will',
                                    password=generate_password_hash('123', method='pbkdf2:sha256'),
                                    nome_completo='Will Admin', is_admin=True,
                                    must_change_password=True))
                db.session.commit()
            if TabelaPreco.query.count() == 0:
                for tipo, valor in [('Reparo com PCI', 180.00), ('Reparo Geral', 120.00),
                                    ('Calibração', 90.00), ('Diagnóstico', 60.00)]:
                    db.session.add(TabelaPreco(tipo_servico=tipo, valor=valor))
                db.session.commit()
            return  # sucesso
        except Exception as e:
            print(f'DB init attempt {attempt + 1} failed: {e}')
            if attempt < 4:
                time.sleep(3)

with app.app_context():
    _init_db()

if __name__ == '__main__':
    app.run(debug=True)
