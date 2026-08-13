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
from core.google_calendar_client import GoogleCalendarClient, GoogleCalendarNotConfigured, format_event
from core.x_news_research import XNewsResearch, XNotConfigured
from core.tasker_client import TaskerClient, TaskerDispatchError, TaskerNotConfigured
from core.universal_task_router import TaskIntent, confirmation_prompt as task_confirmation_prompt, parse_task_intent
from core.workspace_actions import (
    WorkspaceIntent,
    confirmation_prompt,
    is_cancellation,
    is_confirmation,
    parse_workspace_intent,
)

ROOT = Path(os.getenv("ATENA_ROOT", Path(__file__).resolve().parents[1]))
MEMORY_DB = Path(os.getenv("ATENA_MEMORY_DB", str(ROOT / "atena_evolution" / "memory.sqlite3")))
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
OLLAMA_CHAT = os.getenv("ATENA_OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct")
SESSION_PATH = Path(os.getenv("ATENA_TELEGRAM_SESSION_PATH", str(ROOT / "data" / "telegram_sessions.json")))
VOICE_SETTINGS_PATH = Path(os.getenv("ATENA_TELEGRAM_VOICE_SETTINGS_PATH", str(ROOT / "data" / "telegram_voice_settings.json")))
MAX_HISTORY = 12
MAX_MESSAGE = 3900


