import { fetchAuthSession } from 'aws-amplify/auth';
import App, { authFetch } from './App';

jest.mock('aws-amplify/auth', () => ({
  fetchAuthSession: jest.fn(),
  signOut: jest.fn(),
  updatePassword: jest.fn(),
}));

beforeEach(() => {
  fetchAuthSession.mockReset();
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
});

test('exports the application component', () => {
  expect(App).toBeDefined();
});

test('authFetch sends the Cognito ID token only to the requested backend', async () => {
  fetchAuthSession.mockResolvedValue({
    tokens: {
      idToken: { toString: () => 'test-id-token' },
    },
  });

  await authFetch('/settings', { method: 'POST', body: '{}' });

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe('/settings');
  expect(options.headers.get('Authorization')).toBe('test-id-token');
  expect(options.headers.get('Content-Type')).toBe('application/json');
});

test('authFetch does not call the API without an ID token', async () => {
  fetchAuthSession.mockResolvedValue({ tokens: {} });

  await expect(authFetch('/settings')).rejects.toThrow('再ログイン');
  expect(global.fetch).not.toHaveBeenCalled();
});
