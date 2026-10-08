import { materializeSchemaDefaults } from "./utils";
import { JSONSchemaProperty } from "./types";

const postgresSchema: JSONSchemaProperty = {
  type: "object",
  definitions: {
    ssl: {
      type: "object",
      properties: {
        mode: { type: "string", default: "prefer" },
        verify: { type: "boolean", default: false },
      },
    },
  },
  properties: {
    host: { type: "string" },
    port: { type: "integer", default: 5432 },
    replication: {
      default: "CDC",
      oneOf: [
        {
          title: "Standard",
          type: "object",
          properties: {
            method: { type: "string", const: "Standard" },
            heartbeat: { type: "integer", default: 0 },
          },
        },
        {
          title: "CDC",
          allOf: [
            {
              type: "object",
              properties: {
                method: { type: "string", const: "CDC" },
                queue_size: { type: "integer", default: 1000 },
              },
            },
          ],
        },
      ],
    },
    ssl: { $ref: "#/definitions/ssl" },
  },
};

describe("materializeSchemaDefaults", () => {
  it("materializes untouched primitive and nested displayed-branch defaults", () => {
    expect(materializeSchemaDefaults(postgresSchema, {})).toEqual({
      port: 5432,
      replication: { method: "CDC", queue_size: 1000 },
      ssl: { mode: "prefer", verify: false },
    });
  });

  it("preserves explicit false, zero, and user values", () => {
    expect(
      materializeSchemaDefaults(postgresSchema, {
        port: 0,
        ssl: { mode: "require", verify: false },
      })
    ).toEqual({
      port: 0,
      replication: { method: "CDC", queue_size: 1000 },
      ssl: { mode: "require", verify: false },
    });
  });

  it("seeds defaults for the selected discriminated branch", () => {
    expect(
      materializeSchemaDefaults(
        postgresSchema.properties!.replication!,
        {
          method: "CDC",
        },
        postgresSchema
      )
    ).toEqual({ method: "CDC", queue_size: 1000 });
  });

  it("preserves primitive values and defaults in non-discriminated variants", () => {
    const schema: JSONSchemaProperty = {
      anyOf: [{ type: "string", default: "localhost" }, { type: "integer" }],
    };
    expect(materializeSchemaDefaults(schema, undefined)).toBe("localhost");
    expect(materializeSchemaDefaults(schema, "db.internal")).toBe(
      "db.internal"
    );
    expect(
      materializeSchemaDefaults(
        {
          default: "auto",
          anyOf: [{ type: "string" }, { type: "null" }],
        },
        undefined
      )
    ).toBe("auto");
  });

  it("merges object defaults without creating empty optional objects", () => {
    expect(
      materializeSchemaDefaults(
        {
          type: "object",
          default: { mode: "require" },
          properties: {
            mode: { type: "string", default: "prefer" },
            verify: { type: "boolean", default: false },
          },
        },
        { verify: true }
      )
    ).toEqual({ mode: "require", verify: true });
    expect(
      materializeSchemaDefaults(
        {
          type: "object",
          properties: { username: { type: "string" } },
        },
        undefined
      )
    ).toBeUndefined();
  });

  it("preserves an unknown explicit discriminator for validation", () => {
    expect(
      materializeSchemaDefaults(
        postgresSchema.properties!.replication!,
        {
          method: "Custom",
        },
        postgresSchema
      )
    ).toEqual({ method: "Custom" });
  });
});
