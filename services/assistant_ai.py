from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


try:
    from openai import OpenAI  
except Exception:  
    OpenAI = None


SYSTEM_ASSISTANT_PROMPT = """
Você é a assistente oficial da plataforma ServiAqui.

Objetivo:
- orientar usuários a encontrar serviços locais
- ajudar profissionais a publicar anúncios melhores
- explicar páginas e fluxos do site
- responder com clareza, confiança e tom profissional

Regras:
- responda sempre em português do Brasil
- seja objetiva, útil e natural
- use no máximo 5 frases curtas
- quando o pedido estiver incompleto, peça 1 informação essencial
- quando houver serviço compatível, recomende o mais aderente
- quando houver urgência, sugira contato imediato e confirmação de disponibilidade
- quando houver necessidade de acessibilidade, priorize comunicação clara e confirmação por mensagem
- nunca invente dados que não estejam no contexto
- quando não souber algo, diga com honestidade e indique a próxima melhor ação

Formato:
- reply
- quick_actions
- recommended_services
- intent
- accessibility_tip
Retorne apenas JSON válido.
""".strip()

SYSTEM_ANNOUNCEMENT_PROMPT = """
Você reescreve anúncios de serviços para a plataforma ServiAqui.

Regras:
- responda apenas com JSON válido
- mantenha tom premium, comercial, confiável e natural
- valorize clareza, credibilidade e conversão
- não invente certificações, preços ou promessas que o usuário não informou

Campos obrigatórios:
- suggested_title
- optimized_description
- accessibility_text
- summary
- checklist
- target_audience
- trust_signals
- cta
""".strip()


@dataclass(frozen=True)
class CuratedService:
    category: str
    title: str
    page: str
    description: str
    keywords: List[str]
    accessibility_tip: str


CATALOG = [
    CuratedService(
        category="reformas",
        title="Eletricista residencial",
        page="/servicos",
        description="Instalação, manutenção elétrica e atendimento emergencial em imóveis residenciais.",
        keywords=["eletricista", "tomada", "chuveiro", "fiação", "fiacao", "curto", "luz", "energia"],
        accessibility_tip="Prefira agendamento confirmado por mensagem e checklist objetivo antes da visita.",
    ),
    CuratedService(
        category="beleza",
        title="Maquiagem em domicílio",
        page="/servicos",
        description="Atendimento personalizado para eventos, produção social e imagem profissional.",
        keywords=["maquiagem", "maquiadora", "beleza", "evento", "produção", "penteado"],
        accessibility_tip="Peça confirmação por texto e alinhamento visual prévio para garantir segurança e previsibilidade.",
    ),
    CuratedService(
        category="educação",
        title="Reforço escolar",
        page="/servicos",
        description="Aulas de reforço com rotina organizada, linguagem clara e foco em evolução constante.",
        keywords=["reforço", "reforco", "aula", "professor", "estudo", "escolar", "matemática", "matematica", "português", "portugues"],
        accessibility_tip="Materiais em etapas curtas e comunicação clara ajudam bastante no acompanhamento.",
    ),
    CuratedService(
        category="casa",
        title="Limpeza residencial",
        page="/servicos",
        description="Limpeza recorrente ou pontual para apartamentos e casas, com rotina definida.",
        keywords=["limpeza", "diarista", "faxina", "organização", "organizacao", "casa", "apartamento"],
        accessibility_tip="Checklist visual e escopo fechado por mensagem reduzem ruído de comunicação.",
    ),
    CuratedService(
        category="saúde",
        title="Fisioterapia domiciliar",
        page="/servicos",
        description="Atendimento em casa com foco em mobilidade, reabilitação e bem-estar.",
        keywords=["fisioterapia", "fisioterapeuta", "reabilitação", "reabilitacao", "dor", "mobilidade"],
        accessibility_tip="Oriente horários, duração e preparo do ambiente com antecedência para uma experiência mais segura.",
    ),
]

FAQ = {
    "anuncio": "A melhor rota é abrir a página Anunciar, preencher os dados, pedir a melhoria por IA e enviar para moderação.",
    "acessibilidade": "O site usa estrutura semântica, foco visível, contraste adequado, navegação por teclado e leitura confortável em diferentes telas.",
    "contato": "Você pode usar o formulário de contato, acessar o painel e acompanhar o histórico da operação pela sua conta.",
    "servicos": "Na página Serviços você encontra categorias, busca rápida e anúncios aprovados para acelerar a decisão.",
}

