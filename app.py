import os, io, smtplib, json, secrets, threading
import cloudinary, cloudinary.uploader
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import Flask, render_template, redirect, url_for, request, flash, send_file, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from datetime import datetime
from database import db, User, OrdemServico, Estoque, TabelaPreco, PecaOS, Filial, supervisor_autorizadas, LogOS, brt_now

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
if _db_url.startswith('postgresql'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_size': 3,
        'max_overflow': 2,
        'connect_args': {'connect_timeout': 10},
    }

# E-mail config (edite conforme seu servidor SMTP)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')
EMAIL_MINIPA = os.environ.get('EMAIL_MINIPA', 'assistencia@minipa.com.br')

def _enviar_email_bg(para, assunto, corpo):
    """Envia e-mail em background thread para não bloquear a requisição."""
    def _send():
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = para
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=28) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Erro ao enviar e-mail para %s', para)
    t = threading.Thread(target=_send, daemon=True)
    t.start()

db.init_app(app)
csrf = CSRFProtect(app)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])

# Jinja filter para JSON
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except (json.JSONDecodeError, TypeError):
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

# ── Helpers ──────────────────────────────────────────────────────

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

def _can_access_os(os_data):
    """Verifica se o usuário atual tem acesso à OS (por filial)."""
    if current_user.is_admin or current_user.is_gerente:
        return True
    if current_user.is_supervisor:
        ids = [f.id for f in current_user.autorizadas_supervisionadas]
        return os_data.filial_id in ids if ids else False
    return os_data.filial_id == current_user.filial_id

STATUSES = [
    'Aberta',
    'Em análise',
    'Aguardando peça',
    'Peça enviada',
    'Manutenção concluída',
    'Equipamento retirado pelo cliente',
    'Concluída',
    'Enviada para fabricante',
]

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

@app.context_processor
def inject_globals():
    return {'STATUSES': STATUSES, 'STATUS_COLORS': STATUS_COLORS}

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

# ── Rotas de PDF ─────────────────────────────────────────────────────────────────────────

@app.route('/relatorio/os/<int:id>')
@login_required
def pdf_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    if not _can_access_os(os_data):
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
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
    p.drawString(40, H - 58, brt_now().strftime('%d/%m/%Y %H:%M'))
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

