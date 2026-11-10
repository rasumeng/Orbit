import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: process.env.VITE_ASSET_BASE || '/',
  envDir: process.env.VITE_ENV_DIR || undefined,
  plugins: [react()],
})
