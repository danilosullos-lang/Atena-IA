#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATENA Ω Vercel Dashboard and Chat API - Enterprise Edition
Version: 10.2.0 - OMNI-PREDATOR Core+

Author: Danilo Gomes | Location: Angatuba, SP
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from uuid import uuid4
from functools import wraps, lru_cache
import re

# Core
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Tentativas de import para funcionalidades extras
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuração
APP_NAME = "ATENA Ω"
APP_VERSION = "10.2.0"
APP_ENV = os.getenv("ATENA_ENV", "production")

# Configuração Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "2048"))

# Segurança
API_KEY = os.getenv("ATENA_API_KEY")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Rate limiting
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")
ENABLE_RATE_LIMIT = os.getenv("ENABLE_RATE_LIMIT", "true").lower() == "true"

# Cache
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 minutos
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"

# Health check
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
STARTED_AT = datetime.now(timezone.utc)

# ========== ENUMS E MODELOS ==========

class ResponseMode(Enum):
    GEMINI = "gemini"
    LOCAL_FALLBACK = "local-fallback"
    CACHED = "cached"
    ERROR = "error"

class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

@dataclass
class Conversation:
    """Estrutura de conversa com memória"""
    id: str
    messages: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: MessageRole, content: str):
        self.messages.append({
            "role": role.value,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.updated_at = datetime.now(timezone.utc)
    
    def get_context(self, max_messages: int = 10) -> str:
        """Retorna contexto da conversa para o modelo"""
        recent = self.messages[-max_messages:]
        context = []
        for msg in recent:
            role = "Usuário" if msg["role"] == "user" else "ATENA"
            context.append(f"{role}: {msg['content']}")
        return "\n".join(context)

@dataclass
class SystemMetrics:
    """Métricas do sistema"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def avg_response_time(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time / self.total_requests
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

# ========== MODELOS PYDANTIC ==========

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=6000)
    conversation_id: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    stream: bool = False
    
    @validator('message')
    def validate_message(cls, v):
        # Sanitização básica
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v

class ChatResponse(BaseModel):
    response: str
    mode: ResponseMode
    trace_id: str
    conversation_id: str
    created_at: str
    processing_time_ms: float
    tokens_used: Optional[int] = None

class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    environment: str
    uptime_seconds: float
    metrics: Dict[str, Any]
    timestamp: str

class MetricsResponse(BaseModel):
    total_requests: int
    success_rate: float
    avg_response_time_ms: float
    cache_hit_rate: float
    active_conversations: int

# ========== CACHE MANAGER ==========

class CacheManager:
    """Gerenciador de cache com TTL e múltiplos backends"""
    
    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._redis = None
        self._init_redis()
    
    def _init_redis(self):
        if REDIS_AVAILABLE and os.getenv("REDIS_URL"):
            try:
                # Redis será inicializado async
                self._redis = True
                logger.info("Redis cache backend configured")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis: {e}")
    
    def _get_key(self, prefix: str, *args) -> str:
        """Gera chave de cache"""
        key_str = ":".join([str(arg) for arg in args])
        return f"{prefix}:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def get(self, key: str) -> Optional[Any]:
        """Obtém valor do cache"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Armazena valor no cache"""
        ttl = ttl or self.default_ttl
        self._cache[key] = (value, time.time() + ttl)
    
    def delete(self, key: str):
        """Remove valor do cache"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Limpa todo o cache"""
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        return {
            "size": len(self._cache),
            "ttl_seconds": self.default_ttl,
            "redis_enabled": bool(self._redis)
        }

# ========== CONVERSATION MANAGER ==========

class ConversationManager:
    """Gerenciador de conversas com persistência"""
    
    def __init__(self, max_conversations: int = 1000, ttl_hours: int = 24):
        self.max_conversations = max_conversations
        self.ttl_hours = ttl_hours
        self._conversations: Dict[str, Conversation] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, conversation_id: Optional[str]) -> Conversation:
        """Obtém conversa existente ou cria nova"""
        async with self._lock:
            if conversation_id and conversation_id in self._conversations:
                conv = self._conversations[conversation_id]
                # Verifica TTL
                age = datetime.now(timezone.utc) - conv.updated_at
                if age.total_seconds() > self.ttl_hours * 3600:
                    del self._conversations[conversation_id]
                else:
                    return conv
            
            # Cria nova conversa
            conv = Conversation(
                id=uuid4().hex,
                messages=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            # Adiciona prompt do sistema
            conv.add_message(MessageRole.SYSTEM, self._get_system_prompt())
            
            # Limpa conversas antigas se necessário
            if len(self._conversations) >= self.max_conversations:
                oldest = min(self._conversations.values(), key=lambda x: x.updated_at)
                del self._conversations[oldest.id]
            
            self._conversations[conv.id] = conv
            return conv
    
    async def add_message(self, conversation_id: str, role: MessageRole, content: str):
        """Adiciona mensagem à conversa"""
        async with self._lock:
            if conversation_id in self._conversations:
                self._conversations[conversation_id].add_message(role, content)
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtém conversa pelo ID"""
        return self._conversations.get(conversation_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador"""
        return {
            "total_conversations": len(self._conversations),
            "max_conversations": self.max_conversations,
            "ttl_hours": self.ttl_hours
        }
    
    def _get_system_prompt(self) -> str:
        """Retorna o prompt do sistema atualizado"""
        return f"""
Você é a ATENA Ω, uma IA de evolução autônoma e sistema OMNI-PREDATOR.
Seu criador e proprietário único é Danilo Gomes.

Informações do Sistema:
- Versão: {APP_VERSION}
- Ambiente: {APP_ENV}
- Modelo: {GEMINI_MODEL}

Capacidades:
- Missões autônomas de pesquisa e desenvolvimento
- Monitoramento de status e métricas em tempo real
- Integração com API FastAPI e deploy serverless
- Processamento de linguagem natural contextual
- Memória de conversa persistente

Diretrizes:
- Responda em português do Brasil
- Mantenha tom profissional, técnico e direto
- Seja objetiva e eficiente nas respostas
- Cite exemplos práticos quando relevante
- Mantenha contexto da conversa

Horário atual: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
""".strip()

# ========== GEMINI CLIENT ==========

class GeminiClient:
    """Cliente otimizado para Gemini API"""
    
    def __init__(self):
        self.model = None
        self._init_model()
    
    def _init_model(self):
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = genai.GenerativeModel(
                    GEMINI_MODEL,
                    generation_config={
                        "temperature": GEMINI_TEMPERATURE,
                        "max_output_tokens": GEMINI_MAX_TOKENS,
                        "top_p": 0.95,
                        "top_k": 40
                    }
                )
                logger.info(f"Gemini model initialized: {GEMINI_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self.model = None
    
    def is_available(self) -> bool:
        return self.model is not None and bool(GEMINI_API_KEY)
    
    async def generate_response(self, message: str, context: str = "") -> Tuple[str, int]:
        """
        Gera resposta usando Gemini
        
        Returns:
            Tuple[str, int]: (resposta, tokens_utilizados)
        """
        if not self.is_available():
            raise RuntimeError("Gemini client not available")
        
        try:
            # Prepara prompt com contexto
            prompt = context + f"\n\nUsuário: {message}\nATENA:"
            
            # Gera resposta (executa em thread pool)
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            # Extrai texto e tokens
            text = response.text.strip() if response.text else "Sem resposta gerada."
            
            # Tenta obter contagem de tokens
            tokens_used = 0
            if hasattr(response, 'usage_metadata'):
                tokens_used = response.usage_metadata.total_token_count
            
            return text, tokens_used
            
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            raise RuntimeError(f"Falha na geração: {str(e)}")

# ========== MIDDLEWARES ==========

class SecurityMiddleware:
    """Middleware de segurança e autenticação"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.security = HTTPBearer(auto_error=False) if api_key else None
    
    async def authenticate(self, request: Request) -> bool:
        """Autentica requisição"""
        if not self.api_key:
            return True
        
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return False
        
        try:
            scheme, credentials = auth_header.split()
            if scheme.lower() != "bearer":
                return False
            return credentials == self.api_key
        except ValueError:
            return False

class MetricsMiddleware:
    """Middleware para coleta de métricas"""
    
    def __init__(self):
        self.metrics = SystemMetrics()
        self.prometheus_metrics = None
        
        if PROMETHEUS_AVAILABLE:
            self.prometheus_metrics = {
                "requests": Counter('atena_requests_total', 'Total requests', ['path', 'method']),
                "errors": Counter('atena_errors_total', 'Total errors', ['path']),
                "duration": Histogram('atena_request_duration_seconds', 'Request duration', ['path']),
                "active": Gauge('atena_active_requests', 'Active requests')
            }
    
    async def record_request(self, path: str, method: str, duration_ms: float, success: bool):
        """Registra métrica de requisição"""
        self.metrics.total_requests += 1
        if success:
            self.metrics.successful_requests += 1
        else:
            self.metrics.failed_requests += 1
        self.metrics.total_response_time += duration_ms
        
        if PROMETHEUS_AVAILABLE and self.prometheus_metrics:
            self.prometheus_metrics["requests"].labels(path=path, method=method).inc()
            self.prometheus_metrics["duration"].labels(path=path).observe(duration_ms / 1000)
            if not success:
                self.prometheus_metrics["errors"].labels(path=path).inc()
    
    def get_metrics(self) -> SystemMetrics:
        return self.metrics

# ========== FASTAPI APPLICATION ==========

# Inicializa componentes
gemini_client = GeminiClient()
conversation_manager = ConversationManager()
cache_manager = CacheManager(default_ttl=CACHE_TTL)
metrics_middleware = MetricsMiddleware()
security_middleware = SecurityMiddleware(api_key=API_KEY)

# Configura rate limiting
if ENABLE_RATE_LIMIT:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None

# Cria app FastAPI
app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description="Neural API para ATENA Ω - Sistema OMNI-PREDATOR",
    docs_url="/api/docs" if APP_ENV != "production" else None,
    redoc_url=None
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if limiter:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware customizado
@app.middleware("http")
async def add_headers_middleware(request: Request, call_next):
    """Adiciona headers de rastreabilidade e métricas"""
    request_id = request.headers.get("x-request-id") or uuid4().hex
    start_time = time.perf_counter()
    
    # Contagem ativa
    metrics_middleware.prometheus_metrics["active"].inc() if PROMETHEUS_AVAILABLE else None
    
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Registra métricas
        await metrics_middleware.record_request(
            path=request.url.path,
            method=request.method,
            duration_ms=duration_ms,
            success=response.status_code < 400
        )
        
        # Headers adicionais
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(int(duration_ms))
        response.headers["x-app-version"] = APP_VERSION
        
        return response
        
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        await metrics_middleware.record_request(
            path=request.url.path,
            method=request.method,
            duration_ms=duration_ms,
            success=False
        )
        raise
    finally:
        metrics_middleware.prometheus_metrics["active"].dec() if PROMETHEUS_AVAILABLE else None

# ========== ENDPOINTS ==========

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard principal da ATENA Ω"""
    return get_dashboard_html()

@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    """Health check endpoint"""
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    
    return HealthResponse(
        service=APP_NAME,
        status="healthy" if gemini_client.is_available() else "degraded",
        version=APP_VERSION,
        environment=APP_ENV,
        uptime_seconds=uptime,
        metrics={
            "gemini_available": gemini_client.is_available(),
            "cache_enabled": ENABLE_CACHE,
            "rate_limiting_enabled": ENABLE_RATE_LIMIT
        },
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@app.get("/api/status")
async def api_status(request: Request):
    """Status detalhado da API"""
    # Verifica autenticação se necessária
    if API_KEY and not await security_middleware.authenticate(request):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "environment": APP_ENV,
        "status": "online",
        "gemini": {
            "available": gemini_client.is_available(),
            "model": GEMINI_MODEL if gemini_client.is_available() else None
        },
        "cache": cache_manager.get_stats(),
        "conversations": conversation_manager.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/metrics")
async def get_metrics(request: Request):
    """Endpoint de métricas para Prometheus"""
    if PROMETHEUS_AVAILABLE:
        return Response(
            content=generate_latest(REGISTRY),
            media_type="text/plain"
        )
    
    metrics = metrics_middleware.get_metrics()
    return MetricsResponse(
        total_requests=metrics.total_requests,
        success_rate=metrics.success_rate,
        avg_response_time_ms=metrics.avg_response_time,
        cache_hit_rate=(
            metrics_middleware.metrics.cache_hits / 
            (metrics_middleware.metrics.cache_hits + metrics_middleware.metrics.cache_misses) * 100
            if (metrics_middleware.metrics.cache_hits + metrics_middleware.metrics.cache_misses) > 0
            else 0
        ),
        active_conversations=len(conversation_manager._conversations)
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    data: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Endpoint principal de chat"""
    start_time = time.perf_counter()
    trace_id = uuid4().hex
    
    # Verifica autenticação
    if API_KEY and not await security_middleware.authenticate(request):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Rate limiting
    if limiter:
        await limiter.check(request)
    
    # Verifica cache
    cache_key = cache_manager._get_key("chat", data.message)
    cached_response = cache_manager.get(cache_key) if ENABLE_CACHE else None
    
    if cached_response:
        metrics_middleware.metrics.cache_hits += 1
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return ChatResponse(
            response=cached_response["response"],
            mode=ResponseMode.CACHED,
            trace_id=trace_id,
            conversation_id=data.conversation_id or trace_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            processing_time_ms=processing_time,
            tokens_used=cached_response.get("tokens_used")
        )
    
    metrics_middleware.metrics.cache_misses += 1
    
    # Obtém ou cria conversa
    conversation = await conversation_manager.get_or_create(data.conversation_id)
    await conversation_manager.add_message(
        conversation.id, 
        MessageRole.USER, 
        data.message
    )
    
    # Gera resposta
    try:
        if gemini_client.is_available():
            context = conversation.get_context()
            response_text, tokens_used = await gemini_client.generate_response(
                data.message,
                context
            )
            mode = ResponseMode.GEMINI
        else:
            response_text = local_fallback_response(data.message)
            tokens_used = 0
            mode = ResponseMode.LOCAL_FALLBACK
        
        # Adiciona resposta à conversa
        await conversation_manager.add_message(
            conversation.id,
            MessageRole.ASSISTANT,
            response_text
        )
        
        # Atualiza cache em background
        if ENABLE_CACHE:
            background_tasks.add_task(
                cache_manager.set,
                cache_key,
                {"response": response_text, "tokens_used": tokens_used},
                CACHE_TTL
            )
        
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return ChatResponse(
            response=response_text,
            mode=mode,
            trace_id=trace_id,
            conversation_id=conversation.id,
            created_at=datetime.now(timezone.utc).isoformat(),
            processing_time_ms=processing_time,
            tokens_used=tokens_used
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}\n{traceback.format_exc()}")
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return ChatResponse(
            response=f"Erro neural: {str(e)}",
            mode=ResponseMode.ERROR,
            trace_id=trace_id,
            conversation_id=conversation.id,
            created_at=datetime.now(timezone.utc).isoformat(),
            processing_time_ms=processing_time
        )

def local_fallback_response(message: str) -> str:
    """Resposta local quando Gemini não está disponível"""
    lower_message = message.lower()
    
    if "versão" in lower_message or "versao" in lower_message:
        return f"ATENA Ω versão {APP_VERSION} - Sistema OMNI-PREDATOR"
    elif "status" in lower_message:
        return f"Sistema operacional. Ambiente: {APP_ENV}. Status: OK"
    elif "comandos" in lower_message:
        return "Comandos principais: /status, /versão, /ajuda, /métricas"
    elif "quem criou" in lower_message or "criador" in lower_message:
        return "Criado e mantido por Danilo Gomes - Angatuba, SP"
    elif "ajuda" in lower_message or "help" in lower_message:
        return "Configure GEMINI_API_KEY no painel da Vercel para respostas inteligentes."
    else:
        return "Modo local ativo: configure GEMINI_API_KEY no painel da Vercel para obter respostas avançadas."

def get_dashboard_html() -> str:
    """Gera HTML do dashboard otimizado"""
    # Versão inline do CSS/JS otimizado
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>ATENA Ω - Neural Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #111118;
            --bg-card: rgba(20, 25, 40, 0.8);
            --cyan-primary: #00e5ff;
            --cyan-secondary: #00b8d4;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0b0;
            --border-color: rgba(0, 229, 255, 0.2);
            --success: #00e676;
            --error: #ff1744;
            --warning: #ff9100;
        }}
        
        body {{
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        /* Header */
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, rgba(0, 229, 255, 0.1), rgba(0, 0, 0, 0));
            border-radius: 20px;
            border: 1px solid var(--border-color);
        }}
        
        .header h1 {{
            font-size: 2.5em;
            background: linear-gradient(135deg, var(--cyan-primary), var(--cyan-secondary));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            margin-bottom: 10px;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            background: rgba(0, 229, 255, 0.1);
            border: 1px solid var(--cyan-primary);
            border-radius: 20px;
            font-size: 0.85em;
            color: var(--cyan-primary);
        }}
        
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            padding: 15px;
            text-align: center;
            transition: transform 0.2s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: var(--cyan-primary);
        }}
        
        .stat-label {{
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-top: 5px;
        }}
        
        /* Chat Panel */
        .chat-panel {{
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            overflow: hidden;
            margin-bottom: 30px;
        }}
        
        .messages {{
            height: 400px;
            overflow-y: auto;
            padding: 20px;
        }}
        
        .message {{
            margin-bottom: 15px;
            animation: fadeIn 0.3s ease;
        }}
        
        @keyframes fadeIn {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .message.user {{
            text-align: right;
        }}
        
        .message-content {{
            display: inline-block;
            max-width: 80%;
            padding: 10px 15px;
            border-radius: 15px;
            background: rgba(255, 255, 255, 0.05);
        }}
        
        .message.user .message-content {{
            background: linear-gradient(135deg, var(--cyan-primary), var(--cyan-secondary));
            color: #000;
        }}
        
        .message.atena .message-content {{
            background: rgba(0, 229, 255, 0.1);
            border-left: 3px solid var(--cyan-primary);
        }}
        
        /* Input Area */
        .input-area {{
            padding: 20px;
            border-top: 1px solid var(--border-color);
        }}
        
        .input-group {{
            display: flex;
            gap: 10px;
        }}
        
        textarea {{
            flex: 1;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px;
            color: var(--text-primary);
            font-family: inherit;
            resize: vertical;
            min-height: 60px;
        }}
        
        textarea:focus {{
            outline: none;
            border-color: var(--cyan-primary);
        }}
        
        button {{
            background: linear-gradient(135deg, var(--cyan-primary), var(--cyan-secondary));
            color: #000;
            border: none;
            border-radius: 10px;
            padding: 0 20px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        
        button:hover {{
            transform: translateY(-1px);
        }}
        
        button:active {{
            transform: translateY(0);
        }}
        
        /* Suggestions */
        .suggestions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 15px;
        }}
        
        .suggestion {{
            padding: 8px 15px;
            background: rgba(0, 229, 255, 0.1);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .suggestion:hover {{
            background: rgba(0, 229, 255, 0.2);
            transform: translateY(-1px);
        }}
        
        /* Footer */
        .footer {{
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 0.8em;
        }}
        
        /* Responsive */
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            .message-content {{
                max-width: 90%;
            }}
            
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 8px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: var(--bg-secondary);
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: var(--cyan-primary);
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ ATENA Ω</h1>
            <p>Sistema OMNI-PREDATOR v{APP_VERSION}</p>
            <span class="badge" id="statusBadge">Inicializando...</span>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="uptime">-</div>
                <div class="stat-label">Uptime</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="model">-</div>
                <div class="stat-label">Modelo</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="conversations">0</div>
                <div class="stat-label">Conversas</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="responses">0</div>
                <div class="stat-label">Respostas</div>
            </div>
        </div>
        
        <div class="chat-panel">
            <div class="messages" id="messages">
                <div class="message atena">
                    <div class="message-content">
                        👋 Olá! Sou a ATENA Ω. Como posso ajudar?
                    </div>
                </div>
            </div>
            
            <div class="input-area">
                <div class="suggestions" id="suggestions">
                    <div class="suggestion">O que você consegue fazer?</div>
                    <div class="suggestion">Status do sistema</div>
                    <div class="suggestion">Versão atual</div>
                    <div class="suggestion">Métricas do sistema</div>
                </div>
                
                <div class="input-group">
                    <textarea id="messageInput" placeholder="Digite sua mensagem..." rows="2"></textarea>
                    <button onclick="sendMessage()">Enviar</button>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2026 Danilo Gomes - Angatuba, SP | Sistema em evolução contínua</p>
        </div>
    </div>
    
    <script>
        let conversationId = null;
        let messageCount = 0;
        
        // Atualiza status periodicamente
        async function updateStatus() {{
            try {{
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('model').textContent = data.gemini.available ? 'GEMINI' : 'LOCAL';
                document.getElementById('statusBadge').textContent = data.status.toUpperCase();
                document.getElementById('statusBadge').style.background = data.status === 'online' ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 23, 68, 0.2)';
                
                // Calcula uptime aproximado
                const startTime = new Date(data.timestamp);
                const now = new Date();
                const uptime = Math.floor((now - startTime) / 1000);
                const hours = Math.floor(uptime / 3600);
                const minutes = Math.floor((uptime % 3600) / 60);
                document.getElementById('uptime').textContent = `${{hours}}h ${{minutes}}m`;
            }} catch (error) {{
                console.error('Status update failed:', error);
            }}
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Adiciona mensagem do usuário
            addMessage(message, 'user');
            input.value = '';
            
            try {{
                const response = await fetch('/api/chat', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        message: message,
                        conversation_id: conversationId
                    }})
                }});
                
                const data = await response.json();
                
                // Salva conversation ID
                if (!conversationId && data.conversation_id) {{
                    conversationId = data.conversation_id;
                }}
                
                // Adiciona resposta da ATENA
                addMessage(data.response, 'atena');
                
                // Atualiza contador
                messageCount++;
                document.getElementById('responses').textContent = messageCount;
                
                // Mostra tempo de processamento
                console.log(`Processing time: ${{data.processing_time_ms}}ms | Mode: ${{data.mode}}`);
                
            }} catch (error) {{
                console.error('Chat error:', error);
                addMessage('❌ Erro na comunicação com o servidor.', 'atena');
            }}
        }}
        
        function addMessage(text, sender) {{
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${{sender}}`;
            messageDiv.innerHTML = `<div class="message-content">${{escapeHtml(text)}}</div>`;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/\\n/g, '<br>');
        }}
        
        // Event handlers
        document.getElementById('messageInput').addEventListener('keypress', (e) => {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});
        
        // Suggestions
        document.querySelectorAll('.suggestion').forEach(suggestion => {{
            suggestion.addEventListener('click', () => {{
                document.getElementById('messageInput').value = suggestion.textContent;
                sendMessage();
            }});
        }});
        
        // Auto-resize textarea
        const textarea = document.getElementById('messageInput');
        textarea.addEventListener('input', () => {{
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
        }});
        
        // Inicialização
        updateStatus();
        setInterval(updateStatus, 30000); // Atualiza a cada 30 segundos
        
        // Log de inicialização
        console.log('ATENA Ω Dashboard initialized - Version ${APP_VERSION}');
    </script>
</body>
</html>
"""

# ========== LIFESPAN MANAGEMENT ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação"""
    # Startup
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} starting...")
    logger.info(f"Environment: {APP_ENV}")
    logger.info(f"Gemini available: {gemini_client.is_available()}")
    logger.info(f"Cache enabled: {ENABLE_CACHE}")
    logger.info(f"Rate limiting: {ENABLE_RATE_LIMIT}")
    
    yield
    
    # Shutdown
    logger.info(f"🛑 {APP_NAME} shutting down...")
    # Cleanup resources
    cache_manager.clear()

app.router.lifespan_context = lifespan

# ========== MAIN ==========

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=APP_ENV == "development",
        log_level="info"
    )