def _draw_pecas_por_autorizada(filial_id=None, filial_ids=None):
    """Gera PDF de peças solicitadas agrupadas por autorizada. Se filial_id, apenas aquela."""
    from sqlalchemy.orm import joinedload as _jl
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4
    BLUE = (0.05, 0.28, 0.63)

    def cabecalho_pagina():
        p.setFillColorRGB(*BLUE)
        p.rect(0, H - 70, W, 70, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(40, H - 38, "RELATÓRIO DE PEÇAS SOLICITADAS POR AUTORIZADA")
        p.setFont("Helvetica", 9)
        p.drawString(40, H - 56, f"Gerado em {brt_now().strftime('%d/%m/%Y às %H:%M')}")
        p.setFillColor(colors.black)
        return H - 90

    if filial_id:
        filiais = Filial.query.filter_by(id=filial_id).all()
    elif filial_ids is not None:
        filiais = Filial.query.filter(Filial.id.in_(filial_ids)).order_by(Filial.nome).all()
    else:
        filiais = Filial.query.order_by(Filial.nome).all()

    y = cabecalho_pagina()

    for filial in filiais:
        # busca OS desta filial que têm peças
        ordens = (OrdemServico.query
                  .filter_by(filial_id=filial.id)
                  .options(_jl(OrdemServico.pecas))
                  .all())
        pecas_encontradas = [peca for os_ in ordens for peca in os_.pecas]
        if not pecas_encontradas:
            continue

        # Cabeçalho da autorizada
        if y < 140:
            p.showPage()
            y = cabecalho_pagina()
        p.setFillColorRGB(*BLUE)
        p.rect(30, y - 4, W - 60, 22, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 10)
        loc = f" — {filial.cidade}/{filial.estado}" if filial.cidade else ""
        p.drawString(36, y + 4, f"{filial.nome}{loc}")
        p.setFillColor(colors.black)
        y -= 28

        # Header da tabela
        p.setFont("Helvetica-Bold", 8)
        p.setFillColorRGB(0.9, 0.9, 0.9)
        p.rect(30, y - 2, W - 60, 16, fill=1, stroke=0)
        p.setFillColor(colors.black)
        p.drawString(34, y + 4,  "OS#")
        p.drawString(80, y + 4,  "Equipamento")
        p.drawString(220, y + 4, "Cód. Peça")
        p.drawString(300, y + 4, "Descrição")
        p.drawString(490, y + 4, "Qtd")
        y -= 18

        p.setFont("Helvetica", 8)
        for os_ in ordens:
            for peca in os_.pecas:
                if y < 50:
                    p.showPage()
                    y = cabecalho_pagina()
                    p.setFont("Helvetica", 8)
                p.drawString(34,  y, f"{os_.id:05d}")
                p.drawString(80,  y, (os_.equipamento or '')[:22])
                p.drawString(220, y, (peca.codigo or '—')[:12])
                desc = (peca.descricao or '—')[:28]
                p.drawString(300, y, desc)
                p.drawString(490, y, str(peca.quantidade))
                y -= 13
        y -= 8

    if y == H - 90:
        p.setFont("Helvetica", 11)
        p.setFillColorRGB(0.6, 0.6, 0.6)
        p.drawCentredString(W / 2, H / 2, "Nenhuma peça solicitada encontrada.")
        p.setFillColor(colors.black)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

@app.route('/relatorio/pecas_por_autorizada')
@login_required
def pdf_pecas_autorizada():
    if not (current_user.is_admin or current_user.is_gerente or current_user.is_supervisor):
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
    ids = [f.id for f in current_user.autorizadas_supervisionadas] if current_user.is_supervisor else None
    buf = _draw_pecas_por_autorizada(filial_ids=ids)
    return send_file(buf, as_attachment=True,
                     download_name="pecas_por_autorizada.pdf", mimetype='application/pdf')

@app.route('/relatorio/pecas_por_autorizada/email', methods=['POST'])
@login_required
def email_pecas_autorizada():
    if not (current_user.is_admin or current_user.is_gerente or current_user.is_supervisor):
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
    DESTINO = 'wfmalcato@minipa.com.br'
    ids = [f.id for f in current_user.autorizadas_supervisionadas] if current_user.is_supervisor else None
    if ids is not None:
        filiais = Filial.query.filter(Filial.id.in_(ids)).order_by(Filial.nome).all()
    else:
        filiais = Filial.query.order_by(Filial.nome).all()
    nomes_filiais = ', '.join(f.nome for f in filiais) if filiais else 'Todas'
    filiais_detalhe = '\n'.join(
        f"  • {f.nome}{(' — ' + f.cidade + '/' + f.estado) if f.cidade else ''}"
        for f in filiais
    )
    cargo = ('Administrador' if current_user.is_admin else
             'Gerente' if current_user.is_gerente else 'Supervisor')
    _now_str = brt_now().strftime('%d/%m/%Y às %H:%M')
    _date_str = brt_now().strftime('%d/%m/%Y')
    _date_file = brt_now().strftime('%Y%m%d')
    _remetente = current_user.nome_completo
    try:
        buf = _draw_pecas_por_autorizada(filial_ids=ids)
        pdf_bytes = buf.read()
    except Exception:
        app.logger.exception('Erro ao gerar relatório de peças')
        flash('Erro ao gerar relatório. Tente novamente.', 'error')
        return redirect(url_for('dashboard'))
    assunto = f"Relatório de Peças — {nomes_filiais} — {_date_str}"
    corpo = (
        f"Prezado William,\n\n"
        f"Segue em anexo o relatório de peças solicitadas, gerado em {_now_str}.\n\n"
        f"Autorizada(s) incluída(s) no relatório:\n{filiais_detalhe}\n\n"
        f"Responsável pelo envio: {_remetente} ({cargo})\n\n"
        f"Atenciosamente,\n{_remetente}\n"
        f"Minipa Precision — Assistência Técnica Autorizada"
    )
    filename_pdf = f"pecas_por_autorizada_{_date_file}.pdf"
    def _enviar_relatorio():
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = DESTINO
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            att = MIMEApplication(pdf_bytes, _subtype='pdf')
            att.add_header('Content-Disposition', 'attachment', filename=filename_pdf)
            msg.attach(att)
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=90) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
        except Exception:
            app.logger.exception('Erro ao enviar relatório de peças para %s', DESTINO)
    threading.Thread(target=_enviar_relatorio, daemon=True).start()
    flash(f'Relatório sendo enviado para {DESTINO}!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/enviar_email/<int:id>', methods=['POST'])
