const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const openapi = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'api-reference', 'openapi.json'), 'utf8')
);

describe('openapi.json API specification', () => {
  test('is valid JSON and loads without error', () => {
    expect(openapi).toBeDefined();
    expect(typeof openapi).toBe('object');
  });

  describe('top-level fields', () => {
    test('has valid openapi version string', () => {
      expect(openapi.openapi).toBeDefined();
      expect(openapi.openapi).toMatch(/^3\.\d+\.\d+$/);
    });

    test('has info object with required fields', () => {
      expect(openapi.info).toBeDefined();
      expect(openapi.info.title).toBeDefined();
      expect(typeof openapi.info.title).toBe('string');
      expect(openapi.info.version).toBeDefined();
      expect(typeof openapi.info.version).toBe('string');
    });

    test('has info description', () => {
      expect(openapi.info.description).toBeDefined();
      expect(typeof openapi.info.description).toBe('string');
      expect(openapi.info.description.length).toBeGreaterThan(0);
    });

    test('has info license', () => {
      expect(openapi.info.license).toBeDefined();
      expect(openapi.info.license.name).toBeDefined();
      expect(typeof openapi.info.license.name).toBe('string');
    });
  });

  describe('servers', () => {
    test('has at least one server', () => {
      expect(openapi.servers).toBeDefined();
      expect(Array.isArray(openapi.servers)).toBe(true);
      expect(openapi.servers.length).toBeGreaterThan(0);
    });

    test('each server has a url', () => {
      for (const server of openapi.servers) {
        expect(server.url).toBeDefined();
        expect(typeof server.url).toBe('string');
        expect(server.url.length).toBeGreaterThan(0);
      }
    });
  });

  describe('security', () => {
    test('has security definitions', () => {
      expect(openapi.security).toBeDefined();
      expect(Array.isArray(openapi.security)).toBe(true);
    });

    test('security schemes are defined in components', () => {
      expect(openapi.components).toBeDefined();
      expect(openapi.components.securitySchemes).toBeDefined();
      for (const securityReq of openapi.security) {
        for (const schemeName of Object.keys(securityReq)) {
          expect(openapi.components.securitySchemes[schemeName]).toBeDefined();
        }
      }
    });

    test('bearer auth scheme is properly configured', () => {
      const bearer = openapi.components.securitySchemes.bearerAuth;
      expect(bearer).toBeDefined();
      expect(bearer.type).toBe('http');
      expect(bearer.scheme).toBe('bearer');
    });
  });

  describe('paths', () => {
    test('has paths object', () => {
      expect(openapi.paths).toBeDefined();
      expect(typeof openapi.paths).toBe('object');
      expect(Object.keys(openapi.paths).length).toBeGreaterThan(0);
    });

    test('all paths start with /', () => {
      for (const pathKey of Object.keys(openapi.paths)) {
        expect(pathKey.startsWith('/')).toBe(true);
      }
    });

    test('each operation has a description', () => {
      for (const [pathKey, methods] of Object.entries(openapi.paths)) {
        for (const [method, operation] of Object.entries(methods)) {
          expect(operation.description).toBeDefined();
          expect(typeof operation.description).toBe('string');
          expect(operation.description.length).toBeGreaterThan(0);
        }
      }
    });

    test('each operation has responses', () => {
      for (const [pathKey, methods] of Object.entries(openapi.paths)) {
        for (const [method, operation] of Object.entries(methods)) {
          expect(operation.responses).toBeDefined();
          expect(Object.keys(operation.responses).length).toBeGreaterThan(0);
        }
      }
    });

    test('GET /plants has limit query parameter', () => {
      const getPlants = openapi.paths['/plants'].get;
      expect(getPlants.parameters).toBeDefined();
      const limitParam = getPlants.parameters.find((p) => p.name === 'limit');
      expect(limitParam).toBeDefined();
      expect(limitParam.in).toBe('query');
      expect(limitParam.schema.type).toBe('integer');
    });

    test('POST /plants has a request body', () => {
      const postPlants = openapi.paths['/plants'].post;
      expect(postPlants.requestBody).toBeDefined();
      expect(postPlants.requestBody.required).toBe(true);
      expect(postPlants.requestBody.content['application/json']).toBeDefined();
    });

    test('DELETE /plants/{id} has id path parameter', () => {
      const deletePlant = openapi.paths['/plants/{id}'].delete;
      expect(deletePlant.parameters).toBeDefined();
      const idParam = deletePlant.parameters.find((p) => p.name === 'id');
      expect(idParam).toBeDefined();
      expect(idParam.in).toBe('path');
      expect(idParam.required).toBe(true);
      expect(idParam.schema.type).toBe('integer');
    });
  });

  describe('webhooks', () => {
    test('has webhooks object if present', () => {
      if (openapi.webhooks) {
        expect(typeof openapi.webhooks).toBe('object');
        expect(Object.keys(openapi.webhooks).length).toBeGreaterThan(0);
      }
    });

    test('webhook operations have descriptions and responses', () => {
      if (openapi.webhooks) {
        for (const [hookPath, methods] of Object.entries(openapi.webhooks)) {
          for (const [method, operation] of Object.entries(methods)) {
            expect(operation.description).toBeDefined();
            expect(operation.responses).toBeDefined();
          }
        }
      }
    });
  });

  describe('component schemas', () => {
    test('has component schemas', () => {
      expect(openapi.components.schemas).toBeDefined();
      expect(Object.keys(openapi.components.schemas).length).toBeGreaterThan(0);
    });

    test('Plant schema has required name field', () => {
      const plant = openapi.components.schemas.Plant;
      expect(plant).toBeDefined();
      expect(plant.type).toBe('object');
      expect(plant.required).toContain('name');
      expect(plant.properties.name).toBeDefined();
      expect(plant.properties.name.type).toBe('string');
    });

    test('Plant schema has optional tag field', () => {
      const plant = openapi.components.schemas.Plant;
      expect(plant.properties.tag).toBeDefined();
      expect(plant.properties.tag.type).toBe('string');
    });

    test('NewPlant schema extends Plant with required id', () => {
      const newPlant = openapi.components.schemas.NewPlant;
      expect(newPlant).toBeDefined();
      expect(newPlant.allOf).toBeDefined();
      expect(Array.isArray(newPlant.allOf)).toBe(true);

      const plantRef = newPlant.allOf.find((s) => s.$ref);
      expect(plantRef.$ref).toBe('#/components/schemas/Plant');

      const idSchema = newPlant.allOf.find((s) => s.properties && s.properties.id);
      expect(idSchema).toBeDefined();
      expect(idSchema.required).toContain('id');
      expect(idSchema.properties.id.type).toBe('integer');
    });

    test('Error schema has required error and message fields', () => {
      const error = openapi.components.schemas.Error;
      expect(error).toBeDefined();
      expect(error.type).toBe('object');
      expect(error.required).toContain('error');
      expect(error.required).toContain('message');
      expect(error.properties.error.type).toBe('integer');
      expect(error.properties.message.type).toBe('string');
    });

    test('all $ref references resolve to existing schemas', () => {
      const schemaNames = Object.keys(openapi.components.schemas);
      const refs = [];

      const collectRefs = (obj) => {
        if (obj && typeof obj === 'object') {
          if (obj.$ref) refs.push(obj.$ref);
          for (const val of Object.values(obj)) {
            collectRefs(val);
          }
        }
      };
      collectRefs(openapi.paths);
      collectRefs(openapi.webhooks);
      collectRefs(openapi.components.schemas);

      for (const ref of refs) {
        const match = ref.match(/^#\/components\/schemas\/(.+)$/);
        if (match) {
          expect(schemaNames).toContain(match[1]);
        }
      }
    });
  });
});
