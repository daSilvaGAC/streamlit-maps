"""
Classifica as denúncias de poluição sonora em duas fases:

1. Contexto (onde ocorre o ruído): bares, templos, obras, vias etc.
2. Modalidade do som (o que gera o ruído): música, maquinário, alarmes, animais etc.

Os resultados combinam contexto + modalidade para gerar o campo "Tipo de Fonte" e
adicionam informações auxiliares (pontuação, termos que dispararam cada regra e
inferências de horário). Também são produzidos clusters TF-IDF para análise exploratória.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

GEOJSON_PATH = Path("mga_denuncias_20-23.geojson")
OUTPUT_GEOJSON_PATH = Path("mga_denuncias_20-23_modalidade.geojson")

TYPE_PROPERTY = "Tipo de Fonte Modalidade"
CONTEXT_PROPERTY = "fonte_contexto_sugerido"
CONTEXT_SCORE_PROPERTY = "fonte_contexto_score"
CONTEXT_TERMS_PROPERTY = "fonte_contexto_termos"
MODALITY_PROPERTY = "fonte_modalidade"
MODALITY_SCORE_PROPERTY = "fonte_modalidade_score"
MODALITY_TERMS_PROPERTY = "fonte_modalidade_termos"
TIME_PROPERTY = "fonte_horario"
CLUSTER_PROPERTY = "fonte_cluster"

DEFAULT_CLUSTERS = 6
TOP_TERMS_PER_CLUSTER = 10

CONTEXT_KEYWORDS: Dict[str, set[str]] = {
    "bar_evento": {
        "bar",
        "bares",
        "churrasco",
        "festa",
        "balada",
        "residencia",
        "residencial",
        "comercio",
        "comércio",
        "evento",
        "lanchonete",
        "restaurante",
        "pub",
        "boteco",
        "adega",
        "cervejaria",
        "choperia",
        "boate",
        "lounge",
        "taproom",
        "estabelecimento",
        "pizzaria",
        "cafeteria",
    },
    "igreja_templo": {
        "igreja",
        "templo",
        "missa",
        "culto",
        "pastor",
        "louvor",
        "celebracao",
        "celebração",
        "evangelico",
        "evangélico",
        "paroquia",
        "paróquia",
    },
    "obra_construcao": {
        "obra",
        "obras",
        "construção",
        "construcao",
        "construcão",
        "construir",
        "construtora",
        "reforma",
        "reformar",
        "bairro",
        "prédio",
        "predio",
    },
    "industria_servico": {
        "industria",
        "indústria",
        "usina",
        "empresa",
        "comercio",
        "comércio",
        "fabrica",
        "fábrica",
        "oficina",
        "serralheria",
        "metalurgica",
        "metalúrgica",
    },
    "via_publica": {
        "rua",
        "avenida",
        "cruzamento",
        "praça",
        "rotatória",
        "semáforo",
        "semáfaro",
        "pista",
        "rodovia",
        "estrada",
    },
    "residencial": {
        "casa",
        "vizinho",
        "apartamento",
        "condominio",
        "condomínio",
        "prédio",
        "predio",
        "sobrado",
    },
    "area_lazer": {
        "quadra",
        "campo",
        "ginásio",
        "ginásio",
        "parque",
        "praça",
        "club",
        "clube",
    },
    "veiculos_transito": {
        "carro",
        "moto",
        "motocicleta",
        "caminhao",
        "caminhão",
        "veiculo",
        "veículo",
        "ônibus",
        "van",
        "trio",
        "caminhonete",
    },
}

AUDIO_KEYWORDS: Dict[str, set[str]] = {
    "musica": {
        "musica",
        "música",
        "som",
        "vivo",
        "banda",
        "show",
        "voz",
        "cantor",
        "cantora",
        "dj",
        "palco",
        "instrumento",
        "instrumental",
        "ensaio",
        "acustico",
        "acústico",
        "microfone",
        "teclado",
        "violão",
        "violino",
        "percussão",
        "percussao",
        "karaoke",
        "karaokê",
        "caixa",
        "caixas",
        "ritmo",
    },
    "maquinario": {
        "maquina",
        "máquina",
        "gerador",
        "compressor",
        "serra",
        "martelo",
        "martelar",
        "martelete",
        "furadeira",
        "betoneira",
        "britadeira",
        "perfurar",
        "perfuratriz",
        "trator",
        "equipamento",
        "indústria",
    },
    "veiculo": {
        "carro",
        "moto",
        "motocicleta",
        "automotivo",
        "escapamento",
        "ronco",
        "motor",
        "sirene",
        "acelerar",
        "buzina",
        "caminhao",
        "caminhão",
        "ônibus",
        "van",
        "trio",
    },
    "alarme": {
        "alarme",
        "disparo",
        "disparar",
        "sirene",
        "sensor",
        "bip",
        "estacionamento",
        "garagem",
        "entrada",
        "saida",
        "saída",
        "portaria",
        "vigia",
        "monitoramento",
    },
    "animal": {
        "cachorro",
        "cao",
        "cão",
        "latido",
        "latir",
        "galo",
        "galinha",
        "papagaio",
        "animal",
    },
    "fogos": {
        "fogos",
        "artificio",
        "artifício",
        "estouro",
        "rojão",
        "rojões",
        "pirotecnia",
        "foguete",
    },
    "vozes_aglomeracao": {
        "falar",
        "grito",
        "gritar",
        "aplausos",
        "torcida",
        "multidão",
        "pessoas",
        "cliente",
        "frequente",
        "risada",
        "aglomeração",
        "aglomeraçao",
        "bate-papo",
        "palmas",
    },
}

TIME_KEYWORDS: Dict[str, set[str]] = {
    "manha": {"manhã", "manha", "7h", "6h", "8h", "9h"},
    "tarde": {"tarde", "15h", "16h", "17h"},
    "noite": {"noite", "19h", "20h", "21h", "22h", "23h"},
    "madrugada": {
        "madrugada",
        "00h",
        "01h",
        "02h",
        "03h",
        "04h",
        "05h",
    },
    "fim_de_semana": {"sábado", "sabado", "domingo", "feriado"},
}


@dataclass
class MatchResult:
    label: str | None
    score: int
    matched_terms: Tuple[str, ...]


def load_geojson(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_geojson(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _match_categories(
    tokens: Iterable[str], categories: Dict[str, set[str]]
) -> Dict[str, set[str]]:
    token_set = {str(tok).lower() for tok in tokens if tok}
    matches: Dict[str, set[str]] = {}
    for label, keywords in categories.items():
        overlap = token_set.intersection(keywords)
        if overlap:
            matches[label] = overlap
    return matches


def _select_best(matches: Dict[str, set[str]]) -> MatchResult:
    best_label = None
    best_terms: Tuple[str, ...] = tuple()
    best_score = 0
    for label, tokens in matches.items():
        score = len(tokens)
        if score > best_score:
            best_label = label
            best_terms = tuple(sorted(tokens))
            best_score = score
    return MatchResult(best_label, best_score, best_terms)


def _extract_time_windows(tokens: Iterable[str]) -> List[str]:
    token_set = {str(tok).lower() for tok in tokens if tok}
    windows = []
    for label, keywords in TIME_KEYWORDS.items():
        if token_set.intersection(keywords):
            windows.append(label)
    return windows


def build_cluster_model(
    texts: List[str],
) -> tuple[List[int], TfidfVectorizer | None, KMeans | None]:
    if not texts:
        return [], None, None  # type: ignore[arg-type]
    if not any(text.strip() for text in texts):
        return [0] * len(texts), None, None

    n_clusters = min(DEFAULT_CLUSTERS, max(1, len(texts)))
    vectorizer = TfidfVectorizer(token_pattern=r"[^\s]+")
    matrix = vectorizer.fit_transform(texts)

    if n_clusters == 1:
        labels = [0] * len(texts)
        model = None  # type: ignore[assignment]
    else:
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        labels = model.fit_predict(matrix).tolist()

    return labels, vectorizer, model


def describe_clusters(
    model: KMeans | None, vectorizer: TfidfVectorizer | None
) -> dict[int, List[str]]:
    if model is None or vectorizer is None:
        return {0: []}
    terms = vectorizer.get_feature_names_out()
    cluster_terms: dict[int, List[str]] = {}
    for idx, centroid in enumerate(model.cluster_centers_):
        top_ids = centroid.argsort()[::-1][:TOP_TERMS_PER_CLUSTER]
        cluster_terms[idx] = [terms[i] for i in top_ids]
    return cluster_terms


def main() -> None:
    data = load_geojson(GEOJSON_PATH)
    features = data.get("features", [])

    docs: List[str] = []
    rule_counts: Counter[str] = Counter()

    # Classificação por regras
    for feature in features:
        props = feature.setdefault("properties", {})
        tokens = props.get("descricao_tokens") or []
        if not isinstance(tokens, list):
            tokens = []
        tokens = [str(tok).lower() for tok in tokens if tok]

        context_matches = _match_categories(tokens, CONTEXT_KEYWORDS)
        audio_matches = _match_categories(tokens, AUDIO_KEYWORDS)
        context_result = _select_best(context_matches)
        audio_result = _select_best(audio_matches)
        windows = _extract_time_windows(tokens)

        if audio_result.label:
            label = audio_result.label
        else:
            label = "indefinido"

        props[TYPE_PROPERTY] = label
        props[CONTEXT_PROPERTY] = context_result.label or ""
        props[CONTEXT_SCORE_PROPERTY] = context_result.score
        props[CONTEXT_TERMS_PROPERTY] = list(context_result.matched_terms)
        props[MODALITY_PROPERTY] = audio_result.label or ""
        props[MODALITY_SCORE_PROPERTY] = audio_result.score
        props[MODALITY_TERMS_PROPERTY] = list(audio_result.matched_terms)
        props[TIME_PROPERTY] = windows
        rule_counts[label] += 1

        text_repr = " ".join(tokens)
        docs.append(text_repr)

    # Clusterização para apoio exploratório
    cluster_labels, vectorizer, model = build_cluster_model(docs)
    cluster_terms = describe_clusters(model, vectorizer)

    for feature, label in zip(features, cluster_labels):
        feature["properties"][CLUSTER_PROPERTY] = f"cluster_{label}"

    save_geojson(OUTPUT_GEOJSON_PATH, data)

    print(
        f"Processadas {len(features)} denúncias. "
        f"Resultados salvos em '{OUTPUT_GEOJSON_PATH.name}'."
    )
    print("Sugestão de termos por cluster:")
    for cluster_id, terms in cluster_terms.items():
        highlight = ", ".join(terms[:TOP_TERMS_PER_CLUSTER])
        print(f" - cluster_{cluster_id}: {highlight}")

    print("Distribuição por regra léxica:")
    for label, count in rule_counts.most_common():
        print(f" - {label}: {count}")


if __name__ == "__main__":
    main()
