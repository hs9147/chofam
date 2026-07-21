import { useState } from 'react';
import Async from '../components/Async';
import { api } from '../lib/api';
import { isAdmin } from '../lib/auth';
import { fmtDate } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { GiteaSyncResult } from '../lib/types';

export default function Organizations() {
  const state = useApi(() => api.listOrgs());
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<GiteaSyncResult | null>(null);
  const [syncError, setSyncError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.createOrg(name.trim());
      setName('');
      state.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const syncFromGitea = async () => {
    setSyncBusy(true);
    setSyncError('');
    setSyncResult(null);
    try {
      const result = await api.syncOrgsFromGitea();
      setSyncResult(result);
      state.reload();
    } catch (err) {
      setSyncError((err as Error).message);
    } finally {
      setSyncBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 4 }}>
        <h2 style={{ margin: 0 }}>조직 (사내 Git 작업공간)</h2>
        <div className="spacer" />
        {isAdmin() && (
          <button className="small secondary" disabled={syncBusy} onClick={syncFromGitea}>
            {syncBusy ? '동기화 중...' : 'Gitea에서 동기화'}
          </button>
        )}
      </div>
      <p className="mutedtext" style={{ fontSize: 12 }}>
        조직을 만들면 사내 Gitea에 동일한 이름의 Organization이 함께 생성됩니다. 조직
        소속 프로젝트는 리포를 플랫폼이 내부에서 자동으로 만들고 관리합니다 — 일반
        사용자에게는 Git 주소 등 메타 정보가 노출되지 않습니다.
      </p>
      {isAdmin() && (
        <p className="mutedtext" style={{ fontSize: 12 }}>
          "Gitea에서 동기화"는 반대 방향입니다 — Gitea에는 있지만 아직 플랫폼이 모르는
          조직/리포(수동으로 Gitea에서 직접 만든 경우 등)를 찾아 가져옵니다. 리포 타입은
          시그니처 파일(requirements.txt/package.json 등)로 추론하며, 추론할 수 없는
          리포는 건너뛰고 아래에 이유가 표시됩니다.
        </p>
      )}
      {syncError && <p className="error">{syncError}</p>}
      {syncResult && (
        <div className="panel" style={{ marginBottom: 16, fontSize: 12 }}>
          <div>새 조직 {syncResult.orgs_created.length}개, 새 프로젝트 {syncResult.projects_created.length}개 가져옴</div>
          {syncResult.orgs_created.length > 0 && (
            <div className="mutedtext">조직: {syncResult.orgs_created.join(', ')}</div>
          )}
          {syncResult.projects_created.length > 0 && (
            <div className="mutedtext">프로젝트: {syncResult.projects_created.join(', ')}</div>
          )}
          {syncResult.skipped.length > 0 && (
            <div className="mutedtext">
              건너뜀: {syncResult.skipped.map((s) => `${s.name}(${s.reason})`).join(', ')}
            </div>
          )}
        </div>
      )}
      <form onSubmit={submit} style={{ marginBottom: 16 }}>
        <label className="field" style={{ display: 'inline-flex', marginRight: 10 }}>
          조직 이름 — 빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: portal-team)
          <div className="row">
            <input
              placeholder="portal-team"
              value={name}
              onChange={(e) => setName(e.target.value)}
              pattern="[a-z0-9][a-z0-9-]{1,40}"
              title="빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: portal-team)"
              required
              style={{ width: 240 }}
            />
            <button type="submit" disabled={busy}>
              {busy ? '생성 중...' : '+ 조직 생성'}
            </button>
          </div>
        </label>
      </form>
      {error && <p className="error">{error}</p>}
      <Async state={state} empty="등록된 조직이 없습니다.">
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>이름</th>
                <th>프로젝트 수</th>
                <th>생성일</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id}>
                  <td>{o.name}</td>
                  <td className="mono">{o.project_count}</td>
                  <td className="mono">{fmtDate(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
    </div>
  );
}
