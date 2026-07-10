const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const mailLogs = db.collection('mail_logs');
const mailTemplates = db.collection('mail_templates');

module.exports = { mailLogs, mailTemplates };
