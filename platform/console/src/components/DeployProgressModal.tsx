import { useEffect, useRef, useState } from 'react';
import Modal from './Modal';
import { api, ApiError } from '../lib/api';
import type { BuildProfile, DeploymentStatus } from '../lib/types';

const TERMINAL: DeploymentStatus[] = ['running', 'failed', 'stopped'];

// 이미 큐로 시작된 배포(deploymentIds)의 진행 상황을 GET /deployments 폴링으로 로그창에
// 출력한다. 배포 요청(POST) 자체는 호출측(클릭 핸들러)에서 한 번만 수행하므로 이 컴포넌트는
// 폴링만 한다 — StrictMode 이중 마운트에서도 중복 배포가 발생하지 않는다.
// 완료(모든 레코드가 종료 상태) 전까지는 닫기가 막히고, 완료 후 "확인"으로만 닫는다.
export default function DeployProgressModal({
  projectId, projectName, profile, deploymentIds, onClose,
}: {
  projectId: number;
  projectName: string;
  profile: BuildProfile;
  deploymentIds: number[];
  onClose: () => void;
}) {
  const [lines, setLines] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const logRef = useRef<HTMLPreElement | null>(null);

  const append = (line: string) => setLines((prev) => [...prev, line]);

  // 새 줄이 추가될 때마다 항상 최신 줄로 스크롤
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const lastStatus: Record<number, string> = {};

    const poll = async () => {
      if (cancelled) return;
      try {
        const rows = await api.deployments(projectId);
        const mine = rows.filter((r) => deploymentIds.includes(r.id));
        for (const r of mine) {
          if (lastStatus[r.id] !== r.status) {
            lastStatus[r.id] = r.status;
            const label = r.component ? `${r.component} ` : '';
            append(`· ${label}#${r.id}: ${r.status}${r.error ? ` — ${r.error.slice(0, 300)}` : ''}`);
          }
        }
        const allTerminal =
          mine.length === deploymentIds.length && mine.every((r) => TERMINAL.includes(r.status));
        if (allTerminal) {
          const anyFail = mine.some((r) => r.status === 'failed');
          append(anyFail ? '배포 실패.' : '배포 완료.');
          try {
            const res = await api.logs(projectId, profile, 200);
            const text = (res as { logs?: string }).logs;
            if (text && text.trim()) {
              append('--- 로그 ---');
              append(text.trimEnd());
            }
          } catch {
            /* 완료 후 로그 tail 조회 실패는 진행 결과에 영향 없음 — 무시 */
          }
          if (!cancelled) {
            setFailed(anyFail);
            setDone(true);
          }
          return;
        }
      } catch (e) {
        append(`폴링 오류: ${(e as ApiError).message}`);
      }
      timer = window.setTimeout(poll, 1500);
    };

    append(`배포 진행 상황을 확인합니다… (${projectName} · ${profile})`);
    poll();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [projectId, profile, projectName, deploymentIds]);

  return (
    <Modal title={`배포 진행 — ${projectName} (${profile})`} onClose={done ? onClose : () => {}}>
      <pre
        ref={logRef}
        className="mono"
        style={{
          background: '#0d0d0d',
          color: '#e0e0e0',
          padding: 12,
          borderRadius: 6,
          maxHeight: 360,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          fontSize: 12,
          margin: 0,
        }}
      >
        {lines.join('\n')}
        {!done ? '\n▍진행 중…' : ''}
      </pre>
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
        <button className={failed ? 'danger' : ''} onClick={onClose} disabled={!done}>
          {done ? '확인' : '진행 중…'}
        </button>
      </div>
    </Modal>
  );
}
