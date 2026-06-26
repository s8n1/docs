const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const docsConfig = JSON.parse(fs.readFileSync(path.join(ROOT, 'docs.json'), 'utf8'));

describe('docs.json configuration', () => {
  test('is valid JSON and loads without error', () => {
    expect(docsConfig).toBeDefined();
    expect(typeof docsConfig).toBe('object');
  });

  describe('required top-level fields', () => {
    test('has $schema field', () => {
      expect(docsConfig.$schema).toBeDefined();
      expect(typeof docsConfig.$schema).toBe('string');
    });

    test('has name field', () => {
      expect(docsConfig.name).toBeDefined();
      expect(typeof docsConfig.name).toBe('string');
      expect(docsConfig.name.length).toBeGreaterThan(0);
    });

    test('has theme field', () => {
      expect(docsConfig.theme).toBeDefined();
      expect(typeof docsConfig.theme).toBe('string');
    });

    test('has favicon field pointing to an existing file', () => {
      expect(docsConfig.favicon).toBeDefined();
      const faviconPath = path.join(ROOT, docsConfig.favicon);
      expect(fs.existsSync(faviconPath)).toBe(true);
    });
  });

  describe('colors configuration', () => {
    const hexColorRegex = /^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/;

    test('has colors object', () => {
      expect(docsConfig.colors).toBeDefined();
      expect(typeof docsConfig.colors).toBe('object');
    });

    test('has valid primary color (hex)', () => {
      expect(docsConfig.colors.primary).toBeDefined();
      expect(docsConfig.colors.primary).toMatch(hexColorRegex);
    });

    test('has valid light color (hex) if present', () => {
      if (docsConfig.colors.light) {
        expect(docsConfig.colors.light).toMatch(hexColorRegex);
      }
    });

    test('has valid dark color (hex) if present', () => {
      if (docsConfig.colors.dark) {
        expect(docsConfig.colors.dark).toMatch(hexColorRegex);
      }
    });
  });

  describe('logo configuration', () => {
    test('has logo object', () => {
      expect(docsConfig.logo).toBeDefined();
      expect(typeof docsConfig.logo).toBe('object');
    });

    test('light logo file exists', () => {
      expect(docsConfig.logo.light).toBeDefined();
      const logoPath = path.join(ROOT, docsConfig.logo.light);
      expect(fs.existsSync(logoPath)).toBe(true);
    });

    test('dark logo file exists', () => {
      expect(docsConfig.logo.dark).toBeDefined();
      const logoPath = path.join(ROOT, docsConfig.logo.dark);
      expect(fs.existsSync(logoPath)).toBe(true);
    });
  });

  describe('navigation structure', () => {
    test('has navigation object with tabs', () => {
      expect(docsConfig.navigation).toBeDefined();
      expect(docsConfig.navigation.tabs).toBeDefined();
      expect(Array.isArray(docsConfig.navigation.tabs)).toBe(true);
      expect(docsConfig.navigation.tabs.length).toBeGreaterThan(0);
    });

    test('each tab has a name and groups', () => {
      for (const tab of docsConfig.navigation.tabs) {
        expect(tab.tab).toBeDefined();
        expect(typeof tab.tab).toBe('string');
        expect(tab.groups).toBeDefined();
        expect(Array.isArray(tab.groups)).toBe(true);
        expect(tab.groups.length).toBeGreaterThan(0);
      }
    });

    test('each group has a name and pages array', () => {
      for (const tab of docsConfig.navigation.tabs) {
        for (const group of tab.groups) {
          expect(group.group).toBeDefined();
          expect(typeof group.group).toBe('string');
          expect(group.pages).toBeDefined();
          expect(Array.isArray(group.pages)).toBe(true);
          expect(group.pages.length).toBeGreaterThan(0);
        }
      }
    });

    test('all page references in navigation resolve to existing .mdx files', () => {
      const missingPages = [];
      for (const tab of docsConfig.navigation.tabs) {
        for (const group of tab.groups) {
          for (const page of group.pages) {
            const pagePath = path.join(ROOT, `${page}.mdx`);
            if (!fs.existsSync(pagePath)) {
              missingPages.push(page);
            }
          }
        }
      }
      expect(missingPages).toEqual([]);
    });

    test('no duplicate page references across navigation', () => {
      const allPages = [];
      for (const tab of docsConfig.navigation.tabs) {
        for (const group of tab.groups) {
          allPages.push(...group.pages);
        }
      }
      const duplicates = allPages.filter((page, i) => allPages.indexOf(page) !== i);
      expect(duplicates).toEqual([]);
    });
  });

  describe('navbar configuration', () => {
    test('has navbar object if present', () => {
      if (docsConfig.navbar) {
        expect(typeof docsConfig.navbar).toBe('object');
      }
    });

    test('navbar links have label and href', () => {
      if (docsConfig.navbar && docsConfig.navbar.links) {
        for (const link of docsConfig.navbar.links) {
          expect(link.label).toBeDefined();
          expect(typeof link.label).toBe('string');
          expect(link.href).toBeDefined();
          expect(typeof link.href).toBe('string');
        }
      }
    });

    test('navbar primary button has required fields', () => {
      if (docsConfig.navbar && docsConfig.navbar.primary) {
        expect(docsConfig.navbar.primary.type).toBeDefined();
        expect(docsConfig.navbar.primary.label).toBeDefined();
        expect(docsConfig.navbar.primary.href).toBeDefined();
      }
    });
  });

  describe('global anchors', () => {
    test('anchors have required fields', () => {
      if (docsConfig.navigation.global && docsConfig.navigation.global.anchors) {
        for (const anchor of docsConfig.navigation.global.anchors) {
          expect(anchor.anchor).toBeDefined();
          expect(typeof anchor.anchor).toBe('string');
          expect(anchor.href).toBeDefined();
          expect(typeof anchor.href).toBe('string');
          expect(anchor.icon).toBeDefined();
          expect(typeof anchor.icon).toBe('string');
        }
      }
    });

    test('anchor hrefs are valid URLs', () => {
      const urlRegex = /^https?:\/\//;
      if (docsConfig.navigation.global && docsConfig.navigation.global.anchors) {
        for (const anchor of docsConfig.navigation.global.anchors) {
          expect(anchor.href).toMatch(urlRegex);
        }
      }
    });
  });

  describe('footer configuration', () => {
    test('social links are valid URLs if present', () => {
      const urlRegex = /^https?:\/\//;
      if (docsConfig.footer && docsConfig.footer.socials) {
        for (const [platform, url] of Object.entries(docsConfig.footer.socials)) {
          expect(url).toMatch(urlRegex);
        }
      }
    });
  });
});
