const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const docsConfig = JSON.parse(fs.readFileSync(path.join(ROOT, 'docs.json'), 'utf8'));

function getAllMdxFiles(dir, baseDir) {
  baseDir = baseDir || dir;
  let results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && entry.name !== 'node_modules' && entry.name !== '__tests__' && !entry.name.startsWith('.')) {
      results = results.concat(getAllMdxFiles(fullPath, baseDir));
    } else if (entry.isFile() && entry.name.endsWith('.mdx')) {
      results.push(path.relative(baseDir, fullPath));
    }
  }
  return results;
}

function getNavigationPages() {
  const pages = [];
  for (const tab of docsConfig.navigation.tabs) {
    for (const group of tab.groups) {
      pages.push(...group.pages);
    }
  }
  return pages;
}

describe('documentation structure', () => {
  const allMdxFiles = getAllMdxFiles(ROOT);
  const navPages = getNavigationPages();

  describe('file existence', () => {
    test('docs.json exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'docs.json'))).toBe(true);
    });

    test('README.md exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'README.md'))).toBe(true);
    });

    test('favicon file exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'favicon.svg'))).toBe(true);
    });

    test('logo files exist', () => {
      expect(fs.existsSync(path.join(ROOT, 'logo', 'light.svg'))).toBe(true);
      expect(fs.existsSync(path.join(ROOT, 'logo', 'dark.svg'))).toBe(true);
    });
  });

  describe('navigation completeness', () => {
    test('every content MDX file (excluding snippets) is referenced in navigation', () => {
      const unreferenced = [];
      for (const mdxFile of allMdxFiles) {
        const pageName = mdxFile.replace(/\.mdx$/, '');
        const isSnippet = mdxFile.startsWith('snippets/');
        if (!isSnippet && !navPages.includes(pageName)) {
          unreferenced.push(pageName);
        }
      }
      expect(unreferenced).toEqual([]);
    });

    test('every navigation page reference has a corresponding MDX file', () => {
      const missing = [];
      for (const page of navPages) {
        const filePath = path.join(ROOT, `${page}.mdx`);
        if (!fs.existsSync(filePath)) {
          missing.push(page);
        }
      }
      expect(missing).toEqual([]);
    });
  });

  describe('image references', () => {
    test('images directory exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'images'))).toBe(true);
    });

    test('image files in images/ are valid formats', () => {
      const validExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
      const imageFiles = fs.readdirSync(path.join(ROOT, 'images'));
      for (const file of imageFiles) {
        const ext = path.extname(file).toLowerCase();
        expect(validExtensions).toContain(ext);
      }
    });

    test('logo files are SVG format', () => {
      const logoDir = path.join(ROOT, 'logo');
      if (fs.existsSync(logoDir)) {
        const logoFiles = fs.readdirSync(logoDir);
        for (const file of logoFiles) {
          expect(path.extname(file).toLowerCase()).toBe('.svg');
        }
      }
    });
  });

  describe('snippet structure', () => {
    test('snippets directory exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'snippets'))).toBe(true);
    });

    test('snippet files are MDX format', () => {
      const snippetDir = path.join(ROOT, 'snippets');
      const snippetFiles = fs.readdirSync(snippetDir);
      for (const file of snippetFiles) {
        expect(path.extname(file)).toBe('.mdx');
      }
    });

    test('snippet files are not empty', () => {
      const snippetDir = path.join(ROOT, 'snippets');
      const snippetFiles = fs.readdirSync(snippetDir);
      for (const file of snippetFiles) {
        const content = fs.readFileSync(path.join(snippetDir, file), 'utf8');
        expect(content.trim().length).toBeGreaterThan(0);
      }
    });
  });

  describe('directory structure', () => {
    test('expected content directories exist', () => {
      const expectedDirs = ['essentials', 'api-reference', 'ai-tools'];
      for (const dir of expectedDirs) {
        expect(fs.existsSync(path.join(ROOT, dir))).toBe(true);
      }
    });

    test('api-reference/endpoint directory exists', () => {
      expect(fs.existsSync(path.join(ROOT, 'api-reference', 'endpoint'))).toBe(true);
    });

    test('openapi.json exists in api-reference directory', () => {
      expect(fs.existsSync(path.join(ROOT, 'api-reference', 'openapi.json'))).toBe(true);
    });
  });
});