@login_required
def enviar_email(id):
    os_data = OrdemServico.query.get_or_404(id)
    if not _can_access_os(os_data):
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
    destino = (os_data.filial.email if os_data.filial and os_data.filial.email else None) or EMAIL_MINIPA
    try:
        pdf_bytes = draw_pdf_os(os_data).read()
    except Exception:
        app.logger.exception('Erro ao gerar PDF da OS %s', id)
        flash('Erro ao gerar PDF. Tente novamente.', 'error')
        return redirect(url_for('ver_os', id=id))
    os_num = f"{os_data.id:05d}"
    equip = os_data.equipamento
    serie = os_data.serie
    nome_user = current_user.nome_completo
    assunto = f"Solicitação de peças – OS nº {os_num}"
    corpo = (f"Prezados,\n\nInformamos a abertura da Ordem de Serviço nº {os_num} "
             f"referente ao equipamento modelo {equip} (S/N: {serie}).\n"
             f"Segue em anexo relatório contendo defeito apresentado e peças solicitadas.\n\n"
             f"Atenciosamente,\n{nome_user}\nMinipa Precision — Assistência Técnica Autorizada")
    # Atualiza status antes de sair da requisição
    os_data.status = 'Enviada para fabricante'
    db.session.add(LogOS(os_id=os_data.id, usuario=nome_user, tipo='status',
                         descricao='Status alterado para "Enviada para fabricante" via envio de e-mail'))
    db.session.commit()
    def _enviar_os():
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = destino
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            att = MIMEApplication(pdf_bytes, _subtype='pdf')
            att.add_header('Content-Disposition', 'attachment', filename=f"OS_{os_num}.pdf")
            msg.attach(att)
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=90) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
        except Exception:
            app.logger.exception('Erro ao enviar e-mail OS %s', os_num)
    threading.Thread(target=_enviar_os, daemon=True).start()
    flash('E-mail sendo enviado para a Minipa!', 'success')
    return redirect(url_for('ver_os', id=id))

# ── API ─────────────────────────────────────────────────────────────────────────────────────

@app.route('/api/tabela_precos')
@login_required
def api_tabela_precos():
    itens = TabelaPreco.query.all()
    return jsonify([{'id': i.id, 'tipo': i.tipo_servico, 'valor': i.valor} for i in itens])

