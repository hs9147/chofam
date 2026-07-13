const crypto = require('crypto');

describe('tossService', () => {
  const KEY = crypto.randomBytes(32).toString('base64');

  beforeEach(() => {
    jest.resetModules();
    process.env.TOSS_SECRET_KEY = 'test_sk';
    process.env.TOSS_SECURITY_KEY = KEY;
    delete process.env.TOSS_API_BASE;
  });

  afterEach(() => {
    delete process.env.TOSS_SECRET_KEY;
    delete process.env.TOSS_SECURITY_KEY;
    delete global.fetch;
  });

  const svc = () => require('./tossService');

  describe('isConfigured', () => {
    it('두 키가 모두 있어야 true', () => {
      expect(svc().isConfigured()).toBe(true);
      delete process.env.TOSS_SECURITY_KEY;
      expect(svc().isConfigured()).toBe(false);
    });
  });

  describe('JWE encrypt/decrypt', () => {
    it('암호화한 본문을 같은 키로 복호화하면 원본과 같다', async () => {
      const { encryptBody, decryptBody } = svc();
      const body = { refPayoutId: 'p-1', amount: { currency: 'KRW', value: 9670 } };
      const jwe = await encryptBody(body);
      expect(jwe.split('.')).toHaveLength(5); // JWE compact 형식
      await expect(decryptBody(jwe)).resolves.toEqual(body);
    });
  });

  describe('resolveSchedule (KST)', () => {
    // Date.UTC 기준: KST = UTC+9
    it('화요일 10시(KST)는 EXPRESS', () => {
      // 2026-07-14(화) 10:00 KST = 01:00 UTC
      const r = svc().resolveSchedule(new Date(Date.UTC(2026, 6, 14, 1, 0)));
      expect(r).toEqual({ scheduleType: 'EXPRESS', payoutDate: null });
    });

    it('금요일 16시(KST)는 다음 월요일 SCHEDULED', () => {
      // 2026-07-17(금) 16:00 KST = 07:00 UTC
      const r = svc().resolveSchedule(new Date(Date.UTC(2026, 6, 17, 7, 0)));
      expect(r).toEqual({ scheduleType: 'SCHEDULED', payoutDate: '2026-07-20' });
    });

    it('토요일은 다음 월요일 SCHEDULED', () => {
      // 2026-07-18(토) 12:00 KST = 03:00 UTC
      const r = svc().resolveSchedule(new Date(Date.UTC(2026, 6, 18, 3, 0)));
      expect(r).toEqual({ scheduleType: 'SCHEDULED', payoutDate: '2026-07-20' });
    });

    it('영업일 08시 이전은 익영업일 SCHEDULED (보수적)', () => {
      // 2026-07-14(화) 07:00 KST = 2026-07-13 22:00 UTC
      const r = svc().resolveSchedule(new Date(Date.UTC(2026, 6, 13, 22, 0)));
      expect(r).toEqual({ scheduleType: 'SCHEDULED', payoutDate: '2026-07-15' });
    });
  });

  describe('registerSeller / requestPayout', () => {
    it('registerSeller는 암호화 요청을 보내고 응답을 복호화해 반환한다', async () => {
      const s = svc();
      global.fetch = jest.fn(async (url, opts) => {
        expect(url).toBe('https://api.tosspayments.com/v2/sellers');
        expect(opts.headers['TossPayments-api-security-mode']).toBe('ENCRYPTION');
        expect(opts.headers.Authorization).toBe(
          `Basic ${Buffer.from('test_sk:').toString('base64')}`
        );
        // 요청 본문이 실제로 JWE로 암호화됐는지 복호화로 확인
        const sent = await s.decryptBody(opts.body);
        expect(sent).toEqual({
          refSellerId: 'u1',
          businessType: 'INDIVIDUAL',
          account: { bankCode: '004', accountNumber: '12345678901234', holderName: '홍길동' },
        });
        return {
          ok: true,
          text: async () => s.encryptBody({ id: 'seller_abc', status: 'APPROVAL_REQUIRED' }),
        };
      });

      const result = await s.registerSeller({
        refSellerId: 'u1', bankCode: '004',
        accountNumber: '12345678901234', holderName: '홍길동',
      });
      expect(result).toEqual({ sellerId: 'seller_abc', status: 'APPROVAL_REQUIRED' });
    });

    it('requestPayout은 시간창에 따라 scheduleType을 정해 전송한다', async () => {
      const s = svc();
      let sentBody;
      global.fetch = jest.fn(async (url, opts) => {
        expect(url).toBe('https://api.tosspayments.com/v2/payouts');
        sentBody = await s.decryptBody(opts.body);
        return {
          ok: true,
          text: async () => s.encryptBody({ id: 'payout_1', status: 'REQUESTED' }),
        };
      });

      // 금요일 16시 KST → SCHEDULED 월요일
      const result = await s.requestPayout(
        { refPayoutId: 'c-1', sellerId: 'seller_abc', amount: 9670, description: 'Liv-ay 정산' },
        new Date(Date.UTC(2026, 6, 17, 7, 0)),
      );
      expect(sentBody).toEqual({
        refPayoutId: 'c-1',
        destination: 'seller_abc',
        scheduleType: 'SCHEDULED',
        payoutDate: '2026-07-20',
        amount: { currency: 'KRW', value: 9670 },
        transactionDescription: 'Liv-ay 정산',
      });
      expect(result).toEqual({
        payoutId: 'payout_1', status: 'REQUESTED',
        scheduleType: 'SCHEDULED', payoutDate: '2026-07-20',
      });
    });

    it('토스 에러 응답(평문 JSON)은 status 502 에러로 전파된다', async () => {
      const s = svc();
      global.fetch = jest.fn(async () => ({
        ok: false,
        status: 400,
        text: async () => JSON.stringify({ error: { code: 'INVALID_ACCOUNT', message: '유효하지 않은 계좌' } }),
      }));

      await expect(
        s.requestPayout({ refPayoutId: 'c-2', sellerId: 's', amount: 10000 })
      ).rejects.toMatchObject({ status: 502, code: 'INVALID_ACCOUNT', message: '유효하지 않은 계좌' });
    });
  });
});
