const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const mailLogs = db.collection('mail_logs');

module.exports = { db, mailLogs };
