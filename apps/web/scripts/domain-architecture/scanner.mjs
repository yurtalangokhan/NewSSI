import { createRequire } from "node:module";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(new URL("../../package.json", import.meta.url));
const ts = require("typescript");

const SOURCE_ROOT = "apps/web/src";
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"]);
const LEGACY_MODULES = new Set([
  "@/lib/fetcher", "@/lib/userSS", "@/lib/utilsSS", "@/lib/agentsSS",
  "@/lib/chat/fetchBackendChatSessionSS", "@/lib/search/utilsSS", "@/lib/tools/fetchTools",
  "@/lib/agents/apiPaths", "@/lib/api/serverHttpClient", "@/lib/api/client/serverHttpClient",
  "@/lib/api/serverClient", "@/lib/api/client/serverClient",
]);
const TRANSPORTS = new Map([
  ["fetch", "native-fetch"], ["authenticatedFetch", "authenticated-fetch"],
  ["idempotentFetch", "idempotent-fetch"], ["apiRequest", "direct-api-request"],
]);
const UI_ROOTS = /^(?:@\/|.*apps\/web\/src\/)(?:app|components|refresh-components|refresh-pages|sections|hooks|layouts|providers|ee)\//;
const GATEWAYS = new Set([
  "app/api/[...path]/route.ts", "app/api/agent/[...path]/route.ts",
  "app/api/langgraph/[...path]/route.ts", "app/api/rag/[...path]/route.ts",
  "app/api/user-service/[...path]/route.ts", "app/mcp/[[...path]]/route.ts",
]);
const ENDPOINT_FIELDS = new Set(["path", "url", "endpoint", "route", "backendPath"]);
const REQUEST_CALLS = new Set(["fetch", "authenticatedFetch", "idempotentFetch", "apiRequest", "backendRequest", "useSWR"]);

function normalizedFile(file) {
  return file.replaceAll("\\", "/").replace(/^\.\//, "");
}

function sourcePath(file) {
  return normalizedFile(file).replace(/^.*apps\/web\/src\//, "");
}

function isTest(file) {
  return /(?:^|\/)(?:tests|__tests__|__mocks__)\//.test(file) ||
    /\.(?:test|spec)\.[cm]?[jt]sx?$/.test(file) || /\.d\.[cm]?ts$/.test(file);
}

function isDomain(file) {
  return /^lib\/api\/domains\//.test(sourcePath(file));
}

function isDomainHookOrchestration(file) {
  return /^lib\/api\/domains\/.+\/(?:hooks|[^/]+-hooks)\.[cm]?[jt]sx?$/.test(sourcePath(file));
}

function isAllowedHookDependency(file, module) {
  return isDomainHookOrchestration(file) && /^@\/(?:hooks|providers)\//.test(module);
}

function isTransportBoundary(file) {
  return /^lib\/api\/http\//.test(sourcePath(file));
}

function location(ast, node) {
  const point = ast.getLineAndCharacterOfPosition(node.getStart(ast));
  return { line: point.line + 1, column: point.character + 1 };
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteralLike(node)) return node.text;
  return undefined;
}

function expressionName(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node)) return node.name.text;
  if (ts.isElementAccessExpression(node) && ts.isStringLiteralLike(node.argumentExpression)) return node.argumentExpression.text;
  return undefined;
}

