import { useState } from 'react';
import Async from '../components/Async';
import Modal from '../components/Modal';
import StatusPill from '../components/StatusPill';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import type { OrgOut } from '../lib/types';

const TYPE_HINTS: Record<string, string> = {
  external_api: '{"url": "https://...", "api_key": "..."}',
  internal_api: '{"target_project": "다른-프로젝트명"}',
  database: '{"dsn": "postgresql://user:pw@host/db"}',
  file_storage: '{"endpoint": "http://...", "bucket": "..."}',
};

export default function Modules() {
  const state = useApi(() => api.listModules());
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>모듈 레지스트리</h2>
        <div className="spacer" />
        <button onClick={() => setShowCreate(true)}>+ 새 모듈</button>
      </div>
      <p className="mutedtext" style={{ fontSize: 12 }}>
        api_key·dsn·secret 등 민감 필드는 암호화 저장되며 이후 마스킹(•••)으로만 표시됩니다.
      </p>
      <Async state={state} empty="등록된 모듈이 없습니다.">
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>이름</th>
                <th>타입</th>
                <th>카테고리</th>
                <th>범위</th>
                <th>설정</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td><StatusPill value={m.type} /></td>
                  <td className="mutedtext">{m.category || '—'}</td>
                  <td>
                    <StatusPill value={m.organization_id ? 'org' : 'global'} />
                  </td>
                  <td className="mono">{JSON.stringify(m.config)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {showCreate && (
        <CreateModuleModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            state.reload();
          }}
        />
      )}
    </div>
  );
}

function CreateModuleModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const orgs = useApi<OrgOut[]>(() => api.listOrgs());
  const [name, setName] = useState('');
  const [type, setType] = useState('external_api');
  const [category, setCategory] = useState('');
  const [organizationId, setOrganizationId] = useState('');
  const [config, setConfig] = useState(TYPE_HINTS.external_api);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(config);
    } catch {
      setError('설정이 올바른 JSON이 아닙니다.');
      setBusy(false);
      return;
    }
    try {
      await api.createModule(
        name.trim(), type, parsed,
        category.trim() || undefined,
        organizationId ? Number(organizationId) : undefined,
      );
      onCreated();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="새 모듈" onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label className="field">
          이름 — 빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: news-api)
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            pattern="[a-z0-9][a-z0-9-]{1,40}"
            title="빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: news-api)"
            placeholder="news-api"
            required
          />
        </label>
        <label className="field">
          타입
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value);
              setConfig(TYPE_HINTS[e.target.value]);
            }}
          >
            <option value="external_api">external_api — 외부 API</option>
            <option value="internal_api">internal_api — 플랫폼 내 프로젝트</option>
            <option value="database">database — DB 연결</option>
            <option value="file_storage">file_storage — 파일 저장소</option>
          </select>
        </label>
        <label className="field">
          카테고리 (선택 — 예: news, llm, payment. 자원 목록에서 API를 묶어 보여줍니다)
          <input value={category} onChange={(e) => setCategory(e.target.value)} />
        </label>
        {orgs.data && orgs.data.length > 0 && (
          <label className="field">
            조직 범위 (선택 — 지정 시 해당 조직 프로젝트에만 노출, 예: 조직별 DB)
            <select value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>
              <option value="">전역 (모든 프로젝트)</option>
              {orgs.data.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          설정 (JSON)
          <textarea
            className="mono"
            rows={4}
            value={config}
            onChange={(e) => setConfig(e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="secondary" onClick={onClose}>
            취소
          </button>
          <button type="submit" disabled={busy}>
            {busy ? '등록 중...' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