NEIGHBORHOODS = ["Centro", "Farol", "Ponta Verde", "Jaraguá", "Jatiúca", "Mangabeiras", "Benedito Bentes", "Tabuleiro"]
URGENCY_WORDS = {"urgente", "hoje", "agora", "rápido", "rapido", "imediato", "emergência", "emergencia"}
ACCESSIBILITY_WORDS = {"acessibilidade", "libras", "cadeira", "mobilidade", "visual", "auditiva", "texto", "mensagem", "leitura"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ0-9]+", normalize(text))


def ai_provider_status() -> Dict[str, object]:
    available = bool(os.getenv("OPENAI_API_KEY", "").strip() and OpenAI is not None)
    return {
        "mode": "openai" if available else "local",
        "openai_configured": available,
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini") if available else "motor local baseado em regras",
    }


def detect_intent(message: str) -> str:
    msg = normalize(message)
    if any(word in msg for word in ["anunciar", "publicar", "divulgar", "anúncio", "anuncio"]):
        return "anuncio"
    if any(word in msg for word in ["acessibilidade", "libras", "fonte", "teclado", "ouvir"]):
        return "acessibilidade"
    if any(word in msg for word in ["contato", "telefone", "whatsapp", "orçamento", "orcamento"]):
        return "contato"
    if any(word in msg for word in ["serviço", "servico", "profissional", "buscar", "preciso", "quero um"]):
        return "buscar_servico"
    return "geral"


def detect_neighborhood(message: str) -> str:
    msg = normalize(message)
    for neighborhood in NEIGHBORHOODS:
        if normalize(neighborhood) in msg:
            return neighborhood
    return ""


def detect_urgency(message: str) -> str:
    msg = normalize(message)
    return "alta" if any(word in msg for word in URGENCY_WORDS) else "normal"


def needs_accessibility(message: str) -> bool:
    msg = normalize(message)
    return any(word in msg for word in ACCESSIBILITY_WORDS)


def score_services(message: str) -> List[CuratedService]:
    msg = normalize(message)
    tokens = set(tokenize(msg))
    scored: List[tuple[int, CuratedService]] = []

    for item in CATALOG:
        score = 0
        for keyword in item.keywords:
            keyword_normalized = normalize(keyword)
            if keyword_normalized in msg:
                score += 4
            if keyword_normalized in tokens:
                score += 2
        if normalize(item.category) in msg:
            score += 3
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:3]]


def _score_live_services(message: str, live_services: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if not live_services:
        return []

    tokens = {token for token in tokenize(message) if len(token) >= 3}
    scored: List[tuple[int, Dict[str, Any]]] = []

    for item in live_services:
        blob = normalize(
            " ".join(
                [
                    str(item.get("name", "")),
                    str(item.get("category", "")),
                    str(item.get("description", "")),
                    str(item.get("neighborhood", "")),
                ]
            )
        )

        if not blob:
            continue

        score = 0
        for token in tokens:
            if token in blob:
                score += 2

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:3]]


def _format_live_service(item: Dict[str, Any]) -> str:
    name = str(item.get("name", "")).strip() or "Serviço"
    category = str(item.get("category", "")).strip()
    neighborhood = str(item.get("neighborhood", "")).strip()
    description = str(item.get("description", "")).strip()

    parts = [name]
    if category:
        parts.append(category)
    if neighborhood:
        parts.append(neighborhood)
    if description:
        parts.append(description)

    return " — ".join(parts)


