import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Async from '../components/Async';
import Modal from '../components/Modal';
import StatusPill from '../components/StatusPill';
import { api } from '../lib/api';
import { fmtDate } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { BuildProfile, ProjectType } from '../lib/types';

export default function Projects() {
  const state = useApi(() => api.listProjects());
  const [showCreate, setShowCreate] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>프로젝트</h2>
        <div className="spacer" />
        <button onClick={() => setShowCreate(true)}>+ 새 프로젝트</button>
      </div>
      <Async state={state} empty="프로젝트가 없습니다.">
        {(projects) => (
          <table>
            <thead>
              <tr>
                <th>이름</th>
                <th>타입</th>
                <th>Git</th>
                <th>브랜치</th>
                <th>기본 프로필</th>
                <th>생성일</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="clickable" onClick={() => navigate(`/projects/${p.id}`)}>
                  <td>{p.name}</td>
                  <td><StatusPill value={p.type} /></td>
                  <td className="mono">{p.git_url}</td>
                  <td className="mono">{p.branch}</td>
                  <td><StatusPill value={p.default_profile} /></td>
                  <td className="mono">{fmtDate(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {showCreate && (
        <CreateModal
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

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    name: '',
    type: 'react' as ProjectType,
    git_url: '',
    branch: 'main',
    domain: '',
    health_check_path: '/',
    default_profile: 'release' as BuildProfile,
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.createProject({ ...form, domain: form.domain || null });
      onCreated();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="새 프로젝트" onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label className="field">
          이름 (소문자·숫자·하이픈)
          <input value={form.name} onChange={(e) => set('name', e.target.value)} required />
        </label>
        <label className="field">
          타입
          <select value={form.type} onChange={(e) => set('type', e.target.value)}>
            <option value="react">react</option>
            <option value="python">python</option>
            <option value="node">node</option>
            <option value="llm">llm</option>
          </select>
        </label>
        <label className="field">
          Git URL
          <input value={form.git_url} onChange={(e) => set('git_url', e.target.value)} required />
        </label>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>
            브랜치
            <input value={form.branch} onChange={(e) => set('branch', e.target.value)} />
          </label>
          <label className="field" style={{ flex: 1 }}>
            기본 프로필
            <select
              value={form.default_profile}
              onChange={(e) => set('default_profile', e.target.value)}
            >
              <option value="release">release</option>
              <option value="development">development</option>
            </select>
          </label>
        </div>
        <label className="field">
          도메인 (선택 — 비우면 {'{이름}.{기본도메인}'})
          <input value={form.domain} onChange={(e) => set('domain', e.target.value)} />
        </label>
        <label className="field">
          헬스체크 경로
          <input
            value={form.health_check_path}
            onChange={(e) => set('health_check_path', e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="secondary" onClick={onClose}>
            취소
          </button>
          <button type="submit" disabled={busy}>
            {busy ? '생성 중...' : '생성'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
