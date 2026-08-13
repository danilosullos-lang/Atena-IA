#!/usr/bin/env python3
"""Ponte Telegram ↔ Atena/Ollama para conversas autorizadas."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import aiohttp

from core.audio_gateway import AudioGateway, AudioGatewayError
from core.memory_store import MemoryStore

ROOT = Path(os.getenv("ATENA_ROOT", Path(__file__).resolve().parents[1]))
MEMORY_DB = Path(os.getenv("ATENA_MEMORY_DB", str(ROOT / "atena_evolution" / "memory.sqlite3")))
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
OLLAMA_CHAT = os.getenv("ATENA_OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct")
SESSION_PATH = Path(os.getenv("ATENA_TELEGRAM_SESSION_PATH", str(ROOT / "data" / "telegram_sessions.json")))
VOICE_SETTINGS_PATH = Path(os.getenv("ATENA_TELEGRAM_VOICE_SETTINGS_PATH", str(ROOT / "data" / "telegram_voice_settings.json")))
MAX_HISTORY = 12
MAX_MESSAGE = 3900

logging.basicConfig(level=os.getenv("ATENA_TELEGRAM_LOG_LEVEL", "INFO"))
log = logging.getLogger("atena.telegram")


class TelegramError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise TelegramError(f"variável ausente: {name}")
    return value


def allowed_chat(chat_id: int, configured: str) -> bool:
    return str(chat_id) in {item.strip() for item in configured.split(",") if item.strip()}


def clip(text: str, limit: int = MAX_MESSAGE) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_sessions() -> dict[str, list[dict[str, str]]]:
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_sessions(sessions: dict[str, list[dict[str, str]]]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(sessions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_voice_settings() -> set[str]:
    try:
        data = json.loads(VOICE_SETTINGS_PATH.read_text(encoding="utf-8"))
        return {str(item) for item in data if str(item).strip()} if isinstance(data, list) else set()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()


def save_voice_settings(enabled: set[str]) -> None:
    VOICE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_SETTINGS_PATH.write_text(json.dumps(sorted(enabled), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AtenaTelegramChat:
    def __init__(self, token: str, chat_allowlist: str, model: str = MODEL) -> None:
        self.token = token
        self.chat_allowlist = chat_allowlist
        self.model = model
        self.sessions = load_sessions()
        self.voice_enabled = load_voice_settings()
        self.audio = AudioGateway()
        self.offset = 0
        self.http: aiohttp.ClientSession | None = None

    async def api(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        assert self.http is not None
        url = TELEGRAM_API.format(token=self.token, method=method)
        for attempt in range(3):
            try:
                async with self.http.post(url, json=payload or {}) as response:
                    body = await response.json(content_type=None)
                    if response.status != 200 or not body.get("ok"):
                        description = body.get("description", f"HTTP {response.status}")
                        raise TelegramError(f"Telegram {method}: {description}")
                    return body.get("result")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 2:
                    raise TelegramError(f"Telegram indisponível: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
        raise TelegramError(f"Telegram {method} falhou")

    async def send(self, chat_id: int, text: str) -> None:
        await self.api("sendMessage", {"chat_id": chat_id, "text": clip(text), "disable_web_page_preview": True})

    async def send_voice(self, chat_id: int, audio_path: Path) -> None:
        assert self.http is not None
        url = TELEGRAM_API.format(token=self.token, method="sendVoice")
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("voice", audio_path.read_bytes(), filename="atena.wav", content_type="audio/wav")
        async with self.http.post(url, data=data, timeout=aiohttp.ClientTimeout(total=60)) as response:
            body = await response.json(content_type=None)
            if response.status != 200 or not body.get("ok"):
                raise TelegramError(f"Telegram sendVoice: {body.get('description', response.status)}")

    async def download_file(self, file_id: str, suffix: str = ".ogg") -> tuple[bytes, str]:
        assert self.http is not None
        metadata = await self.api("getFile", {"file_id": file_id})
        file_path = str((metadata or {}).get("file_path", ""))
        if not file_path:
            raise TelegramError("Telegram não retornou o caminho do áudio")
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
            if response.status != 200:
                raise TelegramError(f"download de áudio HTTP {response.status}")
            data = await response.read()
        return data, suffix

    async def ollama(self, chat_id: int, user_text: str) -> str:
        assert self.http is not None
        history = self.sessions.setdefault(str(chat_id), [])
        system = (
            "Você é a Atena, assistente técnica do projeto Atena-IA. "
            "Responda em português claro. Você pode explicar o repositório, "
            "as memórias e as propostas, mas não execute comandos, não revele "
            "segredos e não prometa que uma hipótese é aprendizagem comprovada. "
            "Quando uma ação exigir alteração, push, pagamento, exclusão ou produção, "
            "explique que é necessária confirmação e validação."
        )
        messages = [{"role": "system", "content": system}, *history[-MAX_HISTORY:], {"role": "user", "content": user_text}]
        payload = {"model": self.model, "stream": False, "messages": messages, "options": {"temperature": 0.2, "num_predict": 550}}
        async with self.http.post(OLLAMA_CHAT, json=payload, timeout=aiohttp.ClientTimeout(total=180)) as response:
            if response.status != 200:
                raise TelegramError(f"Ollama HTTP {response.status}")
            data = await response.json(content_type=None)
            answer = str(data.get("message", {}).get("content", "Não consegui gerar uma resposta."))
        history.extend([{"role": "user", "content": clip(user_text, 1200)}, {"role": "assistant", "content": clip(answer, 1800)}])
        self.sessions[str(chat_id)] = history[-MAX_HISTORY:]
        save_sessions(self.sessions)
        return answer

    async def best_store_deals(self, minimum_discount: float = 50.0, limit: int = 10) -> str:
        """Consulta as melhores ofertas atuais sem enviar alertas duplicados."""
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.store_discount_alert import best_deals

        report = await asyncio.to_thread(
            best_deals,
            ["steam", "epic", "gog", "nuuvem", "humble"],
            minimum_discount,
            limit,
        )
        deals = report.get("deals", [])
        errors = report.get("errors", [])
        if not deals:
            suffix = "\n\nFalhas: " + "; ".join(errors) if errors else ""
            return "Não encontrei ofertas acima do limite informado agora." + suffix

        lines = [
            f"ATENA — melhores ofertas do dia (mínimo {minimum_discount:g}% OFF)",
            f"Consulta: {report.get('checked_at', '')}",
            "",
        ]
        for index, deal in enumerate(deals, 1):
            price = f" | {deal.get('current_price')}" if deal.get("current_price") else ""
            lines.append(
                f"{index}. [{deal.get('store', '').upper()}] {deal.get('title', 'Sem título')} — "
                f"{float(deal.get('discount_percent', 0)):g}% OFF{price}\n"
                f"{deal.get('product_url', '')}"
            )
        if errors:
            lines.extend(["", "Lojas com erro nesta consulta: " + "; ".join(errors)])
        return clip("\n".join(lines))

    def latest_proposal(self) -> dict[str, Any] | None:
        proposals = sorted((ROOT / "atena_evolution" / "proposals").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not proposals:
            return None
        try:
            return json.loads(proposals[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    async def command(self, chat_id: int, text: str) -> str | None:
        command = text.split()[0].lower().split("@", 1)[0]
        if command == "/start":
            return "Olá. Sou a ponte de conversa da Atena. Envie uma pergunta ou use /help."
        if command == "/help":
            return "Comandos: /status, /aprendizagens, /capabilities, /modelo, /reset, /voz on|off|status, /pesquisar <tema>, /fila e /ofertas [mínimo%] [limite]. Mensagens comuns são respondidas pelo modelo local."
        if command == "/voz":
            option = text.split(maxsplit=1)[1].strip().lower() if len(text.split(maxsplit=1)) > 1 else "status"
            if option == "on":
                self.voice_enabled.add(str(chat_id))
                save_voice_settings(self.voice_enabled)
                return "Modo de voz ativado. Envie uma mensagem de voz para conversar com a Atena."
            if option == "off":
                self.voice_enabled.discard(str(chat_id))
                save_voice_settings(self.voice_enabled)
                return "Modo de voz desativado. Continuarei respondendo por texto."
            if option == "status":
                return "Modo de voz: " + ("ativado" if str(chat_id) in self.voice_enabled else "desativado")
            return "Uso: /voz on, /voz off ou /voz status."
        if command in {"/ofertas", "/oferta"}:
            parts = text.split()
            try:
                minimum_discount = float(parts[1]) if len(parts) > 1 else float(os.getenv("ATENA_MIN_DISCOUNT", "50"))
                limit = int(parts[2]) if len(parts) > 2 else 10
            except ValueError:
                return "Uso: /ofertas [desconto mínimo] [quantidade]. Exemplo: /ofertas 60 8"
            if not 0 <= minimum_discount <= 100 or not 1 <= limit <= 20:
                return "Use desconto entre 0 e 100 e quantidade entre 1 e 20."
            return await self.best_store_deals(minimum_discount, limit)
        if command == "/pesquisar":
            topic = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not topic:
                return "Uso: /pesquisar <tema>. Exemplo: /pesquisar tecnologia quântica"
            with MemoryStore(MEMORY_DB) as store:
                intent_id = store.enqueue_research(chat_id, topic, f"Pesquisar fontes e evidências sobre {topic}.")
            return f"Pesquisa enfileirada para o próximo ciclo: {topic}\nID: {intent_id}"
        if command == "/fila":
            with MemoryStore(MEMORY_DB) as store:
                intents = [item for item in store.pending_research() if str(item.get("chat_id")) == str(chat_id)]
            if not intents:
                return "Não há pesquisas pendentes para este chat."
            return clip("Pesquisas pendentes:\n" + "\n".join(f"• {item['topic']} ({item['status']})" for item in intents[:10]))
        if command == "/modelo":
            return f"Modelo local ativo: {self.model}\nBackend: Ollama em {OLLAMA_CHAT}"
        if command == "/reset":
            self.sessions.pop(str(chat_id), None)
            save_sessions(self.sessions)
            return "Histórico desta conversa removido."
        if command == "/status":
            memory = ROOT / "atena_evolution" / "llm_learning_memory.json"
            proposal = self.latest_proposal()
            return f"Atena online. Memória: {'disponível' if memory.exists() else 'ausente'}. Última proposta: {'disponível' if proposal else 'ausente'}. Modelo: {self.model}."
        if command == "/aprendizagens":
            proposal = self.latest_proposal()
            if not proposal:
                return "Ainda não encontrei uma proposta de aprendizagem."
            obs = proposal.get("observations", {})
            insights = obs.get("insights", [])
            risks = obs.get("risks", [])
            return clip("Última aprendizagem:\n" + "\n".join(f"• {x}" for x in insights[:5]) + "\n\nRiscos:\n" + "\n".join(f"• {x}" for x in risks[:5]))
        if command == "/capabilities":
            try:
                from core.capability_registry import catalog_dicts
                items = catalog_dicts()
                runnable = sum(bool(item.get("entrypoints")) for item in items)
                return f"Catálogo: {len(items)} capacidades. Pontos executáveis descobertos: {runnable}. A execução de módulos continua sujeita a validação e autorização."
            except Exception as exc:
                return f"Não consegui ler o catálogo: {type(exc).__name__}."
        return None

    async def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat = message.get("chat", {})
        chat_id = int(chat.get("id"))
        if not allowed_chat(chat_id, self.chat_allowlist):
            log.warning("mensagem ignorada de chat não autorizado: %s", chat_id)
            return
        text = str(message.get("text", "")).strip()
        voice = message.get("voice") or message.get("audio")
        temporary_audio: Path | None = None
        try:
            if voice and not text:
                if str(chat_id) not in self.voice_enabled:
                    await self.send(chat_id, "Modo de voz desativado. Envie /voz on para ativá-lo.")
                    return
                file_id = str(voice.get("file_id", ""))
                if not file_id:
                    raise AudioGatewayError("mensagem de voz sem file_id")
                audio_bytes, suffix = await self.download_file(file_id)
                transcript = await asyncio.to_thread(self.audio.transcribe_bytes, audio_bytes, suffix)
                text = transcript["text"]
                await self.send(chat_id, f"Transcrição: {clip(text, 900)}")
            if not text:
                return
            answer = await self.command(chat_id, text)
            if answer is None:
                answer = await self.ollama(chat_id, text)
            await self.send(chat_id, answer)
            if voice and str(chat_id) in self.voice_enabled:
                temporary_audio = await asyncio.to_thread(self.audio.synthesize, answer)
                await self.send_voice(chat_id, temporary_audio)
        except (AudioGatewayError, TelegramError) as exc:
            log.warning("falha controlada no áudio/Telegram: %s", exc)
            await self.send(chat_id, f"Não consegui processar o áudio agora: {exc}")
        except Exception as exc:
            log.exception("falha ao processar mensagem")
            await self.send(chat_id, f"Não consegui processar agora: {type(exc).__name__}. Verifique o log da Atena.")
        finally:
            AudioGateway.remove_file(temporary_audio)

    async def run(self, once: bool = False, poll_timeout: int = 25) -> None:
        # O long polling pode demorar ligeiramente além do timeout declarado pelo Telegram.
        # Um timeout transitório não deve encerrar a ponte e interromper as mensagens.
        client_timeout = aiohttp.ClientTimeout(total=poll_timeout + 60, connect=15, sock_read=poll_timeout + 45)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            self.http = session
            await self.api("getMe")
            log.info("ponte Telegram iniciada; modelo=%s", self.model)
            while True:
                try:
                    updates = await self.api("getUpdates", {"offset": self.offset, "timeout": poll_timeout, "allowed_updates": ["message"]})
                except TelegramError as exc:
                    log.warning("polling Telegram temporariamente indisponível; tentando novamente: %s", exc)
                    if once:
                        raise
                    await asyncio.sleep(5)
                    continue
                for update in updates or []:
                    self.offset = max(self.offset, int(update["update_id"]) + 1)
                    await self.handle_update(update)
                if once:
                    return


def main() -> int:
    parser = argparse.ArgumentParser(description="Conversa Telegram com a Atena/Ollama")
    parser.add_argument("--once", action="store_true", help="faz uma consulta de updates e encerra")
    parser.add_argument("--poll-timeout", type=int, default=25)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    try:
        token = required_env("ATENA_TELEGRAM_BOT_TOKEN")
        chats = required_env("ATENA_TELEGRAM_CHAT_ID")
        asyncio.run(AtenaTelegramChat(token, chats, args.model).run(args.once, args.poll_timeout))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.error("ponte encerrada: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
