import { useState } from 'react';
import Async from '../components/Async';
import { api } from '../lib/api';
import { fmtDate } from '../lib/format';
import { useApi } from '../lib/hooks';

export default function Organizations() {
  const state = useApi(() => api.listOrgs());
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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

  return (
    <div className="panel">
      <h2>조직 (사내 Git 작업공간)</h2>
      <p className="mutedtext" style={{ fontSize: 12 }}>
        조직을 만들면 사내 Gitea에 동일한 이름의 Organization이 함께 생성됩니다. 조직
        소속 프로젝트는 리포를 플랫폼이 내부에서 자동으로 만들고 관리합니다 — 일반
        사용자에게는 Git 주소 등 메타 정보가 노출되지 않습니다.
      </p>
      <form onSubmit={submit} style={{ marginBottom: 16 }}>
        <label className="field" style={{ display: 'inline-flex', marginRight: 10 }}>
          조직 이름 — 빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: shop-team)
          <div className="row">
            <input
              placeholder="shop-team"
              value={name}
              onChange={(e) => setName(e.target.value)}
              pattern="[a-z0-9][a-z0-9-]{1,40}"
              title="빈칸 없이 소문자·숫자·하이픈만 사용하세요 (예: shop-team)"
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
