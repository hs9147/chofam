const express = require('express');
const cors = require('cors');
const mailRouter = require('./routes/mail');
const payoutRouter = require('./routes/payout');
const billingRouter = require('./routes/billing');

const app = express();
const allowedOrigins = [
  'https://cho-fam.web.app',
  'https://hi-liv-ay.netlify.app'
];

app.use(cors({ origin: allowedOrigins }));
app.use(express.json());

app.get(['/health', '/api/health'], (req, res) => res.json({ ok: true }));
app.use(['/mail', '/api/mail'], mailRouter);
app.use(['/payout', '/api/payout'], payoutRouter);
app.use(['/billing', '/api/billing'], billingRouter);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(err.status || 500).json({ ok: false, error: err.message || 'internal_error' });
});

module.exports = app;
