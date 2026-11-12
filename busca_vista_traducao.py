"""Tradução local de trechos públicos; nunca acessa a rede."""
import logging
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus, urlencode

from core.i18n import t

logger = logging.getLogger(__name__)

_MODELO_LOCAL = Path(__file__).resolve().parent / "assets" / "modelos_traducao" / "translate-en_pt-1_9"


class TraducaoLocalIndisponivel(Exception):
    pass


def preparar_texto_local(texto, identidade):
    """Retira contatos identificáveis e bloqueia indícios restantes."""
    revisado = re.sub(_DADOS_SENSIVEIS[0][0], "[removido]", texto, flags=re.I)
    revisado = re.sub(_DADOS_SENSIVEIS[1][0], "[removido]", revisado, flags=re.I)
    tecnicos = set(_PALAVRAS_INICIAIS) | {
        "spool", "pinion", "bearing", "gear", "drag", "reel", "brake",
        "handle", "washer", "shaft", "shimano", "daiwa", "abu", "penn",
        "which", "how", "what", "why", "when",
    }
    for campo in ("fabricante", "familia", "modelo"):
        tecnicos.update(re.findall(r"[a-z]+", (identidade or {}).get(campo, "").lower()))

    def ocultar_nome(match):
        palavras = match.group().lower().split()
        return match.group() if any(p in tecnicos for p in palavras) else "[removido]"

    revisado = re.sub(
        r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç]{2,}"
        r"(?:[ \t]+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç]{2,})+",
        ocultar_nome, revisado,
    )
    motivos = [m for m in detectar_sensiveis(revisado, identidade)
               if m not in {"bv_dado_nao_tecnico", "bv_dado_nome"}]
    if motivos:
        raise TraducaoLocalIndisponivel("dados_sensiveis")
    return revisado


def traduzir_texto_local(texto, origem, locale, identidade, cancelamento):
    """Traduz localmente sem descarte silencioso ou envio para serviços externos."""
    destino = locale.lower().replace("-", "_").split("_")[0]
    origem = (origem or "").lower().split("-")[0].split("_")[0]
    if origem == destino and origem:
        return texto
    if (origem, destino) != ("en", "pt"):
        raise TraducaoLocalIndisponivel("idioma")
    if not (_MODELO_LOCAL / "model" / "model.bin").is_file():
        raise TraducaoLocalIndisponivel("modelo")
    try:
        import ctranslate2
        import sentencepiece
    except ImportError as exc:
        raise TraducaoLocalIndisponivel("modelo") from exc

    texto = preparar_texto_local(texto, identidade)
    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(_MODELO_LOCAL / "sentencepiece.model"))
    tradutor = ctranslate2.Translator(str(_MODELO_LOCAL / "model"), device="cpu", intra_threads=2)
    protegidos = set(re.findall(r"\b[A-Za-z]*\d[A-Za-z0-9.-]*\b", texto))
    for campo in ("fabricante", "familia", "modelo"):
        protegidos.update(p for p in (identidade or {}).get(campo, "").split() if len(p) >= 3)
    padrao = (r"(?<!\w)(?:" + "|".join(re.escape(p) for p in sorted(protegidos, key=len, reverse=True))
              + r")(?!\w)") if protegidos else None

    def traduzir_corpo(corpo, proteger=True):
        if cancelamento.is_set():
            raise InterruptedError("cancelado")
        if not re.search(r"[^\W\d_]", corpo):
            return corpo
        espaco_inicio = re.match(r"\s*", corpo).group()
        espaco_fim = re.search(r"\s*$", corpo).group()
        tokens = tradutor.translate_batch(
            [tokenizer.encode(corpo.strip(), out_type=str)], beam_size=4,
            max_input_length=0, max_decoding_length=512, replace_unknowns=True,
        )[0].hypotheses[0]
        if not tokens or len(tokens) >= 512:
            raise TraducaoLocalIndisponivel("incompleta")
        saida_traduzida = tokenizer.decode(tokens).replace("▁", " ").strip()
        if not saida_traduzida:
            raise TraducaoLocalIndisponivel("incompleta")
        termos = Counter(p.lower() for p in re.findall(padrao, corpo, re.I)) if proteger and padrao else Counter()
        termos_saida = Counter(p.lower() for p in re.findall(padrao, saida_traduzida, re.I)) if termos else Counter()
        if termos and termos != termos_saida:
            fragmentos = re.split(f"({padrao})", corpo, flags=re.I)
            return "".join(fragmento if re.fullmatch(padrao, fragmento, re.I)
                           else traduzir_corpo(fragmento, proteger=False) for fragmento in fragmentos if fragmento)
        return espaco_inicio + saida_traduzida + espaco_fim

    partes = re.split(r"(\n+)", texto)
    saida = []
    for parte in partes:
        if cancelamento.is_set():
            raise InterruptedError("cancelado")
        if not parte or parte.startswith("\n"):
            saida.append(parte)
            continue
        frases = re.split(r"(?<=[.!?])(?=\s)", parte)
        for frase in frases:
            pedacos = re.findall(r"\s+|\S+", frase)
            trecho = ""
            for pedaco in pedacos + [""]:
                candidato = trecho + pedaco
                if pedaco and len(tokenizer.encode(candidato, out_type=str)) <= 100:
                    trecho = candidato
                    continue
                if trecho.strip():
                    saida.append(traduzir_corpo(trecho))
                else:
                    saida.append(trecho)
                trecho = pedaco
                if pedaco and len(tokenizer.encode(pedaco, out_type=str)) > 100:
                    raise TraducaoLocalIndisponivel("incompleta")
    resultado = "".join(saida)
    if padrao and Counter(p.lower() for p in re.findall(padrao, texto, re.I)) != Counter(
        p.lower() for p in re.findall(padrao, resultado, re.I)
    ):
        raise TraducaoLocalIndisponivel("identificador")
    return resultado


