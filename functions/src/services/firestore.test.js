beforeEach(() => {
  jest.resetModules();
  jest.clearAllMocks();
});

describe('firestore service', () => {
  let admin;

  beforeEach(() => {
    jest.mock('firebase-admin', () => {
      const collectionMock = jest.fn();
      const firestoreMock = jest.fn(() => ({
        collection: collectionMock
      }));
      return {
        apps: [],
        initializeApp: jest.fn(),
        firestore: firestoreMock
      };
    });

    admin = require('firebase-admin');
  });

  it('should call initializeApp when admin.apps.length is 0', () => {
    admin.apps.length = 0;

    require('./firestore');

    expect(admin.initializeApp).toHaveBeenCalledTimes(1);
  });

  it('should not call initializeApp when admin.apps.length is > 0', () => {
    admin.apps = ['app1'];

    require('./firestore');

    expect(admin.initializeApp).not.toHaveBeenCalled();
  });

  it('should initialize db, mailLogs, and mailTemplates correctly', () => {
    admin.apps.length = 0;

    // Mock the collection implementation for this test
    const mockCollection = jest.fn((name) => `collection_${name}`);
    admin.firestore.mockImplementationOnce(() => ({
      collection: mockCollection
    }));

    const firestore = require('./firestore');

    expect(admin.firestore).toHaveBeenCalledTimes(1);
    expect(mockCollection).toHaveBeenCalledWith('mail_logs');
    expect(mockCollection).toHaveBeenCalledWith('mail_templates');

    expect(firestore.db).toBeDefined();
    expect(firestore.mailLogs).toBe('collection_mail_logs');
    expect(firestore.mailTemplates).toBe('collection_mail_templates');
  });
});
