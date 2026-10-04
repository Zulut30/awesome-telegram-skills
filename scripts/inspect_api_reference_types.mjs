/** Compiler-symbol audit of examples resolved through the installed tarball. */
// Pinned workspace TypeScript 7.0.2: the root only exposes version metadata.
import {API} from 'typescript/unstable/sync';
import * as ts from 'typescript/unstable/ast';
import fs from 'node:fs';
import path from 'node:path';
const [consumer, indexPath] = process.argv.slice(2);
const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
const root = path.resolve(consumer);
const files = fs.readdirSync(path.join(root, 'src')).filter(p => p.endsWith('.ts')).map(p => path.join(root, 'src', p));
const config = path.join(root, 'tsconfig.audit.json');
fs.writeFileSync(config, JSON.stringify({compilerOptions: {strict: true, target: 'ES2022',
  module: 'NodeNext', lib: ['ES2022', 'DOM'], noEmit: true}, include: ['src/*.ts']}));
const api = new API({cwd: root});
let snapshot;
try {
snapshot = api.updateSnapshot({openProjects: [config]});
const project = snapshot.getProject(config);
if (!project) throw Error('Compiler project unavailable');
const program = project.program, checker = project.checker;
const errors = [...program.getSyntacticDiagnostics(), ...program.getSemanticDiagnostics(), ...program.getProgramDiagnostics(), ...program.getGlobalDiagnostics(), ...program.getConfigFileParsingDiagnostics()];
if (errors.length) throw Error('Compiler audit diagnostics: ' + JSON.stringify(errors));
const expected = index.symbols.filter(s => s.module === '@awesome-telegram/patterns');
const used = new Set(); let exports;
const installed = fs.realpathSync(path.join(root, 'node_modules/@awesome-telegram/patterns'));
const ownedFiles = new Set(files.map(file => path.resolve(file)));
for (const file of program.getSourceFileNames().filter(file => ownedFiles.has(path.resolve(file)) && !file.endsWith('negative-types.ts')).map(file => program.getSourceFile(file))) {
  for (const statement of file.statements) {
    if (!ts.isImportDeclaration(statement) || statement.moduleSpecifier.text !== '@awesome-telegram/patterns') continue;
    const module = checker.getSymbolAtLocation(statement.moduleSpecifier);
    exports = checker.getExportsOfModule(module);
    for (const binding of statement.importClause?.namedBindings?.elements ?? []) {
      const symbol = checker.getSymbolAtLocation(binding.name);
      const target = checker.getAliasedSymbol(symbol);
      if (!target?.declarations?.length) throw Error('Imported symbol has no declaration');
      for (const declaration of target.declarations) {
        const resolved = fs.realpathSync(declaration.resolve().getSourceFile().fileName);
        if (!resolved.startsWith(installed + path.sep)) throw Error('Type resolved outside installed tarball');
      }
      let referenced = false;
      function visit(node) {
        if (ts.isImportDeclaration(node)) return;
        if (ts.isIdentifier(node) && checker.getSymbolAtLocation(node) === symbol) referenced = true;
        node.forEachChild(visit);
      }
      visit(file);
      if (referenced) used.add(binding.propertyName?.text ?? binding.name.text);
    }
  }
}
if (!exports || exports.length !== expected.length || expected.some(s => !used.has(s.name)) || exports.some(s => !expected.some(e => e.name === s.name))) {
  throw Error('Installed TypeScript exports lack documented, actually referenced example bindings');
}
const negativeTypeCases = fs.readFileSync(path.join(root, 'src/negative-types.ts'), 'utf8').match(/@ts-expect-error/g)?.length ?? 0;
if (negativeTypeCases !== 7) throw Error('Negative typing coverage drift');
console.log(JSON.stringify({passed: true, installedExportSymbols: exports.length, referencedSymbols: used.size,
  typeOnly: expected.filter(s => s.kind === 'type').length, negativeTypeCases, source: installed}));
} finally { snapshot?.dispose(); api.close(); }
