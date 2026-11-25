"""Testes de escopo por autorizada (tenant) e de validação de upload.

Rodar:  python3 -m pytest tests/ -v
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix='.db')
os.environ.setdefault('SECRET_KEY', 'teste')
os.environ['DATABASE_URL'] = 'sqlite:///' + _DB_PATH
# Credenciais fake: o upload é interceptado, nada sai para a rede.
os.environ.update({'CLOUDINARY_CLOUD_NAME': 'c', 'CLOUDINARY_API_KEY': 'k',
                   'CLOUDINARY_API_SECRET': 's'})

import app as appmod                                    # noqa: E402
from app import app as flask_app, db                    # noqa: E402
from database import User, Filial, OrdemServico, PecaOS, Anexo  # noqa: E402
from werkzeug.security import generate_password_hash     # noqa: E402

# ── Bytes de arquivos reais, para a validação por conteúdo ────────────────
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 64
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
WEBP = b'RIFF' + b'\x00\x00\x00\x00' + b'WEBP' + b'\x00' * 64
PDF = b'%PDF-1.4\n' + b'\x00' * 64
HTML = b'<!doctype html><script>alert(1)</script>'
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'
EXE = b'MZ\x90\x00' + b'\x00' * 64          # .exe renomeado para .jpg


def arquivo(conteudo, nome):
    return (io.BytesIO(conteudo), nome)


@pytest.fixture(scope='session', autouse=True)
def _isolar_ambiente():
    """Nenhum teste toca Cloudinary ou SMTP, e o rate limit do login sai do caminho.

    O login tem "5 per minute" por IP; como cada teste faz login, a suíte inteira
    bate no limite e passa a receber 429 em vez da resposta real.

    O stub de upload devolve os campos das duas gerações: secure_url para o
    salvar_foto ainda em uso, e public_id/resource_type/format/type para o
    salvar_anexo. cloudinary.config NÃO é stubado — a entrega precisa do SDK
    configurado de verdade, com estas credenciais falsas.
    """
    appmod.limiter.enabled = False

    contador = {'n': 0}

    def _upload(arquivo, **kw):
        contador['n'] += 1
        ext = (arquivo.filename.rsplit('.', 1)[-1].lower()
               if '.' in arquivo.filename else '')
        bruto = ext not in ('jpg', 'jpeg', 'png', 'webp', 'pdf')
        pid = f"minipa_os/{kw['public_id']}" if kw.get('public_id') \
            else f'minipa_os/{arquivo.filename}'
        return {
            'secure_url': f'https://res.cloudinary.com/c/image/upload/v1/{pid}',
            'public_id': pid,
            'resource_type': 'raw' if bruto else 'image',
            'format': None if bruto else ext,
            'type': kw.get('type', 'upload'),
        }
    appmod.cloudinary.uploader.upload = _upload

    # A rota busca o arquivo pelo urlopen; devolvemos bytes sem sair da máquina.
    class _Upstream:
        def __init__(self, dados):
            self._buf = io.BytesIO(dados)
            self.headers = {'Content-Length': str(len(dados))}
        def read(self, n=-1):
            return self._buf.read(n)
        def close(self):
            self._buf.close()

    appmod.CONTEUDO_FAKE = b'conteudo-do-anexo'
    appmod.URLS_PEDIDAS = []

    def _urlopen(url, timeout=None):
        appmod.URLS_PEDIDAS.append(url)
        if getattr(appmod, 'CLOUDINARY_FALHA', False):
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        return _Upstream(appmod.CONTEUDO_FAKE)
    appmod.urllib.request.urlopen = _urlopen

    appmod._enviar_email = lambda *a, **k: None
    appmod._enviar_email_bg = lambda *a, **k: None
    appmod._enviar_os_fabricante = lambda *a, **k: None


@pytest.fixture
def ctx():
    """Banco limpo com autorizadas e um usuário de cada papel.

    Devolve só ids: manter o app_context aberto durante o teste deixa a sessão
    pendurada sobre o mesmo arquivo SQLite e um teste contamina o seguinte.
    """
    flask_app.config.update(WTF_CSRF_ENABLED=False, TESTING=True)
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        info = Filial(nome='Info Eletro', cidade='Criciuma', estado='SC',
                      email='info@e.com', ativa=True)
        voltcom = Filial(nome='Voltcom', cidade='Joinville', estado='SC',
                         email='volt@e.com', ativa=True)
        alheia = Filial(nome='Spectrum', cidade='BH', estado='MG',
                        email='spec@e.com', ativa=True)
        db.session.add_all([info, voltcom, alheia])
        db.session.commit()

        senha = generate_password_hash('123')
        admin = User(username='admin', password=senha, nome_completo='Admin',
                     is_admin=True, must_change_password=False)
        gerente = User(username='gerente', password=senha, nome_completo='Gerente',
                       is_gerente=True, must_change_password=False)
        tecnico = User(username='tecnico', password=senha, nome_completo='Tecnico Com',
                       filial_id=info.id, must_change_password=False)
        tec_orfao = User(username='orfao', password=senha, nome_completo='Tecnico Sem',
                         must_change_password=False)
        supervisor = User(username='supervisor', password=senha, nome_completo='Supervisor Com',
                          is_supervisor=True, filial_id=voltcom.id, must_change_password=False)
        supervisor.autorizadas_supervisionadas = [voltcom, info]
        sup_orfao = User(username='suporfao', password=senha, nome_completo='Supervisor Sem',
                         is_supervisor=True, must_change_password=False)
        db.session.add_all([admin, gerente, tecnico, tec_orfao, supervisor, sup_orfao])
        db.session.commit()

        dados = {
            'filiais': {'info': info.id, 'voltcom': voltcom.id, 'alheia': alheia.id},
            'users': {u.username: u.id for u in User.query.all()},
        }
        db.session.remove()
    return dados


def entrar(usuario):
    c = flask_app.test_client()
    c.post('/', data={'username': usuario, 'password': '123'}, follow_redirects=True)
    return c


def criar_os(cliente, filial_id=None, **extras):
    dados = {'cliente': 'Cliente Teste', 'equipamento': 'ET-1507B', 'serie': 'S1',
             'status': 'Aberta', 'tipo_pessoa': 'PF'}
    if filial_id is not None:
        dados['filial_id'] = str(filial_id)
    dados.update(extras)
    return cliente.post('/nova_os', data=dados, follow_redirects=True,
                        content_type='multipart/form-data')


def total_os():
    with flask_app.app_context():
        return OrdemServico.query.count()


# ══════════════ ETAPA 4 — escopo por autorizada ══════════════

def test_tecnico_com_autorizada_cria_os(ctx):
    r = criar_os(entrar('tecnico'))
    assert r.status_code == 200
    with flask_app.app_context():
        o = OrdemServico.query.one()
        assert o.filial_id == ctx['filiais']['info']
        assert o.tecnico == 'Tecnico Com'


def test_tecnico_sem_autorizada_bloqueado_com_mensagem(ctx):
    r = criar_os(entrar('orfao'))
    assert 'Sua autorizada ainda não está vinculada' in r.get_data(as_text=True)
    assert 'Fale com o administrador do Minipa OS' in r.get_data(as_text=True)
    assert total_os() == 0


def test_tecnico_nao_burla_enviando_filial_alheia(ctx):
    """O filial_id do POST é ignorado para técnico: vale o vínculo dele."""
    r = criar_os(entrar('tecnico'), filial_id=ctx['filiais']['alheia'])
    assert r.status_code == 200
    with flask_app.app_context():
        assert OrdemServico.query.one().filial_id == ctx['filiais']['info']


def test_supervisor_com_filial_vazia_bloqueado(ctx):
    r = criar_os(entrar('supervisor'), filial_id='')
    assert 'Sua autorizada ainda não está vinculada' in r.get_data(as_text=True)
    assert total_os() == 0


def test_supervisor_sem_filial_no_post_bloqueado(ctx):
    """Campo ausente de todo — era o furo do `if filial_id and ...`."""
    r = criar_os(entrar('supervisor'))
    assert 'Sua autorizada ainda não está vinculada' in r.get_data(as_text=True)
    assert total_os() == 0


def test_supervisor_com_autorizada_que_nao_supervisiona_bloqueado(ctx):
    r = criar_os(entrar('supervisor'), filial_id=ctx['filiais']['alheia'])
    assert 'você não atende essa autorizada' in r.get_data(as_text=True)
    assert total_os() == 0


def test_supervisor_cria_na_autorizada_que_supervisiona(ctx):
    r = criar_os(entrar('supervisor'), filial_id=ctx['filiais']['info'])
    assert r.status_code == 200
    with flask_app.app_context():
        assert OrdemServico.query.one().filial_id == ctx['filiais']['info']


def test_supervisor_sem_vinculo_bloqueado(ctx):
    r = criar_os(entrar('suporfao'), filial_id=ctx['filiais']['info'])
    assert 'você não atende essa autorizada' in r.get_data(as_text=True)
    assert total_os() == 0


@pytest.mark.parametrize('papel', ['admin', 'gerente'])
def test_admin_e_gerente_criam_para_qualquer_autorizada(ctx, papel):
    r = criar_os(entrar(papel), filial_id=ctx['filiais']['alheia'])
    assert r.status_code == 200
    with flask_app.app_context():
        assert OrdemServico.query.one().filial_id == ctx['filiais']['alheia']


# ══════════════ ETAPA 3 — aviso no painel de admin ══════════════

def _bloco_sem_autorizada(html):
    """Isola o bloco de aviso do painel, para não casar com o resto da página."""
    marca = 'id="sem-autorizada"'
    if marca not in html:
        return None
    return html.split(marca, 1)[1].split('<!-- Modal', 1)[0]


def test_painel_lista_apenas_usuarios_sem_vinculo(ctx):
    bloco = _bloco_sem_autorizada(entrar('admin').get('/dashboard').get_data(as_text=True))
    assert bloco is not None, 'o bloco deveria aparecer para admin'
    assert 'Tecnico Sem' in bloco and 'Supervisor Sem' in bloco
    for vinculado in ('Tecnico Com', 'Supervisor Com'):
        assert vinculado not in bloco, f'{vinculado} tem vínculo e não devia ser listado'


def test_painel_confirma_quando_todos_vinculados(ctx):
    with flask_app.app_context():
        info = db.session.get(Filial, ctx['filiais']['info'])
        orfao = User.query.filter_by(username='orfao').first()
        orfao.filial_id = info.id
        sup = User.query.filter_by(username='suporfao').first()
        sup.autorizadas_supervisionadas = [info]
        db.session.commit()
        db.session.remove()
    bloco = _bloco_sem_autorizada(entrar('admin').get('/dashboard').get_data(as_text=True))
    assert 'Todos os usuários estão vinculados' in bloco
    assert 'Editar cadastro' not in bloco


@pytest.mark.parametrize('papel', ['gerente', 'tecnico', 'supervisor'])
def test_painel_nao_aparece_para_outros_papeis(ctx, papel):
    html = entrar(papel).get('/dashboard').get_data(as_text=True)
    assert 'id="sem-autorizada"' not in html
    assert 'Todos os usuários estão vinculados' not in html


# ══════════════ ETAPA 2 — validação de upload ══════════════

@pytest.mark.parametrize('conteudo,nome', [
    (JPG, 'nota.jpg'), (PNG, 'nota.png'), (WEBP, 'nota.webp'), (PDF, 'nota.pdf')])
def test_nota_fiscal_aceita_tipos_validos(ctx, conteudo, nome):
    r = criar_os(entrar('tecnico'), foto_nf=arquivo(conteudo, nome))
    assert r.status_code == 200
    with flask_app.app_context():
        assert OrdemServico.query.one().foto_nf is not None


@pytest.mark.parametrize('conteudo,nome,rotulo', [
    (HTML, 'pagina.html', 'html'),
    (HTML, 'disfarcado.jpg', 'html com extensão de imagem'),
    (SVG, 'vetor.svg', 'svg'),
    (EXE, 'virus.jpg', 'executável renomeado para .jpg')])
def test_nota_fiscal_recusa_tipo_proibido(ctx, conteudo, nome, rotulo):
    r = criar_os(entrar('tecnico'), foto_nf=arquivo(conteudo, nome))
    texto = r.get_data(as_text=True)
    assert 'não é um arquivo' in texto, f'deveria recusar {rotulo}'
    assert total_os() == 0, f'{rotulo} não pode deixar OS salva pela metade'


def test_pdf_recusado_nas_fotos_de_defeito(ctx):
    """PDF só vale na nota fiscal."""
    r = criar_os(entrar('tecnico'), **{'fotos_defeito[]': arquivo(PDF, 'doc.pdf')})
    assert 'JPG, PNG ou WEBP' in r.get_data(as_text=True)
    assert total_os() == 0


def test_arquivo_grande_demais_recusado(ctx):
    grande = JPG + b'\x00' * (10 * 1024 * 1024 + 1)
    r = criar_os(entrar('tecnico'), foto_nf=arquivo(grande, 'enorme.jpg'))
    texto = r.get_data(as_text=True)
    assert 'limite é 10 MB' in texto
    assert total_os() == 0


def test_arquivo_no_limite_passa(ctx):
    no_limite = JPG + b'\x00' * (10 * 1024 * 1024 - len(JPG))
    r = criar_os(entrar('tecnico'), foto_nf=arquivo(no_limite, 'limite.jpg'))
    assert r.status_code == 200
    assert total_os() == 1


def test_edicao_tambem_valida_anexo(ctx):
    cliente = entrar('tecnico')
    criar_os(cliente)
    with flask_app.app_context():
        oid = OrdemServico.query.one().id
        antes = OrdemServico.query.one().cliente
    r = cliente.post(f'/os/{oid}/editar',
                     data={'cliente': 'Nome Alterado', 'equipamento': 'ET', 'serie': 'S1',
                           'status': 'Aberta', 'tipo_pessoa': 'PF',
                           'foto_nf': arquivo(EXE, 'virus.jpg')},
                     content_type='multipart/form-data', follow_redirects=True)
    assert 'não é um arquivo' in r.get_data(as_text=True)
    with flask_app.app_context():
        assert OrdemServico.query.one().cliente == antes, 'edição não podia ter sido gravada'


# ══════════════ ETAPA 5 — foto da peça ══════════════

def test_peca_com_foto_e_gravada(ctx):
    r = criar_os(entrar('tecnico'), **{
        'peca_codigo[]': 'DSP-01', 'peca_descricao[]': 'Display LCD',
        'peca_quantidade[]': '2', 'peca_obs[]': 'urgente',
        'peca_foto[]': arquivo(JPG, 'display.jpg')})
    assert r.status_code == 200
    with flask_app.app_context():
        p = PecaOS.query.one()
        assert p.descricao == 'Display LCD' and p.quantidade == 2
        assert p.foto and p.foto.startswith('https://res.cloudinary.com/')


def test_peca_sem_foto_e_gravada(ctx):
    r = criar_os(entrar('tecnico'), **{
        'peca_codigo[]': 'CAP-22', 'peca_descricao[]': 'Capacitor',
        'peca_quantidade[]': '5', 'peca_obs[]': ''})
    assert r.status_code == 200
    with flask_app.app_context():
        p = PecaOS.query.one()
        assert p.descricao == 'Capacitor' and p.foto is None


def test_foto_de_peca_invalida_recusa_a_os(ctx):
    r = criar_os(entrar('tecnico'), **{
        'peca_codigo[]': 'X', 'peca_descricao[]': 'Peca',
        'peca_quantidade[]': '1', 'peca_obs[]': '',
        'peca_foto[]': arquivo(EXE, 'fake.jpg')})
    assert 'não é um arquivo' in r.get_data(as_text=True)
    assert total_os() == 0


def test_foto_da_peca_aparece_na_os(ctx):
    cliente = entrar('tecnico')
    criar_os(cliente, **{'peca_codigo[]': 'DSP-01', 'peca_descricao[]': 'Display',
                         'peca_quantidade[]': '1', 'peca_obs[]': '',
                         'peca_foto[]': arquivo(PNG, 'display.png')})
    with flask_app.app_context():
        oid = OrdemServico.query.one().id
        url = PecaOS.query.one().foto
    html = cliente.get(f'/os/{oid}').get_data(as_text=True)
    assert url in html


# ══════════════ Regressão: escopo de leitura ══════════════

def test_tecnico_nao_ve_os_de_outra_autorizada(ctx):
    criar_os(entrar('admin'), filial_id=ctx['filiais']['alheia'])
    with flask_app.app_context():
        oid = OrdemServico.query.one().id
    cliente = entrar('tecnico')
    for rota in (f'/os/{oid}', f'/os/{oid}/editar', f'/relatorio/os/{oid}'):
        r = cliente.get(rota, follow_redirects=True)
        assert 'Sem permissão' in r.get_data(as_text=True), rota


def test_tecnico_sem_autorizada_nao_ve_nenhuma_os(ctx):
    criar_os(entrar('admin'), filial_id=ctx['filiais']['info'])
    html = entrar('orfao').get('/dashboard').get_data(as_text=True)
    assert 'Nenhuma OS encontrada' in html


# ══════════════ Rota de anexo ══════════════

def _anexo_na_os(os_id, **campos):
    """Cria direto um Anexo na OS — o upload ainda não grava em Anexo."""
    padrao = dict(categoria='nota_fiscal', public_id='minipa_os/abc123',
                  resource_type='image', formato='pdf',
                  tipo_entrega='authenticated', nome_original='nota.pdf')
    padrao.update(campos)
    with flask_app.app_context():
        a = Anexo(os_id=os_id, **padrao)
        db.session.add(a)
        db.session.commit()
        return a.id


def _os_do(login='tecnico', filial=None):
    criar_os(entrar(login), filial_id=filial)
    with flask_app.app_context():
        return OrdemServico.query.order_by(OrdemServico.id.desc()).first().id


def test_dono_abre_o_anexo(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id)
    r = entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    assert r.status_code == 200
    assert r.get_data() == appmod.CONTEUDO_FAKE


def test_outra_autorizada_recebe_404(ctx):
    os_id = _os_do('admin', ctx['filiais']['alheia'])
    anexo_id = _anexo_na_os(os_id)
    r = entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    assert r.status_code == 404
    assert appmod.CONTEUDO_FAKE not in r.get_data()


def test_deslogado_vai_para_o_login(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id)
    r = flask_app.test_client().get(f'/os/{os_id}/anexo/{anexo_id}')
    assert r.status_code == 302
    assert '/?next=' in r.headers['Location']


def test_anexo_de_outra_os_da_404_mesmo_tendo_acesso_as_duas(ctx):
    """Trocar o id do anexo na URL não pode entregar o arquivo da outra OS."""
    cliente = entrar('tecnico')
    criar_os(cliente)
    criar_os(cliente)
    with flask_app.app_context():
        a, b = OrdemServico.query.order_by(OrdemServico.id).all()
        os_de_a, os_de_b = a.id, b.id
    anexo_de_b = _anexo_na_os(os_de_b, public_id='minipa_os/outro')
    r = cliente.get(f'/os/{os_de_a}/anexo/{anexo_de_b}')
    assert r.status_code == 404


def test_headers_de_seguranca_e_content_type_fixo(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id, formato='pdf', nome_original='nota.pdf')
    r = entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    assert r.headers['Content-Type'].startswith('application/pdf')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'private' in r.headers['Cache-Control']
    assert r.headers['Content-Disposition'].startswith('inline')
    assert 'nota.pdf' in r.headers['Content-Disposition']


def test_formato_fora_da_lista_nao_e_servido(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id, formato='svg')
    assert entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}').status_code == 404


def test_falha_do_cloudinary_nao_expoe_url(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id)
    appmod.CLOUDINARY_FALHA = True
    try:
        r = entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    finally:
        appmod.CLOUDINARY_FALHA = False
    assert r.status_code == 502
    corpo = r.get_data(as_text=True)
    assert 'Não foi possível abrir o anexo' in corpo
    assert 'cloudinary' not in corpo.lower()


def test_anexo_authenticated_usa_url_assinada(ctx):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id, tipo_entrega='authenticated')
    entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    pedida = appmod.URLS_PEDIDAS[-1]
    assert '/authenticated/' in pedida
    assert 's--' in pedida, 'authenticated precisa ir assinada'


def test_anexo_legado_abre_sem_assinatura(ctx):
    """tipo_entrega='upload' passa pela mesma rota, com o mesmo escopo."""
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id, tipo_entrega='upload',
                            public_id='minipa_os/legado')
    assert entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}').status_code == 200
    pedida = appmod.URLS_PEDIDAS[-1]
    assert '/upload/' in pedida and 's--' not in pedida


def test_anexo_legado_bloqueia_outra_autorizada(ctx):
    os_id = _os_do('admin', ctx['filiais']['alheia'])
    anexo_id = _anexo_na_os(os_id, tipo_entrega='upload')
    assert entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}').status_code == 404


def test_sem_credenciais_do_cloudinary_a_rota_devolve_502(ctx, monkeypatch):
    os_id = _os_do()
    anexo_id = _anexo_na_os(os_id)
    monkeypatch.delenv('CLOUDINARY_CLOUD_NAME', raising=False)
    r = entrar('tecnico').get(f'/os/{os_id}/anexo/{anexo_id}')
    assert r.status_code == 502


# ══════════════ Backfill ══════════════

URL_LEGADA = ('https://res.cloudinary.com/dvhr9h3zb/image/upload/v1788375295/'
              'minipa_os/nota-fiscal-827446_a1b2c3.pdf')


def test_backfill_interpreta_url_legada():
    from backfill_anexos import interpretar
    d = interpretar(URL_LEGADA)
    assert d['public_id'] == 'minipa_os/nota-fiscal-827446_a1b2c3'
    assert d['resource_type'] == 'image'
    assert d['tipo_entrega'] == 'upload'
    assert d['formato'] == 'pdf'
    assert d['nome_original'] == 'nota-fiscal-827446_a1b2c3.pdf'


def test_backfill_interpreta_raw_e_assinada():
    from backfill_anexos import interpretar
    raw = interpretar('https://res.cloudinary.com/c/raw/upload/v1/minipa_os/abc.pdf')
    assert raw['resource_type'] == 'raw' and raw['formato'] == 'pdf'
    assinada = interpretar(
        'https://res.cloudinary.com/c/image/authenticated/s--Xy9--/v1/minipa_os/zz.jpg')
    assert assinada['tipo_entrega'] == 'authenticated'
    assert assinada['public_id'] == 'minipa_os/zz'


@pytest.mark.parametrize('ruim', [
    None, '', 'não é url', 'https://exemplo.com/foto.jpg', 'ftp://res.cloudinary.com/x'])
def test_backfill_rejeita_url_invalida(ruim):
    from backfill_anexos import interpretar
    assert interpretar(ruim) is None


def test_backfill_cria_registros_e_e_idempotente(ctx):
    from backfill_anexos import interpretar, coletar
    with flask_app.app_context():
        osd = OrdemServico(cliente='C', equipamento='ET', serie='S1', status='Aberta',
                           filial_id=ctx['filiais']['info'],
                           foto_nf=URL_LEGADA,
                           fotos_defeito=json.dumps([
                               'https://res.cloudinary.com/c/image/upload/v1/minipa_os/d1.jpg',
                               'url-quebrada']))
        db.session.add(osd)
        db.session.commit()
        db.session.add(PecaOS(os_id=osd.id, descricao='Display', quantidade=1,
                              foto='https://res.cloudinary.com/c/image/upload/v1/minipa_os/p1.png'))
        db.session.commit()
        os_id = osd.id

        def rodar():
            criados, invalidas = 0, []
            od = db.session.get(OrdemServico, os_id)
            for categoria, url, peca_id in coletar(od):
                dados = interpretar(url)
                if not dados:
                    invalidas.append(url)
                    continue
                if Anexo.query.filter_by(os_id=os_id,
                                         public_id=dados['public_id']).first():
                    continue
                db.session.add(Anexo(os_id=os_id, peca_id=peca_id, categoria=categoria,
                                     enviado_por='backfill', **dados))
                criados += 1
            db.session.commit()
            return criados, invalidas

        criados, invalidas = rodar()
        assert criados == 3, 'nota fiscal + 1 defeito válido + 1 peça'
        assert invalidas == ['url-quebrada'], 'a URL ruim não pode interromper o resto'
        assert all(a.tipo_entrega == 'upload' for a in Anexo.query.all())

        criados2, _ = rodar()
        assert criados2 == 0, 'rodar de novo não pode duplicar'
        assert Anexo.query.filter_by(os_id=os_id).count() == 3

        # colunas antigas preservadas
        od = db.session.get(OrdemServico, os_id)
        assert od.foto_nf == URL_LEGADA
        assert od.fotos_defeito is not None
        assert PecaOS.query.filter_by(os_id=os_id).one().foto is not None
