const required = [
  'REACT_APP_API_BASE_URL',
  'REACT_APP_COGNITO_USER_POOL_ID',
  'REACT_APP_COGNITO_USER_POOL_CLIENT_ID',
];

const missing = required.filter((name) => !process.env[name]?.trim());
if (missing.length > 0) {
  console.error(`Missing required environment variables: ${missing.join(', ')}`);
  process.exit(1);
}
