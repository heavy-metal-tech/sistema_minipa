"""
BGA AI Module — Minipa Precision
Provides AI-driven BGA soldering profile recommendation, autonomous operation
control simulation, and post-solder quality inspection via Claude vision.
"""
import os
import json
import math
import random
from datetime import datetime

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ── Temperature Profile Simulation ───────────────────────────────────────────

def gerar_log_temperatura(temp_preheat: float, tempo_preheat: int,
                           temp_soak: float, tempo_soak: int,
                           temp_reflow: float, tempo_reflow: int,
                           tempo_acima_liquidus: int = 40) -> list:
    """
    Simulates a realistic BGA reflow temperature curve.
    Returns a list of {t, temp} dicts (one per second).

    Stages:
      1. Preheat   : 25°C → temp_preheat  (ramp-up)
      2. Soak      : temp_preheat → temp_soak  (slow ramp)
      3. Reflow    : temp_soak → temp_reflow  (fast ramp)
      4. TAL hold  : temp_reflow peak  (time above liquidus)
      5. Cooling   : temp_reflow → 25°C  (controlled cool-down)
    """
    log = []
    t = 0

    def _noise(scale=1.5):
        return random.gauss(0, scale)

    # Stage 1 — Preheat (25 → temp_preheat)
    for i in range(tempo_preheat):
        frac = i / max(tempo_preheat - 1, 1)
        temp = 25.0 + (temp_preheat - 25.0) * frac + _noise(0.8)
        log.append({"t": t, "temp": round(temp, 1), "fase": "Pré-aquecimento"})
        t += 1

    # Stage 2 — Soak (temp_preheat → temp_soak)
    for i in range(tempo_soak):
        frac = i / max(tempo_soak - 1, 1)
        temp = temp_preheat + (temp_soak - temp_preheat) * frac + _noise(1.2)
        log.append({"t": t, "temp": round(temp, 1), "fase": "Soak"})
        t += 1

    # Stage 3 — Reflow ramp (temp_soak → temp_reflow)
    for i in range(tempo_reflow):
        frac = i / max(tempo_reflow - 1, 1)
        # Slightly curved ramp using smoothstep
        smooth = frac * frac * (3 - 2 * frac)
        temp = temp_soak + (temp_reflow - temp_soak) * smooth + _noise(2.0)
        log.append({"t": t, "temp": round(temp, 1), "fase": "Reflow"})
        t += 1

    # Stage 4 — TAL hold (peak)
    for i in range(tempo_acima_liquidus):
        temp = temp_reflow + _noise(2.5)
        log.append({"t": t, "temp": round(temp, 1), "fase": "Pico TAL"})
        t += 1

    # Stage 5 — Cooling (exponential decay → 25°C)
    tempo_cooling = max(int((temp_reflow - 25) / 2.0), 60)  # based on max rate 2°C/s
    for i in range(tempo_cooling):
        decay = math.exp(-4.0 * i / tempo_cooling)
        temp = 25.0 + (temp_reflow - 25.0) * decay + _noise(1.5)
        temp = max(temp, 25.0)
        log.append({"t": t, "temp": round(temp, 1), "fase": "Resfriamento"})
        t += 1

    return log


# ── AI Functions ──────────────────────────────────────────────────────────────

def _get_client():
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("Biblioteca 'anthropic' não instalada. Execute: pip install anthropic")
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada nas variáveis de ambiente.")
    return anthropic.Anthropic(api_key=api_key)


def analisar_componente_bga(componente: str, descricao: str = '') -> dict:
    """
    AI analyzes the BGA component and returns recommended soldering parameters.
    This is the 'AI does the soldering itself' intelligence layer:
    it determines the exact thermal profile for each component automatically.

    Returns dict with keys:
      tipo_solda, temp_preheat, tempo_preheat, temp_soak, tempo_soak,
      temp_reflow, tempo_reflow, tempo_acima_liquidus, taxa_resfriamento,
      observacoes_ia, nivel_dificuldade, riscos
    """
    client = _get_client()

    prompt = f"""Você é um engenheiro especialista em processos de soldagem BGA (Ball Grid Array)
e retrabalho de componentes SMD em placas de circuito impresso.

Analise o seguinte componente BGA e defina AUTOMATICAMENTE o perfil de temperatura ideal
para o processo de soldagem/retrabalho. Você está controlando uma máquina BGA autônoma.

Componente: {componente}
{f'Informações adicionais: {descricao}' if descricao else ''}

Retorne SOMENTE um objeto JSON válido com esta estrutura exata:
{{
  "tipo_solda": "<SAC305 ou SnPb ou outro>",
  "temp_preheat": <número float em °C, típico 120-150>,
  "tempo_preheat": <segundos inteiro, típico 60-120>,
  "temp_soak": <número float em °C, típico 150-183>,
  "tempo_soak": <segundos inteiro, típico 60-120>,
  "temp_reflow": <número float em °C, típico 230-260>,
  "tempo_reflow": <segundos inteiro, típico 45-90>,
  "tempo_acima_liquidus": <segundos inteiro TAL, típico 30-60>,
  "taxa_resfriamento": <float °C/segundo máx, típico 1.5-3.0>,
  "observacoes_ia": "<observações técnicas importantes em português>",
  "nivel_dificuldade": "<Baixo, Médio, Alto ou Crítico>",
  "riscos": ["<risco 1>", "<risco 2>"]
}}

Base suas decisões em:
- Tipo/família do componente (CPU, GPU, SoC, memória, FPGA, etc.)
- Sensibilidade térmica típica do package
- Normas IPC/JEDEC para o perfil de reflow
- Necessidade de proteção de componentes adjacentes

Responda APENAS com o JSON, sem markdown, sem texto adicional."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.split("```")[0]
    return json.loads(raw.strip())


def inspecionar_qualidade_bga(foto_url: str, componente: str,
                               perfil_nome: str = '', observacoes: str = '') -> dict:
    """
    AI inspects the BGA solder joint from a post-reflow photo.
    Uses Claude vision to detect defects and assign a quality score.

    Returns dict with keys:
      qualidade (0-100), aprovado (bool), defeitos (list), advertencias (list),
      recomendacoes (list), resumo (str), acao_necessaria (str)
    """
    client = _get_client()

    prompt = f"""Você é um inspetor especialista em soldagem BGA com 20 anos de experiência.
