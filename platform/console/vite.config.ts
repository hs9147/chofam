import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// 백엔드 라우터는 모두 /api/v1 아래 마운트된다 — /health, /status만 예외
// (app/main.py의 API_PREFIX, app/lib/api.ts의 UNPREFIXED_PATHS와 동일해야 함).
const API_PREFIXES = ['/api/v1', '/health', '/status'];

export default defineConfig({
  plugins: [react()],
  base: '/console/',
  server: {
    proxy: Object.fromEntries(
      API_PREFIXES.map((p) => [p, { target: 'http://localhost:7000', changeOrigin: true }]),
    ),
  },
  test: {
    environment: 'node',
  },
});
