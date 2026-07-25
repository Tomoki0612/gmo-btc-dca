import { fetchAuthSession } from 'aws-amplify/auth';
import App, { authFetch, buildFeeTiers, validateRecommendedFees } from './App';

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

test('validateRecommendedFees accepts the current one sat/vB response', () => {
  expect(validateRecommendedFees({
    fastestFee: 1,
    halfHourFee: 1,
    hourFee: 1,
    economyFee: 1,
  })).toMatchObject({
    fastestFee: 1,
    halfHourFee: 1,
    hourFee: 1,
  });
});

test('validateRecommendedFees rejects missing or zero fee fields', () => {
  expect(() => validateRecommendedFees({
    fastestFee: 1,
    halfHourFee: 0,
  })).toThrow('レスポンスが不正');
});

test('buildFeeTiers collapses identical recommendations into one card', () => {
  expect(buildFeeTiers({
    fastestFee: 1,
    halfHourFee: 1,
    hourFee: 1,
  })).toMatchObject({
    allSame: true,
    tiers: [{
      k: 'same',
      label: '全速度帯',
      satvb: 1,
    }],
  });
});

test('buildFeeTiers keeps three cards when recommendations differ', () => {
  const result = buildFeeTiers({
    fastestFee: 8,
    halfHourFee: 4,
    hourFee: 2,
  });

  expect(result.allSame).toBe(false);
  expect(result.tiers.map((tier) => tier.satvb)).toEqual([8, 4, 2]);
});
