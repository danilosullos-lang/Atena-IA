#!/usr/bin/env python3
"""Detecta promoções gratuitas da Steam, confirma na Store e notifica o Telegram."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Atena-IA Steam free-game monitor/1.0"
STEAMDB_URL = "https://steamdb.info/upcoming/free/"
STORE_URL = "https://store.steampowered.com/app/{app_id}/?l=english"


@dataclass
class Promotion:
    app_id: str
    title: str
    store_url: str
    source_url: str
    promotion_type: str
    expires_at: str | None
    description: str

    @property
    def key(self) -> str:
        raw = f"{self.app_id}:{self.promotion_type}:{self.expires_at or 'permanent'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_get(url: str, timeout: int = 30) -> requests.Response:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response


def discover_candidates() -> list[dict]:
    """Descoberta externa; a Store será a fonte final de confirmação."""
    response = http_get(STEAMDB_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    result: list[dict] = []
    for link in soup.select("a[href*='/app/']"):
        href = urljoin(STEAMDB_URL, link.get("href", ""))
        match = re.search(r"/app/(\d+)", href)
        if not match:
            continue
        app_id = match.group(1)
        title = link.get_text(" ", strip=True)
        if not title:
            title = f"App {app_id}"
        item = {"app_id": app_id, "title": title, "source_url": href}
        if item not in result:
            result.append(item)
    return result


def confirm_store(app_id: str, fallback_title: str, source_url: str) -> Promotion | None:
    """Confirma preço/estado na Steam Store; não confia apenas na descoberta."""
    store_url = STORE_URL.format(app_id=app_id)
    details = http_get(
        f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=br&l=portuguese",
    ).json()
    app = details.get(str(app_id), {})
    data = app.get("data", {}) if app.get("success") else {}
    title = str(data.get("name") or fallback_title)
    html = http_get(store_url).text.lower()
    plain = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    is_free = bool(data.get("is_free"))
    price = data.get("price_overview") or {}
    final_price = price.get("final")
    free_markers = ("free to keep", "gratuito para manter", "free weekend", "fim de semana grátis")
    temporary_markers = ("free weekend", "fim de semana grátis", "free to play this weekend")

    # Jogos permanentemente gratuitos só entram se explicitamente habilitados.
    if is_free:
        if os.getenv("ATENA_NOTIFY_PERMANENT_FREE", "0") != "1":
            return None
        return Promotion(app_id, title, store_url, source_url, "free_to_play", None, "Jogo permanentemente gratuito.")

    has_temporary_marker = any(marker in html or marker in plain for marker in temporary_markers)
    has_free_marker = any(marker in html or marker in plain for marker in free_markers)
    if final_price not in (0, "0", None) and not has_free_marker:
        return None
    if not has_free_marker and not has_temporary_marker:
        return None

    promotion_type = "free_weekend" if has_temporary_marker else "free_to_keep"
    description = (
        "Acesso gratuito temporário; pode deixar de funcionar após o prazo."
        if promotion_type == "free_weekend"
        else "Promoção confirmada na página oficial da Steam."
    )
    return Promotion(app_id, title, store_url, source_url, promotion_type, None, description)


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS steam_alerts (
            promotion_key TEXT PRIMARY KEY,
            app_id TEXT NOT NULL,
            title TEXT NOT NULL,
            promotion_type TEXT NOT NULL,
            store_url TEXT NOT NULL,
            source_url TEXT NOT NULL,
            expires_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_notified_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    db.commit()


def unseen(db: sqlite3.Connection, promotion: Promotion) -> bool:
    return db.execute(
        "SELECT 1 FROM steam_alerts WHERE promotion_key = ?", (promotion.key,)
    ).fetchone() is None


def mark_notified(db: sqlite3.Connection, promotion: Promotion) -> None:
    timestamp = now()
    db.execute("""
        INSERT INTO steam_alerts
        (promotion_key, app_id, title, promotion_type, store_url, source_url,
         expires_at, first_seen_at, last_notified_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'notified')
    """, (
        promotion.key, promotion.app_id, promotion.title, promotion.promotion_type,
        promotion.store_url, promotion.source_url, promotion.expires_at,
        timestamp, timestamp,
    ))


def telegram_send(token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "false"},
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("description", "Telegram recusou a mensagem"))


def format_message(promotion: Promotion) -> str:
    label = {
        "free_to_keep": "Gratuito para resgatar",
        "free_weekend": "Free Weekend — acesso temporário",
        "free_to_play": "Free-to-play permanente",
    }[promotion.promotion_type]
    return (
        "ATENA — jogo gratuito confirmado na Steam\n\n"
        f"Título: {promotion.title}\n"
        f"Tipo: {label}\n"
        f"{promotion.description}\n\n"
        f"Steam: {promotion.store_url}\n"
        f"Fonte da descoberta: {promotion.source_url}"
    )


def run(db_path: Path, dry_run: bool = False) -> dict:
    token = os.getenv("ATENA_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("ATENA_TELEGRAM_CHAT_ID", "").strip()
    if not dry_run and (not token or not chat_id):
        raise RuntimeError("ATENA_TELEGRAM_BOT_TOKEN e ATENA_TELEGRAM_CHAT_ID são obrigatórios")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    ensure_schema(db)
    discovered = discover_candidates()
    checked = 0
    sent = 0
    errors: list[str] = []
    try:
        for candidate in discovered:
            try:
                promotion = confirm_store(candidate["app_id"], candidate["title"], candidate["source_url"])
                checked += 1
                if promotion is None or not unseen(db, promotion):
                    continue
                message = format_message(promotion)
                if dry_run:
                    print(message + "\n")
                else:
                    telegram_send(token, chat_id, message)
                mark_notified(db, promotion)
                sent += 1
            except Exception as exc:
                errors.append(f"{candidate.get('app_id')}: {type(exc).__name__}: {exc}")
        db.commit()
    finally:
        db.close()
    return {"discovered": len(discovered), "checked": checked, "sent": sent, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(os.getenv("ATENA_MEMORY_DB", "atena_evolution/memory.sqlite3")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = run(args.db, args.dry_run)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
