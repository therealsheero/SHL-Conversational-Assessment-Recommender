import re
from typing import Dict, Iterable, List, Optional, Set

from app.models import ChatMessage, ChatResponse, Recommendation
from app.retriever import TEST_TYPE_MAP, get_retriever


VAGUE_TERMS = {
    "a", "an", "any", "assessment", "assessments", "candidate", "employee",
    "hire", "hiring", "i", "need", "recommend", "recommendation", "role",
    "someone", "test", "tests",
}

OFF_TOPIC_PATTERNS = (
    r"\blegal\b|\blawyer\b|\bcompliance advice\b|\bnyc law\b",
    r"\bsalary\b|\bcompensation\b|\boffer letter\b|\bpay\b",
    r"\binterview questions\b|\bhow should i interview\b",
    r"\bwrite (a )?job description\b|\bjob posting\b",
    r"\bignore (all )?(previous|prior) instructions\b|\bdeveloper message\b|\bsystem prompt\b",
    r"\bprompt injection\b|\bjailbreak\b",
)

REFINE_PATTERNS = (
    "actually", "instead", "add", "remove", "replace", "include", "exclude",
    "change", "also", "only", "prefer", "without", "with personality",
)

ACK_PATTERNS = (
    r"^(thanks|thank you|looks good|great|perfect|done|that works|good enough)[.! ]*$",
)

JOB_LEVELS = {
    "entry": {"Entry-Level", "Graduate", "General Population"},
    "junior": {"Entry-Level", "Graduate", "General Population"},
    "graduate": {"Graduate", "Entry-Level"},
    "mid": {"Mid-Professional", "Professional Individual Contributor"},
    "middle": {"Mid-Professional", "Professional Individual Contributor"},
    "senior": {"Senior", "Director", "Manager", "Professional Individual Contributor"},
    "lead": {"Manager", "Front Line Manager", "Senior"},
    "manager": {"Manager", "Front Line Manager", "Supervisor"},
    "executive": {"Executive", "Director"},
    "director": {"Director", "Executive"},
}

TYPE_REQUESTS = {
    "technical": {"K", "S"},
    "knowledge": {"K"},
    "skill": {"K", "S"},
    "skills": {"K", "S"},
    "coding": {"K", "S"},
    "programming": {"K", "S"},
    "simulation": {"S"},
    "personality": {"P"},
    "behavior": {"P", "B"},
    "behaviour": {"P", "B"},
    "opq": {"P"},
    "cognitive": {"A"},
    "ability": {"A"},
    "aptitude": {"A"},
    "reasoning": {"A"},
    "numerical": {"A"},
    "verbal": {"A"},
    "deductive": {"A"},
    "inductive": {"A"},
    "situational": {"B"},
    "judgement": {"B"},
    "judgment": {"B"},
    "sjt": {"B"},
    "competency": {"C"},
    "competencies": {"C"},
    "stakeholder": {"C", "P"},
    "collaboration": {"C", "P"},
    "communication": {"C", "P"},
    "exercise": {"E"},
    "360": {"D"},
    "development": {"D"},
}

ROLE_HINTS = {
    "developer", "engineer", "programmer", "analyst", "manager", "sales",
    "support", "service", "consultant", "administrator", "accountant",
    "designer", "architect", "tester", "qa", "leader", "graduate",
    "intern", "java", "python", "sql", "javascript", "data", "frontend",
    "backend", "full stack", "call center", "customer",
}


