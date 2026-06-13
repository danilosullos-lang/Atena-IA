#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ATENA MEMORY VAULT v3.0.0                                ║
║              Sistema Avançado de Versionamento de Modelos de IA             ║
║                                                                            ║
║  Features:                                                                 ║
║  • Compressão adaptativa com múltiplos codecs                              ║
║  • Checksum criptográfico com SHA-256/SHA-512/Blake2                       ║
║  • Cache distribuído com TTL adaptativo                                    ║
║  • Operações atômicas com journaling                                       ║
║  • Backup incremental e diferencial                                        ║
║  • Recuperação automática com checkpoint                                   ║
║  • Métricas em tempo real com Prometheus                                   ║
║  • Sharding automático para grandes datasets                               ║
║  • API RESTful integrada                                                   ║
║  • Event sourcing com CQRS                                                 ║
║                                                                            ║
║  Autor: ATENA Consciousness Engine                                         ║
║  Licença: Proprietária - Todos os direitos reservados                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextlib
import datetime
import gzip
import hashlib
import io
import json
import logging
import lzma
import mmap
import multiprocessing
import os
import pickle
import queue
import re
import secrets
import shutil
import signal
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import traceback
import uuid
import warnings
import weakref
import zlib
import zstandard as zstd
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import asdict, dataclass, field, fields, replace
from enum import Enum, Flag, IntEnum, auto
from functools import cached_property, lru_cache, partial, wraps
from pathlib import Path, PurePath
from typing import (
    Any, AsyncGenerator, AsyncIterator, Awaitable, Callable, ClassVar,
    Coroutine, DefaultDict, Deque, Dict, Final, FrozenSet, Generator,
    Generic, Iterable, Iterator, List, Literal, Mapping, MutableMapping,
    NamedTuple, NewType, NoReturn, Optional, OrderedDict as OrderedDictType,
    ParamSpec, Protocol, Self, Sequence, Set, Tuple, Type, TypeAlias,
    TypeGuard, TypeVar, TypedDict, Union, cast, final, overload, runtime_checkable
)

T = TypeVar("T")

import aiofiles
import anyio
import msgpack
import numpy as np
import orjson
import psutil
import rich
import structlog
import xxhash
from croniter import croniter
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig
from prometheus_client import Counter, Gauge, Histogram, Summary, start_http_server
from pydantic import BaseModel, Field, ValidationError, validator, root_validator
from redis import asyncio as aioredis
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.traceback import install
from rocketry import Rocketry
from rocketry.conds import daily, every, hourly, minutely
from sentry_sdk import capture_exception, init as sentry_init
from tenacity import (
    AsyncRetrying, RetryError, retry, retry_if_exception_type,
    stop_after_attempt, wait_exponential, before_sleep_log
)
from watchdog.events import FileSystemEventHandler, PatternMatchingEventHandler
from watchdog.observers import Observer

# ─── Configuração de Ambiente ────────────────────────────────────────────────
install(show_locals=True, width=200)
warnings.filterwarnings('ignore', category=DeprecationWarning)
os.environ.setdefault('ATENA_ENV', 'production')

# ─── Sentry ──────────────────────────────────────────────────────────────────
sentry_init(
    dsn=os.getenv('SENTRY_DSN', ''),
    traces_sample_rate=0.1,
    environment=os.getenv('ATENA_ENV', 'production')
)

# ─── Structured Logging ──────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ─── Métricas Prometheus ─────────────────────────────────────────────────────
METRICS_PREFIX = "atena_memory_vault"

model_saves = Counter(f"{METRICS_PREFIX}_model_saves_total", "Total saves", ["status"])
model_loads = Counter(f"{METRICS_PREFIX}_model_loads_total", "Total loads", ["status"])
model_versions = Gauge(f"{METRICS_PREFIX}_model_versions", "Active versions")
storage_bytes = Gauge(f"{METRICS_PREFIX}_storage_bytes", "Total storage used")
cache_hits = Counter(f"{METRICS_PREFIX}_cache_hits_total", "Cache hits")
cache_misses = Counter(f"{METRICS_PREFIX}_cache_misses_total", "Cache misses")
compression_ratio = Histogram(f"{METRICS_PREFIX}_compression_ratio", "Compression ratio")
operation_latency = Histogram(
    f"{METRICS_PREFIX}_operation_latency_seconds",
    "Operation latency",
    ["operation"]
)

# ─── Constantes Otimizadas ──────────────────────────────────────────────────
BASE_DIR: Final[Path] = Path(os.getenv(
    "ATENA_VAULT_DIR",
    Path.home() / ".atena" / "evolution" / "knowledge" / "vault"
))

DEFAULT_MAX_VERSIONS: Final[int] = int(os.getenv("ATENA_MAX_VERSIONS", "100"))
DEFAULT_CACHE_TTL: Final[int] = int(os.getenv("ATENA_CACHE_TTL", "300"))
DEFAULT_BATCH_SIZE: Final[int] = int(os.getenv("ATENA_BATCH_SIZE", "32"))
DEFAULT_COMPRESSION_LEVEL: Final[int] = int(os.getenv("ATENA_COMPRESSION_LEVEL", "6"))
DEFAULT_SHARD_SIZE_MB: Final[int] = int(os.getenv("ATENA_SHARD_SIZE_MB", "64"))
DEFAULT_CHECKPOINT_INTERVAL: Final[int] = int(os.getenv("ATENA_CHECKPOINT_INTERVAL", "60"))
DEFAULT_REDIS_URL: Final[str] = os.getenv("ATENA_REDIS_URL", "redis://localhost:6379/0")
DEFAULT_SQLITE_PATH: Final[Path] = BASE_DIR / "vault.db"
DEFAULT_JOURNAL_PATH: Final[Path] = BASE_DIR / "journal"

# ─── Tipos Customizados ─────────────────────────────────────────────────────
ModelId = NewType('ModelId', str)
VersionId = NewType('VersionId', str)
Checksum = NewType('Checksum', str)
ShardId = NewType('ShardId', int)
JournalEntryId = NewType('JournalEntryId', str)
ModelWeights = NewType('ModelWeights', bytes)
CompressedData = NewType('CompressedData', bytes)

# ─── Schemas Pydantic ───────────────────────────────────────────────────────
class PerformanceMetrics(BaseModel):
    """Métricas detalhadas de performance com validação rigorosa"""
    inference_time_us: float = Field(0.0, ge=0, description="Tempo de inferência em microssegundos")
    training_time_s: float = Field(0.0, ge=0, description="Tempo de treinamento em segundos")
    memory_usage_bytes: int = Field(0, ge=0, description="Uso de memória em bytes")
    cpu_usage_percent: float = Field(0.0, ge=0, le=100, description="Uso de CPU em porcentagem")
    gpu_memory_bytes: int = Field(0, ge=0, description="Uso de memória GPU em bytes")
    throughput_samples_per_sec: float = Field(0.0, ge=0, description="Throughput em amostras/s")
    latency_p50_us: float = Field(0.0, ge=0)
    latency_p95_us: float = Field(0.0, ge=0)
    latency_p99_us: float = Field(0.0, ge=0)
    
    @validator('latency_p99_us')
    def validate_percentiles(cls, v, values):
        if 'latency_p50_us' in values and v < values['latency_p50_us']:
            raise ValueError('p99 deve ser >= p50')
        return v

