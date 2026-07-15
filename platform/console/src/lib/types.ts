// platform/app/schemas.py 미러 — 백엔드 스키마 변경 시 이 파일을 함께 갱신한다.

export type ProjectType = 'react' | 'python' | 'node' | 'llm' | 'html' | 'streamlit';
export type BuildProfile = 'development' | 'release';
export type DeploymentStatus = 'building' | 'running' | 'failed' | 'stopped';

export interface ProjectOut {
  id: number;
  name: string;
  type: ProjectType;
  organization_id: number | null;
  // organization_id로 생성된 프로젝트는 비관리자에게 마스킹된 값이 온다
  git_url: string;
  branch: string;
  domain: string | null;
  default_profile: BuildProfile;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
  type: ProjectType;
  // 둘 중 하나만 — organization_id 지정 시 리포를 내부에서 자동 생성(git_url 불가)
  organization_id?: number | null;
  git_url?: string;
  branch: string;
  domain?: string | null;
  health_check_path?: string;
  default_profile?: BuildProfile;
}

export interface OrgOut {
  id: number;
  name: string;
  created_at: string;
  project_count: number;
}

export interface DeploymentOut {
  id: number;
  project_id: number;
  git_sha: string;
  image_tag: string;
  profile: BuildProfile;
  status: DeploymentStatus;
  host_port: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface EnvVarRow {
  key: string;
  is_secret: boolean;
  value: string; // 마스킹된 표시값
}

export interface ModuleOut {
  id: number;
  name: string;
  type: string;
  category: string | null;
  organization_id: number | null;
  config: Record<string, unknown>;
}

export interface ModuleSummary {
  name: string;
  type: string;
  env: string[];
}

// 대화식 편집 화면 자원 리스팅 — 바인딩 여부와 무관하게 사용 가능한 모듈을 아이템화
export interface ResourceItem {
  id: number;
  name: string;
  type: string;
  category: string | null;
  scope: 'global' | 'org';
}

export interface LlmProviderOut {
  id: number;
  name: string;
  kind: 'external' | 'internal';
  base_url: string;
  model: string;
  has_api_key: boolean;
}

export interface ChatSessionOut {
  id: number;
  branch: string;
  provider: string;
}

export interface ChatReply {
  reply: string;
  proposed_change_id: number | null;
}

export interface ReviewFinding {
  severity: string;
  file: string;
  comment: string;
}

export interface ReviewResult {
  findings: ReviewFinding[];
  max_severity: string;
}

export interface PreviewOut {
  id: number;
  project_id: number;
  branch: string;
  url: string;
  status: 'running' | 'expired' | 'failed';
  expires_at: string;
}

export interface ProjectFilesOut {
  files: string[];
}

export interface ProjectFileContentOut {
  path: string;
  content: string;
}

// 서버구성 시각화 — 런타임/프록시 백엔드 + 등록된 사이트(라우팅 항목) 목록
export interface ServerConfigSite {
  project_id: number;
  project_name: string;
  profile: BuildProfile;
  domain: string;
  status: string;
  redirect_count: number;
}

export interface ServerConfigOut {
  runtime_backend: string;
  proxy_backend: string;
  sites: ServerConfigSite[];
}

export interface RedirectRule {
  id: number;
  project_id: number;
  from_path: string;
  to_path: string;
  kind: 'redirect' | 'rewrite';
  status_code: number;
  created_at: string;
}

export interface AuditRow {
  actor: string;
  action: string;
  target: string;
  detail: Record<string, unknown> | null;
  at: string;
}

export interface GpuInfo {
  index: number;
  name: string;
  vram_total: number;
  vram_used: number;
  util_percent: number;
}

export interface StatusSnapshot {
  host_os?: string;
  gpu_supported?: boolean;
  docker_hint?: string;
  cpu_percent?: number;
  memory?: { total: number; used: number; percent: number };
  disk?: { total: number; used: number; percent: number };
  gpus: GpuInfo[];
  system?: string;
}

export interface HealthInfo {
  ok: boolean;
  tier: string;
  host_os: string;
  features: string[];
  gitea_url: string | null;
}

export interface PaymentOut {
  id: number;
  order_id: string;
  payment_key: string;
  amount: number;
  status: 'ready' | 'confirmed' | 'canceled' | 'failed';
  method: string | null;
  source: string;
  fail_reason: string | null;
  created_at: string;
}

export interface ApiKeyIssued {
  name: string;
  key: string;
  is_admin: boolean;
}
