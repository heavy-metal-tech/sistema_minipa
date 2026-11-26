"""Backfill: cria uma linha em Anexo para cada anexo das colunas antigas.

Só mexe no banco — não toca no Cloudinary. Os arquivos continuam como estão
(type='upload'); quem os converte para 'authenticated' é o outro script.

    python3 backfill_anexos.py              # dry-run: só lista o que faria
    python3 backfill_anexos.py --apply      # grava

Idempotente: o índice único (os_id, public_id) impede duplicata, e o script
confere antes de inserir. Rodar de novo só pega o que entrou no intervalo.
"""
import argparse
import io
import json
import re
import sys
import urllib.parse
import urllib.request

import cloudinary
import cloudinary.api
from cloudinary.utils import cloudinary_url

from app import app, _configurar_cloudinary, _detectar_tipo
from database import db, OrdemServico, Anexo


def banco_alvo(uri):
    """URI do banco com a senha mascarada, para imprimir sem vazar credencial."""
    try:
        partes = urllib.parse.urlsplit(uri)
        if partes.password:
            netloc = partes.netloc.replace(f':{partes.password}@', ':***@')
            partes = partes._replace(netloc=netloc)
        return urllib.parse.urlunsplit(partes)
    except Exception:
        return '(não foi possível interpretar a URL do banco)'


def conferir_banco(permitir_sqlite):
    """Mostra contra qual banco vamos rodar e barra o SQLite local.

    Sem DATABASE_URL o app cai no SQLite de desenvolvimento, e o script roda
    até o fim relatando "0 anexos" — saída que parece legítima e não mexeu em
    produção nenhuma. Melhor abortar com a razão na tela.
    """
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    print(f'Banco alvo: {banco_alvo(uri)}')
    if uri.startswith('sqlite'):
        if not permitir_sqlite:
            print('\nABORTADO: isto é um SQLite local, não o banco de produção.')
            print('A variável DATABASE_URL não está definida neste ambiente.')
            print('Rodar aqui não altera a produção e devolveria uma saída enganosa.')
            print('\nDefina DATABASE_URL, ou passe --permitir-sqlite se a intenção')
            print('for mesmo mexer no banco local.')
            return False
        print('  (SQLite local, liberado por --permitir-sqlite)')
    print()
    return True

# https://res.cloudinary.com/<cloud>/<resource_type>/<type>/v123/<public_id>.<fmt>
_URL = re.compile(
    r'^https?://res\.cloudinary\.com/[^/]+/'
    r'(?P<resource_type>image|raw|video)/'
    r'(?P<tipo_entrega>upload|authenticated|private)/'
    r'(?:s--[^/]+--/)?'          # assinatura, quando houver
    r'(?:v\d+/)?'                # versão, quando houver
    r'(?P<public_id>.+?)'
    r'(?:\.(?P<formato>[A-Za-z0-9]{2,5}))?$'
)


def interpretar(url):
    """Extrai os campos da URL. Devolve dict ou None se não reconhecer."""
    if not url or not isinstance(url, str):
        return None
    m = _URL.match(url.strip())
    if not m:
        return None
    d = m.groupdict()
    if not d['public_id']:
        return None
    return {
        'public_id': d['public_id'],
        'resource_type': d['resource_type'],
        'tipo_entrega': d['tipo_entrega'],
        'formato': (d['formato'] or '').lower(),
        # O nome original não existe nas URLs legadas; o trecho final do
        # public_id é o mais próximo disso, e serve de nome de download.
        'nome_original': d['public_id'].rsplit('/', 1)[-1] +
                         (f".{d['formato'].lower()}" if d['formato'] else ''),
    }


def _formato_pela_api(public_id, resource_type, tipo_entrega):
    """Pergunta o formato à Admin API do Cloudinary. '' se ela não souber."""
    try:
        info = cloudinary.api.resource(public_id,
                                       resource_type=resource_type or 'image',
                                       type=tipo_entrega or 'upload')
    except Exception:
        return ''
    return (info.get('format') or '').lower()


def _formato_pelo_conteudo(public_id, resource_type, tipo_entrega):
    """Baixa os primeiros bytes e identifica pela assinatura. '' se não souber.

    É o recurso final: para arquivos 'raw' a Admin API costuma não devolver
    format, e o conteúdo é a única fonte que não depende de convenção de nome.
    """
    try:
        url, _ = cloudinary_url(public_id,
                                resource_type=resource_type or 'image',
                                type=tipo_entrega or 'upload',
                                sign_url=(tipo_entrega == 'authenticated'),
                                secure=True)
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-15'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            cabecalho = resp.read(16)
    except Exception:
        return ''
    return _detectar_tipo(io.BytesIO(cabecalho)) or ''