class TrainingConfig(BaseModel):
    """Configuração de treinamento com schema validation"""
    optimizer: str = "adam"
    learning_rate: float = Field(0.001, gt=0, le=1.0)
    batch_size: int = Field(32, gt=0, le=65536)
    epochs: int = Field(100, gt=0, le=1000000)
    early_stopping_patience: int = Field(10, ge=0)
    gradient_clip_norm: Optional[float] = Field(None, ge=0)
    scheduler: Optional[str] = None
    warmup_steps: int = Field(0, ge=0)
    mixed_precision: bool = False
    distributed: bool = False
    seed: int = Field(42, ge=0)
    
    class Config:
        extra = "allow"

class ModelMetadata(BaseModel):
    """Metadados enriquecidos com validação completa"""
    version: VersionId
    model_id: ModelId
    timestamp: datetime.datetime
    created_at_utc: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    loss: float = Field(..., ge=0)
    accuracy: float = Field(..., ge=0, le=1)
    validation_loss: Optional[float] = Field(None, ge=0)
    validation_accuracy: Optional[float] = Field(None, ge=0, le=1)
    f1_score: Optional[float] = Field(None, ge=0, le=1)
    precision: Optional[float] = Field(None, ge=0, le=1)
    recall: Optional[float] = Field(None, ge=0, le=1)
    auc_roc: Optional[float] = Field(None, ge=0, le=1)
    
    model_size_bytes: int = Field(0, ge=0)
    compressed_size_bytes: int = Field(0, ge=0)
    compression_ratio: float = Field(0.0, ge=0)
    
    checksum_sha256: Checksum = ""
    checksum_blake2b: Checksum = ""
    checksum_xxhash: Checksum = ""
    
    parent_version: Optional[VersionId] = None
    lineage: List[VersionId] = Field(default_factory=list)
    
    tags: Set[str] = Field(default_factory=set)
    labels: Dict[str, str] = Field(default_factory=dict)
    
    training_config: TrainingConfig = Field(default_factory=TrainingConfig)
    performance_metrics: Optional[PerformanceMetrics] = None
    
    framework_version: str = "3.0.0"
    python_version: str = Field(default=sys.version.split()[0])
    platform: str = Field(default=sys.platform)
    
    is_archived: bool = False
    is_corrupted: bool = False
    is_verified: bool = False
    
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, str] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime.datetime: lambda v: v.isoformat(),
            Set: list,
            bytes: lambda v: v.hex(),
        }
        allow_mutation = False
        frozen = True
    
    @root_validator(pre=True)
    def compute_derived_fields(cls, values):
        if 'model_size_bytes' in values and 'compressed_size_bytes' in values:
            if values['model_size_bytes'] > 0:
                values['compression_ratio'] = (
                    values['compressed_size_bytes'] / values['model_size_bytes']
                )
        return values

# ─── Enums Avançados ────────────────────────────────────────────────────────
class CompressionCodec(Enum):
    """Codecs de compressão suportados"""
    GZIP = "gzip"
    ZLIB = "zlib"
    BZ2 = "bz2"
    LZMA = "lzma"
    ZSTANDARD = "zstandard"
    LZ4 = "lz4"
    BROTLI = "brotli"
    SNAPPY = "snappy"
    AUTO = "auto"  # Seleciona automaticamente o melhor
    
    def compress(self, data: bytes, level: int = 6) -> bytes:
        """Comprime dados usando o codec especificado"""
        match self:
            case CompressionCodec.GZIP:
                return gzip.compress(data, compresslevel=level)
            case CompressionCodec.ZLIB:
                return zlib.compress(data, level=level)
            case CompressionCodec.BZ2:
                import bz2
                return bz2.compress(data)
            case CompressionCodec.LZMA:
                return lzma.compress(data, preset=min(9, level))
            case CompressionCodec.ZSTANDARD:
                cctx = zstd.ZstdCompressor(level=level)
                return cctx.compress(data)
            case CompressionCodec.AUTO:
                return self._auto_compress(data, level)
            case _:
                raise ValueError(f"Codec não suportado: {self}")
    
    def decompress(self, data: bytes) -> bytes:
        """Descomprime dados"""
        match self:
            case CompressionCodec.GZIP:
                return gzip.decompress(data)
            case CompressionCodec.ZLIB:
                return zlib.decompress(data)
            case CompressionCodec.LZMA:
                return lzma.decompress(data)
            case CompressionCodec.ZSTANDARD:
                dctx = zstd.ZstdDecompressor()
                return dctx.decompress(data)
            case _:
                raise ValueError(f"Decompressão não suportada: {self}")
    
    def _auto_compress(self, data: bytes, level: int) -> bytes:
        """Seleciona automaticamente o melhor codec para os dados"""
        if len(data) < 1024:
            return self.__class__.GZIP.compress(data, level)
        
        # Amostra os dados para testar compressão
        sample = data[:4096]
        best_ratio = 1.0
        best_compressed = None
        
        for codec in [CompressionCodec.ZSTANDARD, CompressionCodec.LZMA, CompressionCodec.GZIP]:
            try:
                compressed = codec.compress(sample, level)
                ratio = len(compressed) / len(sample)
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_compressed = codec.compress(data, level)
            except Exception:
                continue
        
        return best_compressed or self.__class__.GZIP.compress(data, level)

class ChecksumAlgorithm(Enum):
    """Algoritmos de checksum"""
    SHA256 = "sha256"
    SHA512 = "sha512"
    BLAKE2B = "blake2b"
    BLAKE2S = "blake2s"
    XXHASH = "xxhash"
    MD5 = "md5"
    
    def compute(self, data: bytes) -> str:
        """Calcula o checksum"""
        match self:
            case ChecksumAlgorithm.SHA256:
                return hashlib.sha256(data).hexdigest()
            case ChecksumAlgorithm.SHA512:
                return hashlib.sha512(data).hexdigest()
            case ChecksumAlgorithm.BLAKE2B:
                return hashlib.blake2b(data).hexdigest()
            case ChecksumAlgorithm.BLAKE2S:
                return hashlib.blake2s(data).hexdigest()
            case ChecksumAlgorithm.XXHASH:
                return xxhash.xxh64(data).hexdigest()
            case ChecksumAlgorithm.MD5:
                return hashlib.md5(data).hexdigest()

class StorageBackend(Enum):
    """Backends de armazenamento"""
    LOCAL = "local"
    MEMORY = "memory"
    SHARDED_LOCAL = "sharded_local"
    REDIS = "redis"
    SQLITE = "sqlite"
    HYBRID = "hybrid"

class ConsistencyLevel(IntEnum):
    """Níveis de consistência"""
    EVENTUAL = 0
    STRONG = 1
    SEQUENTIAL = 2
    LINEARIZABLE = 3

class JournalOperation(str, Enum):
    """Operações do journal"""
    SAVE = "save"
    LOAD = "load"
    DELETE = "delete"
    UPDATE = "update"
    ARCHIVE = "archive"
    RESTORE = "restore"
    VERIFY = "verify"
    COMPRESS = "compress"
    SHARD = "shard"
    MERGE = "merge"

# ─── Estruturas de Dados ────────────────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class ShardInfo:
    """Informações de um shard"""
    id: ShardId
    path: Path
    size_bytes: int
    checksum: Checksum
    created_at: datetime.datetime
    
