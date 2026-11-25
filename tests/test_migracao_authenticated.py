"""Testes do script que converte anexos de 'upload' para 'authenticated'.

Todo o Cloudinary é simulado: nada sai da máquina e nenhum arquivo real é tocado.
"""
import csv
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reaproveita a configuração de ambiente da outra suíte (banco temporário, etc.)
from test_tenant_e_uploads import ctx, _isolar_ambiente, flask_app, appmod  # noqa: F401,E402

import migrar_anexos_authenticated as mig                      # noqa: E402
from database import db, OrdemServico, Anexo                   # noqa: E402


@pytest.fixture
def anexos(ctx):
    """Três anexos legados e um já convertido."""
    with flask_app.app_context():
        osd = OrdemServico(cliente='C', equipamento='ET', serie='S1', status='Aberta',
                           filial_id=ctx['filiais']['info'])
        db.session.add(osd)
        db.session.commit()
        db.session.add_all([
            Anexo(os_id=osd.id, categoria='nota_fiscal', public_id='minipa_os/a1',
                  resource_type='image', formato='pdf', tipo_entrega='upload'),
            Anexo(os_id=osd.id, categoria='defeito', public_id='minipa_os/a2',
                  resource_type='image', formato='jpg', tipo_entrega='upload'),
            Anexo(os_id=osd.id, categoria='defeito', public_id='minipa_os/a3',
                  resource_type='raw', formato='pdf', tipo_entrega='upload'),
            Anexo(os_id=osd.id, categoria='defeito', public_id='minipa_os/ja',
                  resource_type='image', formato='png', tipo_entrega='authenticated'),
        ])
        db.session.commit()
        db.session.remove()
    return True


@pytest.fixture
def cloudinary_falso(monkeypatch, tmp_path):
    """Captura os renames e simula o fechamento da URL antiga."""
    estado = {'renames': [], 'falhar': set(), 'ainda_responde': set()}

    def _rename(de, para, **kw):
        if de in estado['falhar']:
            raise RuntimeError('Cloudinary recusou o rename')
        estado['renames'].append({'de': de, 'para': para,
                                  'resource_type': kw.get('resource_type'),
                                  'type': kw.get('type'), 'to_type': kw.get('to_type'),
                                  'invalidate': kw.get('invalidate')})
        return {'public_id': para}

    monkeypatch.setattr(mig.cloudinary.uploader, 'rename', _rename)
    # Por padrão a URL antiga passa a responder 404 após a conversão
    monkeypatch.setattr(mig, 'ainda_responde',
                        lambda url, timeout=15: url in estado['ainda_responde'])
    estado['csv'] = str(tmp_path / 'backup.csv')
    return estado


def rodar(estado, *extra):
    sys.argv = ['migrar', '--csv', estado['csv'], *extra]
    return mig.main()