def infer_task_type(text: str) -> str:
    lowered = text.casefold()
    if any(marker in lowered for marker in ("últimas notícias", "notícia", "pesquise", "fontes", "nasa", "atualmente", "hoje")):
        return "web_research"
    if any(marker in lowered for marker in ("código", "script", "python", "github", "pull request", "bug", "programar")):
        return "code"
    if any(marker in lowered for marker in ("privado", "senha", "e-mail da empresa", "email da empresa")):
        return "private"
    return "telegram"

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
        self.pending_workspace: dict[str, Any] = {}
        self.pending_device: dict[str, Any] = {}
        self.tasker = TaskerClient()
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

    @staticmethod
    def needs_current_web(text: str) -> bool:
        markers = (
            "quando", "que dia", "qual dia", "horário", "hora", "próximo jogo",
            "joga", "jogar", "partida", "placar", "resultado", "hoje", "amanhã",
            "atualmente", "últimas notícias", "notícia", "cotação", "preço atual",
        )
        lowered = text.casefold()
        teams = ("santos", "palmeiras", "corinthians", "são paulo", "flamengo", "brasil")
        return any(marker in lowered for marker in markers) and any(team in lowered for team in teams) or any(marker in lowered for marker in ("hoje", "amanhã", "atualmente", "últimas notícias", "preço atual"))

    async def current_web_answer(self, chat_id: int, question: str) -> str:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from core.web_research import build_context, search_web

        evidence = await asyncio.to_thread(search_web, question, 5)
        context = build_context(question, evidence)
        answer = await self.ollama(
            chat_id,
            "Responda diretamente à pergunta do usuário em português. Não diga que você não tem internet: "
            "a pesquisa abaixo foi fornecida pelo sistema. Não confunda uma notificação de aprendizagem com a resposta. "
            "Informe data/horário quando houver fonte suficiente e termine com 'Fontes:' e as URLs usadas.\n\n" + context,
            task_type="web_research",
        )
        return "ATENA — resposta atual\n\n" + answer

    async def ollama(self, chat_id: int, user_text: str, task_type: str | None = None) -> str:
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
        selected_task = task_type or infer_task_type(user_text)
        try:
            from core.atena_llm_router import get_router
            router = await get_router()
            routed = await router.generate(
                user_text,
                context="\n".join(f"{item['role']}: {item['content']}" for item in history[-MAX_HISTORY:]),
                task_type=selected_task,
                temperature=0.2,
                max_tokens=550,
            )
            answer = routed.content
        except Exception as exc:
            log.warning("roteador LLM indisponível; usando Ollama direto: %s", exc)
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
            return "Comandos: /status, /aprendizagens, /capabilities, /modelo, /reset, /voz on|off|status, /pesquisar <tema>, /x <notícia>, /fila, /ofertas [mínimo%] [limite], /agenda, /agendar <evento>, /criar planilha <título>. Também aceito: abrir Spotify, tocar <música> de <artista>, pausar mídia, próxima música, status do celular. Ações sensíveis exigem confirmação."
        # Ações de workspace são sempre interpretadas antes do Ollama.
        workspace_intent = parse_workspace_intent(chat_id, text)
        if workspace_intent is not None:
            if workspace_intent.action == "calendar_list":
                if workspace_intent.provider == "microsoft":
                    return "A consulta Outlook ainda precisa do conector Microsoft Graph. O Google Calendar pode ser ativado com OAuth desktop."
                try:
                    events = await asyncio.to_thread(GoogleCalendarClient().upcoming, 10)
                except GoogleCalendarNotConfigured as exc:
                    return f"Google Calendar ainda não configurado: {exc}"
                except Exception as exc:
                    log.exception("falha ao listar eventos do Google Calendar")
                    return f"Não consegui consultar o Google Calendar: {type(exc).__name__}."
                if not events:
                    return "ATENA — agenda\n\nNenhum evento futuro encontrado."
                return clip("ATENA — agenda\n\n" + "\n".join(f"• {format_event(event)}" for event in events))
            if workspace_intent.requires_confirmation:
                self.pending_workspace[str(chat_id)] = workspace_intent.to_dict()
                return confirmation_prompt(workspace_intent)
        pending = self.pending_workspace.get(str(chat_id))
        if pending:
            pending_id = str(pending.get("id", ""))
            if is_confirmation(text, pending_id):
                self.pending_workspace.pop(str(chat_id), None)
                intent = WorkspaceIntent(**pending)
                if intent.action == "calendar_create":
                    if intent.provider == "microsoft":
                        return "Ação confirmada, mas o conector Outlook ainda não está configurado. Nenhum evento foi criado."
                    try:
                        event = await asyncio.to_thread(GoogleCalendarClient().create_event, intent.parameters)
                    except GoogleCalendarNotConfigured as exc:
                        return f"Confirmação recebida, mas o Google Calendar ainda não está configurado: {exc}"
                    except Exception as exc:
                        log.exception("falha ao criar evento no Google Calendar")
                        return f"Confirmação recebida, mas não consegui criar o evento: {type(exc).__name__}."
                    return f"ATENA — evento criado\n\n{format_event(event)}\n{event.get('htmlLink', '')}".strip()
                return "Confirmação registrada. O adaptador desta ação ainda precisa ser configurado; nenhuma alteração foi feita."
            if is_cancellation(text, pending_id):
                self.pending_workspace.pop(str(chat_id), None)
                return "Ação cancelada; nenhuma planilha ou evento foi alterado."
        pending_device = self.pending_device.get(str(chat_id))
        if pending_device:
            pending_id = str(pending_device.get("id", ""))
            normalized = " ".join(text.strip().split()).casefold()
            if normalized == f"confirmar {pending_id}".casefold():
                self.pending_device.pop(str(chat_id), None)
                try:
                    await self.tasker.approve(
                        approval_id=pending_id,
                        requester_chat_id=str(chat_id),
                        action=str(pending_device["action"]),
                        target=str(pending_device["target"]),
                        parameters=dict(pending_device.get("parameters", {})),
                        expires_in=120,
                    )
                    result = await self.tasker.dispatch(
                        action=str(pending_device["action"]),
                        target=str(pending_device["target"]),
                        parameters=dict(pending_device.get("parameters", {})),
                        command_id=pending_id,
                        approval_id=pending_id,
                    )
                except TaskerNotConfigured as exc:
                    return f"Confirmação recebida, mas o gateway Android ainda não está configurado: {exc}."
                except TaskerDispatchError as exc:
                    log.exception("falha ao aprovar/despachar ação sensível")
                    return f"Ação não executada: {exc}"
                return f"Ação sensível confirmada e enfileirada no Tasker. ID: {result.get('command_id', pending_id)}"
            if normalized == f"cancelar {pending_id}".casefold():
                self.pending_device.pop(str(chat_id), None)
                return "Ação Android cancelada; nenhum aplicativo ou arquivo foi alterado."

        task_intent = parse_task_intent(text)
        if task_intent is not None:
            if task_intent.requires_confirmation:
                self.pending_device[str(chat_id)] = {
                    "id": task_intent.id,
                    "action": task_intent.action,
                    "target": task_intent.target,
                    "parameters": task_intent.parameters,
                }
                return task_confirmation_prompt(task_intent)
            try:
                result = await self.tasker.dispatch(
                    action=task_intent.action,
                    target=task_intent.target,
                    parameters=task_intent.parameters,
                    command_id=task_intent.id,
                )
            except TaskerNotConfigured as exc:
                return f"Roteador Android ainda não configurado: {exc}."
            except TaskerDispatchError as exc:
                log.exception("falha ao despachar tarefa Android")
                return f"Não consegui entregar a tarefa ao Tasker: {exc}"
            return f"Tarefa Android enfileirada: {task_intent.action}\nID: {result.get('command_id', task_intent.id)}"

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
        if command in {"/x", "/noticiasx"}:
            query = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not query:
                return "Uso: /x <tema>. Exemplo: /x últimas notícias sobre inteligência artificial"
            try:
                posts = await asyncio.to_thread(XNewsResearch().search, query, 10)
            except XNotConfigured as exc:
                return f"Pesquisa no X indisponível: {exc}"
            except Exception as exc:
                log.exception("falha na pesquisa do X")
                return f"Não consegui consultar o X agora: {type(exc).__name__}."
            if not posts:
                return "ATENA — X\n\nNenhum post recente encontrado para essa consulta."
            lines = ["ATENA — notícias recentes no X", ""]
            for post in posts[:10]:
                snippet = " ".join(post.text.split())[:240]
                lines.append(f"• {snippet}\n  {post.url}")
            return clip("\n".join(lines))
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
                if self.needs_current_web(text):
                    try:
                        answer = await self.current_web_answer(chat_id, text)
                    except Exception as exc:
                        log.warning("pesquisa web indisponível: %s", exc)
                        answer = "ATENA — resposta atual\n\nNão consegui confirmar essa informação em fontes públicas agora. Tente novamente em alguns instantes ou use /pesquisar para enfileirar uma investigação no próximo ciclo."
                else:
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