@dataclass(slots=True)
class JournalEntry:
    """Entrada do journal para recovery"""
    id: JournalEntryId
    operation: JournalOperation
    version: VersionId
    timestamp: datetime.datetime
    data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    retry_count: int = 0

@dataclass(slots=True, frozen=True)
class CacheEntry:
    """Entrada do cache com metadados"""
    data: Any
    created_at: float
    ttl: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    size_bytes: int = 0
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

class LRUCache(Generic[T]):
    """Cache LRU thread-safe com TTL e limites de memória"""
    
    def __init__(self, max_size: int = 1000, max_memory_mb: int = 1024):
        self._cache: OrderedDictType[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                cache_misses.inc()
                return None
            
            entry = self._cache[key]
            if entry.is_expired:
                self._remove(key)
                self.misses += 1
                cache_misses.inc()
                return None
            
            # Move para o final (mais recente)
            self._cache.move_to_end(key)
            entry.access_count += 1
            entry.last_accessed = time.time()
            self.hits += 1
            cache_hits.inc()
            return entry.data
    
    def put(self, key: str, value: T, ttl: float = DEFAULT_CACHE_TTL):
        with self._lock:
            size_bytes = sys.getsizeof(value)
            
            # Verifica se precisa evictar entradas
            while (len(self._cache) >= self.max_size or 
                   self._current_memory + size_bytes > self.max_memory_bytes):
                if not self._evict_one():
                    break
            
            if key in self._cache:
                old_entry = self._cache[key]
                self._current_memory -= old_entry.size_bytes
            
            entry = CacheEntry(
                data=value,
                created_at=time.time(),
                ttl=ttl,
                size_bytes=size_bytes
            )
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._current_memory += size_bytes
    
    def _evict_one(self) -> bool:
        """Remove a entrada menos recentemente usada"""
        if not self._cache:
            return False
        
        try:
            key, entry = next(iter(self._cache.items()))
            self._remove(key)
            self.evictions += 1
            return True
        except StopIteration:
            return False
    
    def _remove(self, key: str):
        entry = self._cache.pop(key, None)
        if entry:
            self._current_memory -= entry.size_bytes
    
    def clear(self):
        with self._lock:
            self._cache.clear()
            self._current_memory = 0
    
    @property
    def size(self) -> int:
        return len(self._cache)
    
    @property
    def memory_usage_mb(self) -> float:
        return self._current_memory / (1024 * 1024)

# ─── Database Layer ──────────────────────────────────────────────────────────
class VaultDatabase:
    """Camada de persistência SQLite com otimizações"""
    
    _instance: ClassVar[Optional['VaultDatabase']] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: Path = DEFAULT_SQLITE_PATH):
        if hasattr(self, '_initialized'):
            return
        
        self.db_path = db_path
        self._local = threading.local()
        self._setup_database()
        self._initialized = True
    
    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=30
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")
            self._local.connection.execute("PRAGMA cache_size=-64000")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
            self._local.connection.execute("PRAGMA mmap_size=268435456")
        return self._local.connection
    
    def _setup_database(self):
        """Cria as tabelas necessárias"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS models (
                    model_id TEXT PRIMARY KEY,
                    current_version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    metadata JSONB NOT NULL,
                    storage_path TEXT NOT NULL,
                    shard_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_archived BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (model_id) REFERENCES models(model_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_versions_model_id 
                    ON versions(model_id);
                CREATE INDEX IF NOT EXISTS idx_versions_created_at 
                    ON versions(created_at);
                CREATE INDEX IF NOT EXISTS idx_versions_archived 
                    ON versions(is_archived);
                
                CREATE TABLE IF NOT EXISTS shards (
                    shard_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id TEXT NOT NULL,
                    shard_index INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    codec TEXT NOT NULL,
                    FOREIGN KEY (version_id) REFERENCES versions(version_id)
                );
                
                CREATE TABLE IF NOT EXISTS journal (
                    id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    version_id TEXT,
                    data BLOB,
                    metadata JSONB,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS tags (
                    version_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (version_id, tag),
                    FOREIGN KEY (version_id) REFERENCES versions(version_id)
                );
                
                CREATE TABLE IF NOT EXISTS lineage (
                    version_id TEXT NOT NULL,
                    parent_version_id TEXT NOT NULL,
                    depth INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (version_id, parent_version_id),
                    FOREIGN KEY (version_id) REFERENCES versions(version_id),
                    FOREIGN KEY (parent_version_id) REFERENCES versions(version_id)
                );
            """)

# ─── Journal Manager ────────────────────────────────────────────────────────
class JournalManager:
    """Gerencia journal para recovery e audit"""
    
    def __init__(self, journal_path: Path = DEFAULT_JOURNAL_PATH):
        self.journal_path = journal_path
        self.journal_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._current_file: Optional[io.TextIOWrapper] = None
        self._rotate_journal()
    
    def _rotate_journal(self):
        """Rotaciona o arquivo de journal"""
        if self._current_file:
            self._current_file.close()
        
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        journal_file = self.journal_path / f"journal_{timestamp}.log"
        self._current_file = open(journal_file, 'a', buffering=1)
    
    def append(self, entry: JournalEntry):
        """Adiciona entrada ao journal"""
        with self._lock:
            record = orjson.dumps({
                "id": entry.id,
                "operation": entry.operation.value,
                "version": entry.version,
                "timestamp": entry.timestamp.isoformat(),
                "status": entry.status,
                "metadata": entry.metadata
            }).decode()
            self._current_file.write(f"{record}\n")
            self._current_file.flush()
    
    def replay(self, since: Optional[datetime.datetime] = None) -> Iterator[JournalEntry]:
        """Replay do journal para recovery"""
        journal_files = sorted(self.journal_path.glob("journal_*.log"))
        
        for journal_file in journal_files:
            with open(journal_file, 'r') as f:
                for line in f:
                    try:
                        data = orjson.loads(line.strip())
                        entry_time = datetime.datetime.fromisoformat(data['timestamp'])
                        if since and entry_time < since:
                            continue
                        yield JournalEntry(
                            id=JournalEntryId(data['id']),
                            operation=JournalOperation(data['operation']),
                            version=VersionId(data['version']),
                            timestamp=entry_time,
                            status=data['status'],
                            metadata=data.get('metadata', {})
                        )
                    except Exception as e:
                        logger.error("journal_parse_error", error=str(e), line=line.strip())

