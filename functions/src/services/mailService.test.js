const { resend, renderTemplate } = require('./mailService');
const { mailLogs } = require('./firestore');
const sgMail = require('@sendgrid/mail');

jest.mock('./firestore', () => ({
  mailLogs: {
    doc: jest.fn(),
    add: jest.fn(),
  },
  mailTemplates: {
    doc: jest.fn(),
  }
}));

jest.mock('@sendgrid/mail', () => ({
  setApiKey: jest.fn(),
  send: jest.fn(),
}));

describe('mailService', () => {
  describe('renderTemplate', () => {
    it('should return an empty string when text is falsy', () => {
      expect(renderTemplate(null, {})).toBe('');
      expect(renderTemplate(undefined, {})).toBe('');
      expect(renderTemplate('', {})).toBe('');
    });

    it('should return the original text when no placeholders are present', () => {
      const text = 'Hello world, this is a plain text.';
      expect(renderTemplate(text, {})).toBe(text);
      expect(renderTemplate(text, { name: 'Jules' })).toBe(text);
    });

    it('should replace a single placeholder', () => {
      const text = 'Hello {{ name }}!';
      expect(renderTemplate(text, { name: 'Jules' })).toBe('Hello Jules!');
    });

    it('should replace multiple placeholders', () => {
      const text = 'Hello {{ name }}, welcome to {{ place }}!';
      expect(renderTemplate(text, { name: 'Jules', place: 'Earth' })).toBe('Hello Jules, welcome to Earth!');
    });

    it('should handle different spacing within placeholders', () => {
      const text1 = 'Hello {{name}}!';
      const text2 = 'Hello {{  name  }}!';
      const text3 = 'Hello {{ name}}!';
      expect(renderTemplate(text1, { name: 'Jules' })).toBe('Hello Jules!');
      expect(renderTemplate(text2, { name: 'Jules' })).toBe('Hello Jules!');
      expect(renderTemplate(text3, { name: 'Jules' })).toBe('Hello Jules!');
    });

    it('should leave placeholder unmodified when corresponding key is missing from data', () => {
      const text = 'Hello {{ name }} and {{ friend }}!';
      expect(renderTemplate(text, { name: 'Jules' })).toBe('Hello Jules and {{ friend }}!');
    });
  });

  describe('resend', () => {
    it('should throw 404 error if mail log does not exist', async () => {
      mailLogs.doc.mockReturnValue({
        get: jest.fn().mockResolvedValue({ exists: false })
      });

      await expect(resend('invalid-log-id')).rejects.toMatchObject({
        message: 'mail_log_not_found',
        status: 404
      });
    });
  });
});
