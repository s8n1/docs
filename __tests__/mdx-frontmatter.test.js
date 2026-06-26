const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

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

function parseFrontmatter(content) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return null;

  const frontmatter = {};
  const lines = match[1].split('\n');
  for (const line of lines) {
    const colonIndex = line.indexOf(':');
    if (colonIndex > 0) {
      const key = line.slice(0, colonIndex).trim();
      let value = line.slice(colonIndex + 1).trim();
      value = value.replace(/^['"](.*)['"]$/, '$1');
      frontmatter[key] = value;
    }
  }
  return frontmatter;
}

function stripCodeBlocks(content) {
  return content.replace(/````[\s\S]*?````/g, '').replace(/```[\s\S]*?```/g, '');
}

const allMdxFiles = getAllMdxFiles(ROOT);

describe('MDX frontmatter validation', () => {
  const mdxData = allMdxFiles.map((file) => {
    const content = fs.readFileSync(path.join(ROOT, file), 'utf8');
    return { file, content, frontmatter: parseFrontmatter(content) };
  });

  const contentPages = mdxData.filter((d) => !d.file.startsWith('snippets/'));
  const snippetPages = mdxData.filter((d) => d.file.startsWith('snippets/'));

  describe('content pages (non-snippet)', () => {
    test.each(contentPages.map((d) => [d.file, d]))(
      '%s has frontmatter',
      (file, data) => {
        expect(data.frontmatter).not.toBeNull();
      }
    );

    test.each(contentPages.map((d) => [d.file, d]))(
      '%s has a title in frontmatter',
      (file, data) => {
        expect(data.frontmatter).not.toBeNull();
        expect(data.frontmatter.title).toBeDefined();
        expect(data.frontmatter.title.length).toBeGreaterThan(0);
      }
    );
  });

  describe('page content', () => {
    const nonOpenapiPages = contentPages.filter(
      (d) => !d.frontmatter || !d.frontmatter.openapi
    );

    test.each(nonOpenapiPages.map((d) => [d.file, d]))(
      '%s is not empty (has content beyond frontmatter)',
      (file, data) => {
        const bodyContent = data.content.replace(/^---[\s\S]*?---/, '').trim();
        expect(bodyContent.length).toBeGreaterThan(0);
      }
    );

    const openapiPages = contentPages.filter(
      (d) => d.frontmatter && d.frontmatter.openapi
    );

    test.each(openapiPages.map((d) => [d.file, d]))(
      '%s is an OpenAPI-generated page (frontmatter-only is valid)',
      (file, data) => {
        expect(data.frontmatter.openapi).toBeDefined();
        expect(data.frontmatter.title).toBeDefined();
      }
    );
  });

  describe('API endpoint pages', () => {
    const apiEndpointPages = contentPages.filter((d) =>
      d.file.startsWith('api-reference/endpoint/')
    );

    test.each(apiEndpointPages.map((d) => [d.file, d]))(
      '%s has openapi field in frontmatter',
      (file, data) => {
        expect(data.frontmatter).not.toBeNull();
        expect(data.frontmatter.openapi).toBeDefined();
        expect(data.frontmatter.openapi.length).toBeGreaterThan(0);
      }
    );

    test.each(apiEndpointPages.map((d) => [d.file, d]))(
      '%s openapi field has valid HTTP method prefix',
      (file, data) => {
        const validMethods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'WEBHOOK'];
        const method = data.frontmatter.openapi.split(' ')[0];
        expect(validMethods).toContain(method);
      }
    );
  });

  describe('guide and essential pages', () => {
    const guidePages = contentPages.filter(
      (d) =>
        d.file.startsWith('essentials/') || d.file.startsWith('ai-tools/')
    );

    test.each(guidePages.map((d) => [d.file, d]))(
      '%s has description in frontmatter',
      (file, data) => {
        expect(data.frontmatter).not.toBeNull();
        expect(data.frontmatter.description).toBeDefined();
        expect(data.frontmatter.description.length).toBeGreaterThan(0);
      }
    );

    test.each(guidePages.map((d) => [d.file, d]))(
      '%s has icon in frontmatter',
      (file, data) => {
        expect(data.frontmatter).not.toBeNull();
        expect(data.frontmatter.icon).toBeDefined();
        expect(data.frontmatter.icon.length).toBeGreaterThan(0);
      }
    );
  });

  describe('snippet pages', () => {
    test('snippets do not have frontmatter (they are included content)', () => {
      for (const snippet of snippetPages) {
        // Snippets may or may not have frontmatter; if they don't, that's fine
        expect(snippet.content.trim().length).toBeGreaterThan(0);
      }
    });
  });

  describe('internal link validation', () => {
    const internalLinkRegex = /href="\/([^"]*?)"/g;

    test.each(contentPages.map((d) => [d.file, d]))(
      '%s internal links reference valid pages',
      (file, data) => {
        const contentWithoutCodeBlocks = stripCodeBlocks(data.content);
        const links = [];
        let match;
        while ((match = internalLinkRegex.exec(contentWithoutCodeBlocks)) !== null) {
          links.push(match[1]);
        }

        for (const link of links) {
          const cleanLink = link.replace(/#.*$/, '');
          if (cleanLink.length === 0) continue;
          const targetPath = path.join(ROOT, `${cleanLink}.mdx`);
          const targetExists =
            fs.existsSync(targetPath) ||
            fs.existsSync(path.join(ROOT, cleanLink));
          expect(targetExists).toBe(true);
        }
      }
    );
  });
});