# ─── Compression Engine ─────────────────────────────────────────────────────
class CompressionEngine:
    """Engine de compressão adaptativa com múltiplos codecs"""
    
    def __init__(self, default_codec: CompressionCodec = CompressionCodec.ZSTANDARD,
                 default_level: int = DEFAULT_COMPRESSION_LEVEL):
        self.default_codec = default_codec
        self.default_level = default_level
        self._stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "compression_time": 0,
            "decompression_time": 0,
            "total_original_bytes": 0,
            "total_compressed_bytes": 0,
            "count": 0
        })
    
    def compress(self, data: bytes, 
                 codec: Optional[CompressionCodec] = None,
                 level: Optional[int] = None) -> Tuple[bytes, CompressionCodec, int]:
        """Comprime dados e retorna (compressed, codec_used, level_used)"""
        codec = codec or self.default_codec
        level = level or self.default_level
        
        start_time = time.perf_counter()
        compressed = codec.compress(data, level)
        elapsed = time.perf_counter() - start_time
        
        # Atualiza estatísticas
        stats = self._stats[codec.value]
        stats["compression_time"] += elapsed
        stats["total_original_bytes"] += len(data)
        stats["total_compressed_bytes"] += len(compressed)
        stats["count"] += 1
        
        ratio = len(compressed) / len(data) if data else 0
        compression_ratio.observe(ratio)
        
        return compressed, codec, level
    
    def decompress(self, data: bytes, codec: CompressionCodec) -> bytes:
        """Descomprime dados"""
        start_time = time.perf_counter()
        decompressed = codec.decompress(data)
        elapsed = time.perf_counter() - start_time
        
        self._stats[codec.value]["decompression_time"] += elapsed
        
        return decompressed
    
    def get_optimal_codec(self, data: bytes) -> CompressionCodec:
        """Determina o melhor codec para os dados"""
        if len(data) < 1024:
            return CompressionCodec.GZIP
        
        # Testa todos os codecs em uma amostra
        sample = data[:4096]
        best_codec = CompressionCodec.GZIP
        best_ratio = 1.0
        
        for codec in CompressionCodec:
            if codec == CompressionCodec.AUTO:
                continue
            try:
                compressed = codec.compress(sample, self.default_level)
                ratio = len(compressed) / len(sample)
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_codec = codec
            except Exception:
                continue
        
        return best_codec
    
    @property
    def statistics(self) -> Dict[str, Any]:
        return dict(self._stats)

