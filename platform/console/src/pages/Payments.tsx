import { useState } from 'react';
import Async from '../components/Async';
import { Confirm } from '../components/Modal';
import StatusPill from '../components/StatusPill';
import { api } from '../lib/api';
import { fmtDate } from '../lib/format';
import { useApi } from '../lib/hooks';

export default function Payments() {
  const [status, setStatus] = useState('');
  const state = useApi(() => api.listPayments(status || undefined), [status]);
  const [cancelKey, setCancelKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const runCancel = async () => {
    if (!cancelKey) return;
    setBusy(true);
    setError('');
    try {
      await api.cancelPayment(cancelKey, '관리자 취소');
      state.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setCancelKey(null);
    }
  };

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>결제 내역 (토스페이먼츠)</h2>
        <div className="spacer" />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">전체 상태</option>
          <option value="confirmed">confirmed</option>
          <option value="canceled">canceled</option>
          <option value="failed">failed</option>
        </select>
        <button className="secondary small" onClick={state.reload}>
          새로고침
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <Async state={state} empty="결제 기록이 없습니다.">
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>주문번호</th>
                <th>금액</th>
                <th>상태</th>
                <th>수단</th>
                <th>요청 서비스</th>
                <th>실패 사유</th>
                <th>일시</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.order_id}</td>
                  <td className="mono">{p.amount.toLocaleString('ko-KR')}원</td>
                  <td><StatusPill value={p.status} /></td>
                  <td>{p.method ?? '-'}</td>
                  <td>{p.source}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{p.fail_reason ?? '-'}</td>
                  <td className="mono">{fmtDate(p.created_at)}</td>
                  <td>
                    {p.status === 'confirmed' && (
                      <button className="danger small" onClick={() => setCancelKey(p.payment_key)}>
                        취소
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {cancelKey && (
        <Confirm
          title="결제 취소"
          message="이 결제를 취소(환불)합니다. 되돌릴 수 없습니다."
          confirmLabel="결제 취소"
          danger
          busy={busy}
          onConfirm={runCancel}
          onClose={() => !busy && setCancelKey(null)}
        />
      )}
    </div>
  );
}
