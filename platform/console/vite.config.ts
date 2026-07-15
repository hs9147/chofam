/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 백엔드에 공통 /api prefix가 없으므로 라우터 prefix를 열거해 프록시한다
const API_PREFIXES = [
  '/projects', '/modules', '/llm', '/chat', '/changes', '/previews',
  '/status', '/audit', '/keys', '/health', '/webhooks', '/orgs',
];

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
