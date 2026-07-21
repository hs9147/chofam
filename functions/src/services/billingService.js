// 토스페이먼츠 결제 승인(청구) 클라이언트.
// - 지급대행(payout, v2)과 달리 결제 승인 API는 JWE 암호화가 없는 v1 평문 JSON이다.
// - 인증: Basic base64(TOSS_SECRET_KEY:)
// 프론트엔드 결제위젯이 만든 paymentKey/orderId/amount를 호출 서비스(백엔드)가 받아
// 이 API로 승인 요청을 넘기면, 토스가 실제 청구를 확정한다.

const API_BASE = () => process.env.TOSS_API_BASE || 'https://api.tosspayments.com';

function isConfigured() {
  return Boolean(process.env.TOSS_SECRET_KEY);
}

// 결제 승인. amount는 KRW 정수이며, 반드시 결제 요청 시점의 금액과 일치해야 한다
// (불일치 시 토스가 거절 → 502로 표면화).
async function confirmPayment({ paymentKey, orderId, amount }) {
  const res = await fetch(`${API_BASE()}/v1/payments/confirm`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${Buffer.from(`${process.env.TOSS_SECRET_KEY}:`).toString('base64')}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ paymentKey, orderId, amount }),
  });

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (_) {
    data = { raw: text };
  }

  if (!res.ok) {
    const err = new Error((data && data.message) || `toss_http_${res.status}`);
    err.status = 502;
    err.code = (data && data.code) || 'toss_error';
    throw err;
  }

  return {
    paymentKey: data.paymentKey,
    orderId: data.orderId,
    status: data.status,
    method: data.method,
    totalAmount: data.totalAmount,
    currency: data.currency,
    approvedAt: data.approvedAt,
  };
}

module.exports = { isConfigured, confirmPayment };