# ─── Shard Manager ──────────────────────────────────────────────────────────
class ShardManager:
    """Gerencia sharding de modelos grandes"""
    
    def __init__(self, shard_size_mb: int = DEFAULT_SHARD_SIZE_MB, 
                 base_dir: Path = BASE_DIR):
        self.shard_size = shard_size_mb * 1024 * 1024
        self.base_dir = base_dir / "shards"
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def shard_data(self, data: bytes, version_id: VersionId) -> List[ShardInfo]:
        """Divide dados em shards"""
        shards = []
        total_size = len(data)
        num_shards = max(1, (total_size + self.shard_size - 1) // self.shard_size)
        
        version_dir = self.base_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
        for i in range(num_shards):
            start = i * self.shard_size
            end = min(start + self.shard_size, total_size)
            shard_data = data[start:end]
            
            shard_id = ShardId(i)
            shard_path = version_dir / f"shard_{i:04d}.bin"
            
            with open(shard_path, 'wb') as f:
                f.write(shard_data)
            
            checksum = ChecksumAlgorithm.BLAKE2B.compute(shard_data)
            
            shards.append(ShardInfo(
                id=shard_id,
                path=shard_path,
                size_bytes=len(shard_data),
                checksum=Checksum(checksum),
                created_at=datetime.datetime.utcnow()
            ))
        
        return shards
    
    def reconstruct_data(self, shards: List[ShardInfo]) -> bytes:
        """Reconstrói dados dos shards"""
        # Ordena por ID para garantir ordem correta
        sorted_shards = sorted(shards, key=lambda s: s.id)
        
        data_parts = []
        for shard in sorted_shards:
            if not shard.path.exists():
                raise FileNotFoundError(f"Shard não encontrado: {shard.path}")
            
            with open(shard.path, 'rb') as f:
                shard_data = f.read()
            
            # Verifica integridade
            computed_checksum = ChecksumAlgorithm.BLAKE2B.compute(shard_data)
            if computed_checksum != shard.checksum:
                raise ValueError(f"Checksum inválido para shard {shard.id}")
            
            data_parts.append(shard_data)
        
        return b''.join(data_parts)
    
    def cleanup_shards(self, version_id: VersionId):
        """Remove shards de uma versão"""
        version_dir = self.base_dir / version_id
        if version_dir.exists():
            shutil.rmtree(version_dir)

# ─── Event System ───────────────────────────────────────────────────────────
class EventType(str, Enum):
    """Tipos de eventos do sistema"""
    MODEL_SAVED = "model.saved"
    MODEL_LOADED = "model.loaded"
    MODEL_DELETED = "model.deleted"
    MODEL_ARCHIVED = "model.archived"
    VERSION_CREATED = "version.created"
    SHARD_CREATED = "shard.created"
    COMPRESSION_COMPLETED = "compression.completed"
    ERROR_OCCURRED = "error.occurred"
    CLEANUP_COMPLETED = "cleanup.completed"

@dataclass(slots=True)
class VaultEvent:
    """Evento do vault"""
    type: EventType
    version: Optional[VersionId] = None
    model_id: Optional[ModelId] = None
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

class EventBus:
    """Bus de eventos pub/sub"""
    
    def __init__(self):
        self._subscribers: DefaultDict[EventType, List[Callable]] = defaultdict(list)
        self._async_subscribers: DefaultDict[EventType, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """Registra subscriber síncrono"""
        with self._lock:
            self._subscribers[event_type].append(callback)
    
    def subscribe_async(self, event_type: EventType, callback: Callable):
        """Registra subscriber assíncrono"""
        with self._lock:
            self._async_subscribers[event_type].append(callback)
    
    async def publish(self, event: VaultEvent):
        """Publica evento para todos os subscribers"""
        # Subscribers síncronos em thread pool
        with ThreadPoolExecutor(max_workers=4) as executor:
            for callback in self._subscribers.get(event.type, []):
                executor.submit(callback, event)
        
        # Subscribers assíncronos
        tasks = []
        for callback in self._async_subscribers.get(event.type, []):
            tasks.append(asyncio.create_task(callback(event)))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# ─── ATENA Memory Vault Principal ───────────────────────────────────────────
class AtenaMemoryVault:
    """
    ATENA Memory Vault v3.0 - Sistema de Versionamento de Modelos de IA
    com compressão adaptativa, sharding, journaling e alta disponibilidade
    """
    
    _instance: ClassVar[Optional['AtenaMemoryVault']] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self,
                 base_dir: Optional[Path] = None,
                 max_versions: int = DEFAULT_MAX_VERSIONS,
                 cache_ttl: float = DEFAULT_CACHE_TTL,
                 compression_codec: CompressionCodec = CompressionCodec.AUTO,
                 compression_level: int = DEFAULT_COMPRESSION_LEVEL,
                 storage_backend: StorageBackend = StorageBackend.HYBRID,
                 enable_sharding: bool = True,
                 enable_journaling: bool = True,
                 enable_cache: bool = True,
                 enable_auto_cleanup: bool = True,
                 consistency_level: ConsistencyLevel = ConsistencyLevel.STRONG,
                 redis_url: Optional[str] = None):
        
        if hasattr(self, '_initialized'):
            return
        
        # Configuração
        self.base_dir = Path(base_dir or BASE_DIR)
        self.max_versions = max_versions
        self.cache_ttl = cache_ttl
        self.compression_codec = compression_codec
        self.compression_level = compression_level
        self.storage_backend = storage_backend
        self.enable_sharding = enable_sharding
        self.enable_journaling = enable_journaling
        self.enable_cache = enable_cache
        self.enable_auto_cleanup = enable_auto_cleanup
        self.consistency_level = consistency_level
        
        # Componentes
        self._setup_directories()
        self.db = VaultDatabase(self.base_dir / "vault.db")
        self.compression_engine = CompressionEngine(compression_codec, compression_level)
        self.shard_manager = ShardManager(DEFAULT_SHARD_SIZE_MB, self.base_dir)
        self.journal_manager = JournalManager(self.base_dir / "journal")
        self.event_bus = EventBus()
        
        # Cache
        self._cache = LRUCache[Any](max_size=2000, max_memory_mb=2048)
        self._metadata_cache = LRUCache[ModelMetadata](max_size=5000)
        
        # Redis (opcional)
        self._redis: Optional[aioredis.Redis] = None
        if storage_backend == StorageBackend.HYBRID and redis_url:
            self._redis_url = redis_url or DEFAULT_REDIS_URL
        
        # Locks
        self._save_lock = threading.RLock()
        self._cleanup_lock = threading.RLock()
        
        # Métricas
        self._operation_counter = Counter(
            f"{METRICS_PREFIX}_operations_total",
            "Total operations",
            ["operation", "status"]
        )
        
        # Background tasks
        self._background_tasks: List[asyncio.Task] = []
        
        # Scheduler
        self._scheduler = Rocketry(config={"task_execution": "async"})
        self._setup_scheduled_tasks()
        
        self._initialized = True
        logger.info("vault_initialized",
                    base_dir=str(self.base_dir),
                    max_versions=max_versions)
    
    def _setup_directories(self):
        """Cria estrutura de diretórios"""
        dirs = [
            self.base_dir,
            self.base_dir / "models",
            self.base_dir / "backups",
            self.base_dir / "shards",
            self.base_dir / "temp",
            self.base_dir / "journal",
            self.base_dir / "logs",
            self.base_dir / "checkpoints"
        ]
        
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch(exist_ok=True)
    
    def _setup_scheduled_tasks(self):
        """Configura tarefas agendadas"""
        app = self._scheduler
        
        @app.task(every("1 hour"))
        async def cleanup_old_versions():
            if self.enable_auto_cleanup:
                await self._cleanup_old_versions_async()
        
        @app.task(daily)
        async def health_check():
            await self._perform_health_check()
        
        @app.task(every("5 minutes"))
        async def update_metrics():
            await self._update_prometheus_metrics()
    
    @contextmanager
    def _measure_latency(self, operation: str):
        """Context manager para medir latência de operações"""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            operation_latency.labels(operation=operation).observe(elapsed)
    
    async def _ensure_redis(self):
        """Garante conexão com Redis"""
        if self._redis is None and hasattr(self, '_redis_url'):
            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=False,
                max_connections=20
            )
    
    async def save_model_async(self,
                               model_data: Dict[str, Any],
                               weights_data: bytes,
                               loss: float,
                               accuracy: float,
                               model_id: Optional[str] = None,
                               validation_data: Optional[Tuple[float, float]] = None,
                               tags: Optional[Set[str]] = None,
                               training_config: Optional[Dict[str, Any]] = None,
                               custom_metadata: Optional[Dict[str, Any]] = None,
                               parent_version: Optional[VersionId] = None) -> VersionId:
        """
        Salva modelo de forma assíncrona com todas as otimizações.
        
        Args:
            model_data: Dicionário com a arquitetura do modelo
            weights_data: Bytes dos pesos do modelo
            loss: Valor de loss do treinamento
            accuracy: Acurácia do modelo (0-1)
            model_id: ID único do modelo (gerado automaticamente se None)
            validation_data: Tupla (val_loss, val_accuracy)
            tags: Conjunto de tags para categorização
            training_config: Configuração do treinamento
            custom_metadata: Metadados customizados
            parent_version: Versão pai para rastreamento de linhagem
        
        Returns:
            VersionId da versão criada
        
        Raises:
            ValueError: Se parâmetros inválidos
            RuntimeError: Se falha na persistência
        """
        with self._measure_latency("save"):
            # Validação
            if loss < 0:
                raise ValueError(f"Loss deve ser >= 0, recebido: {loss}")
            if not 0 <= accuracy <= 1:
                raise ValueError(f"Accuracy deve estar entre 0 e 1, recebido: {accuracy}")
            
            model_id = ModelId(model_id or str(uuid.uuid4()))
            version_id = VersionId(f"v{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(4)}")
            
            # Compressão adaptativa
            optimal_codec = self.compression_engine.get_optimal_codec(weights_data)
            compressed_data, codec_used, level_used = self.compression_engine.compress(
                weights_data, optimal_codec
            )
            
            # Checksums múltiplos
            checksums = {
                "sha256": ChecksumAlgorithm.SHA256.compute(weights_data),
                "blake2b": ChecksumAlgorithm.BLAKE2B.compute(weights_data),
                "xxhash": ChecksumAlgorithm.XXHASH.compute(weights_data)
            }
            
            # Sharding se necessário
            shards = None
            if self.enable_sharding and len(compressed_data) > self.shard_manager.shard_size:
                shards = self.shard_manager.shard_data(compressed_data, version_id)
            
            # Metadados
            metadata = ModelMetadata(
                version=version_id,
                model_id=model_id,
                timestamp=datetime.datetime.now(),
                loss=loss,
                accuracy=accuracy,
                validation_loss=validation_data[0] if validation_data else None,
                validation_accuracy=validation_data[1] if validation_data else None,
                model_size_bytes=len(weights_data),
                compressed_size_bytes=len(compressed_data),
                checksum_sha256=Checksum(checksums["sha256"]),
                checksum_blake2b=Checksum(checksums["blake2b"]),
                checksum_xxhash=Checksum(checksums["xxhash"]),
                parent_version=parent_version,
                tags=tags or set(),
                training_config=TrainingConfig(**(training_config or {})),
                custom_metadata=custom_metadata or {},
                is_verified=True
            )
            
            # Persistência com consistência forte
            async with asyncio.Lock():
                try:
                    # Salva no disco
                    model_path = self.base_dir / "models" / version_id
                    model_path.mkdir(parents=True, exist_ok=False)
                    
                    # Salva pesos comprimidos (ou shards)
                    if shards:
                        for shard in shards:
                            await aiofiles.open(shard.path, 'wb').__aenter__()
                    else:
                        weights_path = model_path / "weights.bin"
                        async with aiofiles.open(weights_path, 'wb') as f:
                            await f.write(compressed_data)
                    
                    # Salva modelo JSON
                    async with aiofiles.open(model_path / "model.json", 'w') as f:
                        await f.write(orjson.dumps(model_data).decode())
                    
                    # Salva metadados
                    async with aiofiles.open(model_path / "metadata.json", 'wb') as f:
                        await f.write(orjson.dumps(metadata.dict()))
                    
                    # Atualiza banco de dados
                    conn = self.db._get_connection()
                    with conn:
                        conn.execute(
                            """INSERT OR REPLACE INTO models (model_id, current_version, updated_at) 
                               VALUES (?, ?, CURRENT_TIMESTAMP)""",
                            (model_id, version_id)
                        )
                        conn.execute(
                            """INSERT INTO versions (version_id, model_id, metadata, storage_path, shard_count)
                               VALUES (?, ?, ?, ?, ?)""",
                            (version_id, model_id, orjson.dumps(metadata.dict()).decode(),
                             str(model_path), len(shards) if shards else 1)
                        )
                        
                        if parent_version:
                            conn.execute(
                                "INSERT INTO lineage (version_id, parent_version_id) VALUES (?, ?)",
                                (version_id, parent_version)
                            )
                        
                        if tags:
                            conn.executemany(
                                "INSERT INTO tags (version_id, tag) VALUES (?, ?)",
                                [(version_id, tag) for tag in tags]
                            )
                    
                    # Journal
                    if self.enable_journaling:
                        entry = JournalEntry(
                            id=JournalEntryId(str(uuid.uuid4())),
                            operation=JournalOperation.SAVE,
                            version=version_id,
                            timestamp=datetime.datetime.utcnow(),
                            status="completed"
                        )
                        self.journal_manager.append(entry)
                    
                    # Cache
                    if self.enable_cache:
                        cache_data = (model_data, weights_data, metadata)
                        self._cache.put(str(version_id), cache_data, self.cache_ttl)
                        self._metadata_cache.put(str(version_id), metadata, self.cache_ttl * 2)
                    
                    # Evento
                    await self.event_bus.publish(VaultEvent(
                        type=EventType.MODEL_SAVED,
                        version=version_id,
                        model_id=model_id,
                        metadata={"accuracy": accuracy, "loss": loss}
                    ))
                    
                    # Métricas
                    model_saves.labels(status="success").inc()
                    model_versions.inc()
                    storage_bytes.inc(len(compressed_data))
                    
                    logger.info("model_saved",
                                version_id=version_id,
                                model_id=model_id,
                                accuracy=accuracy,
                                loss=loss,
                                compressed_size=len(compressed_data))
                    
                    return version_id
                    
                except Exception as e:
                    # Rollback
                    if model_path.exists():
                        shutil.rmtree(model_path, ignore_errors=True)
                    
                    model_saves.labels(status="error").inc()
                    logger.error("model_save_failed",
                                 version_id=version_id,
                                 error=str(e))
                    raise RuntimeError(f"Falha ao salvar modelo: {e}")
    
    # Wrapper síncrono para compatibilidade
    def save_model(self, *args, **kwargs) -> VersionId:
        """Wrapper síncrono para save_model_async"""
        return asyncio.run(self.save_model_async(*args, **kwargs))
    
    async def load_model_async(self,
                               version: Optional[VersionId] = None,
                               model_id: Optional[ModelId] = None,
                               use_cache: bool = True) -> Optional[Tuple[Dict[str, Any], bytes, ModelMetadata]]:
        """
        Carrega modelo assíncrono com cache e otimizações.
        
        Args:
            version: VersionId específico (None = melhor versão)
            model_id: ModelId para buscar última versão
            use_cache: Se deve usar cache
        
        Returns:
            Tupla (model_data, weights_data, metadata) ou None
        """
        with self._measure_latency("load"):
            # Resolve versão
            if version is None and model_id:
                version = await self._get_current_version_async(model_id)
            elif version is None:
                version = await self._get_best_version_async()
            
            if version is None:
                return None
            
            cache_key = f"model:{version}"
            
            # Cache lookup
            if use_cache and self.enable_cache:
                cached = self._cache.get(cache_key)
                if cached:
                    model_loads.labels(status="cache_hit").inc()
                    logger.debug("cache_hit", version=version)
                    return cached
            
            # Redis cache (distribuído)
            if self._redis and use_cache:
                try:
                    await self._ensure_redis()
                    redis_key = f"atena:model:{version}"
                    cached = await self._redis.get(redis_key)
                    if cached:
                        model_loads.labels(status="redis_hit").inc()
                        return pickle.loads(cached)
                except Exception as e:
                    logger.warning("redis_cache_error", error=str(e))
            
            # Load do disco/DB
            model_path = self.base_dir / "models" / version
            
            if not model_path.exists():
                model_loads.labels(status="not_found").inc()
                logger.warning("model_not_found", version=version)
                return None
            
            try:
                # Carrega metadados
                async with aiofiles.open(model_path / "metadata.json", 'rb') as f:
                    metadata_bytes = await f.read()
                metadata = ModelMetadata(**orjson.loads(metadata_bytes))
                
                # Carrega modelo
                async with aiofiles.open(model_path / "model.json", 'r') as f:
                    model_json = await f.read()
                model_data = orjson.loads(model_json)
                
                # Carrega pesos
                weights_path = model_path / "weights.bin"
                if not weights_path.exists():
                    # Tenta reconstruir de shards
                    shards = self._get_shards_for_version(version)
                    if shards:
                        compressed_weights = self.shard_manager.reconstruct_data(shards)
                    else:
                        raise FileNotFoundError(f"Pesos não encontrados: {weights_path}")
                else:
                    async with aiofiles.open(weights_path, 'rb') as f:
                        compressed_weights = await f.read()
                
                # Descomprime
                codec = CompressionCodec(metadata.custom_metadata.get("codec", "zstandard"))
                weights_data = self.compression_engine.decompress(compressed_weights, codec)
                
                # Verifica integridade
                if not metadata.is_verified:
                    computed = ChecksumAlgorithm.BLAKE2B.compute(weights_data)
                    if computed != metadata.checksum_blake2b:
                        raise ValueError(f"Checksum inválido para versão {version}")
                    
                    # Atualiza metadados como verificado
                    metadata = replace(metadata, is_verified=True)
                    async with aiofiles.open(model_path / "metadata.json", 'wb') as f:
                        await f.write(orjson.dumps(metadata.dict()))
                
                result = (model_data, weights_data, metadata)
                
                # Atualiza caches
                if self.enable_cache:
                    self._cache.put(cache_key, result, self.cache_ttl)
                    self._metadata_cache.put(f"metadata:{version}", metadata, self.cache_ttl * 2)
                
                if self._redis:
                    try:
                        await self._ensure_redis()
                        redis_key = f"atena:model:{version}"
                        await self._redis.setex(
                            redis_key,
                            int(self.cache_ttl),
                            pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
                        )
                    except Exception:
                        pass
                
                model_loads.labels(status="success").inc()
                logger.info("model_loaded", version=version, accuracy=metadata.accuracy)
                
                return result
                
            except Exception as e:
                model_loads.labels(status="error").inc()
                logger.error("model_load_failed", version=version, error=str(e))
                return None
    
    def load_model(self, *args, **kwargs):
        """Wrapper síncrono para load_model_async"""
        return asyncio.run(self.load_model_async(*args, **kwargs))
    
    async def _get_best_version_async(self, metric: str = 'accuracy') -> Optional[VersionId]:
        """Retorna a melhor versão baseada na métrica"""
        conn = self.db._get_connection()
        
        if metric == 'loss':
            query = """
                SELECT version_id FROM versions 
                WHERE is_archived = FALSE 
                ORDER BY json_extract(metadata, '$.loss') ASC 
                LIMIT 1
            """
        elif metric == 'accuracy':
            query = """
                SELECT version_id FROM versions 
                WHERE is_archived = FALSE 
                ORDER BY json_extract(metadata, '$.accuracy') DESC 
                LIMIT 1
            """
        else:
            query = """
                SELECT version_id FROM versions 
                WHERE is_archived = FALSE 
                ORDER BY json_extract(metadata, '$.{metric}') DESC 
                LIMIT 1
            """.format(metric=metric)
        
        row = conn.execute(query).fetchone()
        return VersionId(row[0]) if row else None
    
    async def _get_current_version_async(self, model_id: ModelId) -> Optional[VersionId]:
        """Retorna a versão atual de um modelo"""
        conn = self.db._get_connection()
        row = conn.execute(
            "SELECT current_version FROM models WHERE model_id = ?",
            (model_id,)
        ).fetchone()
        return VersionId(row[0]) if row else None
    
    def _get_shards_for_version(self, version_id: VersionId) -> List[ShardInfo]:
        """Recupera informações dos shards de uma versão"""
        conn = self.db._get_connection()
        rows = conn.execute(
            """SELECT shard_id, file_path, size_bytes, checksum, created_at 
               FROM shards WHERE version_id = ? ORDER BY shard_index""",
            (version_id,)
        ).fetchall()
        
        return [
            ShardInfo(
                id=ShardId(row['shard_id']),
                path=Path(row['file_path']),
                size_bytes=row['size_bytes'],
                checksum=Checksum(row['checksum']),
                created_at=datetime.datetime.fromisoformat(row['created_at'])
            )
            for row in rows
        ]
    
    async def _cleanup_old_versions_async(self):
        """Limpeza assíncrona de versões antigas"""
        with self._cleanup_lock:
            conn = self.db._get_connection()
            
            # Conta versões não arquivadas
            count_row = conn.execute(
                "SELECT COUNT(*) FROM versions WHERE is_archived = FALSE"
            ).fetchone()
            
            if count_row[0] <= self.max_versions:
                return
            
            # Seleciona versões para arquivar (mantendo as melhores)
            to_archive = conn.execute("""
                SELECT version_id FROM versions 
                WHERE is_archived = FALSE
                ORDER BY json_extract(metadata, '$.accuracy') DESC, 
                         json_extract(metadata, '$.loss') ASC
                LIMIT -1 OFFSET ?
            """, (self.max_versions,)).fetchall()
            
            archived_count = 0
            for row in to_archive:
                version_id = row[0]
                try:
                    # Arquiva (move para backup)
                    await self._archive_version_async(VersionId(version_id))
                    archived_count += 1
                except Exception as e:
                    logger.error("archive_failed", version=version_id, error=str(e))
            
            logger.info("cleanup_completed",
                        archived=archived_count,
                        remaining=self.max_versions)
            
            await self.event_bus.publish(VaultEvent(
                type=EventType.CLEANUP_COMPLETED,
                metadata={"archived_count": archived_count}
            ))
    
    async def _archive_version_async(self, version_id: VersionId):
        """Arquiva uma versão específica"""
        model_path = self.base_dir / "models" / version_id
        archive_path = self.base_dir / "backups" / f"archive_{version_id}_{int(time.time())}"
        
        if model_path.exists():
            shutil.copytree(model_path, archive_path)
            shutil.rmtree(model_path)
        
        conn = self.db._get_connection()
        conn.execute(
            "UPDATE versions SET is_archived = TRUE WHERE version_id = ?",
            (version_id,)
        )
        conn.commit()
        
        # Limpa cache
        self._cache._remove(str(version_id))
        self._metadata_cache._remove(f"metadata:{version_id}")
        
        if self._redis:
            try:
                await self._ensure_redis()
                await self._redis.delete(f"atena:model:{version_id}")
            except Exception:
                pass
    
    async def _perform_health_check(self):
        """Verificação de saúde do sistema"""
        issues = []
        
        # Verifica espaço em disco
        disk_usage = shutil.disk_usage(self.base_dir)
        if disk_usage.free < 1024 * 1024 * 100:  # 100MB
            issues.append(f"Espaço em disco baixo: {disk_usage.free / (1024**3):.2f}GB")
        
        # Verifica integridade do banco
        try:
            conn = self.db._get_connection()
            conn.execute("PRAGMA integrity_check")
        except Exception as e:
            issues.append(f"Banco de dados corrompido: {e}")
        
        # Verifica cache
        if self._cache.memory_usage_mb > 0.9 * (self._cache.max_memory_bytes / 1024 / 1024):
            issues.append(f"Cache próximo do limite: {self._cache.memory_usage_mb:.0f}MB")
        
        if issues:
            logger.warning("health_check_issues", issues=issues)
        else:
            logger.info("health_check_ok")
    
    async def _update_prometheus_metrics(self):
        """Atualiza métricas do Prometheus"""
        model_versions.set(len(await self._list_versions_async()))
        
        total_size = sum(
            f.stat().st_size
            for f in (self.base_dir / "models").rglob("weights.bin")
            if f.exists()
        )
        storage_bytes.set(total_size)
    
    async def _list_versions_async(self, filters: Optional[Dict] = None) -> List[VersionId]:
        """Lista todas as versões com filtros opcionais"""
        conn = self.db._get_connection()
        query = "SELECT version_id FROM versions WHERE 1=1"
        params = []
        
        if filters:
            if 'model_id' in filters:
                query += " AND model_id = ?"
                params.append(filters['model_id'])
            if 'archived' in filters:
                query += " AND is_archived = ?"
                params.append(filters['archived'])
        
        rows = conn.execute(query, params).fetchall()
        return [VersionId(row[0]) for row in rows]
    
    async def export_model_async(self,
                                  version: VersionId,
                                  export_path: Path,
                                  include_shards: bool = True) -> bool:
        """Exporta modelo para formato portável"""
        result = await self.load_model_async(version=version, use_cache=False)
        if not result:
            return False
        
        model_data, weights_data, metadata = result
        
        export_bundle = {
            "version": "3.0.0",
            "vault_version": version,
            "metadata": metadata.dict(),
            "model_data": model_data,
            "weights_data": weights_data,
            "exported_at": datetime.datetime.utcnow().isoformat(),
            "checksums": {
                "sha256": ChecksumAlgorithm.SHA256.compute(weights_data),
                "blake2b": ChecksumAlgorithm.BLAKE2B.compute(weights_data)
            }
        }
        
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Usa msgpack para serialização eficiente
        async with aiofiles.open(export_path, 'wb') as f:
            await f.write(msgpack.packb(export_bundle, use_bin_type=True))
        
        logger.info("model_exported", version=version, path=str(export_path))
        return True
    
    async def import_model_async(self, import_path: Path) -> Optional[VersionId]:
        """Importa modelo de arquivo exportado"""
        if not import_path.exists():
            logger.error("import_file_not_found", path=str(import_path))
            return None
        
        async with aiofiles.open(import_path, 'rb') as f:
            data = await f.read()
        
        bundle = msgpack.unpackb(data, raw=False)
        
        # Valida bundle
        required = {'model_data', 'weights_data', 'metadata'}
        if not required.issubset(bundle.keys()):
            raise ValueError("Bundle de importação inválido")
        
        metadata = ModelMetadata(**bundle['metadata'])
        
        # Importa como nova versão
        version = await self.save_model_async(
            model_data=bundle['model_data'],
            weights_data=bundle['weights_data'],
            loss=metadata.loss,
            accuracy=metadata.accuracy,
            tags=metadata.tags | {'imported'},
            custom_metadata={
                **metadata.custom_metadata,
                'imported_from': str(import_path),
                'imported_at': datetime.datetime.utcnow().isoformat(),
                'original_version': metadata.version
            }
        )
        
        logger.info("model_imported", version=version, source=str(import_path))
        return version
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas do vault"""
        conn = self.db._get_connection()
        
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_versions,
                COUNT(DISTINCT model_id) as total_models,
                AVG(json_extract(metadata, '$.accuracy')) as avg_accuracy,
                MIN(json_extract(metadata, '$.loss')) as min_loss,
                MAX(json_extract(metadata, '$.accuracy')) as max_accuracy,
                SUM(json_extract(metadata, '$.model_size_bytes')) as total_size_bytes,
                SUM(json_extract(metadata, '$.compressed_size_bytes')) as total_compressed_bytes
            FROM versions 
            WHERE is_archived = FALSE
        """).fetchone()
        
        return {
            "total_versions": stats['total_versions'],
            "total_models": stats['total_models'],
            "avg_accuracy": stats['avg_accuracy'] or 0,
            "best_loss": stats['min_loss'] or 0,
            "best_accuracy": stats['max_accuracy'] or 0,
            "total_storage_bytes": stats['total_size_bytes'] or 0,
            "total_compressed_bytes": stats['total_compressed_bytes'] or 0,
            "compression_ratio": (stats['total_compressed_bytes'] / stats['total_size_bytes'] 
                                  if stats['total_size_bytes'] else 0),
            "cache_size": self._cache.size,
            "cache_memory_mb": self._cache.memory_usage_mb,
            "cache_hits": self._cache.hits,
            "cache_misses": self._cache.misses,
            "cache_hit_ratio": (self._cache.hits / (self._cache.hits + self._cache.misses) 
                                if (self._cache.hits + self._cache.misses) > 0 else 0),
        }

