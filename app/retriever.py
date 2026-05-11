
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_CANDIDATES = [
    ROOT / "app" / "data" / "catalog.json",
    ROOT / "catalog_full.json",
    ROOT / "catalog_listings.json",
]

TEST_TYPE_MAP = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "has", "have", "hiring", "i", "in", "is", "it", "job", "need",
    "of", "on", "or", "our", "role", "test", "tests", "the", "their",
    "this", "to", "want", "we", "who", "with", "work", "works",
}

OUT_OF_SCOPE_NAME_MARKERS = (
    " solution",
    " short form",
    " job focused assessment",
)

ALIASES = {
    "backend": {"server", "api", "java", "python", "sql", "database"},
    "business": {"stakeholder", "communication", "collaboration", "competency"},
    "coding": {"programming", "developer", "software", "automata"},
    "collaboration": {"team", "stakeholder", "communication", "interpersonal"},
    "customer": {"service", "support", "contact", "phone"},
    "data": {"analytics", "analysis", "database", "sql", "python"},
    "developer": {"programming", "software", "coding", "technical"},
    "frontend": {"front", "html", "css", "javascript", "react", "angular"},
    "manager": {"leadership", "management", "supervisor"},
    "sales": {"selling", "customer", "service"},
    "stakeholder": {"communication", "collaboration", "business", "competency"},
    "technical": {"knowledge", "skills", "programming", "coding"},
}


def tokenize(text: str) -> List[str]:
    raw = re.findall(r"[a-zA-Z0-9+#.]+", (text or "").lower())
    tokens = []
    for token in raw:
        token = token.strip(".")
        if not token or token in STOP_WORDS:
            continue
        tokens.append(token)
        if token.endswith("s") and len(token) > 4:
            tokens.append(token[:-1])
    return tokens


def expanded_tokens(text: str) -> List[str]:
    tokens = tokenize(text)
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(ALIASES.get(token, ()))
    return expanded


def _catalog_path() -> Path:
    for path in DEFAULT_CATALOG_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No SHL catalog JSON found. Expected catalog_full.json or app/data/catalog.json.")


def _normalize_product(product: Dict) -> Dict:
    item = dict(product)
    item["name"] = (item.get("name") or "").strip()
    item["url"] = (item.get("url") or "").strip()
    item["description"] = (item.get("description") or "").strip()
    item["test_type"] = "".join(dict.fromkeys(item.get("test_type") or "")) or ""
    item["job_levels"] = item.get("job_levels") or []
    item["languages"] = item.get("languages") or []
    return item


def _is_individual_test_solution(product: Dict) -> bool:
    name = f" {product.get('name', '').lower()} "
    if any(marker in name for marker in OUT_OF_SCOPE_NAME_MARKERS):
        return False
    return bool(product.get("name") and product.get("url") and "product-catalog/view" in product.get("url", ""))