def endereco_google(locale, texto=""):
    idioma = locale.lower().replace("-", "_").split("_")[0]
    if idioma not in {"pt", "en", "es"}:
        raise ValueError("Idioma de tradução não suportado.")
    parametros = {"sl": "auto", "tl": idioma}
    if texto:
        parametros.update({"text": texto, "op": "translate"})
    return "https://translate.google.com/?" + urlencode(parametros)


_DADOS_SENSIVEIS = (
    (r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\w)@[\w.-]+|https?://\S+|\bwww\.\S+", "bv_dado_contato"),
    (r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", "bv_dado_contato"),
    (r"\b(?:rua|avenida|avenue|street|address|endereço|endereco|cep|zip code)\b", "bv_dado_endereco"),
    (r"[$€£¥]|\b(?:preço|preco|price|cost|custo|margin|margem|venda|sales?|invoice|fatura|fornecedor(?:es)?|supplier|estoque|stock|customer|client|cliente|company|empresa|cnpj|cpf|USD|BRL|EUR|dollars?|dólares?|dolares?|euros?|reais|paid|pago|comprou|bought|purchase|valor|ltda|llc|incorporated)\b", "bv_dado_comercial"),
    (r"\bFRS\b|\b(?:ordem de serviço|ordem de servico|service order)\b|(?<!\w)OS\s*[:#-]?\s*\d", "bv_dado_operacional"),
)
_PALAVRAS_INICIAIS = {"the", "my", "this", "that", "hello", "hi", "i", "a", "an", "o", "a", "meu", "minha", "este", "esta"}


def detectar_sensiveis(texto, identidade=None):
    motivos = [chave for padrao, chave in _DADOS_SENSIVEIS if re.search(padrao, texto, re.I)]
    conhecidos = set()
    for campo in ("fabricante", "familia", "modelo"):
        conhecidos.update(re.findall(r"[a-z]+", (identidade or {}).get(campo, "").lower()))
    for nome in re.finditer(r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç]{2,})\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç]{2,})\b", texto):
        primeiro, segundo = (parte.lower() for parte in nome.groups())
        if primeiro not in _PALAVRAS_INICIAIS and not ({primeiro, segundo} <= conhecidos):
            motivos.append("bv_dado_nome")
            break
    tecnico = re.compile(
        r"\b(?:reel|drag|washer|gear|bearing|spool|handle|brake|pinion|clutch|shaft|bail|"
        r"repair|fix(?:ed)?|replac\w*|problem\w*|issue\w*|fail\w*|broken|stuck|"
        r"cause|symptom\w*|diagnos\w*|compatib\w*|part\w*|model\w*|"
        r"carretilha|molinete|freio|arruela|engrenagem|rolamento|carretel|manivela|"
        r"eixo|embreagem|reparo|conserto|troca|defeito|falha|problema|peça|peca|"
        r"causa|sintoma|diagnóstico|diagnostico|compatibilidade|modelo)\b",
        re.I,
    )
    for bloco in re.split(r"\n\s*\n", texto):
        palavras = set(re.findall(r"[a-z]+", bloco.lower()))
        if bloco.strip() and not tecnico.search(bloco) and not (palavras & conhecidos):
            motivos.append("bv_dado_nao_tecnico")
            break
    return list(dict.fromkeys(motivos))


def somente_remocoes(original, revisado):
    caracteres = iter(original)
    return all(any(atual == procurado for atual in caracteres) for procurado in revisado)


