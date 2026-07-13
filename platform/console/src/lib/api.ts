import { getKey, logout } from './auth';
import type {
  ApiKeyIssued,
  AuditRow,
  BuildProfile,
  HealthInfo,
  PaymentOut,
  ChatReply,
  ChatSessionOut,
  DeploymentOut,
  EnvVarRow,
  LlmProviderOut,
  ModuleOut,
  ModuleSummary,
  PreviewOut,
  ProjectCreate,
  ProjectOut,
  ReviewResult,
  StatusSnapshot,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  query?: Record<string, string | number | undefined>,
): Promise<T> {
  let url = path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== '') params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }
  const res = await fetch(url, {
    method,
    headers: {
      'x-api-key': getKey(),
      ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    // 만료/무효 키 — 전역 단일 처리 지점
    logout();
    window.location.hash = '#/login';
    throw new ApiError(401, '인증이 만료되었습니다. 다시 로그인하세요.');
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* 본문 없는 응답 */
  }
  if (!res.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  // 시스템
  health: () => request<HealthInfo>('GET', '/health'),
  status: () => request<StatusSnapshot>('GET', '/status'),
  audit: (limit = 100) => request<AuditRow[]>('GET', '/audit', undefined, { limit }),
  issueKey: (name: string, is_admin: boolean) =>
    request<ApiKeyIssued>('POST', '/keys', { name, is_admin }),

  // 프로젝트
  listProjects: () => request<ProjectOut[]>('GET', '/projects'),
  createProject: (body: ProjectCreate) => request<ProjectOut>('POST', '/projects', body),
  deploy: (id: number, profile?: BuildProfile, git_sha?: string) =>
    request<DeploymentOut>('POST', `/projects/${id}/deploy`, {
      profile: profile ?? null,
      git_sha: git_sha || null,
    }),
  rollback: (id: number, profile: BuildProfile) =>
    request<DeploymentOut>('POST', `/projects/${id}/rollback`, undefined, { profile }),
  stop: (id: number, profile: BuildProfile) =>
    request<void>('POST', `/projects/${id}/stop`, undefined, { profile }),
  deployments: (id: number) => request<DeploymentOut[]>('GET', `/projects/${id}/deployments`),
  logs: (id: number, profile: BuildProfile, tail: number) =>
    request<{ logs: string }>('GET', `/projects/${id}/logs`, undefined, { profile, tail }),
  projectStatus: (id: number) =>
    request<Record<BuildProfile, string>>('GET', `/projects/${id}/status`),
  listEnv: (id: number) => request<EnvVarRow[]>('GET', `/projects/${id}/env`),
  setEnv: (id: number, key: string, value: string, is_secret: boolean) =>
    request<void>('PUT', `/projects/${id}/env`, { key, value, is_secret }),

  // 모듈
  listModules: () => request<ModuleOut[]>('GET', '/modules'),
  createModule: (name: string, type: string, config: Record<string, unknown>) =>
    request<ModuleOut>('POST', '/modules', { name, type, config }),
  projectModules: (id: number) => request<ModuleSummary[]>('GET', `/projects/${id}/modules`),
  bindModule: (projectId: number, moduleId: number, env_prefix: string) =>
    request<{ injected_env: string[] }>(
      'POST', `/projects/${projectId}/modules/${moduleId}/bind`, { env_prefix },
    ),

  // LLM
  listProviders: () => request<LlmProviderOut[]>('GET', '/llm/providers'),
  createProvider: (body: {
    name: string; kind: string; base_url: string; api_key?: string; model: string;
  }) => request<LlmProviderOut>('POST', '/llm/providers', body),
  createChatSession: (project_id: number, provider_id: number, branch?: string) =>
    request<ChatSessionOut>('POST', '/chat/sessions', {
      project_id, provider_id, branch: branch || null,
    }),
  sendChatMessage: (sessionId: number, content: string, files: string[]) =>
    request<ChatReply>('POST', `/chat/sessions/${sessionId}/messages`, { content, files }),
  applyChange: (id: number) =>
    request<{ applied_sha: string; branch: string }>('POST', `/changes/${id}/apply`),
  rejectChange: (id: number) => request<void>('POST', `/changes/${id}/reject`),
  review: (projectId: number, provider_id: number, diff?: string, base_ref?: string) =>
    request<ReviewResult>('POST', `/projects/${projectId}/review`, {
      provider_id, diff: diff || null, base_ref: base_ref || null,
    }),

  // 결제 (payment 모듈)
  listPayments: (status?: string, limit = 50) =>
    request<PaymentOut[]>('GET', '/payments', undefined, { status, limit }),
  cancelPayment: (paymentKey: string, reason: string) =>
    request<PaymentOut>('POST', `/payments/${paymentKey}/cancel`, { reason }),

  // 프리뷰
  createPreview: (projectId: number, branch?: string, ttl_minutes = 60) =>
    request<PreviewOut>('POST', `/projects/${projectId}/preview`, {
      branch: branch || null, ttl_minutes,
    }),
  listPreviews: (projectId: number) =>
    request<PreviewOut[]>('GET', `/projects/${projectId}/previews`),
  deletePreview: (id: number) => request<void>('DELETE', `/previews/${id}`),
};