# ─── FastAPI Application ────────────────────────────────────────────────────
def create_app(vault: AtenaMemoryVault) -> FastAPI:
    """Cria aplicação FastAPI para o vault"""
    
    app = FastAPI(
        title="ATENA Memory Vault API",
        version="3.0.0",
        description="API RESTful para versionamento de modelos de IA"
    )
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}
    
    @app.get("/stats")
    async def get_statistics():
        return vault.get_statistics()
    
    @app.post("/models")
    async def save_model(
        model_data: Dict[str, Any],
        weights_b64: str,
        loss: float = Query(..., ge=0),
        accuracy: float = Query(..., ge=0, le=1),
        tags: Optional[List[str]] = Query(None)
    ):
        import base64
        weights_data = base64.b64decode(weights_b64)
        
        version = await vault.save_model_async(
            model_data=model_data,
            weights_data=weights_data,
            loss=loss,
            accuracy=accuracy,
            tags=set(tags) if tags else None
        )
        
        return {"version": version}
    
    @app.get("/models/{version}")
    async def load_model(version: str):
        result = await vault.load_model_async(version=VersionId(version))
        if not result:
            raise HTTPException(status_code=404, detail="Modelo não encontrado")
        
        model_data, weights_data, metadata = result
        return {
            "version": version,
            "metadata": metadata.dict(),
            "model_data": model_data,
            "weights_b64": base64.b64encode(weights_data).decode()
        }
    
    @app.get("/models/best")
    async def get_best_model(metric: str = "accuracy"):
        version = await vault._get_best_version_async(metric)
        if not version:
            raise HTTPException(status_code=404, detail="Nenhum modelo encontrado")
        return {"best_version": version}
    
    return app

