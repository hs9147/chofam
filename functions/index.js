const { onRequest } = require('firebase-functions/v2/https');
const app = require('./src/app');

exports.api = onRequest(
  { region: 'us-central1', secrets: ['SENDGRID_API_KEY', 'MAIL_API_KEYS'] },
  app
);
