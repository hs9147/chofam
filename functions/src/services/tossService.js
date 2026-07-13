// 토스페이먼츠 지급대행(Payout) 클라이언트.
// - 인증: Basic base64(TOSS_SECRET_KEY:)
// - Request Body 있는 POST는 보안 키(TOSS_SECURITY_KEY)로 JWE(dir+A256GCM) 암호화 후
//   TossPayments-api-security-mode: ENCRYPTION 헤더와 함께 전송. 응답도 같은 키로 복호화.
// - EXPRESS(바로지급)는 영업일 08:00~15:00 KST에만 가능 → 그 외에는 다음 영업일
//   SCHEDULED로 자동 전환한다(공휴일은 판정 불가 — 토스가 거절하면 에러로 표면화).
const crypto = require('crypto');

const API_BASE = () => process.env.TOSS_API_BASE || 'https://api.tosspayments.com';

function isConfigured() {
  return Boolean(process.env.TOSS_SECRET_KEY && process.env.TOSS_SECURITY_KEY);
}

// 보안 키 → 32바이트 AES-256 키.
// 발급 형식(base64/utf8)은 실키로 검증 필요: base64 디코드가 32바이트면 그것을,
// 아니면 utf8 바이트가 32바이트일 때 그대로 사용한다.
function keyBytes() {
  const raw = process.env.TOSS_SECURITY_KEY || '';
  try {
    const b64 = Buffer.from(raw, 'base64');
    if (b64.length === 32 && b64.toString('base64').replace(/=+$/, '') === raw.replace(/=+$/, '')) {
      return b64;
    }
  } catch (_) { /* fall through */ }
  const utf8 = Buffer.from(raw, 'utf8');
  if (utf8.length === 32) return utf8;
  const err = new Error('invalid_toss_security_key');
  err.status = 500;
  throw err;
}

const b64url = (buf) => Buffer.from(buf).toString('base64url');

// JWE Compact (alg=dir, enc=A256GCM)를 Node 내장 crypto로 직접 구성.
// dir 방식은 CEK가 곧 보안 키이므로 encrypted key 파트가 빈 문자열이다.
// AAD는 JWE 스펙대로 protected header의 base64url ASCII 바이트.
async function encryptBody(body) {
  const header = {
    alg: 'dir',
    enc: 'A256GCM',
    iat: new Date().toISOString(),
    nonce: crypto.randomUUID(),
  };
  const protectedB64 = b64url(JSON.stringify(header));
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', keyBytes(), iv);
  cipher.setAAD(Buffer.from(protectedB64, 'ascii'));
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(body), 'utf8'),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return `${protectedB64}..${b64url(iv)}.${b64url(ciphertext)}.${b64url(tag)}`;
}

async function decryptBody(jwe) {
  const [protectedB64, encryptedKey, ivB64, ctB64, tagB64] = jwe.split('.');
  if (encryptedKey !== '') {
    throw new Error('unexpected_jwe_alg'); // dir이 아니면 encrypted key가 비어있지 않음
  }
  const decipher = crypto.createDecipheriv(
    'aes-256-gcm', keyBytes(), Buffer.from(ivB64, 'base64url'),
  );
  decipher.setAAD(Buffer.from(protectedB64, 'ascii'));
  decipher.setAuthTag(Buffer.from(tagB64, 'base64url'));
  const plaintext = Buffer.concat([
    decipher.update(Buffer.from(ctB64, 'base64url')),
    decipher.final(),
  ]);
  return JSON.parse(plaintext.toString('utf8'));
}

async function tossPost(path, body) {
  const encrypted = await encryptBody(body);
  const res = await fetch(`${API_BASE()}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${Buffer.from(`${process.env.TOSS_SECRET_KEY}:`).toString('base64')}`,
      'TossPayments-api-security-mode': 'ENCRYPTION',
      'Content-Type': 'text/plain',
    },
    body: encrypted,
  });

  const text = await res.text();
  // 정상 응답은 JWE로 암호화되어 온다. 에러 응답은 평문 JSON일 수 있어 둘 다 시도.
  let data;
  try {
    data = await decryptBody(text);
  } catch (_) {
    try {
      data = JSON.parse(text);
    } catch (__) {
      data = { raw: text };
    }
  }

  if (!res.ok) {
    const err = new Error(
      (data && data.error && data.error.message) || (data && data.message) || `toss_http_${res.status}`
    );
    err.status = 502;
    err.code = (data && data.error && data.error.code) || (data && data.code) || 'toss_error';
    throw err;
  }
  return data;
}

// EXPRESS 가능 시간창(KST 월~금 08:00~15:00) 판정. 밖이면 다음 영업일 SCHEDULED.
// (당일 08시 이전이어도 보수적으로 익영업일 예약 — 예약 지급일은 미래 날짜여야 함)
function resolveSchedule(now = new Date()) {
  const kst = new Date(now.getTime() + 9 * 3600 * 1000);
  const day = kst.getUTCDay(); // 0=일 ... 6=토
  const hour = kst.getUTCHours();
  const isBusinessDay = day >= 1 && day <= 5;
  if (isBusinessDay && hour >= 8 && hour < 15) {
    return { scheduleType: 'EXPRESS', payoutDate: null };
  }
  const next = new Date(kst);
  do {
    next.setUTCDate(next.getUTCDate() + 1);
  } while (next.getUTCDay() === 0 || next.getUTCDay() === 6);
  const payoutDate = next.toISOString().slice(0, 10);
  return { scheduleType: 'SCHEDULED', payoutDate };
}

// 셀러(지급 대상) 등록 — 개인(INDIVIDUAL) 크리에이터.
async function registerSeller({ refSellerId, bankCode, accountNumber, holderName }) {
  const data = await tossPost('/v2/sellers', {
    refSellerId,
    businessType: 'INDIVIDUAL',
    account: { bankCode, accountNumber, holderName },
  });
  return { sellerId: data.id, status: data.status };
}

// 지급 요청. amount는 KRW 정수.
// (amount의 Money 객체({currency,value}) 여부 등 세부 스키마는 테스트 키로 검증 필요)
async function requestPayout({ refPayoutId, sellerId, amount, description }, now = new Date()) {
  const { scheduleType, payoutDate } = resolveSchedule(now);
  const body = {
    refPayoutId,
    destination: sellerId,
    scheduleType,
    amount: { currency: 'KRW', value: amount },
    transactionDescription: description || '',
  };
  if (payoutDate) body.payoutDate = payoutDate;

  const data = await tossPost('/v2/payouts', body);
  const first = Array.isArray(data) ? data[0] : data;
  return {
    payoutId: first && first.id,
    status: first && first.status,
    scheduleType,
    payoutDate,
  };
}

module.exports = {
  isConfigured,
  resolveSchedule,
  registerSeller,
  requestPayout,
  // 테스트용 내보내기
  encryptBody,
  decryptBody,
};
