from dataclasses import dataclass, field


@dataclass
class IdempotencyConfig:
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str
    idempotency_ttl: int = 86_400
    idempotency_enabled: bool = True
    service_name: str = "unknown"