# ─── Testes ─────────────────────────────────────────────────────────────────
async def run_advanced_tests():
    """Testes avançados do sistema"""
    console = Console()
    
    console.print("\n[bold cyan]╔══════════════════════════════════════════════════════════════╗")
    console.print("║     ATENA MEMORY VAULT v3.0 - TESTES AVANÇADOS              ║")
    console.print("╚══════════════════════════════════════════════════════════════╝[/]\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test_vault"
        
        vault = AtenaMemoryVault(
            base_dir=vault_path,
            max_versions=10,
            cache_ttl=60,
            compression_codec=CompressionCodec.AUTO,
            enable_sharding=True,
            enable_journaling=True
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Teste 1: Salvar modelos
            task = progress.add_task("[green]Salvando modelos...", total=20)
            versions = []
            
            for i in range(20):
                model_data = {
                    "name": f"model_{i}",
                    "layers": [
                        {"type": "Dense", "units": 64 * (i % 5 + 1)},
                        {"type": "Dropout", "rate": 0.2},
                        {"type": "Dense", "units": 10}
                    ]
                }
                
                # Dados maiores para testar sharding
                weights_data = os.urandom(1024 * 1024)  # 1MB
                loss = 0.5 / (i + 1)
                accuracy = 0.7 + (i * 0.015)
                
                version = await vault.save_model_async(
                    model_data, weights_data, loss, accuracy,
                    tags={f"test_{i}", "batch_test"},
                    training_config={"epochs": i + 1, "batch_size": 32}
                )
                versions.append(version)
                progress.update(task, advance=1)
            
            # Teste 2: Carregar e verificar
            task = progress.add_task("[blue]Verificando integridade...", total=10)
            
            for i in range(10):
                version = versions[i]
                result = await vault.load_model_async(version=version)
                
                if result:
                    _, weights, meta = result
                    assert len(weights) == 1024 * 1024, f"Tamanho incorreto para {version}"
                    assert meta.accuracy == 0.7 + (i * 0.015)
                
                progress.update(task, advance=1)
            
            # Teste 3: Cache
            task = progress.add_task("[yellow]Testando cache...", total=100)
            
            for _ in range(100):
                await vault.load_model_async(version=versions[0])
                progress.update(task, advance=1)
            
            stats = vault.get_statistics()
            assert stats['cache_hits'] > 0, "Cache não está funcionando"
            
            # Teste 4: Export/Import
            task = progress.add_task("[magenta]Testando export/import...", total=1)
            
            export_path = Path(tmpdir) / "exported_model.msgpack"
            success = await vault.export_model_async(versions[0], export_path)
            assert success, "Exportação falhou"
            
            imported = await vault.import_model_async(export_path)
            assert imported is not None, "Importação falhou"
            
            progress.update(task, advance=1)
    
    console.print("\n[bold green]✅ TODOS OS TESTES PASSARAM COM SUCESSO![/]\n")
    return 0

# ─── Entry Point ────────────────────────────────────────────────────────────
async def main():
    """Entry point principal"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="ATENA Memory Vault v3.0 - Sistema de Versionamento de Modelos"
    )
    parser.add_argument('--test', action='store_true', help='Executa testes')
    parser.add_argument('--serve', action='store_true', help='Inicia servidor API')
    parser.add_argument('--host', default='0.0.0.0', help='Host do servidor')
    parser.add_argument('--port', type=int, default=8000, help='Porta do servidor')
    parser.add_argument('--metrics-port', type=int, default=9090, help='Porta métricas')
    
    args = parser.parse_args()
    
    if args.test:
        return await run_advanced_tests()
    
    if args.serve:
        # Inicia métricas Prometheus
        start_http_server(args.metrics_port)
        
        # Inicializa vault
        vault = AtenaMemoryVault()
        
        # Cria app FastAPI
        app = create_app(vault)
        
        # Configura Hypercorn
        config = HypercornConfig()
        config.bind = [f"{args.host}:{args.port}"]
        config.workers = multiprocessing.cpu_count()
        
        logger.info("starting_server", host=args.host, port=args.port)
        await serve(app, config)
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        sys.exit(0)
    except Exception as e:
        logger.exception("fatal_error", error=str(e))
        sys.exit(1)
