"""Gateway HTTP para comandos autorizados do Tasker.

Assinatura:
  HMAC-SHA256(secret, f"{timestamp}.{nonce}." + body_bytes)

Headers:
  X-Atena-Timestamp: Unix timestamp em segundos
  X-Atena-Nonce: identificador único da requisição
  X-Atena-Signature: hex digest HMAC-SHA256

O gateway não executa comandos Android arbitrários. Ele somente aceita a
whitelist e devolve uma intenção estruturada para o chamador encaminhar à
Atena/Telegram.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from core.google_sheets_audit import GoogleSheetsAudit, GoogleSheetsNotConfigured

ALLOWED_COMMANDS = {
    "consultar bateria",
    "abrir spotify",
    "pausar mídia",
    "agenda",
    "status atena",
}
MAX_SKEW_SECONDS = int(os.getenv("ATENA_TASKER_MAX_SKEW_SECONDS", "90"))
NONCE_TTL_SECONDS = int(os.getenv("ATENA_TASKER_NONCE_TTL_SECONDS", "300"))
DB_PATH = Path(os.getenv("ATENA_TASKER_GATEWAY_DB", "atena_evolution/tasker_gateway.sqlite3"))

app = FastAPI(title="Atena Tasker Command Gateway", version="1.0")


class TaskerCommand(BaseModel):
    command: str = Field(min_length=1, max_length=120)
    device_id: str = Field(min_length=1, max_length=120)
    timestamp: int | None = None
    nonce: str | None = Field(default=None, min_length=8, max_length=160)


def _secret() -> bytes:
    value = os.getenv("ATENA_TASKER_HMAC_SECRET", "")
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="gateway HMAC não configurado")
    return value.encode("utf-8")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS used_nonces (nonce TEXT PRIMARY KEY, used_at INTEGER NOT NULL)"
    )
    connection.commit()
    return connection


def _clean_nonces(connection: sqlite3.Connection, now: int) -> None:
    connection.execute("DELETE FROM used_nonces WHERE used_at < ?", (now - NONCE_TTL_SECONDS,))


def _verify_signature(raw_body: bytes, timestamp: str, nonce: str, signature: str) -> None:
    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="timestamp inválido") from exc
    if abs(int(time.time()) - timestamp_int) > MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="timestamp expirado")
    if not nonce or len(nonce) < 8:
        raise HTTPException(status_code=401, detail="nonce ausente ou curto")
    signed = f"{timestamp}.{nonce}.".encode("utf-8") + raw_body
    expected = hmac.new(_secret(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise HTTPException(status_code=401, detail="assinatura inválida")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "atena-tasker-gateway"}


def _audit_command(command: str, device_id: str, accepted: bool, details: str = "") -> None:
    if os.getenv("ATENA_AUDIT_SHEETS_ENABLED", "0").lower() not in {"1", "true", "yes"}:
        return
    try:
        GoogleSheetsAudit().append_command(
            command=command,
            device_id=device_id,
            accepted=accepted,
            source="tasker",
            details=details,
        )
    except (GoogleSheetsNotConfigured, Exception):
        # Auditoria nunca deve fazer o comando autorizado falhar; registrar em log
        # em produção para reprocessamento posterior.
        return


@app.post("/v1/tasker/commands")
async def receive_tasker_command(
    request: Request,
    background_tasks: BackgroundTasks,
    x_atena_timestamp: str | None = Header(default=None),
    x_atena_nonce: str | None = Header(default=None),
    x_atena_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    raw_body = await request.body()
    _verify_signature(raw_body, x_atena_timestamp or "", x_atena_nonce or "", x_atena_signature or "")
    try:
        payload = TaskerCommand.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="payload JSON inválido") from exc
    command = " ".join(payload.command.lower().split())
    if command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=403, detail="comando não autorizado")
    now = int(time.time())
    connection = _db()
    try:
        _clean_nonces(connection, now)
        try:
            connection.execute("INSERT INTO used_nonces(nonce, used_at) VALUES (?, ?)", (x_atena_nonce, now))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="nonce já utilizado") from exc
        connection.commit()
    finally:
        connection.close()
    background_tasks.add_task(_audit_command, command, payload.device_id, True)
    return {
        "accepted": True,
        "intent": "device_command",
        "command": command,
        "device_id": payload.device_id,
        "source": "tasker",
        "received_at": now,
    }


def sign_tasker_payload(payload: dict[str, Any], secret: str, timestamp: int, nonce: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    message = f"{timestamp}.{nonce}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