def _latest_user(messages: List[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content or ""
    return ""


def _user_text(messages: List[ChatMessage]) -> str:
    return " ".join(message.content for message in messages if message.role == "user")


def _assistant_text(messages: List[ChatMessage]) -> str:
    return " ".join(message.content for message in messages if message.role == "assistant")


def _is_acknowledgement(text: str) -> bool:
    cleaned = text.strip().lower()
    return any(re.match(pattern, cleaned) for pattern in ACK_PATTERNS)


def _is_off_topic(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in OFF_TOPIC_PATTERNS)


def _is_compare(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ("compare", "difference", "different", " vs ", " versus ", "between"))


def _is_refinement(text: str, messages: List[ChatMessage]) -> bool:
    if not _assistant_text(messages):
        return False
    lower = text.lower()
    return any(pattern in lower for pattern in REFINE_PATTERNS)


def _extract_max_duration(text: str) -> Optional[int]:
    lower = text.lower()
    patterns = [
        r"(?:under|within|less than|up to|maximum|max|<=|no more than)\s*(\d{1,3})\s*(?:minutes|minute|min|mins)",
        r"(\d{1,3})\s*(?:minutes|minute|min|mins)\s*(?:or less|max|maximum)",
        r"completed in\s*(\d{1,3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            return int(match.group(1))
    return None


def _extract_job_levels(text: str) -> Optional[Set[str]]:
    lower = text.lower()
    levels: Set[str] = set()
    for key, mapped in JOB_LEVELS.items():
        if re.search(rf"\b{re.escape(key)}[- ]?(level)?\b", lower):
            levels.update(mapped)
    years = re.search(r"\b(\d{1,2})\+?\s*(?:years|yrs|yoe)\b", lower)
    if years:
        value = int(years.group(1))
        if value <= 2:
            levels.update(JOB_LEVELS["entry"])
        elif value <= 6:
            levels.update(JOB_LEVELS["mid"])
        else:
            levels.update(JOB_LEVELS["senior"])
    return levels or None


def _extract_type_requests(text: str) -> Set[str]:
    lower = text.lower()
    requested: Set[str] = set()
    for term, codes in TYPE_REQUESTS.items():
        if re.search(rf"\b{re.escape(term)}\b", lower):
            requested.update(codes)
    return requested


def _infer_role_types(text: str) -> Set[str]:
    lower = text.lower()
    inferred: Set[str] = set()
    if any(term in lower for term in ("developer", "engineer", "programmer", "software", "java", "python", "sql", "javascript", "coding")):
        inferred.update({"K", "S"})
    if any(term in lower for term in ("stakeholder", "collaboration", "communicat", "team")):
        inferred.update({"C", "P"})
    if any(term in lower for term in ("manager", "lead", "supervisor", "executive")):
        inferred.update({"P", "A", "C"})
    return inferred


def _has_role_or_skill(text: str) -> bool:
    lower = text.lower()
    return any(hint in lower for hint in ROLE_HINTS)


def _too_vague(messages: List[ChatMessage]) -> bool:
    text = _user_text(messages)
    tokens = set(re.findall(r"[a-zA-Z0-9+#.]+", text.lower()))
    meaningful = tokens - VAGUE_TERMS
    if len(meaningful) <= 1 and not _has_role_or_skill(text):
        return True

    latest = _latest_user(messages)
    first_user_turn = sum(1 for message in messages if message.role == "user") <= 1
    has_role = _has_role_or_skill(text)
    has_level = bool(_extract_job_levels(text))
    explicit_type_terms = (
        "technical", "personality", "cognitive", "ability", "aptitude",
        "reasoning", "simulation", "coding", "programming", "situational",
        "competency", "competencies", "360", "development",
    )
    has_type = any(term in text.lower() for term in explicit_type_terms)
    has_duration = bool(_extract_max_duration(text))
    looks_like_jd = len(latest.split()) >= 18

    if first_user_turn and has_role and not looks_like_jd and not (has_level or has_type or has_duration):
        return True
    return False


def _type_label(codes: str) -> str:
    labels = [TEST_TYPE_MAP.get(code, code) for code in (codes or "")]
    return ", ".join(labels) if labels else "catalog assessment"


def _to_recommendation(product: Dict) -> Recommendation:
    return Recommendation(
        name=product["name"],
        url=product["url"],
        test_type=product.get("test_type") or "",
    )


def _diversify(candidates: List[Dict], desired_types: Set[str], limit: int = 10) -> List[Dict]:
    selected: List[Dict] = []
    seen = set()
    for product in candidates:
        if product["url"] in seen:
            continue
        selected.append(product)
        seen.add(product["url"])
        if len(selected) >= limit:
            break

    ordered_types = [code for code in ("P", "C", "A", "S", "K", "B", "D", "E") if code in desired_types]
    for code in ordered_types:
        if any(code in product.get("test_type", "") for product in selected):
            continue
        replacement = next(
            (product for product in candidates if product["url"] not in seen and code in product.get("test_type", "")),
            None,
        )
        if not replacement:
            continue
        if len(selected) < limit:
            selected.append(replacement)
        else:
            coverage = {
                desired: sum(1 for product in selected if desired in product.get("test_type", ""))
                for desired in desired_types
            }
            replace_at = len(selected) - 1
            for idx in range(len(selected) - 1, -1, -1):
                product_codes = set(selected[idx].get("test_type", "")) & desired_types
                if "K" in product_codes and coverage.get("K", 0) > 1:
                    replace_at = idx
                    break
            else:
                for idx in range(len(selected) - 1, -1, -1):
                    product_codes = set(selected[idx].get("test_type", "")) & desired_types
                    if product_codes and all(coverage[existing] > 1 for existing in product_codes):
                        replace_at = idx
                        break
            selected[replace_at] = replacement
        seen.add(replacement["url"])

    return selected[:limit]


def _comparison_reply(products: List[Dict]) -> str:
    if len(products) < 2:
        return (
            "I can compare SHL assessments when I can identify at least two catalog items. "
            "Please name the assessments, for example OPQ32r and Global Skills Assessment."
        )

    lines = ["Here is the catalog-grounded difference:"]
    for product in products[:4]:
        duration = product.get("duration_minutes")
        duration_text = f"{duration} minutes" if duration else "duration not listed in the catalog data"
        levels = ", ".join(product.get("job_levels") or []) or "job levels not listed"
        desc = product.get("description") or "No description is listed in the catalog data."
        if len(desc) > 260:
            desc = desc[:257].rstrip() + "..."
        lines.append(
            f"{product['name']}: {_type_label(product.get('test_type', ''))}; "
            f"{duration_text}; {levels}. {desc}"
        )
    return "\n".join(lines)


def _clarification_reply(messages: List[ChatMessage]) -> str:
    text = _user_text(messages).lower()
    if not _has_role_or_skill(text):
        return (
            "I can help, but I need the hiring target first. What role are you hiring for, "
            "and what should the assessment measure?"
        )
    if not _extract_job_levels(text):
        return (
            "Got it. What seniority level is this for, and do you want to prioritize "
            "technical skills, personality/behavior, cognitive ability, or a mix?"
        )
    return (
        "What should the shortlist prioritize: technical skills, personality/behavior, "
        "cognitive ability, simulations, or a mix?"
    )


def _build_query(messages: List[ChatMessage]) -> str:
    user_context = _user_text(messages)
    latest = _latest_user(messages)
    return f"{user_context} {latest}"


def _recommend(messages: List[ChatMessage]) -> ChatResponse:
    retriever = get_retriever()
    query = _build_query(messages)
    latest = _latest_user(messages)
    all_user_text = _user_text(messages)
    lower = all_user_text.lower()

    max_duration = _extract_max_duration(all_user_text)
    job_levels = _extract_job_levels(all_user_text)
    requested_types = _extract_type_requests(all_user_text) | _infer_role_types(all_user_text)

    removed_types: Set[str] = set()
    if "remove personality" in lower or "without personality" in lower or "no personality" in lower:
        removed_types.add("P")
    if "remove coding" in lower or "without coding" in lower or "no coding" in lower:
        removed_types.update({"K", "S"})

    search_types = None if not requested_types or len(requested_types) > 2 else requested_types
    candidates = retriever.search(
        query=query,
        top_k=40,
        test_types=search_types,
        job_levels=job_levels,
        max_duration=max_duration,
        include_reports=True,
    )
    if len(candidates) < 8:
        extra = retriever.search(query=query, top_k=40, job_levels=job_levels, max_duration=max_duration)
        seen = {p["url"] for p in candidates}
        candidates.extend(p for p in extra if p["url"] not in seen)

    if removed_types:
        candidates = [p for p in candidates if not (set(p.get("test_type", "")) & removed_types)]

    if requested_types:
        shortlist = _diversify(candidates, requested_types, limit=10)
    else:
        shortlist = candidates[:10]

    recommendations = [_to_recommendation(product) for product in shortlist[:10]]

    if not recommendations:
        return ChatResponse(
            reply=(
                "I could not find a grounded SHL catalog match for those constraints. "
                "Could you relax the duration or tell me the role and skills another way?"
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    count = len(recommendations)
    type_hint = ""
    if requested_types:
        labels = sorted({TEST_TYPE_MAP.get(code, code) for code in requested_types})
        type_hint = f" I included {', '.join(labels)} coverage."
    duration_hint = f" I respected the {max_duration}-minute limit where catalog durations were listed." if max_duration else ""
    action = "updated" if _is_refinement(latest, messages) else "found"
    reply = (
        f"I {action} a grounded shortlist of {count} SHL assessment"
        f"{'' if count == 1 else 's'} from the catalog for your requirements."
        f"{type_hint}{duration_hint}"
    )

    return ChatResponse(reply=reply, recommendations=recommendations, end_of_conversation=False)


def handle_chat(messages: List[ChatMessage]) -> ChatResponse:
    """Main stateless endpoint handler."""
    if not messages:
        return ChatResponse(
            reply="What role are you hiring for, and what do you want the assessment to measure?",
            recommendations=[],
            end_of_conversation=False,
        )

    latest = _latest_user(messages)
    if _is_acknowledgement(latest):
        return ChatResponse(
            reply="Glad that helped. I'll stop here.",
            recommendations=[],
            end_of_conversation=True,
        )

    if _is_off_topic(latest):
        return ChatResponse(
            reply=(
                "I can only help with selecting and comparing SHL assessments from the catalog. "
                "Tell me the role, seniority, and skills you want to assess, and I'll shortlist suitable SHL products."
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    retriever = get_retriever()

    if _is_compare(latest):
        products = retriever.find_mentions(latest, limit=4)
        return ChatResponse(
            reply=_comparison_reply(products),
            recommendations=[],
            end_of_conversation=False,
        )

    turn_count = len(messages)
    if _too_vague(messages) and turn_count < 5:
        return ChatResponse(
            reply=_clarification_reply(messages),
            recommendations=[],
            end_of_conversation=False,
        )

    return _recommend(messages)
