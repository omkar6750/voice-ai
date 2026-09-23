import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const source = JSON.parse(readFileSync(new URL('../../../data/openapi.json', import.meta.url), 'utf8'));
mkdirSync(new URL('../src/generated/', import.meta.url), { recursive: true });
writeFileSync(new URL('../src/generated/schema.json', import.meta.url), JSON.stringify(source));