Analise a imagem da placa após o processo de reflow BGA.

Componente soldado: {componente}
{f'Perfil utilizado: {perfil_nome}' if perfil_nome else ''}
{f'Observações do técnico: {observacoes}' if observacoes else ''}

Avalie os seguintes critérios de qualidade IPC-A-610:
1. Alinhamento dos balls de solda
2. Pontes de solda (bridging) entre balls
3. Juntas frias (cold joints) — aspecto fosco/granuloso
4. Balls ausentes ou malformados (voids)
5. Levantamento de pad (pad lifting)
6. Excesso ou falta de pasta de solda
7. Resíduos de flux
8. Orientação e posicionamento do componente

Retorne SOMENTE um JSON válido com esta estrutura:
{{
  "qualidade": <inteiro 0-100>,
  "aprovado": <true ou false>,
  "defeitos": ["<defeito crítico 1>", "<defeito crítico 2>"],
  "advertencias": ["<aviso 1>", "<aviso 2>"],
  "recomendacoes": ["<ação recomendada 1>", "<ação recomendada 2>"],
  "resumo": "<resumo técnico da inspeção em 2-3 frases>",
  "acao_necessaria": "<Nenhuma, Retrabalho menor, Retrabalho completo ou Substituição>"
}}

Critérios de aprovação: qualidade >= 75 = aprovado.
Responda APENAS com o JSON, sem markdown, sem texto adicional."""

    if foto_url:
        content = [
            {"type": "image", "source": {"type": "url", "url": foto_url}},
            {"type": "text", "text": prompt}
        ]
    else:
        # No image — AI provides assessment based on description only
        content = (
            f"Não há imagem disponível para inspeção visual. "
            f"Com base apenas nas informações fornecidas sobre o componente {componente}, "
            f"forneça uma avaliação conservadora indicando que inspeção visual é necessária.\n\n"
            + prompt
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.split("```")[0]
    return json.loads(raw.strip())


def gerar_relatorio_operacao(operacao) -> dict:
    """
    Generates a comprehensive AI report for a completed BGA operation.
    Summarizes profile used, temperature achieved, and quality result.
    """
    client = _get_client()

    log = json.loads(operacao.log_temperatura or '[]')
    resultado = json.loads(operacao.resultado_ia or '{}')
    perfil_ia = json.loads(operacao.perfil_ia_json or '{}')

    temp_max = max((p['temp'] for p in log), default=0)
    temp_min_cooling = min((p['temp'] for p in log if p.get('fase') == 'Resfriamento'), default=25)
    duracao = (operacao.data_fim - operacao.data_inicio).seconds if operacao.data_fim and operacao.data_inicio else 0

    prompt = f"""Gere um relatório técnico resumido em português para uma operação BGA concluída.

Dados da operação:
- Componente: {operacao.componente}
- Status: {operacao.status}
- Duração total: {duracao} segundos
- Temperatura de pico atingida: {temp_max}°C
- Temperatura final de resfriamento: {temp_min_cooling}°C
- Perfil recomendado pela IA: {json.dumps(perfil_ia, ensure_ascii=False)}
- Resultado da inspeção: {json.dumps(resultado, ensure_ascii=False)}
- Score de qualidade: {operacao.qualidade_ia}/100
- Aprovado: {'Sim' if operacao.aprovado_ia else 'Não'}

Retorne SOMENTE um JSON:
{{
  "titulo": "<título do relatório>",
  "resumo_processo": "<2-3 frases sobre o processo>",
  "conformidade_perfil": "<análise se o processo seguiu o perfil recomendado>",
  "conclusao": "<conclusão técnica>",
  "proximos_passos": ["<passo 1>", "<passo 2>"]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.split("```")[0]
    return json.loads(raw.strip())


# ── Fallback mock (when API key not set) ──────────────────────────────────────

def mock_analisar_componente(componente: str) -> dict:
    """Returns a default SAC305 profile when AI is unavailable."""
    return {
        "tipo_solda": "SAC305",
        "temp_preheat": 150.0,
        "tempo_preheat": 90,
        "temp_soak": 183.0,
        "tempo_soak": 90,
        "temp_reflow": 245.0,
        "tempo_reflow": 60,
        "tempo_acima_liquidus": 40,
        "taxa_resfriamento": 2.0,
        "observacoes_ia": "Perfil padrão SAC305 aplicado (API de IA não configurada).",
        "nivel_dificuldade": "Médio",
        "riscos": ["Configure ANTHROPIC_API_KEY para análise personalizada"]
    }


def mock_inspecionar_qualidade(componente: str) -> dict:
    """Returns a placeholder inspection result when AI is unavailable."""
    return {
        "qualidade": 0,
        "aprovado": False,
        "defeitos": [],
        "advertencias": ["Inspeção por IA não disponível — API key não configurada"],
        "recomendacoes": ["Configure ANTHROPIC_API_KEY e faça nova inspeção com foto"],
        "resumo": "Inspeção automática indisponível. Realize inspeção visual manual.",
        "acao_necessaria": "Nenhuma"
    }
