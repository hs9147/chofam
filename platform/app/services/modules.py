"""Module 레지스트리 — 외부/내부 API·DB·파일 저장소를 등록하고 환경변수 규약으로 주입한다.

주입 규약 (env_prefix = "PAY" 예시):
  external_api : PAY_URL, PAY_API_KEY
  internal_api : PAY_URL  (1차: http://{target}.{base_domain}, 2차: http://paas-{target}.{ns}.svc)
  database     : PAY_DSN
  file_storage : PAY_ENDPOINT, PAY_BUCKET
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Module, ModuleBinding, ModuleType, Project
from ..security import decrypt_value, encrypt_value

# config 안에서 저장 시 암호화되는 필드
SENSITIVE_KEYS = {"api_key", "dsn", "password", "secret", "token"}


def encrypt_config(config: dict) -> dict:
    out = {}
    for k, v in config.items():
        if k in SENSITIVE_KEYS and isinstance(v, str) and v:
            out[k] = {"__enc__": encrypt_value(v)}
        else:
            out[k] = v
    return out


def decrypt_config(config: dict) -> dict:
    out = {}
    for k, v in config.items():
        if isinstance(v, dict) and "__enc__" in v:
            out[k] = decrypt_value(v["__enc__"])
        else:
            out[k] = v
    return out


def masked_config(config: dict) -> dict:
    return {k: ("•••" if isinstance(v, dict) and "__enc__" in v else v) for k, v in config.items()}


def binding_env(module: Module, env_prefix: str, settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    cfg = decrypt_config(module.config or {})
    p = env_prefix.upper()
    t = module.type

    if t == ModuleType.external_api:
        env = {f"{p}_URL": cfg.get("url", "")}
        if cfg.get("api_key"):
            env[f"{p}_API_KEY"] = cfg["api_key"]
        return env

    if t == ModuleType.internal_api:
        target = cfg.get("target_project", "")
        if settings.tier == "enterprise":
            url = f"http://paas-{target}.{settings.k8s_namespace}.svc"
        else:
            url = f"https://{target}.{settings.base_domain}"
        return {f"{p}_URL": url}

    if t == ModuleType.database:
        return {f"{p}_DSN": cfg.get("dsn", "")}

    if t == ModuleType.file_storage:
        return {
            f"{p}_ENDPOINT": cfg.get("endpoint", ""),
            f"{p}_BUCKET": cfg.get("bucket", ""),
        }
    return {}


def env_for_project(db: Session, project: Project) -> dict[str, str]:
    """프로젝트에 바인딩된 모든 모듈의 환경변수를 모은다 (배포 시 자동 주입)."""
    rows = db.execute(
        select(ModuleBinding, Module)
        .join(Module, ModuleBinding.module_id == Module.id)
        .where(ModuleBinding.project_id == project.id)
    ).all()
    env: dict[str, str] = {}
    for binding, module in rows:
        env.update(binding_env(module, binding.env_prefix))
    return env


def available_resources(db: Session, project: Project) -> list[dict]:
    """대화식 편집 화면의 자원 리스팅용 — 이 프로젝트에서 사용 가능한 모든 모듈을
    카테고리별로 아이템화한다(바인딩 여부와 무관, 비밀값 제외).

    organization_id가 없는 모듈은 전역(모든 프로젝트에 노출), 있는 모듈은 같은
    조직 소속 프로젝트에만 노출된다("조직별 db" 등 조직 전용 자원).
    """
    rows = db.execute(select(Module).order_by(Module.type, Module.category, Module.name)).scalars()
    result = []
    for m in rows:
        if m.organization_id is not None and m.organization_id != project.organization_id:
            continue
        result.append({
            "id": m.id,
            "name": m.name,
            "type": m.type.value,
            "category": m.category,
            "scope": "org" if m.organization_id is not None else "global",
        })
    return result


def context_for_llm(db: Session, project: Project) -> list[dict]:
    """채팅 컨텍스트용 — LLM이 규약에 맞는 연동 코드를 생성하도록 모듈 목록을 요약(비밀값 제외)."""
    rows = db.execute(
        select(ModuleBinding, Module)
        .join(Module, ModuleBinding.module_id == Module.id)
        .where(ModuleBinding.project_id == project.id)
    ).all()
    summary = []
    for binding, module in rows:
        summary.append({
            "name": module.name,
            "type": module.type.value,
            "env": sorted(binding_env(module, binding.env_prefix).keys()),
        })
    return summary
