import { defineConfig } from 'vite';

// Builds the app as one IIFE that expects React 18 UMD globals (loaded from a CDN by the host page).
// Used only to produce the single-file preview. Normal builds use vite.config.ts.
export default defineConfig({
  esbuild: { jsx: 'transform', jsxInject: "import React from 'react'" },
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: 'dist-artifact',
    emptyOutDir: true,
    cssCodeSplit: false,
    minify: 'esbuild',
    lib: { entry: 'src/main.tsx', name: 'HappenMUJ', formats: ['iife'], fileName: () => 'app.js' },
    rollupOptions: {
      external: ['react', 'react-dom', 'react-dom/client'],
      output: { globals: { react: 'React', 'react-dom': 'ReactDOM', 'react-dom/client': 'ReactDOM' }, assetFileNames: 'app.[ext]' },
    },
  },
});
