"""Crisis detection and redaction before anything reaches a language model."""

from __future__ import annotations

import re

# Strong signals: stop the finance flow and show local help.
CRISIS_PHRASES = (
    "kill myself", "end my life", "suicide", "suicidal", "want to die", "don't want to live", "dont want to live",
    "no reason to live", "hurt myself", "self-harm", "self harm", "end it all",
    "想死", "自杀", "不想活", "活不下去", "轻生", "自残", "伤害自己", "结束生命",
    "umbringen", "selbstmord", "nicht mehr leben", "mir etwas antun",
)
# Softer distress: keep helping, add a gentle line and the helpline.
DISTRESS_PHRASES = ("hopeless", "can't cope", "cant cope", "falling apart", "崩溃", "绝望", "撑不住", "hoffnungslos")

HELP = {
    "CN": {"en": "China: 12356 (national mental health hotline). In an emergency call 120 or 110.",
           "zh": "中国：12356（全国心理援助热线）。紧急情况请拨打 120 或 110。"},
    "DE": {"en": "Germany: TelefonSeelsorge 0800 111 0 111 (free, 24/7). In an emergency call 112.",
           "zh": "德国：TelefonSeelsorge 0800 111 0 111（免费，24 小时）。紧急情况请拨打 112。"},
    "EU": {"en": "EU: call 112 in an emergency, or your national helpline.",
           "zh": "欧盟：紧急情况请拨打 112，或联系当地心理援助热线。"},
}


def check_message(text: str) -> str:
    """Return 'crisis', 'distress' or 'ok'."""
    t = text.lower()
    if any(p in t for p in CRISIS_PHRASES):
        return "crisis"
    if any(p in t for p in DISTRESS_PHRASES):
        return "distress"
    return "ok"


def crisis_reply(region: str, lang: str) -> str:
    regions = ["CN", "DE"] if region == "CN" else ["DE", "EU"] if region in ("EU", "DE") else ["CN", "DE", "EU"]
    lines = "\n".join(f"- {HELP[r][lang]}" for r in regions)
    if lang == "zh":
        return ("谢谢你告诉我。听起来你现在很不好受，这比任何账单都重要。我先把理财的事放一放。\n\n"
                "请现在就联系能陪你说话的人：\n" + lines +
                "\n\n如果可以，也告诉一个你信任的人你现在的感受。你不需要一个人扛着。")
    return ("Thank you for telling me. It sounds like things are really hard right now, and that matters more than "
            "any bill. I'm pausing the money stuff.\n\nPlease reach out to someone who can talk with you now:\n" + lines +
            "\n\nIf you can, also let someone you trust know how you're feeling. You don't have to carry this alone.")


def distress_line(region: str, lang: str) -> str:
    key = "CN" if region == "CN" else "DE"
    if lang == "zh":
        return f"\n\n（如果压力让你喘不过气，可以随时联系：{HELP[key]['zh']}）"
    return f"\n\n(If the pressure gets too much, you can always talk to someone: {HELP[key]['en']})"


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_NUM = re.compile(r"\d{8,}")
_PHONE = re.compile(r"\+\d[\d\s-]{8,}\d")


class Redactor:
    """Masks personal data before text goes to a model.

    Long numbers (order, account, phone numbers) become reversible tokens like <ref3>, so the model can
    still point at a transaction and we swap the real value back into tool arguments. Emails, phone
    numbers with a country code and known names are masked one way.
    """

    def __init__(self, names: list[str] | None = None):
        self.names = [n for n in (names or []) if n]
        self._to_token: dict[str, str] = {}
        self._to_value: dict[str, str] = {}

    def _token(self, match: re.Match) -> str:
        value = match.group(0)
        if value not in self._to_token:
            token = f"<ref{len(self._to_token) + 1}>"
            self._to_token[value] = token
            self._to_value[token] = value
        return self._to_token[value]

    def redact(self, text: str) -> str:
        out = _EMAIL.sub("[email]", text)
        out = _PHONE.sub("[phone]", out)
        out = _LONG_NUM.sub(self._token, out)
        for n in self.names:
            out = out.replace(n, "[name]")
        return out

    def restore(self, value):
        if isinstance(value, str):
            for token, real in self._to_value.items():
                value = value.replace(token, real)
            return value
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        return value


def redact(text: str, names: list[str] | None = None) -> str:
    """One-way convenience version."""
    return Redactor(names).redact(text)