def ler_csv(caminho):
    with open(caminho, encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


# ══════════════ dry-run ══════════════

def test_dry_run_nao_altera_nada(anexos, cloudinary_falso, capsys):
    rodar(cloudinary_falso)
    assert cloudinary_falso['renames'] == [], 'dry-run não pode chamar o Cloudinary'
    with flask_app.app_context():
        assert Anexo.query.filter_by(tipo_entrega='upload').count() == 3
    saida = capsys.readouterr().out
    assert 'DRY-RUN' in saida and 'Nada foi alterado' in saida


def test_dry_run_ja_gera_csv_de_backup(anexos, cloudinary_falso):
    rodar(cloudinary_falso)
    linhas = ler_csv(cloudinary_falso['csv'])
    assert len(linhas) == 3
    assert {l['public_id'] for l in linhas} == {'minipa_os/a1', 'minipa_os/a2', 'minipa_os/a3'}
    for l in linhas:
        assert l['url_antiga'].startswith('https://res.cloudinary.com/')
        assert '/upload/' in l['url_antiga']
        assert l['anexo_id'] and l['os_id']


# ══════════════ conversão ══════════════

def test_apply_converte_respeitando_resource_type(anexos, cloudinary_falso):
    rodar(cloudinary_falso, '--apply')
    renames = {r['de']: r for r in cloudinary_falso['renames']}
    assert set(renames) == {'minipa_os/a1', 'minipa_os/a2', 'minipa_os/a3'}
    assert renames['minipa_os/a3']['resource_type'] == 'raw', 'raw não pode virar image'
    assert renames['minipa_os/a1']['resource_type'] == 'image'
    for r in renames.values():
        assert r['type'] == 'upload' and r['to_type'] == 'authenticated'
        assert r['de'] == r['para'], 'o public_id não deve mudar'
        assert r['invalidate'] is True
    with flask_app.app_context():
        assert Anexo.query.filter_by(tipo_entrega='upload').count() == 0
        assert Anexo.query.filter_by(tipo_entrega='authenticated').count() == 4


def test_pula_o_que_ja_e_authenticated(anexos, cloudinary_falso):
    rodar(cloudinary_falso, '--apply')
    assert 'minipa_os/ja' not in [r['de'] for r in cloudinary_falso['renames']]


def test_idempotente(anexos, cloudinary_falso):
    rodar(cloudinary_falso, '--apply')
    primeira = len(cloudinary_falso['renames'])
    cloudinary_falso['renames'].clear()
    rodar(cloudinary_falso, '--apply')
    assert primeira == 3
    assert cloudinary_falso['renames'] == [], 'a segunda passada não pode converter de novo'


def test_limit_restringe_a_quantidade(anexos, cloudinary_falso):
    rodar(cloudinary_falso, '--apply', '--limit', '1')
    assert len(cloudinary_falso['renames']) == 1
    with flask_app.app_context():
        assert Anexo.query.filter_by(tipo_entrega='upload').count() == 2


# ══════════════ falhas ══════════════

def test_falha_nao_interrompe_e_e_listada(anexos, cloudinary_falso, capsys):
    cloudinary_falso['falhar'].add('minipa_os/a2')
    codigo = rodar(cloudinary_falso, '--apply')
    assert len(cloudinary_falso['renames']) == 2, 'os outros dois seguem'
    saida = capsys.readouterr().out
    assert 'Falhas' in saida and 'minipa_os/a2' in saida
    assert codigo == 1, 'com falha o script sai com código 1'
    with flask_app.app_context():
        falho = Anexo.query.filter_by(public_id='minipa_os/a2').one()
        assert falho.tipo_entrega == 'upload', 'o banco não pode mudar se o Cloudinary falhou'


def test_url_antiga_que_continua_respondendo_e_reportada(anexos, cloudinary_falso, capsys):
    with flask_app.app_context():
        anexo = Anexo.query.filter_by(public_id='minipa_os/a1').one()
        cloudinary_falso['ainda_responde'].add(mig.url_publica(anexo))
    rodar(cloudinary_falso, '--apply')
    saida = capsys.readouterr().out
    assert 'sem confirmação' in saida
    assert 'ainda responde' in saida.lower()


def test_verificacao_inconclusiva_e_reportada(anexos, cloudinary_falso, monkeypatch, capsys):
    monkeypatch.setattr(mig, 'ainda_responde', lambda url, timeout=15: None)
    rodar(cloudinary_falso, '--apply')
    assert 'inconclusiva' in capsys.readouterr().out


# ══════════════ ainda_responde ══════════════

def test_ainda_responde_classifica_os_status(monkeypatch):
    class Resp:
        def __init__(s, status): s.status = status
        def __enter__(s): return s
        def __exit__(s, *a): return False

    monkeypatch.setattr(mig.urllib.request, 'urlopen', lambda *a, **k: Resp(200))
    assert mig.ainda_responde('http://x') is True

    for codigo in (401, 403, 404):
        def _erro(*a, _c=codigo, **k):
            raise urllib.error.HTTPError('http://x', _c, 'erro', {}, None)
        monkeypatch.setattr(mig.urllib.request, 'urlopen', _erro)
        assert mig.ainda_responde('http://x') is False, codigo

    def _rede(*a, **k):
        raise OSError('sem rede')
    monkeypatch.setattr(mig.urllib.request, 'urlopen', _rede)
    assert mig.ainda_responde('http://x') is None, 'erro de rede é inconclusivo, não sucesso'
