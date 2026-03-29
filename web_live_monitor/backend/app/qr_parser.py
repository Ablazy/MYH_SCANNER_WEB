from __future__ import annotations

import re

GAME_CODE_MAP = {
    "8F3": "Honkai Impact 3rd",
    "9E&": "Genshin Impact",
    "8F%": "Honkai: Star Rail",
    "%BA": "Zenless Zone Zero",
}

TICKET_REGEX = re.compile(r"^[A-Za-z0-9_-]{24}$")


def parse_qr_payload(payload: str) -> dict[str, str | None]:
    text = payload.strip()
    game_code: str | None = None
    game_name: str | None = None
    ticket: str | None = None

    if len(text) >= 82:
        candidate_code = text[79:82]
        if candidate_code in GAME_CODE_MAP:
            game_code = candidate_code
            game_name = GAME_CODE_MAP[candidate_code]

    if len(text) >= 24:
        candidate_ticket = text[-24:]
        if TICKET_REGEX.fullmatch(candidate_ticket):
            ticket = candidate_ticket

    return {
        "raw_text": text,
        "game_code": game_code,
        "game_name": game_name,
        "ticket": ticket,
    }
