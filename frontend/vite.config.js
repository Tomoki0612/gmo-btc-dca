import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

const requiredEnv = [
  'REACT_APP_API_BASE_URL',
  'REACT_APP_COGNITO_USER_POOL_ID',
  'REACT_APP_COGNITO_USER_POOL_CLIENT_ID',
];

export default defineConfig(({ mode }) => {
  if (mode !== 'test') {
    const env = loadEnv(mode, process.cwd(), 'REACT_APP_');
    const missing = requiredEnv.filter((name) => !env[name]?.trim());
    if (missing.length) {
      throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
    }
  }

  return {
    plugins: [react()],
    envPrefix: 'REACT_APP_',
    build: { outDir: 'build' },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/setupTests.js'],
      server: {
        deps: {
          // Load the Authenticator through Vitest so its Auth and QR imports can be mocked.
          inline: [/@aws-amplify\/ui(?:-react(?:-core)?)?\//],
        },
      },
    },
  };
});
