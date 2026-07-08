const express = require('express');
const cors = require('cors');
const mailRouter = require('./routes/mail');

const app = express();
app.use(cors({ origin: true }));
app.use(express.json());

app.get(['/health', '/api/health'], (req, res) => res.json({ ok: true }));
app.use(['/mail', '/api/mail'], mailRouter);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(err.status || 500).json({ ok: false, error: err.message || 'internal_error' });
});

module.exports = app;