class CatalogRetriever:

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = Path(catalog_path) if catalog_path else _catalog_path()
        self.products: List[Dict] = []
        self._docs: List[Counter] = []
        self._name_tokens: List[Set[str]] = []
        self._doc_freq: Counter = Counter()
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            raw_products = json.load(f)

        seen_urls = set()
        for raw in raw_products:
            item = _normalize_product(raw)
            if not _is_individual_test_solution(item):
                continue
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            self.products.append(item)

        for product in self.products:
            labels = " ".join(TEST_TYPE_MAP.get(code, code) for code in product.get("test_type", ""))
            doc_text = " ".join(
                [
                    product.get("name", ""),
                    product.get("description", ""),
                    labels,
                    " ".join(product.get("job_levels") or []),
                    " ".join(product.get("languages") or []),
                ]
            )
            tokens = expanded_tokens(doc_text)
            counts = Counter(tokens)
            self._docs.append(counts)
            self._name_tokens.append(set(expanded_tokens(product.get("name", ""))))
            self._doc_freq.update(counts.keys())

        self._loaded = True

    @property
    def count(self) -> int:
        if not self._loaded:
            self.load()
        return len(self.products)

    def search(
        self,
        query: str,
        top_k: int = 10,
        test_types: Optional[Set[str]] = None,
        job_levels: Optional[Set[str]] = None,
        remote_only: bool = False,
        adaptive_only: bool = False,
        max_duration: Optional[int] = None,
        include_reports: bool = True,
    ) -> List[Dict]:
        if not self._loaded:
            self.load()

        query_tokens = expanded_tokens(query)
        query_counts = Counter(query_tokens)
        if not query_counts:
            return []

        n_docs = max(1, len(self.products))
        scored = []
        query_lower = (query or "").lower()

        for idx, product in enumerate(self.products):
            if test_types and not (set(product.get("test_type", "")) & test_types):
                continue
            if remote_only and not product.get("remote_testing"):
                continue
            if adaptive_only and not product.get("adaptive_irt"):
                continue
            if max_duration and product.get("duration_minutes"):
                if int(product["duration_minutes"]) > max_duration:
                    continue
            if job_levels and product.get("job_levels"):
                product_levels = " ".join(product["job_levels"]).lower()
                if not any(level.lower() in product_levels for level in job_levels):
                    continue
            if not include_reports and "report" in product["name"].lower():
                continue

            score = 0.0
            doc = self._docs[idx]
            name_tokens = self._name_tokens[idx]

            for token, q_count in query_counts.items():
                if token not in doc:
                    continue
                idf = math.log((n_docs + 1) / (1 + self._doc_freq[token])) + 1.0
                weight = 2.6 if token in name_tokens else 1.0
                score += min(q_count, 2) * (1 + math.log(doc[token])) * idf * weight

            name_lower = product["name"].lower()
            if name_lower and name_lower in query_lower:
                score += 30.0
            for phrase in _important_phrases(query_lower):
                if phrase in name_lower:
                    score += 12.0
                elif phrase in product.get("description", "").lower():
                    score += 4.0

            score += _explicit_skill_bonus(query_lower, product)
            score += _type_intent_bonus(query_lower, product)
            score += _duration_bonus(max_duration, product)

            if score > 0:
                result = dict(product)
                result["_score"] = round(score, 4)
                scored.append(result)

        scored.sort(key=lambda p: (-p["_score"], p["name"]))
        return scored[:top_k]

    def get_product_by_name(self, name: str) -> Optional[Dict]:
        if not self._loaded:
            self.load()
        needle = (name or "").strip().lower()
        if not needle:
            return None
        for product in self.products:
            if product["name"].lower() == needle:
                return dict(product)
        for product in self.products:
            hay = product["name"].lower()
            if needle in hay or hay in needle:
                return dict(product)
        return None

    def find_mentions(self, text: str, limit: int = 5) -> List[Dict]:
        if not self._loaded:
            self.load()
        text_lower = (text or "").lower()
        mentions = []

        acronym_map = {
            "gsa": "Global Skills Assessment",
            "opq": "Occupational Personality Questionnaire OPQ32r",
            "opq32": "Occupational Personality Questionnaire OPQ32r",
            "opq32r": "Occupational Personality Questionnaire OPQ32r",
            "mq": "Motivation Questionnaire MQM5",
            "verify g+": "Verify - G+",
            "g+": "Verify - G+",
        }
        for key, name in acronym_map.items():
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text_lower):
                product = self.get_product_by_name(name)
                if product:
                    mentions.append(product)

        for product in self.products:
            name = product["name"].lower()
            if len(name) >= 5 and name in text_lower:
                mentions.append(dict(product))

        seen = set()
        unique = []
        for product in mentions:
            if product["url"] in seen:
                continue
            seen.add(product["url"])
            unique.append(product)
        if unique:
            return unique[:limit]
        return self.search(text, top_k=limit)

    def get_catalog_summary(self) -> str:
        if not self._loaded:
            self.load()
        counts = Counter()
        for product in self.products:
            for code in product.get("test_type", ""):
                counts[TEST_TYPE_MAP.get(code, code)] += 1
        bits = [f"Total individual test solutions indexed: {len(self.products)}"]
        bits.extend(f"{label}: {count}" for label, count in sorted(counts.items()))
        return "; ".join(bits)


def _important_phrases(text: str) -> Iterable[str]:
    phrases = [
        "java", "core java", "java 8", "python", "javascript", "sql",
        "data science", "front end", "frontend", "customer service",
        "sales", "project management", "english", "cognitive", "personality",
        "numerical", "deductive", "inductive", "verbal", "automata",
    ]
    return [phrase for phrase in phrases if phrase in text]


def _type_intent_bonus(query_lower: str, product: Dict) -> float:
    product_types = set(product.get("test_type", ""))
    bonus = 0.0
    type_terms = {
        "K": ("technical", "knowledge", "skills", "programming", "coding"),
        "S": ("simulation", "coding", "hands-on", "practical"),
        "P": ("personality", "behavior", "behaviour", "opq"),
        "A": ("cognitive", "ability", "aptitude", "reasoning", "numerical", "verbal"),
        "C": ("competency", "competencies", "collaboration", "stakeholder"),
        "B": ("situational", "judgement", "judgment", "sjt"),
        "E": ("exercise", "assessment center", "role play"),
        "D": ("development", "360"),
    }
    for code, terms in type_terms.items():
        if code in product_types and any(term in query_lower for term in terms):
            bonus += 5.0
    return bonus


def _duration_bonus(max_duration: Optional[int], product: Dict) -> float:
    duration = product.get("duration_minutes")
    if not max_duration or not duration:
        return 0.0
    diff = max_duration - int(duration)
    if diff < 0:
        return -5.0
    return min(3.0, diff / max(max_duration, 1) * 3.0)


def _explicit_skill_bonus(query_lower: str, product: Dict) -> float:
    skills = (
        "java", "python", "javascript", "sql", "aws", "angular", "react",
        "selenium", "oracle", "c#", ".net", "html", "css",
    )
    name = product.get("name", "").lower()
    description = product.get("description", "").lower()
    product_types = set(product.get("test_type", ""))
    score = 0.0

    for skill in skills:
        if not re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", query_lower):
            continue
        in_name = re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", name)
        in_description = re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", description)
        if in_name:
            score += 35.0
        elif in_description:
            score += 10.0
        elif product_types & {"K", "S"}:
            score -= 120.0
    return score


_retriever: Optional[CatalogRetriever] = None


def get_retriever() -> CatalogRetriever:
    global _retriever
    if _retriever is None:
        _retriever = CatalogRetriever()
        _retriever.load()
    return _retriever
