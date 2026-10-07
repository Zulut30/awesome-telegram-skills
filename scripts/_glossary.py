"""One-line explanations of terms that skills use without defining them.

A reference file that mentions a term carries a «Термины:» line before the first mention,
built from these explanations; SKILL.md explains the term right where it first appears.
Each file stays standalone: the explanation travels with the text, not in an external glossary.
"""
from __future__ import annotations

import re

# term -> (pattern that finds a mention in prose, one-line explanation)
TERMS: dict[str, tuple[str, str]] = {
    'ACK': (r'\bACK\b', 'ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; '
                        'это не сообщение об успехе операции'),
    'CAS': (r'\bCAS\b', 'сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения'),
    'квитанция': (r'\breceipts?\b|[Кк]витанци', 'квитанция (receipt) — сохраненная запись о выполненной операции; '
                                              'повтор возвращает ее вместо второго эффекта'),
    'outbox': (r'\boutbox\b', 'события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик '
                              'выполняет их позже'),
    'неизвестный результат': (r'[Нн]еизвестн\w* (?:результат|исход)|\bunknown outcome\b',
                              'запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую '
                              'нельзя, сначала сверка'),
    'сверка': (r'(?<![А-Яа-яЁё])[Сс]верк[аеиуо]\w*|\breconcil\w*',
               'запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей'),
    'entitlement': (r'\bentitlement\b', 'право на возможность (custom emoji, оплаченный доступ), которое проверяется '
                                        'отдельно от самого запроса'),
    'fallback': (r'\bfallback\b', 'запасной вариант, если основная возможность недоступна'),
}
LINE_PREFIX = 'Термины: '


def prose(text: str) -> str:
    """Text a reader sees as words: no code blocks or inline code."""
    text = re.sub(r'^```.*?^```', lambda m: ' ' * len(m.group(0)), text, flags=re.S | re.M)
    return re.sub(r'`[^`\n]+`', lambda m: ' ' * len(m.group(0)), text)


def used_terms(text: str) -> list[str]:
    """Terms a text mentions, plus terms their explanations mention, in glossary order."""
    found = {term for term, (pattern, _) in TERMS.items() if re.search(pattern, prose(text))}
    while True:
        more = {other for term in found for other, (pattern, _) in TERMS.items()
                if other not in found and re.search(pattern, TERMS[term][1])}
        if not more:
            return [term for term in TERMS if term in found]
        found |= more


def with_terms_line(text: str) -> str:
    """Put (or refresh) the «Термины:» line after the title and its availability label."""
    text = re.sub('^' + re.escape(LINE_PREFIX) + '.*\n\n?', '', text, flags=re.M)
    terms = used_terms(text)
    if not terms:
        return text
    title = re.search(r'^# .*\n\n(?:Доступно с .*\n\n)?', text, re.M)
    at = title.end() if title else 0
    return text[:at] + terms_line(terms) + '\n\n' + text[at:]


def terms_line(terms: list[str]) -> str:
    parts = []
    for term in terms:
        explanation = TERMS[term][1]
        parts.append(explanation if term == 'квитанция' else f'**{term}** — {explanation}')
    return LINE_PREFIX + '; '.join(parts) + '.'


def first_mention(text: str, term: str) -> re.Match | None:
    return re.search(TERMS[term][0], prose(text))


def explained(text: str, term: str) -> bool:
    """Defined by a «Термины:» line before the first mention, or right after it in parentheses or a dash."""
    match = first_mention(text, term)
    if match is None:
        return True
    for line in re.finditer('^' + re.escape(LINE_PREFIX) + '.*$', text, re.M):
        if line.start() <= match.start() and TERMS[term][1] in line.group(0):
            return True
    return re.match(r'\w*\s*(?:\(|—|–)', text[match.end():match.end() + 8]) is not None
