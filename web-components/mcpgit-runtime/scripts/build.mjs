import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const corePath = path.join(root, 'src', 'core.js');
const indexPath = path.join(root, 'src', 'index.js');
const outDir = path.join(root, '0.1.1');
const outPath = path.join(outDir, 'index.js');

const core = await readFile(corePath, 'utf8');
const index = await readFile(indexPath, 'utf8');
const importLine = "import { McpGitClient, McpGitError, McpGitHttpTransport, McpGitView } from './core.js';\n";
if (!index.startsWith(importLine)) throw new Error('unexpected src/index.js import boundary');
const reexportLine = "export { McpGitClient, McpGitError, McpGitHttpTransport, McpGitView };";
const host = index.slice(importLine.length)
  .split('\n')
  .filter(line => line.trim() !== reexportLine)
  .join('\n');

await mkdir(outDir, { recursive: true });
await writeFile(outPath, core.trimEnd() + '\n\n' + host, 'utf8');
console.log('WROTE 0.1.1/index.js');