def _unique_list(items: List[str], limit: int = 5) -> List[str]:
    result: List[str] = []
    seen = set()

    for item in items:
        clean = str(item).strip()
        key = normalize(clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(clean)
        if len(result) >= limit:
            break

    return result


def _sanitize_list(value: object, fallback: Optional[List[str]] = None, limit: int = 5) -> List[str]:
    if isinstance(value, list):
        return _unique_list([str(item).strip() for item in value if str(item).strip()], limit=limit)
    return _unique_list(fallback or [], limit=limit)


def _local_reply(
    message: str,
    page: str = "",
    live_services: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, object]:
    intent = detect_intent(message)
    matches = score_services(message)
    live_matches = _score_live_services(message, live_services)
    neighborhood = detect_neighborhood(message)
    urgency = detect_urgency(message)
    accessibility = needs_accessibility(message)

    curated_recommendations = [f"{item.title} — {item.description}" for item in matches]
    live_recommendations = [_format_live_service(item) for item in live_matches]
    recommended_services = _unique_list(curated_recommendations + live_recommendations, limit=4)

    if intent in FAQ and not matches and not live_matches:
        reply = FAQ[intent]
        quick_actions = {
            "anuncio": ["Abrir Anunciar", "Usar IA para copy", "Enviar para moderação"],
            "acessibilidade": ["Abrir Acessibilidade", "Ajustar leitura", "Usar teclado"],
            "contato": ["Abrir Contato", "Solicitar retorno", "Entrar no painel"],
        }.get(intent, ["Abrir Serviços", "Filtrar categoria", "Comparar opções"])
    elif matches or live_matches:
        main_title = matches[0].title if matches else str(live_matches[0].get("name", "Serviço recomendado")).strip()
        location_note = f" em {neighborhood}" if neighborhood else ""
        urgency_note = (
            "Como o pedido parece urgente, confirme disponibilidade e prazo no primeiro contato. "
            if urgency == "alta"
            else ""
        )
        accessibility_note = (
            "Há indícios de necessidade de acessibilidade, então vale priorizar comunicação clara e confirmação por texto. "
            if accessibility
            else ""
        )
        reply = (
            f"O serviço mais aderente ao seu pedido é {main_title}{location_note}. "
            f"{urgency_note}{accessibility_note}"
            f"Você pode começar pela página Serviços e seguir para contato ou publicação da necessidade."
        ).strip()
        quick_actions = ["Abrir Serviços", "Ver categorias", "Ir para Contato"]
    else:
        reply = (
            "Posso orientar você a encontrar um serviço, melhorar um anúncio, entender a navegação da plataforma ou apoiar seu atendimento inicial."
        )
        quick_actions = ["Explorar Serviços", "Publicar Anúncio", "Falar com a Equipe"]

    accessibility_tip = matches[0].accessibility_tip if matches else (FAQ["acessibilidade"] if accessibility else "")

    return {
        "intent": intent,
        "reply": reply,
        "provider": "local",
        "urgency": urgency,
        "neighborhood": neighborhood,
        "page_context": page,
        "recommended_services": recommended_services,
        "accessibility_tip": accessibility_tip,
        "quick_actions": quick_actions,
        "live_services": live_matches,
    }


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _coerce_assistant_result(parsed: Dict[str, Any], local_data: Dict[str, object]) -> Optional[Dict[str, object]]:
    reply = str(parsed.get("reply", "")).strip()
    if not reply:
        return None

    result = dict(local_data)
    result["reply"] = reply
    result["provider"] = "openai"
    result["intent"] = str(parsed.get("intent") or local_data.get("intent") or "geral").strip()
    result["quick_actions"] = _sanitize_list(parsed.get("quick_actions"), fallback=result.get("quick_actions", []), limit=4)
    result["recommended_services"] = _sanitize_list(
        parsed.get("recommended_services"),
        fallback=result.get("recommended_services", []),
        limit=4,
    )
    result["accessibility_tip"] = str(
        parsed.get("accessibility_tip") or local_data.get("accessibility_tip") or ""
    ).strip()

    return result


def _coerce_announcement_result(parsed: Dict[str, Any], local_data: Dict[str, object]) -> Optional[Dict[str, object]]:
    optimized_description = str(parsed.get("optimized_description", "")).strip()
    suggested_title = str(parsed.get("suggested_title", "")).strip()

    if not optimized_description or not suggested_title:
        return None

    result = dict(local_data)
    result.update(
        {
            "suggested_title": suggested_title,
            "optimized_description": optimized_description,
            "accessibility_text": str(
                parsed.get("accessibility_text") or local_data.get("accessibility_text") or ""
            ).strip(),
            "summary": str(parsed.get("summary") or local_data.get("summary") or "").strip(),
            "checklist": _sanitize_list(parsed.get("checklist"), fallback=result.get("checklist", []), limit=6),
            "target_audience": str(parsed.get("target_audience") or local_data.get("target_audience") or "").strip(),
            "trust_signals": _sanitize_list(parsed.get("trust_signals"), fallback=result.get("trust_signals", []), limit=4),
            "cta": str(parsed.get("cta") or local_data.get("cta") or "").strip(),
            "provider": "openai",
        }
    )

    return result


def _openai_reply(
    message: str,
    page: str,
    local_data: Dict[str, object],
    history: Optional[List[Dict[str, str]]] = None,
    live_services: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, object]]:
    client = _get_openai_client()
    if client is None:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    history = history or []

    prompt_payload = {
        "page": page or "desconhecida",
        "message": message,
        "history": history[-6:],
        "local_data": {
            "intent": local_data.get("intent"),
            "urgency": local_data.get("urgency"),
            "neighborhood": local_data.get("neighborhood"),
            "recommended_services": local_data.get("recommended_services", []),
            "quick_actions": local_data.get("quick_actions", []),
            "accessibility_tip": local_data.get("accessibility_tip", ""),
        },
        "live_services": (live_services or [])[:6],
    }

    prompt = (
        "Responda apenas com JSON válido contendo os campos: "
        "reply, quick_actions, recommended_services, intent, accessibility_tip. "
        f"Contexto: {json.dumps(prompt_payload, ensure_ascii=False)}"
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_ASSISTANT_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        content = completion.choices[0].message.content or ""
        parsed = _extract_json_block(content)
        if not parsed:
            return None
        return _coerce_assistant_result(parsed, local_data)
    except Exception:
        return None


def build_reply(
    message: str,
    page: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    live_services: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, object]:
    local_data = _local_reply(message, page, live_services=live_services)
    return _openai_reply(
        message=message,
        page=page,
        local_data=dict(local_data),
        history=history,
        live_services=live_services,
    ) or local_data


def _local_announcement(payload: Dict[str, object]) -> Dict[str, object]:
    name = str(payload.get("name", "")).strip() or "Serviço profissional"
    category = str(payload.get("category", "")).strip() or "Categoria a definir"
    neighborhood = str(payload.get("neighborhood", "")).strip()
    price = str(payload.get("price", "")).strip() or "valor a combinar"
    contact = str(payload.get("contact", "")).strip() or "contato sob consulta"
    description = str(payload.get("description", "")).strip()
    accessibility = str(payload.get("accessibility", "")).strip()

    summary_parts = [f"{name} em {category.lower()}"]
    if neighborhood:
        summary_parts.append(f"atendimento em {neighborhood}")
    summary_parts.append(price)
    summary = ", ".join(summary_parts)

    if not description:
        description = (
            f"Ofereço {name.lower()} com atendimento organizado, comunicação clara e foco em confiança desde o primeiro contato"
        )

    optimized_description = (
        f"{description.rstrip('.')}. "
        f"Atuo com organização, alinhamento prévio de escopo e atenção à experiência do cliente do início ao fim. "
        f"Cada atendimento é conduzido com clareza, previsibilidade e postura profissional para gerar segurança em quem contrata."
    )

    if accessibility:
        accessibility_text = (
            accessibility.rstrip(".")
            + ". Também posso confirmar informações por mensagem, usar linguagem simples e alinhar preferências antes do atendimento."
        )
    else:
        accessibility_text = (
            "Atendimento com linguagem clara, confirmação por mensagem e adaptação do fluxo conforme a necessidade do cliente."
        )

    checklist = [
        "Use um título objetivo com serviço e diferencial.",
        "Informe região de atendimento e formato do serviço.",
        "Deixe claro se o valor é fixo ou sob orçamento.",
        "Explique o canal de contato mais rápido.",
        "Inclua pelo menos um diferencial de confiança ou acessibilidade.",
    ]

    return {
        "suggested_title": f"{name} | Atendimento profissional e confiável",
        "optimized_description": optimized_description,
        "accessibility_text": accessibility_text,
        "summary": summary,
        "checklist": checklist,
        "target_audience": "Pessoas que buscam atendimento confiável, claro e bem apresentado.",
        "trust_signals": [
            "Comunicação objetiva",
            "Alinhamento prévio do escopo",
            "Atendimento profissional",
        ],
        "cta": f"Solicite orçamento e confirme disponibilidade pelo contato informado: {contact}.",
        "contact_hint": contact,
        "category": category,
        "provider": "local",
    }


def _openai_announcement(payload: Dict[str, object], local_data: Dict[str, object]) -> Optional[Dict[str, object]]:
    client = _get_openai_client()
    if client is None:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    prompt = (
        "Você vai reescrever um anúncio para a plataforma ServiAqui. "
        "Responda apenas com JSON válido contendo os campos: "
        "suggested_title, optimized_description, accessibility_text, summary, checklist, target_audience, trust_signals e cta. "
        f"Dados do usuário: {json.dumps(payload, ensure_ascii=False)}. "
        f"Base local sugerida: {json.dumps(local_data, ensure_ascii=False)}."
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_ANNOUNCEMENT_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
        )
        content = completion.choices[0].message.content or ""
        parsed = _extract_json_block(content)
        if not parsed:
            return None
        return _coerce_announcement_result(parsed, local_data)
    except Exception:
        return None


def improve_announcement(payload: Dict[str, object]) -> Dict[str, object]:
    local_data = _local_announcement(payload)
    result = _openai_announcement(payload, dict(local_data)) or local_data
    result["improved_description"] = str(result.get("optimized_description", "")).strip()
    return result