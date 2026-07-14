// platform/app/schemas.py 미러 — 백엔드 스키마 변경 시 이 파일을 함께 갱신한다.

export type ProjectType = 'react' | 'python' | 'node' | 'llm';
export type BuildProfile = 'development' | 'release';
export type DeploymentStatus = 'building' | 'running' | 'failed' | 'stopped';

export interface ProjectOut {
  id: number;
  name: string;
  type: ProjectType;
  git_url: string;
  branch: string;
  domain: string | null;
  default_profile: BuildProfile;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
  type: ProjectType;
  git_url: string;
  branch: string;
  domain?: string | null;
  health_check_path?: string;
  default_profile?: BuildProfile;
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
  config: Record<string, unknown>;
}

export interface ModuleSummary {
  name: string;
  type: string;
  env: string[];
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
