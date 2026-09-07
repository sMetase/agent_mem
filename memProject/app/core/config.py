# -*- coding: utf-8 -*-
"""
核心配置模块 — 读取 YAML + 环境变量，提供统一配置访问。
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 按优先级查找 .env：项目根目录 → 当前工作目录
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"
if not _env_path.exists():
    _env_path = Path.cwd().parent / ".env"
load_dotenv(_env_path)


class AppConfig(BaseSettings):
    name: str = "Agent Memory System"
    version: str = "1.0.0"
    debug: bool = True
    secret_key: str = ""


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1


class DatabaseConfig(BaseSettings):
    driver: str = "postgresql+asyncpg"
    host: str = "localhost"
    port: int = 5432
    user: str = "memuser"
    password: str = "mempassword"
    database: str = "agent_memory"
    pool_size: int = 10
    max_overflow: int = 5
    pool_recycle: int = 3600

    @property
    def url(self) -> str:
        return f"{self.driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Mem0Config(BaseSettings):
    vector_store: dict = {}
    history_store: dict = {}
    llm: dict = {}
    embedder: dict = {}


class KafkaConfig(BaseSettings):
    bootstrap_servers: str = "localhost:9092"
    topic_memory_write: str = "memory.write"
    topic_memory_result: str = "memory.result"
    topic_memory_dlq: str = "memory.dlq"
    consumer_group: str = "memory-system"
    max_retries: int = 3
    retry_backoff_ms: int = 1000


class RedisConfig(BaseSettings):
    url: str = "redis://localhost:6379/0"
    result_ttl: int = 300
    result_poll_timeout: float = 5.0


class RetrievalConfig(BaseSettings):
    default_top_k: int = 10
    max_top_k: int = 50
    vector_weight: float = 0.4
    keyword_weight: float = 0.2
    recency_weight: float = 0.15
    importance_weight: float = 0.15
    confidence_weight: float = 0.1
    enable_rerank: bool = True


class GenerationConfig(BaseSettings):
    extraction_batch_size: int = 20
    schedule_interval_minutes: int = 5
    extraction_schedule_enabled: bool = False
    extraction_window_start: str = "00:00"
    extraction_window_end: str = "23:59"
    extraction_timezone: str = "Asia/Shanghai"
    max_memory_text_length: int = 2000
    max_summary_length: int = 500
    # fail-safe: 默认走真实 Pipeline。Mock 仅限开发期在 settings.yaml 显式开启，
    # 避免配置读取异常时静默返回正则假结果（2026-07-17 全量测试事故根因之一）
    use_mock_extraction: bool = False
    use_mq_wait: bool = False


class CompressionConfig(BaseSettings):
    trigger_session_length: int = 30
    compressed_context_length: int = 3000
    preserve_critical_info: bool = True


class AuthConfig(BaseSettings):
    enabled: bool = False
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    api_key_header: str = "X-API-Key"


class LoggingConfig(BaseSettings):
    level: str = "INFO"
    format: str = "text"
    output: str = "both"


class MonitoringConfig(BaseSettings):
    prometheus_enabled: bool = False
    metrics_port: int = 9090


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    mem0: Mem0Config = Mem0Config()
    kafka: KafkaConfig = KafkaConfig()
    redis: RedisConfig = RedisConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    generation: GenerationConfig = GenerationConfig()
    compression: CompressionConfig = CompressionConfig()
    auth: AuthConfig = AuthConfig()
    logging: LoggingConfig = LoggingConfig()
    monitoring: MonitoringConfig = MonitoringConfig()


GENERATION_SCHEDULE_FIELDS = {
    "extraction_schedule_enabled",
    "extraction_window_start",
    "extraction_window_end",
    "extraction_timezone",
}


def _resolve_env_vars(value: str) -> str:
    if not isinstance(value, str):
        return value
    pattern = re.compile(r'\$\{(\w+)(?::-([^}]*))?\}')
    def replacer(match):
        var_name = match.group(1)
        default = match.group(2)
        return os.environ.get(var_name, default if default is not None else "")
    return pattern.sub(replacer, value)


def _resolve_dict(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _resolve_dict(v)
        elif isinstance(v, str):
            result[k] = _resolve_env_vars(v)
        else:
            result[k] = v
    return result


def load_settings(config_path: Optional[str] = None) -> Settings:
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    resolved = _resolve_dict(raw)

    return Settings(
        app=AppConfig(**resolved.get("app", {})),
        server=ServerConfig(**resolved.get("server", {})),
        database=DatabaseConfig(**resolved.get("database", {})),
        mem0=Mem0Config(**resolved.get("mem0", {})),
        kafka=KafkaConfig(**resolved.get("kafka", {})),
        redis=RedisConfig(**resolved.get("redis", {})),
        retrieval=RetrievalConfig(**resolved.get("retrieval", {})),
        generation=GenerationConfig(**resolved.get("generation", {})),
        compression=CompressionConfig(**resolved.get("compression", {})),
        auth=AuthConfig(**resolved.get("auth", {})),
        logging=LoggingConfig(**resolved.get("logging", {})),
        monitoring=MonitoringConfig(**resolved.get("monitoring", {})),
    )


def persist_generation_schedule(updates: dict, config_path: Optional[str] = None) -> None:
    """Persist extraction schedule fields without rewriting YAML comments or env vars."""
    path = Path(config_path) if config_path else Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    unknown_fields = set(updates) - GENERATION_SCHEDULE_FIELDS
    if unknown_fields:
        raise ValueError(f"不允许持久化配置字段: {', '.join(sorted(unknown_fields))}")

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_generation = False
    found_fields: set[str] = set()
    rendered: list[str] = []

    for line in lines:
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            in_generation = line.strip() == "generation:"

        match = re.match(r"^(\s{2})(extraction_(?:schedule_enabled|window_start|window_end|timezone)):\s*.*?(\r?\n)?$", line)
        if in_generation and match and match.group(2) in updates:
            key = match.group(2)
            value = updates[key]
            if isinstance(value, bool):
                serialized = "true" if value else "false"
            else:
                serialized = f'"{str(value).replace(chr(34), chr(92) + chr(34))}"'
            newline = match.group(3) or ""
            line = f"{match.group(1)}{key}: {serialized}{newline}"
            found_fields.add(key)
        rendered.append(line)

    missing_fields = set(updates) - found_fields
    if missing_fields:
        raise ValueError(f"settings.yaml 缺少配置字段: {', '.join(sorted(missing_fields))}")

    content = "".join(rendered)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)

    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
