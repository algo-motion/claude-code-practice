import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `npm run dev` proxy API sang Flask (python -m flask --app app run --port 5000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:5000', '/auth': 'http://127.0.0.1:5000' } },
});
