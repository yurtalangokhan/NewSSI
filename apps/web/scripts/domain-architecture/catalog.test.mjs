import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

const root = path.resolve(import.meta.dirname, "../../src/lib/api/domains");

test("every domain owns one catalog with no standalone endpoint exports", () => {
  const violations = [];
  for (const domain of fs.readdirSync(root)) {
    const file = path.join(root, domain, "endpoints.ts");
    if (!fs.existsSync(file)) continue;
    const source = ts.createSourceFile(
      file,
      fs.readFileSync(file, "utf8"),
      ts.ScriptTarget.Latest,
      true
    );
    const catalog =
      domain.replace(/-([a-z])/g, (_, c) => c.toUpperCase()) + "Endpoints";
    let catalogs = 0;
    for (const statement of source.statements) {
      const exported = statement.modifiers?.some(
        (m) => m.kind === ts.SyntaxKind.ExportKeyword
      );
      if (!exported) continue;
      if (ts.isVariableStatement(statement)) {
        for (const declaration of statement.declarationList.declarations) {
          if (declaration.name.getText(source) === catalog) catalogs++;
          else
            violations.push(
              `${domain}: standalone ${declaration.name.getText(source)}`
            );
        }
      }
      // Selects an existing preview URL or catalog download URL; owns no address.
      if (
        ts.isFunctionDeclaration(statement) &&
        !(domain === "chat" && statement.name?.text === "resolveDownloadHref")
      ) {
        violations.push(`${domain}: standalone ${statement.name?.text}`);
      }
    }
    if (catalogs !== 1) violations.push(`${domain}: expected one ${catalog}`);
    function visit(node, inCatalog = false) {
      if (
        ts.isVariableDeclaration(node) &&
        node.name.getText(source) === catalog
      )
        inCatalog = true;
      if (
        !inCatalog &&
        (ts.isStringLiteralLike(node) || ts.isTemplateHead(node)) &&
        /^\/(?:api(?:\/|$)|mcp(?:\/|$))/.test(node.text)
      ) {
        violations.push(`${domain}: endpoint address outside catalog`);
      }
      ts.forEachChild(node, (child) => visit(child, inCatalog));
    }
    visit(source);
  }
  assert.deepEqual(violations, []);
});
