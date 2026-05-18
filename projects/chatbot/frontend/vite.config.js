import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// Plugin: serve workspace docs/ at /agentdocs in dev
function serveDocsPlugin() {
  const docsDir = path.resolve(__dirname, '../../../docs')
  const mimeMap = { '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript', '.json': 'application/json' }
  return {
    name: 'serve-docs',
    configureServer(server) {
      server.middlewares.use('/agentdocs', (req, res, next) => {
        const relPath = req.url === '/' ? 'index.html' : req.url.replace(/^\//, '')
        const filePath = path.join(docsDir, relPath)
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          const ext = path.extname(filePath)
          res.setHeader('Content-Type', mimeMap[ext] || 'text/plain')
          res.end(fs.readFileSync(filePath))
        } else {
          next()
        }
      })
    }
  }
}

export default defineConfig({
  plugins: [react(), serveDocsPlugin()],
  root: '.',
  base: '/chatbot/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
