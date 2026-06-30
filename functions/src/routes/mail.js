const express = require('express');
const { requireApiKey, requireAdmin } = require('../middleware/apiKeyAuth');
const mailService = require('../services/mailService');
const { mailLogs } = require('../services/firestore');

const router = express.Router();

router.use(requireApiKey);

// POST /mail/send  { to, templateId, dynamicData }
router.post('/send', async (req, res, next) => {
  try {
    const { to, templateId, dynamicData } = req.body || {};
    if (!to || !templateId) {
      return res.status(400).json({ ok: false, error: 'to_and_templateId_required' });
    }
    const result = await mailService.dispatch({ to, templateId, dynamicData, source: req.source });
    res.json({ ok: true, ...result });
  } catch (err) {
    next(err);
  }
});

// GET /mail/logs?source=liv-ay&status=failed&limit=50
router.get('/logs', requireAdmin, async (req, res, next) => {
  try {
    const { source, status, limit } = req.query;
    let query = mailLogs.orderBy('createdAt', 'desc');
    if (source) query = query.where('source', '==', source);
    if (status) query = query.where('status', '==', status);
    query = query.limit(Math.min(Number(limit) || 50, 200));

    const snapshot = await query.get();
    const logs = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
    res.json({ ok: true, logs });
  } catch (err) {
    next(err);
  }
});

// POST /mail/logs/:id/resend
router.post('/logs/:id/resend', requireAdmin, async (req, res, next) => {
  try {
    const result = await mailService.resend(req.params.id);
    res.json({ ok: true, ...result });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