def partes_google(texto, locale, limite_url=1800):
    if not texto:
        raise ValueError("Texto vazio.")
    prefixo_max = "[Parte 999999/999999]\n"
    disponivel = limite_url - len(endereco_google(locale, prefixo_max))
    if disponivel <= 0:
        raise ValueError("Limite de endereço insuficiente.")
    partes = []
    inicio = 0
    tamanho = 0
    for posicao, caractere in enumerate(texto):
        codificado = 1 if caractere == " " or (caractere.isascii() and (caractere.isalnum() or caractere in "-_.~")) else len(quote_plus(caractere))
        if codificado > disponivel:
            raise ValueError("Limite de endereço insuficiente.")
        if tamanho + codificado > disponivel or posicao - inicio >= 5000 - len(prefixo_max):
            partes.append(texto[inicio:posicao])
            inicio = posicao
            tamanho = 0
        tamanho += codificado
    partes.append(texto[inicio:])
    total = len(partes)
    return [endereco_google(locale, f"[Parte {i}/{total}]\n{parte}" if total > 1 else parte)
            for i, parte in enumerate(partes, 1)]

_STATUS = (
    ("Identidade técnica insuficiente; nenhuma consulta externa foi enviada.", "bv_identidade_insuficiente"),
    ("Sem relato confirmado da variante; pesquisando a família.", "bv_pesquisando_familia"),
    ("Nenhuma discussão correspondente confirmada nesta pesquisa.", "bv_sem_resultados"),
    ("Limite de discussões analisadas; pesquisa incompleta", "bv_limite_discussoes"),
    ("limite de discussões; pesquisa incompleta", "bv_limite_discussoes"),
    ("Prazo total da pesquisa esgotado", "bv_prazo_total"),
    ("discussão(ões) com possível relato; frequência e reparos não verificados.", "bv_resumo_relato"),
    ("discussão(ões) encontrada(s).", "bv_discussoes_encontradas"),
    ("Pesquisando relatos:", "bv_pesquisando_relatos"),
    ("Pesquisando:", "bv_pesquisando"),
    ("Falha na pesquisa de relatos:", "bv_falha_pesquisa"),
    ("bloqueio ou verificação", "bv_bloqueio"),
    ("tempo excedido", "bv_tempo_excedido"),
    ("indisponível", "bv_indisponivel"),
    ("bloqueado", "bv_bloqueado"),
    ("demais fontes continuam.", "bv_fontes_continuam"),
    ("Limitações:", "bv_limitacoes"),
    ("Discussão", "bv_discussao"),
)


def localizar_status(texto, locale):
    if texto.startswith("Falha na pesquisa de relatos:"):
        partes = texto.split(": ", 2)
        texto = ": ".join(partes[:2])
    if locale.lower().startswith("pt"):
        return texto
    for original, chave in _STATUS:
        texto = texto.replace(original, t(chave, locale=locale))
    return texto


def traduzir_item(item, locale, identidade):
    """Usa somente modelos Argos já instalados; falhas preservam o original."""
    origem = item.get("idioma", "")
    destino = locale.lower().split("_")[0]
    if origem and origem == destino:
        return dict(item), True
    if not origem:
        return dict(item), False
    try:
        from argostranslate import translate
    except ImportError:
        return dict(item), False
    try:
        idiomas = {idioma.code: idioma for idioma in translate.get_installed_languages()}
        if origem not in idiomas or destino not in idiomas:
            return dict(item), False
        tradutor = idiomas[origem].get_translation(idiomas[destino])
        if tradutor is None:
            return dict(item), False
        resultado = dict(item)
        protegidos = set(re.findall(r"\b[A-Za-z]*\d[A-Za-z0-9.-]*\b", " ".join(
            str(item.get(campo, "")) for campo in ("titulo", "sintomas", "causa", "reparo")
        )))
        for campo in ("fabricante", "familia", "modelo"):
            protegidos.update(palavra for palavra in (identidade or {}).get(campo, "").split() if len(palavra) >= 3)
        for campo in ("titulo", "sintomas", "causa", "reparo"):
            original = item.get(campo, "")
            if not original:
                continue
            termos = {
                ocorrencia
                for p in protegidos
                for ocorrencia in re.findall(rf"(?<!\w){re.escape(p)}(?!\w)", original, re.I)
            }
            texto = tradutor.translate(original)
            if not texto or any(not re.search(rf"(?<!\w){re.escape(p)}(?!\w)", texto) for p in termos):
                return dict(item), False
            resultado[campo] = texto
        return resultado, True
    except Exception:
        logger.exception("Falha na tradução local de conteúdo público")
        return dict(item), False
