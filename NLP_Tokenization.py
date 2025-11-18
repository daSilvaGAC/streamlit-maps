"""
Processa as descrições de denúncias de poluição sonora contidas no arquivo
`mga_denuncias_20-23.geojson`, aplicando tokenização, remoção de stopwords e
lemmatização com o modelo `pt_core_news_lg` do spaCy. Os tokens resultantes são
armazenados em uma nova coluna (propriedade GeoJSON) chamada
`descricao_tokens`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List

import nltk
import spacy

GEOJSON_PATH = Path("mga_denuncias_20-23.geojson")
TOKEN_PROPERTY = "descricao_tokens"
URL_REGEX = re.compile(r"https?://\\S+|www\\.\\S+", flags=re.IGNORECASE)
ALPHA_REGEX = re.compile(r"[a-zà-ú]{2,}", flags=re.IGNORECASE)
IR_FORMS = {"vou", "vais", "vai", "vamos", "ides", "vão"}


def _ensure_stopwords() -> set[str]:
    """Carrega a lista de stopwords do NLTK e adiciona termos comuns das denúncias."""
    try:
        stopwords = nltk.corpus.stopwords.words("portuguese")
    except LookupError:
        nltk.download("stopwords")
        stopwords = nltk.corpus.stopwords.words("portuguese")

    extras = {
        "'",
        "pra",
        "eh",
        "vcs",
        "lá",
        "né",
        "q",
        "o",
        "tá",
        "co",
        "t",
        "s",
        "rt",
        "pq",
        "ta",
        "tô",
        "ihh",
        "ih",
        "otc",
        "vc",
        "barulho",
        "https",
        "n",
        "qdo",
        "hj",
        "tb",
        "dia",
        "noite",
        "madrugada",
        "todo",
        "durante",
        "pois",
        "vez",
        "outro",
        "poder",
        "ficar",
        "fazer",
        "solicitar",
        "pedido",
        "pedir",
        "reclamar",
        "reclamação",
        "prefeitura",
        "protocolo",
        "urgente",
        "providência",
        "providencia",
    }
    return {w.lower() for w in stopwords}.union(extras)


def _clean_tokens(doc: Iterable[spacy.tokens.Token], stopwords: set[str]) -> List[str]:
    """Converte tokens do spaCy em uma lista de lemas normalizados."""
    normalized_tokens: List[str] = []
    for token in doc:
        raw = token.text.strip().lower()
        if not raw or raw in stopwords:
            continue
        if token.is_space or token.is_punct or token.like_num:
            continue
        if any(ch.isdigit() for ch in raw):
            continue
        if URL_REGEX.search(raw):
            continue
        if not ALPHA_REGEX.search(raw):
            continue

        lemma = token.lemma_.strip().lower() or raw
        lemma = "ir" if lemma in IR_FORMS else lemma

        if lemma in stopwords:
            continue

        normalized_tokens.append(lemma)
    return normalized_tokens


def process_geojson() -> None:
    """Executa o pipeline de NLP e persiste o resultado no GeoJSON."""
    if not GEOJSON_PATH.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {GEOJSON_PATH}")

    stopwords = _ensure_stopwords()
    nlp = spacy.load("pt_core_news_lg")

    with GEOJSON_PATH.open(encoding="utf-8") as source:
        data = json.load(source)

    features = data.get("features", [])
    for feature in features:
        props = feature.setdefault("properties", {})
        descricao = props.get("Descrição") or ""
        texto_tratado = URL_REGEX.sub(" ", str(descricao)).lower()
        doc = nlp(texto_tratado)
        tokens = _clean_tokens(doc, stopwords)
        props[TOKEN_PROPERTY] = tokens

    with GEOJSON_PATH.open("w", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2)

    print(
        f"Processadas {len(features)} denúncias. "
        f"Tokens armazenados na coluna '{TOKEN_PROPERTY}'."
    )


if __name__ == "__main__":
    process_geojson()