def descobrir_formato(dados):
    """Preenche o formato quando a URL legada não trazia extensão.

    Alguns anexos antigos subiram como 'raw' com public_id aleatório, então o
    formato não está na URL. Assumir PDF seria chute: gravar 'pdf' num JPEG faz
    o navegador recusar o arquivo. Pergunta-se ao Cloudinary, e se ele não
    souber, lê-se a assinatura do próprio arquivo.

    Devolve (formato, origem) — origem serve para mostrar na tela de onde veio.
    """
    if dados.get('formato'):
        return dados['formato'], 'url'
    if not _configurar_cloudinary():
        return '', 'sem credenciais'
    fmt = _formato_pela_api(dados['public_id'], dados['resource_type'],
                            dados['tipo_entrega'])
    if fmt:
        return fmt, 'api'
    fmt = _formato_pelo_conteudo(dados['public_id'], dados['resource_type'],
                                 dados['tipo_entrega'])
    if fmt:
        return fmt, 'conteúdo'
    return '', 'não identificado'


def coletar(os_data):
    """Todos os anexos legados de uma OS: (categoria, url, peca_id)."""
    itens = []
    if os_data.foto_nf:
        itens.append(('nota_fiscal', os_data.foto_nf, None))
    if os_data.fotos_defeito:
        try:
            for url in json.loads(os_data.fotos_defeito) or []:
                itens.append(('defeito', url, None))
        except (ValueError, TypeError):
            itens.append(('defeito', os_data.fotos_defeito, None))
    for peca in os_data.pecas:
        if peca.foto:
            itens.append(('peca', peca.foto, peca.id))
    return itens


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='grava de verdade (sem isso é dry-run)')
    ap.add_argument('--permitir-sqlite', action='store_true',
                    help='deixa rodar contra o SQLite local (por padrão aborta)')
    args = ap.parse_args()
    dry = not args.apply

    criados = pulados = 0
    nao_interpretadas = []

    with app.app_context():
        if not conferir_banco(args.permitir_sqlite):
            return 2
        db.create_all()          # cria a tabela anexo se ainda não existir
        ordens = OrdemServico.query.order_by(OrdemServico.id).all()
        print(f'{"DRY-RUN — nada será gravado" if dry else "APLICANDO"} | '
              f'{len(ordens)} OS para examinar\n')

        for os_data in ordens:
            for categoria, url, peca_id in coletar(os_data):
                dados = interpretar(url)
                if not dados:
                    nao_interpretadas.append((os_data.id, categoria, url))
                    print(f'  ?  OS {os_data.id:>5} {categoria:<12} URL não reconhecida')
                    continue
                ja_existe = Anexo.query.filter_by(
                    os_id=os_data.id, public_id=dados['public_id']).first()
                if ja_existe:
                    pulados += 1
                    print(f'  =  OS {os_data.id:>5} {categoria:<12} já migrado')
                    continue
                # URL sem extensão: descobre o formato real em vez de deixar vazio
                dados['formato'], origem = descobrir_formato(dados)
                marca = '' if origem == 'url' else f' [formato via {origem}]'
                print(f'  +  OS {os_data.id:>5} {categoria:<12} {dados["public_id"]}'
                      f' ({dados["resource_type"]}/{dados["tipo_entrega"]},'
                      f' {dados["formato"] or "SEM FORMATO"}){marca}')
                criados += 1
                if not dry:
                    db.session.add(Anexo(os_id=os_data.id, peca_id=peca_id,
                                         categoria=categoria,
                                         enviado_por='backfill', **dados))

        if not dry and criados:
            db.session.commit()

    print(f'\n{"seriam criados" if dry else "criados"}: {criados}'
          f' | já existentes: {pulados}'
          f' | não interpretadas: {len(nao_interpretadas)}')
    if nao_interpretadas:
        print('\nURLs não interpretadas (nenhum registro criado para estas):')
        for os_id, categoria, url in nao_interpretadas:
            print(f'  OS {os_id} [{categoria}] {url}')
    if dry:
        print('\nNada foi gravado. Rode com --apply para aplicar.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
