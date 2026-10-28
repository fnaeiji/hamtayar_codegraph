"""Evidence-based C# declared base types and constructor-supplied dependencies.

AST supplement to CGC, not a compiler/DI-container/assembly binder. Unresolved and
ambiguous types remain explicit references; runtime implementations are not inferred.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

TYPES={'class_declaration':'Class','interface_declaration':'Interface','struct_declaration':'Struct','record_declaration':'Class'}
PRIMITIVES={'int','long','short','byte','bool','char','float','double','decimal','string','object','uint','ulong','ushort','sbyte','nint','nuint'}

def text(node):return node.text.decode('utf-8') if node else ''
def field(node,name):return node.child_by_field_name(name)
def walk(node):
    stack=[node]
    while stack:
        current=stack.pop();yield current;stack.extend(reversed(current.named_children))

def type_ref(node):
    value=''.join(text(node).split()).replace('global::','')
    if node.type in ('nullable_type','ref_type') and node.named_children:return type_ref(node.named_children[0])
    arity=0;name=value
    # Read the outer generic arguments, never split commas inside nested types.
    target=node
    if node.type in ('qualified_name','alias_qualified_name'):
        target=field(node,'name') or node.named_children[-1]
    if target.type=='generic_name':
        args=next((c for c in target.named_children if c.type=='type_argument_list'),None)
        arity=len(args.named_children) if args else 0
        simple=text(target.named_children[0]);qualifier=field(node,'qualifier') if node.type=='qualified_name' else None
        prefix=text(qualifier).replace('global::','')+'.' if qualifier else ''
        name=prefix+simple
    return {'name':name.rstrip('?'),'arity':arity,'display':value,'absolute':text(node).startswith('global::')}

def using_rules(nodes):
    imports=[];aliases={}
    for node in nodes:
        if node.type!='using_directive' or any(c.type=='static' for c in node.children):continue
        alias=field(node,'name')
        if alias and len(node.named_children)>1:aliases[text(alias)]=type_ref(node.named_children[-1])
        elif node.named_children:imports.append(text(node.named_children[-1]).replace('global::',''))
    return imports,aliases

def parse_source(source,path):
    from tree_sitter import Parser,Language
    import tree_sitter_c_sharp
    parser=Parser(Language(tree_sitter_c_sharp.language()));root=parser.parse(source.encode('utf-8')).root_node
    output=[];imports,aliases=using_rules(root.named_children)
    file_namespace=next((text(field(n,'name')) for n in root.named_children if n.type=='file_scoped_namespace_declaration'),'')
    globals_,_=using_rules([n for n in root.named_children if text(n).lstrip().startswith('global using ')])
    def visit(container,namespace,parents,imports,aliases):
        local_imports,local_aliases=using_rules(container.named_children)
        imports=list(dict.fromkeys(imports+local_imports));aliases={**aliases,**local_aliases}
        for node in container.named_children:
            if node.type=='namespace_declaration':
                name=text(field(node,'name'));body=field(node,'body')
                if body:visit(body,'.'.join(filter(None,[namespace,name])),parents,imports,aliases)
            elif node.type in TYPES:
                name=text(field(node,'name'));body=field(node,'body')
                if not name or not body:continue
                parameters=next((n for n in node.named_children if n.type=='type_parameter_list'),None)
                arity=len(parameters.named_children) if parameters else 0
                qualified='.'.join(filter(None,[namespace,*parents,name]))
                bases=next((n for n in node.named_children if n.type=='base_list'),None)
                facts={'name':name,'qualified':qualified,'arity':arity,'namespace':namespace,'kind':'Struct' if node.type=='record_declaration' and any(c.type=='struct' for c in node.children) else TYPES[node.type],
                       'partial':any(text(n)=='partial' for n in node.named_children if n.type=='modifier'),
                       'path':path,'line':node.start_point.row+1,'end':node.end_point.row+1,
                       'imports':imports,'aliases':aliases,'bases':[type_ref(n) for n in bases.named_children] if bases and not bases.has_error else [],'fields':[],'uses':set()}
                fields={}
                for member in body.named_children:
                    if member.type!='field_declaration' or any(text(n)=='static' for n in member.named_children):continue
                    declaration=next((n for n in member.named_children if n.type=='variable_declaration'),None)
                    if not declaration or not field(declaration,'type'):continue
                    ref=type_ref(field(declaration,'type'))
                    for variable in declaration.named_children:
                        if variable.type=='variable_declarator':
                            identifier=field(variable,'name')
                            fields[text(identifier)]={'name':text(identifier),'type':ref,'line':identifier.start_point.row+1,'declaration_line':member.start_point.row+1}
                for member in body.named_children:
                    if member.type=='constructor_declaration':
                        params=field(member,'parameters');parameters={}
                        if params:
                            for param in params.named_children:
                                if param.type=='parameter' and field(param,'type') and field(param,'name'):
                                    parameters[text(field(param,'name'))]={'type':type_ref(field(param,'type')),'line':param.start_point.row+1}
                        block=field(member,'body')
                        def assignments(n):
                            stack=[n]
                            while stack:
                                current=stack.pop()
                                if current.type in ('lambda_expression','anonymous_method_expression','local_function_statement'):continue
                                if current.type=='assignment_expression':yield current
                                stack.extend(reversed(current.named_children))
                        for assignment in assignments(block) if block else []:
                            if text(field(assignment,'operator'))!='=':continue
                            left,right=field(assignment,'left'),field(assignment,'right')
                            if not left or not right or right.type!='identifier':continue
                            if left.type=='identifier' and text(left) not in parameters:field_name=text(left)
                            elif left.type=='member_access_expression' and text(field(left,'expression'))=='this':field_name=text(field(left,'name'))
                            else:continue
                            declaration=fields.get(field_name);param=parameters.get(text(right))
                            if declaration and param and declaration['type']['name'] not in PRIMITIVES and declaration['type']['display']==param['type']['display']:
                                facts['fields'].append({**declaration,'parameter':text(right),'parameter_line':param['line'],'constructor_line':field(member,'name').start_point.row+1})
                    if member.type=='method_declaration':
                        shadowed={text(field(n,'name')) for n in walk(member) if n.type in ('parameter','variable_declarator') and field(n,'name')}
                        for child in walk(member):
                            if child.type=='member_access_expression':
                                receiver=field(child,'expression')
                                if receiver and receiver.type=='identifier' and text(receiver) not in shadowed:facts['uses'].add(text(receiver))
                                elif receiver and receiver.type=='member_access_expression' and text(field(receiver,'expression'))=='this':facts['uses'].add(text(field(receiver,'name')))
                facts['uses']=sorted(facts['uses']);output.append(facts)
                visit(body,namespace,parents+[name],imports,aliases)
    visit(root,file_namespace,[],imports,aliases)
    return {'types':output,'global_imports':globals_,'has_syntax_errors':root.has_error}


def enrich(db,project,index,workspace,selected_paths=None,cancelled=None,log=None):
    log=log or (lambda _:None);root=workspace.resolve()
    files=[Path(p) for p in selected_paths if Path(p).suffix.lower()=='.cs'] if selected_paths is not None else list(root.rglob('*.cs'))
    if not files:return {'types':0,'services':0,'unresolved':0,'unmatched':0}
    try:
        import tree_sitter,tree_sitter_c_sharp
    except ImportError:raise ValueError('C# semantic dependencies are missing. Run HamtayarDemo/scripts/setup.ps1, restart, and retry publication.') from None
    def check():
        if cancelled is not None and cancelled.is_set():raise ValueError('Cancelled during C# semantic analysis')
    facts=[];global_imports=defaultdict(list);scopes={};warnings=[]
    def assembly(path):
        directory=path.parent
        if directory in scopes:return scopes[directory]
        traversed=[]
        while directory.is_relative_to(root):
            if directory in scopes:result=scopes[directory];break
            traversed.append(directory);projects=list(directory.glob('*.csproj'))
            if projects:result='|'.join(sorted(p.relative_to(root).as_posix() for p in projects));break
            if directory==root:result='workspace';break
            directory=directory.parent
        for directory in traversed:scopes[directory]=result
        return result
    log(f'C# semantics: reading {len(files):,} selected files...')
    for i,path in enumerate(files):
        check()
        if not path.resolve().is_relative_to(root):raise ValueError('C# path outside selected workspace')
        parsed=parse_source(path.read_text(encoding='utf-8'),path.relative_to(root).as_posix())
        if parsed['has_syntax_errors']:warnings.append(path.relative_to(root).as_posix())
        file_scope=assembly(path)
        for item in parsed['types']:item['assembly']=file_scope;facts.append(item)
        global_imports[file_scope].extend(parsed['global_imports'])
        if (i+1)%500==0:log(f'C# semantics: {i+1:,}/{len(files):,} files read')
    canonical=defaultdict(list)
    for n in db.stream('MATCH (n:HamtayarEntity) WHERE n.index=$index AND n.kind IN ["Class","Interface","Struct"] RETURN n.id AS id,n.name AS name,n.path AS path,n.line AS line',index=index):canonical[n['path']].append(n)
    unmatched=0
    for item in facts:
        candidates=canonical[item['path']]
        exact=[n for n in candidates if n['line']==item['line']]
        if len(exact)!=1:exact=[n for n in candidates if n['name'].split('.')[-1].split('<')[0]==item['name']]
        item['id']=exact[0]['id'] if len(exact)==1 else None
        if not item['id']:unmatched+=1
    groups=defaultdict(list)
    for item in facts:groups[(item['assembly'],item['qualified'],item['arity'])].append(item)
    inventory=defaultdict(list)
    for (assembly_name,qualified,arity),parts in groups.items():
        if len(parts)==1 or all(p['partial'] for p in parts):
            inventory[(qualified,arity)].append(parts)
    def resolve(ref,owner):
        name,arity=ref['name'],ref['arity'];absolute=ref.get('absolute',False)
        if name in owner['aliases']:
            alias=owner['aliases'][name];name,arity=alias['name'],alias['arity'];absolute=alias.get('absolute',False)
        elif '.' in name and name.split('.')[0] in owner['aliases']:
            prefix,rest=name.split('.',1);alias=owner['aliases'][prefix];name=alias['name']+'.'+rest;absolute=alias.get('absolute',False)
        namespace=owner['qualified'].rsplit('.',1)[0] if '.' in owner['qualified'] else ''
        tiers=[]
        while namespace:
            tiers.append([namespace+'.'+name]);namespace=namespace.rpartition('.')[0]
        tiers.append([name])
        if absolute:tiers=[[name]]
        else:tiers.append(list(dict.fromkeys(n+'.'+name for n in owner['imports']+global_imports[owner['assembly']])))
        for candidates in tiers:
            matches=[]
            for candidate in candidates:matches.extend(inventory.get((candidate,arity),[]))
            local=[p for p in matches if p[0]['assembly']==owner['assembly']]
            matches=local or matches
            unique={ (p[0]['assembly'],p[0]['qualified'],p[0]['arity']):p for p in matches }
            if unique:
                if len(unique)==1:return next(iter(unique.values())),'resolved_in_project'
                return None,'ambiguous'
        return None,'unresolved'
    def ident(value):return hashlib.sha256((index+':csharp:'+value).encode()).hexdigest()
    def write_nodes(rows):
        from .publication import NODE_WRITE
        for i in range(0,len(rows),200):check();db.run(NODE_WRITE,rows=rows[i:i+200])
    def links(rows):
        for i in range(0,len(rows),200):
            check();db.run('UNWIND $rows AS row MATCH (a:HamtayarEntity {id:row.a}),(b:HamtayarEntity {id:row.b}) WHERE a.index=$index AND b.index=$index MERGE (a)-[r:HAMTAYAR_LINK {kind:row.kind}]->(b) SET r.evidence_path=row.path,r.line=row.line,r.origin="csharp_ast",r.declared_type=row.declared_type',rows=rows[i:i+200],index=index)
    stats={'types':len(facts),'services':0,'unresolved':0,'unmatched':unmatched,'syntax_error_files':warnings[:30]}
    for key,parts in groups.items():
        check()
        # Merge facts across partial declarations only within the same project scope.
        combined=parts if all(p['partial'] for p in parts) else []
        for owner in parts:
            if not owner['id']:continue
            contributing=combined or [owner]
            base_refs=[(ref,p) for p in contributing for ref in p['bases']]
            if base_refs:
                db.run('MATCH (a:HamtayarEntity {id:$id})-[r:HAMTAYAR_LINK]->() WHERE a.index=$index AND r.kind IN ["INHERITS","INHERITS_FROM","EXTENDS","IMPLEMENTS","BASE_TYPE"] DELETE r',id=owner['id'],index=index)
            for ref,evidence in base_refs:
                target,status=resolve(ref,evidence);resolved=next((p for p in sorted(target or [],key=lambda p:(p['path'],p['line'])) if p['id']),None)
                if resolved:
                    target_id=resolved['id'];kind='IMPLEMENTS' if resolved['kind']=='Interface' and owner['kind']!='Interface' else 'INHERITS'
                else:
                    stats['unresolved']+=1;status='source_definition_unmatched' if target else status;kind='BASE_TYPE';target_id=ident(owner['id']+':base:'+ref['display'])
                    write_nodes([{'id':target_id,'project':project,'index':index,'name':ref['display'],'kind':'ExternalType','path':'','line':1,'end':1,'declared_type':ref['display'],'resolution':status,'semantic_role':'declared_base_type','properties':'{}'}])
                links([{'a':owner['id'],'b':target_id,'kind':kind,'path':evidence['path'],'line':evidence['line'],'declared_type':ref['display']}])
            dependencies=defaultdict(list)
            for part in contributing:
                for dependency in part['fields']:dependencies[dependency['type']['display']].append((dependency,part))
            for declared,pairs in dependencies.items():
                first,evidence=pairs[0];target,status=resolve(first['type'],evidence)
                service_id=ident(owner['id']+':dependency:'+declared)
                write_nodes([{'id':service_id,'project':project,'index':index,'name':declared,'kind':'Service','path':evidence['path'],'line':first['line'],'end':first['line'],'declared_type':declared,'resolution':status,'semantic_role':'constructor_dependency','field_names':sorted({d['name'] for d,p in pairs}),'properties':'{}'}])
                stats['services']+=1
                links([{'a':owner['id'],'b':service_id,'kind':'INJECTS','path':evidence['path'],'line':first['line']}])
                if any(d['name'] in part['uses'] for d,p in pairs for part in contributing):links([{'a':owner['id'],'b':service_id,'kind':'USES_SERVICE','path':evidence['path'],'line':first['line']}])
                resolved=next((p for p in sorted(target or [],key=lambda p:(p['path'],p['line'])) if p['id']),None)
                if resolved:links([{'a':service_id,'b':resolved['id'],'kind':'DECLARED_TYPE','path':evidence['path'],'line':first['line']}])
                annotations=[]
                for dependency,part in pairs:
                    annotations.extend([{'path':part['path'],'name':dependency['name'],'lines':list({dependency['line'],dependency['declaration_line']}),'declared_type':declared}, {'path':part['path'],'name':dependency['parameter'],'lines':list({dependency['parameter_line'],dependency['constructor_line']}),'declared_type':declared}])
                db.run('UNWIND $rows AS row MATCH (n:HamtayarEntity) WHERE n.index=$index AND n.path=row.path AND n.name=row.name AND n.line IN row.lines AND n.kind IN ["Variable","Parameter"] SET n.semantic_role="injected_field",n.declared_type=row.declared_type',rows=annotations,index=index)
    log(f'C# semantics complete: {stats["types"]:,} declarations, {stats["services"]:,} injected dependency references, {stats["unresolved"]:,} unresolved/ambiguous bases, {unmatched:,} unmatched declarations.')
    return stats