function importedModule(file, specifier) {
  if (!specifier.startsWith(".")) return specifier.replace(/\.[cm]?[jt]sx?$/, "");
  return normalizedFile(join(dirname(file), specifier)).replace(/^.*apps\/web\/src\//, "@/").replace(/\.[cm]?[jt]sx?$/, "");
}

export function analyzeSource(file, source) {
  file = normalizedFile(file);
  const result = { file, findings: [], exceptions: [] };
  if (isTest(file) || isTransportBoundary(file)) return result;
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const bindings = new Map();
  const endpointBindings = new Set();
  const gateway = GATEWAYS.has(sourcePath(file));
  const route = /^app\/.+\/route\.[cm]?[jt]s$/.test(sourcePath(file));

  function add(signal, node, details = {}) {
    result.findings.push({ signal, ...location(ast, node), ...details });
  }

  function visitImports(node) {
    if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument) && ts.isStringLiteralLike(node.argument.literal)) {
      const module = importedModule(file, node.argument.literal.text);
      if (isDomain(file) && UI_ROOTS.test(module) && !isAllowedHookDependency(file, module)) {
        add("domain-ui-import", node, { module });
      }
    }
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (!node.moduleSpecifier || !ts.isStringLiteralLike(node.moduleSpecifier)) return;
      const module = importedModule(file, node.moduleSpecifier.text);
      const named = node.importClause?.namedBindings;
      const inlineTypesOnly = Boolean(named && ts.isNamedImports(named) && !node.importClause?.name &&
        named.elements.length > 0 && named.elements.every((specifier) => specifier.isTypeOnly));
      const exportedTypesOnly = Boolean(ts.isExportDeclaration(node) &&
        (node.isTypeOnly || (node.exportClause && ts.isNamedExports(node.exportClause) &&
          node.exportClause.elements.length > 0 && node.exportClause.elements.every((specifier) => specifier.isTypeOnly))));
      const typeOnly = Boolean(node.importClause?.isTypeOnly || inlineTypesOnly || exportedTypesOnly);
      if (LEGACY_MODULES.has(module) && !typeOnly) add("legacy-facade-import", node, { module });
      if (module.startsWith("@/lib/api/modules/") && !typeOnly) add("old-module-import", node, { module });
      if (isDomain(file) && UI_ROOTS.test(module) && !isAllowedHookDependency(file, module)) {
        add("domain-ui-import", node, { module });
      }
      const clause = node.importClause;
      if (clause && !clause.isTypeOnly) {
        if (clause.name) bindings.set(clause.name.text, "default");
        const runtimeBindings = clause.namedBindings;
        if (runtimeBindings && ts.isNamespaceImport(runtimeBindings)) bindings.set(runtimeBindings.name.text, "*");
        else if (runtimeBindings) for (const specifier of runtimeBindings.elements) {
          if (!specifier.isTypeOnly) {
            bindings.set(specifier.name.text, (specifier.propertyName ?? specifier.name).text);
            if (/^@\/lib\/api\/domains\/[^/]+\/endpoints$/.test(module)) endpointBindings.add(specifier.name.text);
          }
        }
      }
    }
    ts.forEachChild(node, visitImports);
  }
  visitImports(ast);

  function callName(expression) {
    const direct = expressionName(expression);
    if (ts.isIdentifier(expression)) return bindings.get(expression.text) ?? direct;
    if ((ts.isPropertyAccessExpression(expression) || ts.isElementAccessExpression(expression)) &&
        ts.isIdentifier(expression.expression) &&
        ["window", "globalThis", "self"].includes(expression.expression.text)) return direct;
    if ((ts.isPropertyAccessExpression(expression) || ts.isElementAccessExpression(expression)) &&
        ts.isIdentifier(expression.expression) && bindings.get(expression.expression.text) === "*") return direct;
    return undefined;
  }

  function titleException(node) {
    if (sourcePath(file) !== "lib/sources.ts" || callName(node.expression) !== "fetch") return false;
    const argument = node.arguments[0];
    if (!argument || !ts.isIdentifier(argument) || argument.text !== "url") return false;
    for (let owner = node.parent; owner; owner = owner.parent) {
      if (ts.isFunctionLike(owner)) return ts.isFunctionDeclaration(owner) && owner.name?.text === "fetchTitleFromUrl";
    }
    return false;
  }

  function usesEndpointDescriptor(expression) {
    while (ts.isPropertyAccessExpression(expression) || ts.isElementAccessExpression(expression) || ts.isCallExpression(expression)) {
      expression = expression.expression;
    }
    return ts.isIdentifier(expression) && endpointBindings.has(expression.text);
  }

  function routeTarget(signal, node, details = {}) {
    if (gateway) result.exceptions.push({ signal, ...location(ast, node), kind: "dynamic-gateway-adapter" });
    else add(signal, node, details);
  }

  function visit(node) {
    if (ts.isCallExpression(node)) {
      const name = callName(node.expression);
      const signal = TRANSPORTS.get(name);
      if (signal) {
        if (titleException(node)) result.exceptions.push({ signal, ...location(ast, node), kind: "external-title-fetch" });
        else if (!(isDomain(file) && signal === "direct-api-request")) add(signal, node);
      }
      const requestUrl = node.arguments[0] && endpointValue(node.arguments[0]);
      if (!route && REQUEST_CALLS.has(name) && requestUrl?.startsWith("/api") &&
          !/\/endpoints\.[cm]?[jt]s$/.test(file)) {
        add("inline-endpoint-literal", node.arguments[0], { endpoint: requestUrl });
      }
      if (route && name === "proxyToBackend" && node.arguments[1] && !usesEndpointDescriptor(node.arguments[1])) {
        routeTarget("route-proxy-target", node.arguments[1]);
      }
      if (route && name === "backendRequest" && node.arguments[0]) {
        const target = node.arguments[0];
        if (usesEndpointDescriptor(target)) {
          // A direct imported descriptor is fully resolved.
        } else if (!ts.isObjectLiteralExpression(target)) {
          routeTarget("route-backend-target", target, { reason: "unresolved-target" });
        } else {
        const object = target;
        const descriptorSpread = object.properties.some((property) =>
          ts.isSpreadAssignment(property) && usesEndpointDescriptor(property.expression));
        const targetFields = object.properties.filter((property) =>
          !ts.isSpreadAssignment(property) && ["service", "path", "url", "baseUrl"].includes(propertyName(property.name)));
        if (!descriptorSpread && targetFields.length === 0) {
          routeTarget("route-backend-target", object, { reason: "missing-domain-descriptor" });
        }
        for (const property of object.properties) {
          const field = !ts.isSpreadAssignment(property) ? propertyName(property.name) : undefined;
          if (["service", "path", "url", "baseUrl"].includes(field)) {
            routeTarget("route-backend-target", property, { field });
          }
        }
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  return result;
}

function endpointValue(expression) {
  if (!expression) return null;
  if (ts.isStringLiteralLike(expression) && expression.text.startsWith("/")) return expression.text;
  if (ts.isNoSubstitutionTemplateLiteral(expression) && expression.text.startsWith("/")) return expression.text;
  if (ts.isTemplateExpression(expression) && expression.head.text.startsWith("/")) {
    return expression.head.text + expression.templateSpans.map((span) => "${}" + span.literal.text).join("");
  }
  if (ts.isBinaryExpression(expression) && expression.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = endpointValue(expression.left);
    if (!left) return null;
    const right = ts.isStringLiteralLike(expression.right) ? expression.right.text : "${}";
    return left + right;
  }
  return null;
}

function containingMethod(node) {
  for (let current = node; current; current = current.parent) {
    if (!ts.isObjectLiteralExpression(current)) continue;
    for (const property of current.properties) {
      if (!ts.isPropertyAssignment(property) || propertyName(property.name) !== "method") continue;
      if (ts.isStringLiteralLike(property.initializer)) return property.initializer.text.toUpperCase();
    }
    return "UNKNOWN";
  }
  return "UNKNOWN";
}

function ownerOf(file) {
  return sourcePath(file).match(/^lib\/api\/domains\/([^/]+)\//)?.[1] ?? "outside-domain";
}

export function inventoryEndpointContracts(file, source) {
  file = normalizedFile(file);
  const contracts = [];
  const shapeCandidates = [];
  const unresolved = [];
  if (isTest(file)) return { contracts, shapeCandidates, unresolved };
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const endpointFile = /\/endpoints\.[cm]?[jt]s$/.test(file);
  const seen = new Set();

  function record(node, expression, context, method = containingMethod(node)) {
    const at = location(ast, node);
    const normalized = endpointValue(expression);
    const identity = String(expression.getStart(ast));
    if (seen.has(identity)) return;
    seen.add(identity);
    if (normalized) {
      const entry = { file, owner: ownerOf(file), method, normalized, context, ...at };
      if (method === "UNKNOWN") shapeCandidates.push(entry);
      else contracts.push(entry);
    } else {
      unresolved.push({ file, owner: ownerOf(file), kind: "dynamic-endpoint-contract", context, ...at });
    }
  }

  function requestMethod(node, name) {
    if (["apiRequest", "fetch", "authenticatedFetch", "idempotentFetch", "useSWR"].includes(name)) {
      const options = node.arguments[1];
      if (!options) return "GET";
      if (ts.isObjectLiteralExpression(options)) {
        const method = options.properties.find((property) =>
          ts.isPropertyAssignment(property) && propertyName(property.name) === "method");
        if (method && ts.isStringLiteralLike(method.initializer)) return method.initializer.text.toUpperCase();
      }
    }
    return "UNKNOWN";
  }

  function visit(node) {
    if (ts.isPropertyAssignment(node) && ENDPOINT_FIELDS.has(propertyName(node.name))) {
      record(node, node.initializer, `property:${propertyName(node.name)}`);
    } else if (ts.isShorthandPropertyAssignment(node) && ENDPOINT_FIELDS.has(node.name.text)) {
      record(node, node.name, `property:${node.name.text}`);
    } else if (ts.isCallExpression(node) && REQUEST_CALLS.has(expressionName(node.expression)) && node.arguments[0]) {
      const name = expressionName(node.expression);
      record(node.arguments[0], node.arguments[0], `call:${name}`, requestMethod(node, name));
    } else if (endpointFile && (ts.isStringLiteralLike(node) || ts.isTemplateExpression(node) || ts.isBinaryExpression(node)) &&
        !(ts.isBinaryExpression(node.parent) && endpointValue(node.parent))) {
      const value = endpointValue(node);
      if (value) record(node, node, "endpoint-expression");
      else if (ts.isBinaryExpression(node) &&
          (ts.isReturnStatement(node.parent) || ts.isArrowFunction(node.parent))) {
        record(node, node, "computed-endpoint-expression");
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  contracts.sort((a, b) => a.line - b.line || a.column - b.column);
  shapeCandidates.sort((a, b) => a.line - b.line || a.column - b.column);
  unresolved.sort((a, b) => a.line - b.line || a.column - b.column);
  return { contracts, shapeCandidates, unresolved };
}

function sourceFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (["node_modules", ".next"].includes(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...sourceFiles(path));
    else if (SOURCE_EXTENSIONS.has(extname(entry.name))) files.push(path);
  }
  return files;
}

function unwrapExpression(node) {
  while (node && (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) ||
    ts.isSatisfiesExpression(node) || ts.isNonNullExpression(node))) node = node.expression;
  return node;
}

/** Resolve only statically provable domain request operations. */
export function inventoryDomainOperations(repositoryRoot) {
  const root = resolve(repositoryRoot);
  const files = sourceFiles(resolve(root, SOURCE_ROOT));
  const configPath = resolve(root, "apps/web/tsconfig.json");
  let compilerOptions = { allowJs: true, jsx: ts.JsxEmit.Preserve, noResolve: false };
  if (existsSync(configPath)) {
    const config = ts.readConfigFile(configPath, (file) => readFileSync(file, "utf8"));
    if (!config.error) compilerOptions = ts.parseJsonConfigFileContent(
      config.config, ts.sys, dirname(configPath), undefined, configPath,
    ).options;
  }
  const program = ts.createProgram(files, compilerOptions);
  const checker = program.getTypeChecker();
  const operations = [];
  const unresolved = [];

  function symbolDeclaration(node) {
    let symbol = checker.getSymbolAtLocation(node);
    if (symbol && (symbol.flags & ts.SymbolFlags.Alias)) symbol = checker.getAliasedSymbol(symbol);
    return symbol?.valueDeclaration ?? symbol?.declarations?.[0];
  }

  function callableDeclaration(node) {
    const declaration = symbolDeclaration(node);
    if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer &&
        ts.isFunctionLike(declaration.initializer)) return declaration.initializer;
    return declaration && ts.isFunctionLike(declaration) ? declaration : null;
  }

  function substitute(text, env) {
    let value = text;
    for (const [name, replacement] of env) value = value.replace(new RegExp(`\\b${name}\\b`, "g"), replacement);
    return value.replace(/\s+/g, "");
  }

  function value(expression, env = new Map(), seen = new Set()) {
    expression = unwrapExpression(expression);
    if (!expression || seen.has(expression)) return null;
    seen.add(expression);
    if (ts.isStringLiteralLike(expression)) return expression.text;
    if (ts.isTemplateExpression(expression)) return expression.head.text +
      expression.templateSpans.map((span) => `\${${substitute(span.expression.getText(), env)}}${span.literal.text}`).join("");
    if (ts.isBinaryExpression(expression) && expression.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const left = value(expression.left, env, new Set(seen));
      const right = value(expression.right, env, new Set(seen));
      return left !== null && right !== null ? left + right : null;
    }
    if (ts.isIdentifier(expression)) {
      if (env.has(expression.text)) return `\${${env.get(expression.text)}}`;
      const declaration = symbolDeclaration(expression);
      return declaration && "initializer" in declaration ? value(declaration.initializer, env, seen) : null;
    }
    if (ts.isPropertyAccessExpression(expression) || ts.isElementAccessExpression(expression)) {
      const name = ts.isPropertyAccessExpression(expression) ? expression.name : expression.argumentExpression;
      const declaration = name && symbolDeclaration(name);
      return declaration && "initializer" in declaration ? value(declaration.initializer, env, seen) : null;
    }
    if (ts.isCallExpression(expression)) {
      const declaration = callableDeclaration(expression.expression);
      if (!declaration) return null;
      const callEnv = new Map(env);
      declaration.parameters.forEach((parameter, index) => {
        if (ts.isIdentifier(parameter.name) && expression.arguments[index]) {
          callEnv.set(parameter.name.text, substitute(expression.arguments[index].getText(), env));
        }
      });
      const body = declaration.body;
      if (!body) return null;
      const returned = ts.isBlock(body) ? body.statements.find(ts.isReturnStatement)?.expression : body;
      return returned ? value(returned, callEnv, seen) : null;
    }
    return null;
  }

  function objectLiteral(expression, seen = new Set()) {
    expression = unwrapExpression(expression);
    if (!expression || seen.has(expression)) return null;
    seen.add(expression);
    if (ts.isObjectLiteralExpression(expression)) return expression;
    if (ts.isIdentifier(expression) || ts.isPropertyAccessExpression(expression)) {
      const declaration = symbolDeclaration(ts.isIdentifier(expression) ? expression : expression.name);
      return declaration && "initializer" in declaration ? objectLiteral(declaration.initializer, seen) : null;
    }
    if (ts.isCallExpression(expression)) {
      const declaration = callableDeclaration(expression.expression);
      if (!declaration || !declaration.body) return null;
      const returned = ts.isBlock(declaration.body) ? declaration.body.statements.find(ts.isReturnStatement)?.expression : declaration.body;
      return returned ? objectLiteral(returned, seen) : null;
    }
    return null;
  }

  // undefined means definitely absent; null means a runtime value is unknown.
  function objectField(expression, field, seen = new Set()) {
    const object = objectLiteral(expression);
    if (!object || seen.has(object)) return null;
    seen.add(object);
    for (const property of [...object.properties].reverse()) {
      const key = "name" in property && property.name
        ? ts.isComputedPropertyName(property.name)
          ? value(property.name.expression)
          : propertyName(property.name)
        : undefined;
      if ("name" in property && property.name && ts.isComputedPropertyName(property.name) && key == null) return null;
      if (ts.isPropertyAssignment(property) && key === field) return value(property.initializer);
      if (ts.isShorthandPropertyAssignment(property) && property.name.text === field) return value(property.name);
      if (ts.isSpreadAssignment(property)) {
        const inherited = objectField(property.expression, field, new Set(seen));
        if (inherited !== undefined) return inherited;
      }
    }
    return undefined;
  }

  function operationName(node) {
    for (let owner = node.parent; owner; owner = owner.parent) {
      if (ts.isFunctionDeclaration(owner) && owner.name) return owner.name.text;
      if ((ts.isArrowFunction(owner) || ts.isFunctionExpression(owner)) &&
          ts.isVariableDeclaration(owner.parent) && ts.isIdentifier(owner.parent.name)) return owner.parent.name.text;
    }
    return "<module>";
  }

  for (const source of program.getSourceFiles()) {
    const file = normalizedFile(source.fileName);
    if (!/^lib\/api\/domains\/[^/]+\/(?:api|server)\.[cm]?[jt]s$/.test(sourcePath(file))) continue;
    function visit(node) {
      if (ts.isCallExpression(node) && ["apiRequest", "backendRequest"].includes(expressionName(node.expression))) {
        const transport = expressionName(node.expression);
        const target = transport === "apiRequest" ? value(node.arguments[0]) : objectField(node.arguments[0], "path");
        let method = "GET";
        const options = transport === "apiRequest" ? node.arguments[1] : node.arguments[0];
        if (options) {
          const literalMethod = objectField(options, "method");
          if (typeof literalMethod === "string" && /^[A-Za-z]+$/.test(literalMethod)) method = literalMethod.toUpperCase();
          else if (literalMethod !== undefined) method = null;
        }
        const entry = { file: relative(root, source.fileName), operation: operationName(node), transport,
          line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1 };
        if (target && method) operations.push({ ...entry, method, target });
        else unresolved.push({ ...entry, reason: !target ? "dynamic-target" : "dynamic-method" });
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
  }
  const groups = new Map();
  for (const operation of operations) {
    const key = `${operation.target}\0${operation.method}`;
    groups.set(key, [...(groups.get(key) ?? []), operation]);
  }
  return { operations, duplicateGroups: [...groups.values()].filter((group) => group.length > 1), unresolved };
}

export function scanRepository(repositoryRoot) {
  const root = resolve(repositoryRoot);
  const sourceRoot = resolve(root, SOURCE_ROOT);
  if (!existsSync(sourceRoot)) throw new Error(`Source root does not exist: ${sourceRoot}`);
  const violations = [];
  const exceptions = [];
  const contracts = [];
  const shapeCandidates = [];
  const unresolved = [];
  for (const absolute of sourceFiles(sourceRoot)) {
    const file = normalizedFile(relative(root, absolute));
    const source = readFileSync(absolute, "utf8");
    const analysis = analyzeSource(file, source);
    violations.push(...analysis.findings.map((finding) => ({ file, ...finding })));
    exceptions.push(...analysis.exceptions.map((exception) => ({ file, ...exception })));
    const inventory = inventoryEndpointContracts(file, source);
    contracts.push(...inventory.contracts);
    shapeCandidates.push(...inventory.shapeCandidates);
    unresolved.push(...inventory.unresolved);
  }
  const groups = new Map();
  for (const contract of contracts) {
    const key = `${contract.normalized}\0${contract.method}`;
    groups.set(key, [...(groups.get(key) ?? []), contract]);
  }
  const duplicates = [...groups.values()].filter((group) => group.length > 1);
  const operationInventory = inventoryDomainOperations(root);
  return { violations, exceptions, inventory: { contracts, shapeCandidates, duplicates, unresolved, operationInventory } };
}

function print(result, json, verbose = false) {
  if (json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  for (const finding of result.violations) process.stdout.write(`[VIOLATION] ${finding.file}:${finding.line} ${finding.signal}\n`);
  for (const exception of result.exceptions) process.stdout.write(`[EXCEPTION] ${exception.file}:${exception.line} ${exception.kind}\n`);
  if (verbose) {
    for (const item of result.inventory.unresolved) process.stdout.write(`[UNRESOLVED] ${item.file}:${item.line} ${item.context}\n`);
    for (const item of result.inventory.operationInventory.unresolved) process.stdout.write(`[UNRESOLVED OPERATION] ${item.file}:${item.line} ${item.operation} ${item.reason}\n`);
  }
  process.stdout.write(`[OPERATIONS] ${result.inventory.operationInventory.operations.length} resolved; ${result.inventory.operationInventory.duplicateGroups.length} duplicate URL+method groups; ${result.inventory.operationInventory.unresolved.length} actionable unresolved\n`);
  process.stdout.write(`[INVENTORY] ${result.inventory.contracts.length} known-method contracts; ${result.inventory.shapeCandidates.length} unknown-method shapes; ${result.inventory.duplicates.length} exact URL+method duplicate groups; ${result.inventory.unresolved.length} unresolved dynamic contracts\n`);
  process.stdout.write(`[${result.violations.length ? "FAIL" : "PASS"}] ${result.violations.length} domain architecture violations\n`);
}

function runCli() {
  const args = process.argv.slice(2);
  const rootIndex = args.indexOf("--root");
  const defaultRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
  const root = rootIndex >= 0 ? args[rootIndex + 1] : defaultRoot;
  const result = scanRepository(root);
  print(result, args.includes("--json"), args.includes("--verbose"));
  process.exitCode = result.violations.length ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) runCli();
