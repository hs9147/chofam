const { onRequest } = require('firebase-functions/v2/https');
const app = require('./src/app');

exports.api = onRequest(
  {
    region: 'us-central1',
    secrets: ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS', 'MAIL_API_KEYS', 'TOSS_SECRET_KEY', 'TOSS_SECURITY_KEY'],
    invoker: 'public',
  },
  app
);
