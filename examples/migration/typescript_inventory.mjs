import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const [project,compiler]=process.argv.slice(2);
const require=createRequire(import.meta.url);const ts=require(compiler);
const directory=path.join(project,'node_modules','@awesome-telegram','patterns');
const metadata=JSON.parse(fs.readFileSync(path.join(directory,'package.json'),'utf8'));
const file=path.join(directory,metadata.exports?.['.']?.types??metadata.types);
const program=ts.createProgram([file],{module:ts.ModuleKind.NodeNext,moduleResolution:ts.ModuleResolutionKind.NodeNext,target:ts.ScriptTarget.ES2022,lib:['lib.es2022.d.ts','lib.dom.d.ts'],skipLibCheck:true});
if(program.getSyntacticDiagnostics().length)throw Error('Declaration parser rejected syntax; inventory is incomplete');
const checker=program.getTypeChecker();const source=program.getSourceFile(file);const module=checker.getSymbolAtLocation(source);
const printer=ts.createPrinter({removeComments:true});
const print=node=>printer.printNode(ts.EmitHint.Unspecified,node,node.getSourceFile()).replace(/\s+/g,' ').trim();
const symbols={};
for(const exported of checker.getExportsOfModule(module)){
  const symbol=exported.flags&ts.SymbolFlags.Alias?checker.getAliasedSymbol(exported):exported;
  symbols[exported.name]=(symbol.declarations??[]).map(decl=>{
    if(ts.isClassDeclaration(decl)){
      return {kind:'class',typeParameters:decl.typeParameters?.map(print)??[],extends:decl.heritageClauses?.map(print)??[],
        members:decl.members.filter(member=>!member.modifiers?.some(mod=>mod.kind===ts.SyntaxKind.PrivateKeyword||mod.kind===ts.SyntaxKind.ProtectedKeyword)).map(print)};
    }
    return {kind:ts.SyntaxKind[decl.kind],declaration:print(decl)};
  });
}
const origin=fs.realpathSync(fileURLToPath(import.meta.resolve('@awesome-telegram/patterns')));
if(!origin.startsWith(fs.realpathSync(directory)+path.sep))throw Error('Public import escaped installed consumer');
const runtime=await import('@awesome-telegram/patterns');
console.log(JSON.stringify({version:JSON.parse(fs.readFileSync(path.join(directory,'package.json'),'utf8')).version,parserVersion:ts.version,syntacticDiagnostics:0,symbols,runtime:Object.keys(runtime).sort(),nativeMethods:runtime.TELEGRAM_NATIVE_METHODS,nativeEvents:runtime.TELEGRAM_NATIVE_EVENTS}));
