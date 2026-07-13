const express = require('express');
const { requireApiKey } = require('../middleware/apiKeyAuth');
const tossService = require('../services/tossService');
const { payoutLogs } = require('../services/firestore');
const asyncHandler = require('../middleware/asyncHandler');

const router = express.Router();

router.use(requireApiKey);

// 지급 API 사용을 허용할 소스 목록 (MAIL_ADMIN_SOURCES 패턴)
function getPayoutSources() {
  return (process.env.PAYOUT_SOURCES || 'liv-ay').split(',');
}

router.use((req, res, next) => {
  if (!getPayoutSources().includes(req.source)) {
    console.warn(`[PayoutAuth] Forbidden source: '${req.source}'`);
    return res.status(403).json({ ok: false, error: 'forbidden' });
  }
  if (!tossService.isConfigured()) {
    return res.status(503).json({ ok: false, error: 'payout_not_configured' });
  }
  next();
});

// POST /payout/sellers  { refSellerId, bankCode, accountNumber, holderName }
router.post('/sellers', asyncHandler(async (req, res) => {
  const { refSellerId, bankCode, accountNumber, holderName } = req.body || {};
  if (!refSellerId || !bankCode || !accountNumber || !holderName) {
    return res.status(400).json({ ok: false, error: 'seller_fields_required' });
  }

  const result = await tossService.registerSeller({ refSellerId, bankCode, accountNumber, holderName });

  await payoutLogs.add({
    type: 'seller_registered',
    source: req.source,
    refSellerId,
    sellerId: result.sellerId,
    status: result.status,
    createdAt: new Date(),
  });
  res.json({ ok: true, ...result });
}));

// POST /payout/request  { refPayoutId, sellerId, amount, description }
router.post('/request', asyncHandler(async (req, res) => {
  const { refPayoutId, sellerId, amount, description } = req.body || {};
  if (!refPayoutId || !sellerId) {
    return res.status(400).json({ ok: false, error: 'payout_fields_required' });
  }
  if (!Number.isInteger(amount) || amount <= 0) {
    return res.status(400).json({ ok: false, error: 'invalid_amount' });
  }

  const result = await tossService.requestPayout({ refPayoutId, sellerId, amount, description });

  await payoutLogs.add({
    type: 'payout_requested',
    source: req.source,
    refPayoutId,
    sellerId,
    amount,
    scheduleType: result.scheduleType,
    payoutDate: result.payoutDate,
    tossPayoutId: result.payoutId || null,
    status: result.status || 'REQUESTED',
    createdAt: new Date(),
  });
  res.json({ ok: true, ...result });
}));

module.exports = router;
