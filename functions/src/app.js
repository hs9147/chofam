const express = require('express');
const cors = require('cors');
const mailRouter = require('./routes/mail');

const app = express();
const allowedOrigins = [
  'https://CHO-FAM.web.app',
  'https://cho-fam.web.app',
  'https://CHO-FAM.firebaseapp.com',
  'https://cho-fam.firebaseapp.com',
  'https://chofam-home.web.app',
  'http://localhost:5000',
  'http://127.0.0.1:5000'
];

app.use(cors({
  origin: function (origin, callback) {
    if (!origin) return callback(null, true);
    if (allowedOrigins.indexOf(origin) !== -1) {
      return callback(null, true);
    }
    return callback(new Error('Not allowed by CORS'));
  }
}));
app.use(express.json());

app.get(['/health', '/api/health'], (req, res) => res.json({ ok: true }));
app.use(['/mail', '/api/mail'], mailRouter);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(err.status || 500).json({ ok: false, error: err.message || 'internal_error' });
});

module.exports = app;