# ── Navegação ───────────────────────────────────────────────────────────────────────────────

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
    from datetime import timedelta
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload

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

    # OS list with search/filter
    query = base_q
    if q:
        query = query.filter(
            OrdemServico.cliente.ilike(f'%{q}%') |
            OrdemServico.equipamento.ilike(f'%{q}%')
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    page = request.args.get('page', 1, type=int)
    paginacao = query.order_by(OrdemServico.id.desc()).paginate(page=page, per_page=25, error_out=False)
    ordens = paginacao
    estoque = Estoque.query.all()

    # Stats — uma query GROUP BY em vez de N queries separadas
    counts_raw = base_q.with_entities(
        OrdemServico.status, func.count(OrdemServico.id)
    ).group_by(OrdemServico.status).all()
    counts = dict(counts_raw)

    # Faturamento: carrega só a coluna valor (não todos os campos)
    valores = base_q.with_entities(OrdemServico.valor).all()
    faturamento = 0.0
    for (v,) in valores:
        if v:
            v_clean = v.replace(',', '.').replace(' ', '')
            try:
                faturamento += float(v_clean)
            except ValueError:
                pass

    stats = {
        'abertas': counts.get('Aberta', 0),
        'aguardando': counts.get('Aguardando peça', 0),
        'concluidas': counts.get('Concluída', 0),
        'total': sum(counts.values()),
        'faturamento': faturamento,
    }
    status_data = [counts.get(s, 0) for s in STATUSES]

    # Gráfico OS por mês (últimos 6 meses)
    meses = []
    os_por_mes = []
    _now = brt_now().replace(day=1)
    for i in range(5, -1, -1):
        total_month = _now.month - i
        if total_month <= 0:
            d = datetime(_now.year - 1, total_month + 12, 1)
        else:
            d = datetime(_now.year, total_month, 1)
        count = base_q.filter(
            db.extract('month', OrdemServico.data_abertura) == d.month,
            db.extract('year', OrdemServico.data_abertura) == d.year
        ).count()
        meses.append(d.strftime('%b/%y'))
        os_por_mes.append(count)

    # Top equipamentos
    top_equip = base_q.with_entities(
        OrdemServico.equipamento, func.count(OrdemServico.id).label('total')
    ).group_by(OrdemServico.equipamento).order_by(
        func.count(OrdemServico.id).desc()
    ).limit(5).all()

    usuarios = User.query.order_by(User.is_admin.desc(), User.nome_completo).all()
    return render_template('dashboard.html', ordens=ordens, estoque=estoque,
                           stats=stats, q=q, status_filter=status_filter,
                           meses=meses, os_por_mes=os_por_mes,
                           status_data=status_data,
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
            allowed = [f.id for f in current_user.autorizadas_supervisionadas]
            if filial_id and filial_id not in allowed:
                flash('Autorizada inválida.', 'error')
                return render_template('nova_os.html', tabela=tabela, filiais=filiais, now=brt_now())
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
        foto_nf_file = request.files.get('foto_nf')
        if foto_nf_file and foto_nf_file.filename:
            caminho_nf = salvar_foto(foto_nf_file)
            if caminho_nf:
                nova.foto_nf = caminho_nf
        db.session.add(nova)
        try:
            db.session.flush()
        except Exception as e:
            db.session.rollback()
            app.logger.exception('Erro ao criar OS')
            flash('Erro ao criar OS. Tente novamente.', 'error')
            return render_template('nova_os.html', tabela=tabela, filiais=filiais, now=brt_now())
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
            app.logger.exception('Erro ao salvar OS')
            flash('Erro ao salvar OS. Tente novamente.', 'error')
            return render_template('nova_os.html', tabela=tabela, filiais=filiais, now=brt_now())
    return render_template('nova_os.html', tabela=tabela, filiais=filiais, now=brt_now())

@app.route('/os/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    if not _can_access_os(os_data):
        flash('Sem permissão para editar esta OS.', 'error')
        return redirect(url_for('dashboard'))
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
        # Upload foto NF
        foto_nf_file = request.files.get('foto_nf')
        if foto_nf_file and foto_nf_file.filename:
            caminho_nf = salvar_foto(foto_nf_file)
            if caminho_nf:
                os_data.foto_nf = caminho_nf
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
    return render_template('editar_os.html', os=os_data, tabela=tabela)

@app.route('/os/<int:id>')
@login_required
def ver_os(id):
    os_data = OrdemServico.query.get_or_404(id)
    if not _can_access_os(os_data):
        flash('Sem permissão para acessar esta OS.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('ver_os.html', os=os_data)

@app.route('/os/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status(id):
    os_data = OrdemServico.query.get_or_404(id)
    if not _can_access_os(os_data):
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
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
    if not (current_user.is_admin or current_user.is_gerente):
        flash('Sem permissão para gerenciar estoque.', 'error')
        return redirect(url_for('dashboard'))
    try:
        novo = Estoque(componente=request.form.get('componente'),
                       quantidade=int(request.form.get('quantidade', 0)),
                       posicao=request.form.get('posicao'))
        db.session.add(novo)
        db.session.commit()
        flash('Item adicionado ao estoque.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Erro ao adicionar item ao estoque')
        flash('Erro ao adicionar item.', 'error')
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
    if not (current_user.is_admin or current_user.is_gerente):
        flash('Sem permissão para gerenciar estoque.', 'error')
        return redirect(url_for('dashboard'))
    item = Estoque.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Item removido do estoque.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/usuarios/editar/<int:id>', methods=['POST'])
@login_required
def editar_usuario(id):
    if not (current_user.is_admin or current_user.is_gerente):
        return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    if user.is_admin and not current_user.is_admin:
        flash('Sem permissão para editar administradores.', 'error')
        return redirect(url_for('dashboard'))
    nome = request.form.get('nome', '').strip()
    username = request.form.get('username', '').strip()
    cargo = request.form.get('cargo', 'tecnico')
    nova_senha = request.form.get('nova_senha', '').strip()
    if nome:
        user.nome_completo = nome
    if username and username != user.username:
        if User.query.filter(db.func.lower(User.username) == username.lower(), User.id != id).first():
            flash(f'Username "{username}" já está em uso.', 'error')
            return redirect(url_for('dashboard'))
        user.username = username
    if nova_senha:
        if len(nova_senha) < 6:
            flash('Senha deve ter no mínimo 6 caracteres.', 'error')
            return redirect(url_for('dashboard'))
        user.password = generate_password_hash(nova_senha)
        user.must_change_password = False
    email_val = request.form.get('email_usuario', '').strip()
    user.email = email_val or None
    if not (user.is_admin and not current_user.is_admin):
        user.is_admin = (cargo == 'admin') and current_user.is_admin
        user.is_gerente = (cargo == 'gerente')
        user.is_supervisor = (cargo == 'supervisor')
    db.session.commit()
    flash(f'Usuário {user.nome_completo} atualizado.', 'success')
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
    if not (current_user.is_admin or current_user.is_gerente):
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
                fid = int(filial_id) if filial_id else None
                user.filial_id = fid
                if user.is_supervisor and fid:
                    # Supervisor enxerga OS pela relação múltipla; só filial_id não dá acesso.
                    f = Filial.query.get(fid)
                    if f and f not in user.autorizadas_supervisionadas:
                        user.autorizadas_supervisionadas.append(f)
                    flash(f'{user.nome_completo} agora supervisiona {f.nome}.', 'success')
                elif (user.is_admin or user.is_gerente) and fid:
                    # Admin e gerente veem todas as OS: agrupar autorizadas exige perfil Supervisor.
                    user.filial_id = None
                    flash(f'{user.nome_completo} é {"administrador" if user.is_admin else "gerente"} '
                          f'e já vê todas as OS — o vínculo não foi aplicado. Para que responda por '
                          f'um grupo de autorizadas, mude o nível para Supervisor no Dashboard e '
                          f'defina as autorizadas em "Supervisores por Região".', 'error')
                elif fid:
                    flash(f'{user.nome_completo} vinculado a {Filial.query.get(fid).nome}.', 'success')
                else:
                    flash(f'{user.nome_completo} sem autorizada (vê tudo).', 'success')
        elif action == 'vincular_supervisor':
            user = User.query.get(int(request.form.get('supervisor_id')))
            filial_ids = request.form.getlist('supervisor_filiais[]')
            if user and user.is_supervisor:
                user.autorizadas_supervisionadas = [Filial.query.get(int(fid)) for fid in filial_ids if fid]
            flash('Supervisor atualizado!', 'success')
        db.session.commit()
    lista = Filial.query.all()
    from sqlalchemy.orm import joinedload as _jl
    usuarios = User.query.options(
        _jl(User.filial),
        _jl(User.autorizadas_supervisionadas)
    ).all()
    supervisores = User.query.filter_by(is_supervisor=True).options(
        _jl(User.autorizadas_supervisionadas)
    ).all()
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

def _gerar_manual_pdf():
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib import colors as rcolors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    AZUL = rcolors.HexColor('#003f6e')
    AZUL2 = rcolors.HexColor('#0077c8')

    titulo = ParagraphStyle('titulo', parent=styles['Title'],
                            textColor=AZUL, fontSize=20, spaceAfter=6)
    h1 = ParagraphStyle('h1', parent=styles['Heading1'],
                        textColor=AZUL, fontSize=13, spaceBefore=14, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'],
                        textColor=AZUL2, fontSize=11, spaceBefore=8, spaceAfter=3)
    corpo = ParagraphStyle('corpo', parent=styles['Normal'],
                           fontSize=9.5, leading=14, spaceAfter=4)
    item = ParagraphStyle('item', parent=corpo, leftIndent=16, bulletIndent=8)

    story = []

    # Capa
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Sistema de Ordens de Serviço", titulo))
    story.append(Paragraph("Minipa Precision — Assistência Técnica Autorizada", styles['Normal']))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"Manual do Usuário — Versão {brt_now().strftime('%m/%Y')}", styles['Italic']))
    story.append(HRFlowable(width='100%', thickness=1.5, color=AZUL, spaceAfter=18))

    # 1. Acesso
    story.append(Paragraph("1. Acesso ao Sistema", h1))
    story.append(Paragraph("Endereço: <b>https://sistema-minipa.onrender.com</b>", corpo))
    story.append(Paragraph("Na tela de login informe seu <b>usuário</b> e <b>senha</b>. "
                            "No primeiro acesso você será obrigado a criar uma nova senha "
                            "(mínimo 6 caracteres). Guarde-a em local seguro.", corpo))

    # 2. Perfis
    story.append(Paragraph("2. Perfis de Acesso", h1))
    data = [
        ['Perfil', 'O que pode fazer'],
        ['Administrador', 'Acesso total: usuários, autorizadas, relatórios, todas as OS'],
        ['Gerente', 'Vê todas as OS, gerencia usuários e estoque, relatórios'],
        ['Supervisor', 'Vê OS das autorizadas que supervisiona, relatório de peças'],
        ['Técnico', 'Abre e edita OS apenas da sua autorizada'],
    ]
    t = Table(data, colWidths=[4*cm, 12*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), AZUL),
        ('TEXTCOLOR', (0,0), (-1,0), rcolors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [rcolors.white, rcolors.HexColor('#f0f6ff')]),
        ('GRID', (0,0), (-1,-1), 0.3, rcolors.HexColor('#d0e3f5')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t)

    # 3. Dashboard
    story.append(Paragraph("3. Dashboard", h1))
    story.append(Paragraph("Tela principal com:", corpo))
    for txt in ["Totais de OS: abertas, aguardando peça, concluídas e faturamento",
                "Gráfico de OS dos últimos 6 meses",
                "Distribuição por status (gráfico de pizza)",
                "Top 5 equipamentos mais atendidos",
                "Fila de reparo com busca e filtro por status",
                "Gerenciamento de estoque e usuários (admin/gerente)"]:
        story.append(Paragraph(f"• {txt}", item))

    # 4. OS
    story.append(Paragraph("4. Ordens de Serviço (OS)", h1))
    story.append(Paragraph("4.1 Abrir Nova OS", h2))
    story.append(Paragraph("Clique em <b>+ Abrir Nova OS</b> no topo do Dashboard ou no menu lateral. "
                            "Preencha os dados do cliente (PF ou PJ), equipamento, defeito relatado "
                            "e peças necessárias. O campo CEP preenche o endereço automaticamente.", corpo))

    story.append(Paragraph("4.2 Acompanhar e Alterar Status", h2))
    data2 = [['Status', 'Significado'],
             ['Aberta', 'OS recém criada, aguardando análise'],
             ['Em análise', 'Técnico avaliando o equipamento'],
             ['Aguardando peça', 'Peça solicitada ao fabricante'],
             ['Peça enviada', 'Fabricante enviou a peça'],
             ['Manutenção concluída', 'Reparo finalizado'],
             ['Equipamento retirado pelo cliente', 'Cliente buscou o equipamento'],
             ['Concluída', 'OS encerrada'],
             ['Enviada para fabricante', 'Equipamento encaminhado à Minipa'],]
    t2 = Table(data2, colWidths=[5.5*cm, 10.5*cm])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), AZUL),
        ('TEXTCOLOR', (0,0), (-1,0), rcolors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [rcolors.white, rcolors.HexColor('#f0f6ff')]),
        ('GRID', (0,0), (-1,-1), 0.3, rcolors.HexColor('#d0e3f5')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t2)

    story.append(Paragraph("4.3 Gerar PDF e Enviar por E-mail", h2))
    story.append(Paragraph("Dentro de uma OS, use os botões no topo: <b>Gerar PDF</b> baixa o relatório "
                            "e <b>Enviar para Minipa</b> envia o PDF por e-mail para a Minipa e "
                            "muda o status para 'Enviada para fabricante'.", corpo))

    # 5. Peças
    story.append(Paragraph("5. Relatório de Peças por Autorizada", h1))
    story.append(Paragraph("Disponível no Dashboard (admin/gerente/supervisor). "
                            "Lista todas as peças solicitadas agrupadas por filial. "
                            "O botão <b>Enviar para Minipa</b> envia o relatório em PDF "
                            "para wfmalcato@minipa.com.br.", corpo))

    # 6. Estoque
    story.append(Paragraph("6. Inventário / Estoque", h1))
    story.append(Paragraph("Visível no Dashboard (admin/gerente). Adicione componentes com "
                            "nome, quantidade e posição de prateleira. Itens com menos de 5 "
                            "unidades são destacados em vermelho.", corpo))

    # 7. Dicas
    story.append(Paragraph("7. Dicas Importantes", h1))
    for txt in [
        "Troque sua senha no primeiro acesso — não compartilhe com terceiros.",
        "O sistema fica inativo no plano gratuito do Render; o primeiro acesso do dia pode demorar até 50 segundos.",
        "Fotos de defeitos e peças são armazenadas na nuvem (Cloudinary) e ficam disponíveis no PDF.",
        "O histórico de cada OS registra automaticamente todas as alterações de status e edições.",
        "Em caso de problema, entre em contato com o administrador do sistema.",
    ]:
        story.append(Paragraph(f"• {txt}", item))

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=AZUL))
    story.append(Paragraph(f"Minipa Precision — Sistema OS   |   Gerado em {brt_now().strftime('%d/%m/%Y')}",
                           ParagraphStyle('rodape', parent=styles['Normal'],
                                          fontSize=8, textColor=rcolors.grey, alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    return buf

def _norm_nome(s):
    """Nome comparável: sem acentos, só letras e números, minúsculo."""
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s.lower() if c.isalnum())

def _autorizada_do_usuario(user):
    """Autorizada cujo nome corresponde ao do usuário. None se não houver correspondência."""
    alvos = {_norm_nome(user.nome_completo), _norm_nome(user.username)}
    alvos = {a for a in alvos if len(a) >= 3}
    if not alvos:
        return None
    melhor, melhor_score = None, 0
    for f in Filial.query.all():
        fn = _norm_nome(f.nome)
        if not fn:
            continue
        for alvo in alvos:
            if fn == alvo:
                score = 1000 + len(alvo)
            elif fn.startswith(alvo) or alvo.startswith(fn):
                score = 500 + len(alvo)
            elif alvo in fn or fn in alvo:
                score = 100 + len(alvo)
            else:
                continue
            if score > melhor_score:
                melhor, melhor_score = f, score
    return melhor

@app.route('/usuarios/enviar_acesso/<int:id>', methods=['POST'])
@login_required
def enviar_acesso_usuario(id):
    if not current_user.is_admin:
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    # Destino vem da tela de Autorizadas, casando pelo NOME do usuário com o da autorizada.
    # Independente do vínculo de supervisão (filial_id), que é outra coisa.
    autorizada = _autorizada_do_usuario(user)
    if autorizada and autorizada.email:
        destino, origem = autorizada.email, autorizada.nome
    elif user.email:
        destino, origem = user.email, 'e-mail pessoal'
    elif user.is_gerente or user.is_admin:
        destino, origem = EMAIL_USER, 'e-mail do sistema'
    else:
        flash(f'{user.nome_completo}: nenhuma autorizada com esse nome tem e-mail cadastrado.', 'error')
        return redirect(url_for('dashboard'))
    # Senha fixa: o usuário é obrigado a trocá-la no primeiro acesso
    NOVA_SENHA = '123456'
    user.password = generate_password_hash(NOVA_SENHA, method='pbkdf2:sha256')
    user.must_change_password = True
    db.session.commit()
    corpo = (
        f"Olá, {user.nome_completo}!\n\n"
        f"Seguem suas credenciais de acesso ao Sistema de Ordens de Serviço Minipa:\n\n"
        f"  Endereço: https://sistema-minipa.onrender.com\n"
        f"  Login:    {user.username}\n"
        f"  Senha:    {NOVA_SENHA}\n\n"
        f"No primeiro acesso você será solicitado a criar uma nova senha pessoal.\n\n"
        f"Em caso de dúvidas entre em contato com o administrador.\n\n"
        f"Atenciosamente,\nMinipa Precision — Assistência Técnica Autorizada"
    )
    def _enviar_credenciais():
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = destino
            msg['Subject'] = 'Acesso ao Sistema Minipa OS — Credenciais de Acesso'
            msg.attach(MIMEText(corpo, 'plain'))
            try:
                pdf_buf = _gerar_manual_pdf()
                att = MIMEApplication(pdf_buf.read(), _subtype='pdf')
                att.add_header('Content-Disposition', 'attachment', filename='manual_sistema_minipa.pdf')
                msg.attach(att)
            except Exception:
                app.logger.exception('Erro ao gerar manual PDF para credenciais')
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=90) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
        except Exception:
            app.logger.exception('Erro ao enviar credenciais para %s', destino)
    threading.Thread(target=_enviar_credenciais, daemon=True).start()
    flash(f'Senha de {user.nome_completo} redefinida. Enviando para {destino} — {origem}.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/cadastrar_autorizadas_faltantes')
@login_required
def cadastrar_autorizadas_faltantes():
    if not current_user.is_admin:
        flash('Sem permissão.', 'error')
        return redirect(url_for('dashboard'))

    LISTA = [
        {'nome': 'IB Instalações Eletro Eletronica', 'cidade': 'Lauro de Freitas', 'estado': 'BA', 'email': 'ibinst@terra.com.br'},
        {'nome': 'M.Micros / GC Marques', 'cidade': 'Fortaleza', 'estado': 'CE', 'email': 'mmicroscentraldevendas@gmail.com'},
        {'nome': 'L.A. Tecnologia / LD Serviços', 'cidade': 'Vitória', 'estado': 'ES', 'email': 'laureano@latecnologia.com.br'},
        {'nome': 'Precisa Instrumentação e Calibração', 'cidade': 'Juiz de Fora', 'estado': 'MG', 'email': 'contato@precisacalibracao.com.br'},
        {'nome': 'Elet. Lindoaldo / Lindoaldo Rodrigues', 'cidade': 'Campina Grande', 'estado': 'PB', 'email': 'lindoaldo@yahoo.com.br'},
        {'nome': 'JED Com. / Ind. Automação', 'cidade': 'Mossoró', 'estado': 'RN', 'email': 'atendimento@indautomacao.com.br'},
        {'nome': 'Sertefor Eletrônica', 'cidade': 'Fortaleza', 'estado': 'CE', 'email': 'sertefor@hotmail.com'},
        {'nome': 'CETECQ / Marcelo Felicio', 'cidade': 'João Pessoa', 'estado': 'PB', 'email': 'cetecq.marcelo@yahoo.com'},
        {'nome': 'Nexus do Brasil', 'cidade': 'Rio Branco', 'estado': 'AC', 'email': 'nexusdptecnico@gmail.com'},
        {'nome': 'Link Tecnologia Ltda', 'cidade': 'Belém', 'estado': 'PA', 'email': 'linkltda@yahoo.com.br'},
        {'nome': 'Siatec Eletrônica', 'cidade': '', 'estado': 'SP', 'email': 'siatec.eletronica@uol.com.br'},
        {'nome': 'Walm Lab', 'cidade': '', 'estado': 'RS', 'email': 'comercial@walmlab.com.br'},
        {'nome': 'Mitec Instrumentos Industriais', 'cidade': '', 'estado': 'RS', 'email': 'mitec@mitec.com.br'},
        {'nome': 'Startech Eletronica Industrial', 'cidade': '', 'estado': 'SC', 'email': 'eletronicastartech@gmail.com'},
        {'nome': 'LEMP Instrumentos de Precisão', 'cidade': '', 'estado': 'RS', 'email': 'lemp@lemp.com.br'},
        {'nome': 'AGR Eletrônica', 'cidade': '', 'estado': 'RS', 'email': 'agr@agreletronica.com.br'},
        {'nome': 'Infoeletro', 'cidade': '', 'estado': 'RS', 'email': 'infoeletro@infoeletro.com.br'},
    ]

    criadas = []
    atualizadas = []
    ignoradas = []

    existing = Filial.query.all()
    existing_names_lower = {f.nome.lower().strip(): f for f in existing}

    for item in LISTA:
        nome_lower = item['nome'].lower().strip()
        match = existing_names_lower.get(nome_lower)
        if not match:
            words = [w for w in nome_lower.split() if len(w) > 3]
            for ex_name, ex_filial in existing_names_lower.items():
                if any(w in ex_name for w in words):
                    match = ex_filial
                    break
        if match:
            changed = False
            if not match.email and item['email']:
                match.email = item['email']
                changed = True
            if not match.cidade and item['cidade']:
                match.cidade = item['cidade']
                changed = True
            if not match.estado and item['estado']:
                match.estado = item['estado']
                changed = True
            if changed:
                atualizadas.append(f"{match.nome} — email/cidade/estado atualizados")
            else:
                ignoradas.append(f"{match.nome} — já estava completo")
        else:
            nova = Filial(
                nome=item['nome'],
                cidade=item['cidade'],
                estado=item['estado'],
                email=item['email'],
                ativa=True,
            )
            db.session.add(nova)
            criadas.append(f"{item['nome']} ({item['cidade']}/{item['estado']})")

    db.session.commit()

    html = '<style>body{font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px;}h2{color:#003f6e;}ul{margin:8px 0 20px;}li{margin:4px 0;}.ok{color:#16a34a;}.upd{color:#d97706;}.skip{color:#6b7280;}</style>'
    html += f'<h2>Cadastro de Autorizadas — Resultado</h2>'
    html += f'<p><strong class="ok">Criadas ({len(criadas)}):</strong></p><ul>'
    for x in criadas:
        html += f'<li class="ok">✔ {x}</li>'
    html += '</ul>'
    html += f'<p><strong class="upd">Atualizadas ({len(atualizadas)}):</strong></p><ul>'
    for x in atualizadas:
        html += f'<li class="upd">↻ {x}</li>'
    html += '</ul>'
    html += f'<p><strong class="skip">Ignoradas (já completas) ({len(ignoradas)}):</strong></p><ul>'
    for x in ignoradas:
        html += f'<li class="skip">— {x}</li>'
    html += '</ul>'
    html += '<br><a href="/" style="color:#0077c8;">← Voltar ao Dashboard</a>'
    return html


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ── Init DB ──────────────────────────────────────────────────────────────────────────────────

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
        'ALTER TABLE ordem_servico ADD COLUMN IF NOT EXISTS foto_nf VARCHAR(300)',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email VARCHAR(150)',
        '''CREATE TABLE IF NOT EXISTS log_os (
            id SERIAL PRIMARY KEY,
            os_id INTEGER REFERENCES ordem_servico(id) ON DELETE CASCADE,
            data TIMESTAMP DEFAULT NOW(),
            usuario VARCHAR(100),
            tipo VARCHAR(50),
            descricao TEXT
        )''',
        'CREATE INDEX IF NOT EXISTS idx_os_status ON ordem_servico(status)',
        'CREATE INDEX IF NOT EXISTS idx_os_filial ON ordem_servico(filial_id)',
        'CREATE INDEX IF NOT EXISTS idx_log_os_id ON log_os(os_id)',
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
