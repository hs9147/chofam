import { useState } from 'react';
import DiffView from '../components/DiffView';
import StatusPill from '../components/StatusPill';
import { api } from '../lib/api';
import { extractDiffFromReply } from '../lib/diff';
import { useApi } from '../lib/hooks';
import type { ChatSessionOut, ReviewResult } from '../lib/types';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  changeId?: number | null;
  changeStatus?: 'proposed' | 'applied' | 'rejected';
  appliedSha?: string;
}

export default function Chat() {
  const projects = useApi(() => api.listProjects());
  const providers = useApi(() => api.listProviders());

  const [projectId, setProjectId] = useState('');
  const [providerId, setProviderId] = useState('');
  const [branch, setBranch] = useState('');
  const [session, setSession] = useState<ChatSessionOut | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [files, setFiles] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);

  const startSession = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      const s = await api.createChatSession(
        Number(projectId), Number(providerId), branch.trim() || undefined,
      );
      setSession(s);
      setMessages([]);
      setReview(null);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session || !input.trim()) return;
    const content = input.trim();
    setMessages((m) => [...m, { role: 'user', content }]);
    setInput('');
    setBusy(true);
    setError('');
    try {
      const fileList = files.split(',').map((f) => f.trim()).filter(Boolean);
      const res = await api.sendChatMessage(session.id, content, fileList);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.reply,
          changeId: res.proposed_change_id,
          changeStatus: res.proposed_change_id ? 'proposed' : undefined,
        },
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (idx: number, action: 'apply' | 'reject') => {
    const msg = messages[idx];
    if (!msg.changeId) return;
    setBusy(true);
    setError('');
    try {
      let appliedSha: string | undefined;
      if (action === 'apply') {
        const res = await api.applyChange(msg.changeId);
        appliedSha = res.applied_sha;
      } else {
        await api.rejectChange(msg.changeId);
      }
      setMessages((m) =>
        m.map((x, i) =>
          i === idx
            ? { ...x, changeStatus: action === 'apply' ? 'applied' : 'rejected', appliedSha }
            : x,
        ),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const runReview = async () => {
    if (!session) return;
    setReviewBusy(true);
    setError('');
    try {
      const res = await api.review(
        Number(projectId), Number(providerId), undefined, `origin/${session.branch}`,
      );
      setReview(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setReviewBusy(false);
    }
  };

  return (
    <>
      <div className="panel">
        <h2>대화식 코드 작성 · 편집</h2>
        <form className="row" onSubmit={startSession}>
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} required>
            <option value="">프로젝트...</option>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)} required>
            <option value="">LLM 프로바이더...</option>
            {(providers.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.kind === 'internal' ? '내부' : '외부'})
              </option>
            ))}
          </select>
          <input
            className="mono"
            placeholder="작업 브랜치 (선택)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            style={{ width: 200 }}
          />
          <button type="submit">세션 시작</button>
          {session && (
            <span className="mutedtext" style={{ fontSize: 12 }}>
              세션 #{session.id} · 브랜치 <span className="mono">{session.branch}</span> ·{' '}
              {session.provider}
            </span>
          )}
        </form>
      </div>

      {session && (
        <div className="panel">
          <div className="chat-thread">
            {messages.map((m, i) => {
              const diff = m.role === 'assistant' ? extractDiffFromReply(m.content) : null;
              const textOnly = diff
                ? m.content.replace(/```(?:diff|patch)\n[\s\S]*?```/, '').trim()
                : m.content;
              return (
                <div key={i} className={`chat-msg ${m.role}`} style={{ maxWidth: diff ? '100%' : undefined }}>
                  {textOnly}
                  {diff && (
                    <div style={{ marginTop: 10 }}>
                      <DiffView diff={diff} />
                      <div className="row" style={{ marginTop: 8 }}>
                        {m.changeStatus === 'proposed' && m.changeId && (
                          <>
                            <button className="small" disabled={busy} onClick={() => decide(i, 'apply')}>
                              승인 (브랜치에 커밋)
                            </button>
                            <button className="small danger" disabled={busy} onClick={() => decide(i, 'reject')}>
                              거절
                            </button>
                          </>
                        )}
                        {m.changeStatus === 'applied' && (
                          <span>
                            <StatusPill value="applied" />{' '}
                            <span className="mono mutedtext">{m.appliedSha?.slice(0, 8)}</span>
                          </span>
                        )}
                        {m.changeStatus === 'rejected' && <StatusPill value="rejected" />}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {busy && <div className="chat-msg assistant mutedtext">응답 생성 중...</div>}
          </div>
          <form onSubmit={send} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="예: 등록된 mail 모듈로 가입 환영 메일 발송 코드를 추가해줘"
            />
            <div className="row">
              <input
                className="mono"
                placeholder="컨텍스트 파일 (콤마 구분, 예: app/main.py, app/models.py)"
                value={files}
                onChange={(e) => setFiles(e.target.value)}
                style={{ flex: 1 }}
              />
              <button type="submit" disabled={busy || !input.trim()}>
                전송
              </button>
              <button
                type="button"
                className="secondary"
                disabled={reviewBusy}
                onClick={runReview}
              >
                {reviewBusy ? '리뷰 중...' : '브랜치 diff 리뷰'}
              </button>
            </div>
          </form>
          {error && <p className="error">{error}</p>}
        </div>
      )}

      {review && (
        <div className="panel">
          <div className="row" style={{ marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>코드 리뷰 결과</h2>
            <StatusPill value={review.max_severity} />
          </div>
          {review.findings.length === 0 ? (
            <p className="mutedtext">지적 사항이 없습니다.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>심각도</th>
                  <th>파일</th>
                  <th>코멘트</th>
                </tr>
              </thead>
              <tbody>
                {review.findings.map((f, i) => (
                  <tr key={i}>
                    <td><StatusPill value={f.severity} /></td>
                    <td className="mono">{f.file}</td>
                    <td>{f.comment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
