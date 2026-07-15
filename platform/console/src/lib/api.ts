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
  OrgOut,
  PreviewOut,
  ProjectCreate,
  ProjectFileContentOut,
  ProjectFilesOut,
  ProjectOut,
  ProjectType,
  RedirectRule,
  ResourceItem,
  ReviewResult,
  ServerConfigOut,
  StatusSnapshot,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

// FastAPI 422는 detail이 [{loc, msg, type}, ...] 배열 — String(array)는 "[object Object]"가
// 되어버리므로 사람이 읽을 수 있는 메시지로 풀어낸다. 나머지 에러(409 등)는 detail이
// 문자열이라 그대로 반환된다.
function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? (d as { loc: unknown[] }).loc.join('.')
            : '';
          const msg = String((d as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return JSON.stringify(d);
      })
      .join('; ');
  }
  return JSON.stringify(detail);
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
        ? formatDetail((data as { detail: unknown }).detail)
        : `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

async function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'x-api-key': getKey() },
    body: formData,
  });
  if (res.status === 401) {
    logout();
    window.location.hash = '#/login';
    throw new ApiError(401, '인증이 만료되었습니다. 다시 로그인하세요.');
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* 본문 없는 응답 */
  }
  if (!res.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? formatDetail((data as { detail: unknown }).detail)
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

  // zip/폴더 업로드로 프로젝트 등록 (조직 필수 — 사내 Gitea 리포로 최초 push)
  uploadProject: (
    form: {
      name: string;
      type: ProjectType;
      organization_id: number;
      branch: string;
      domain?: string;
      health_check_path?: string;
      default_profile: BuildProfile;
      deploy_after_upload: boolean;
    },
    source: { kind: 'zip'; file: File } | { kind: 'folder'; files: FileList },
  ) => {
    const fd = new FormData();
    fd.append('name', form.name);
    fd.append('type', form.type);
    fd.append('organization_id', String(form.organization_id));
    fd.append('branch', form.branch);
    if (form.domain) fd.append('domain', form.domain);
    fd.append('health_check_path', form.health_check_path ?? '/');
    fd.append('default_profile', form.default_profile);
    fd.append('deploy_after_upload', String(form.deploy_after_upload));
    if (source.kind === 'zip') {
      fd.append('zip_file', source.file);
    } else {
      Array.from(source.files).forEach((f) => {
        fd.append('files', f, f.webkitRelativePath || f.name);
      });
    }
    return requestMultipart<ProjectOut>('/projects/upload', fd);
  },

  // 조직 (사내 Gitea 작업공간)
  listOrgs: () => request<OrgOut[]>('GET', '/orgs'),
  createOrg: (name: string) => request<OrgOut>('POST', '/orgs', { name }),
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

  // 코드 확인 화면 (읽기 전용 — 수정은 채팅/diff 승인으로만)
  projectFiles: (id: number) => request<ProjectFilesOut>('GET', `/projects/${id}/files`),
  projectFileContent: (id: number, path: string) =>
    request<ProjectFileContentOut>('GET', `/projects/${id}/files/content`, undefined, { path }),

  // 모듈
  listModules: () => request<ModuleOut[]>('GET', '/modules'),
  createModule: (
    name: string,
    type: string,
    config: Record<string, unknown>,
    category?: string,
    organization_id?: number,
  ) =>
    request<ModuleOut>('POST', '/modules', {
      name, type, config,
      category: category || null,
      organization_id: organization_id ?? null,
    }),
  projectModules: (id: number) => request<ModuleSummary[]>('GET', `/projects/${id}/modules`),
  projectResources: (id: number) => request<ResourceItem[]>('GET', `/projects/${id}/resources`),
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

  // 서버구성 (런타임/프록시 백엔드 시각화 + redirect/rewrite 규칙)
  serverConfig: () => request<ServerConfigOut>('GET', '/server-config'),
  listRedirects: (projectId: number) =>
    request<RedirectRule[]>('GET', `/projects/${projectId}/redirects`),
  createRedirect: (
    projectId: number, from_path: string, to_path: string, kind: string, status_code: number,
  ) =>
    request<RedirectRule>('POST', `/projects/${projectId}/redirects`, {
      from_path, to_path, kind, status_code,
    }),
  deleteRedirect: (id: number) => request<void>('DELETE', `/redirects/${id}`),

  // 프리뷰
  createPreview: (projectId: number, branch?: string, ttl_minutes = 60) =>
    request<PreviewOut>('POST', `/projects/${projectId}/preview`, {
      branch: branch || null, ttl_minutes,
    }),
  listPreviews: (projectId: number) =>
    request<PreviewOut[]>('GET', `/projects/${projectId}/previews`),
  deletePreview: (id: number) => request<void>('DELETE', `/previews/${id}`),
};
