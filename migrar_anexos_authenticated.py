"""Converte os anexos legados de type='upload' para 'authenticated'.

Depois disto a URL pública antiga para de responder e o arquivo só abre pela
rota do sistema, com login e checagem de autorizada.

    python3 migrar_anexos_authenticated.py                    # dry-run: só lista
    python3 migrar_anexos_authenticated.py --apply            # converte tudo
    python3 migrar_anexos_authenticated.py --apply --limit 5  # converte 5

Ordem de cada arquivo, deliberadamente nesta sequência:
  1. grava a linha no CSV de backup (antes de qualquer alteração);
  2. chama o rename no Cloudinary;
  3. só com sucesso, atualiza tipo_entrega no banco;
  4. confere que a URL pública antiga deixou de responder.

Se o passo 2 falhar, o banco não é tocado e o arquivo continua acessível como
antes — o script segue para o próximo e lista a falha no fim. Se o passo 3
falhar, o CSV permite desfazer: o rename inverso traz o arquivo de volta.
"""
import argparse
import csv
import sys
import urllib.error
import urllib.request
from datetime import datetime

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from app import app, _configurar_cloudinary
from database import db, Anexo

CSV_PADRAO = 'backup_anexos_%s.csv'


def url_publica(anexo):
    """URL pública antiga (type='upload'), a que deve morrer após a conversão."""
    url, _ = cloudinary_url(anexo.public_id,
                            resource_type=anexo.resource_type or 'image',
                            type='upload',
                            format=anexo.formato or None,
                            secure=True)
    return url


def ainda_responde(url, timeout=15):
    """True se a URL pública ainda entrega o arquivo.

    404, 401 e 403 contam como "não responde", que é o esperado após converter.
    Erro de rede devolve None: não dá para afirmar nem uma coisa nem outra.
    """
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            return False
        return None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='converte (sem isso é dry-run)')
    ap.add_argument('--limit', type=int, default=None, help='converte no máximo N arquivos')
    ap.add_argument('--csv', default=None, help='caminho do CSV de backup')
    args = ap.parse_args()
    dry = not args.apply
    caminho_csv = args.csv or CSV_PADRAO % datetime.now().strftime('%Y%m%d_%H%M%S')

    convertidos, falhas, nao_confirmados = 0, [], []

    with app.app_context():
        if not _configurar_cloudinary():
            print('ERRO: credenciais do Cloudinary ausentes no ambiente.', file=sys.stderr)
            return 2

        pendentes = (Anexo.query.filter(Anexo.tipo_entrega != 'authenticated')
                     .order_by(Anexo.id).all())
        ja_prontos = Anexo.query.filter_by(tipo_entrega='authenticated').count()
        if args.limit:
            pendentes = pendentes[:args.limit]

        print(f'{"DRY-RUN — nada será alterado" if dry else "APLICANDO"}')
        print(f'{len(pendentes)} a converter | {ja_prontos} já em authenticated')
        print(f'CSV de backup: {caminho_csv}\n')
        if not pendentes:
            print('Nada a fazer.')
            return 0

        arquivo_csv = open(caminho_csv, 'w', newline='', encoding='utf-8')
        escritor = csv.writer(arquivo_csv)
        escritor.writerow(['anexo_id', 'os_id', 'public_id', 'resource_type',
                           'formato', 'url_antiga'])

        try:
            for anexo in pendentes:
                antiga = url_publica(anexo)
                rotulo = f'anexo {anexo.id:>5} (OS {anexo.os_id})'
                # Backup primeiro, sempre — inclusive em dry-run, para você ver o conteúdo
                escritor.writerow([anexo.id, anexo.os_id, anexo.public_id,
                                   anexo.resource_type, anexo.formato, antiga])
                arquivo_csv.flush()

                if dry:
                    print(f'  DRY {rotulo} {anexo.public_id} '
                          f'({anexo.resource_type}) upload -> authenticated')
                    convertidos += 1
                    continue

                try:
                    cloudinary.uploader.rename(
                        anexo.public_id, anexo.public_id,
                        resource_type=anexo.resource_type or 'image',
                        type='upload', to_type='authenticated',
                        invalidate=True,
                    )
                except Exception as exc:
                    falhas.append((anexo.id, anexo.public_id, f'{type(exc).__name__}: {exc}'))
                    print(f'  ERRO {rotulo} rename falhou: {exc}')
                    continue

                # Só agora o banco muda: o Cloudinary já confirmou
                anexo.tipo_entrega = 'authenticated'
                try:
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    falhas.append((anexo.id, anexo.public_id,
                                   f'convertido no Cloudinary mas o banco falhou: {exc}'))
                    print(f'  ERRO {rotulo} banco falhou APÓS converter — ver CSV')
                    continue

                responde = ainda_responde(antiga)
                if responde is True:
                    nao_confirmados.append((anexo.id, antiga, 'URL antiga ainda responde'))
                    print(f'  OK? {rotulo} convertido, mas a URL antiga AINDA responde')
                elif responde is None:
                    nao_confirmados.append((anexo.id, antiga, 'não foi possível verificar'))
                    print(f'  OK? {rotulo} convertido; verificação inconclusiva')
                else:
                    print(f'  OK  {rotulo} convertido e URL antiga fechada')
                convertidos += 1
        finally:
            arquivo_csv.close()

    print(f'\n{"seriam convertidos" if dry else "convertidos"}: {convertidos}'
          f' | falhas: {len(falhas)} | sem confirmação: {len(nao_confirmados)}')
    if falhas:
        print('\nFalhas (nada foi alterado no banco para estes):')
        for anexo_id, public_id, motivo in falhas:
            print(f'  anexo {anexo_id} [{public_id}] {motivo}')
    if nao_confirmados:
        print('\nConvertidos sem confirmação de fechamento da URL antiga:')
        for anexo_id, url, motivo in nao_confirmados:
            print(f'  anexo {anexo_id} ({motivo}) {url}')
        print('  O CDN do Cloudinary pode levar alguns minutos para expirar o cache.')
    if dry:
        print(f'\nNada foi alterado. O CSV em {caminho_csv} mostra o que seria tocado.')
        print('Rode com --apply para converter.')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
