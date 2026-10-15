import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const isLib = process.env.BUILD_MODE === 'lib';

export default defineConfig({
  plugins: [
    react(),
    isLib && dts({
      tsconfigPath: './tsconfig.app.json',
      rollupTypes: true,
      include: ['src'],
    }),
  ].filter(Boolean),
  build: isLib
    ? {
        lib: {
          entry: resolve(__dirname, 'src/index.ts'),
          name: 'TempleChatbot',
          fileName: (format) => `temple-chatbot.${format}.js`,
          formats: ['es', 'umd'],
        },
        rollupOptions: {
          external: ['react', 'react-dom', 'react/jsx-runtime'],
          output: {
            exports: 'named',
            globals: {
              react: 'React',
              'react-dom': 'ReactDOM',
              'react/jsx-runtime': 'jsxRuntime',
            },
            assetFileNames: (assetInfo) => {
              if (assetInfo.name && assetInfo.name.endsWith('.css')) {
                return 'temple-chatbot.css';
              }
              return assetInfo.name || 'assets/[name]-[hash][extname]';
            },
          },
        },
        sourcemap: true,
        emptyOutDir: true,
      }
    : {
        outDir: 'dist-demo',
      },
});
