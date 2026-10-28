from pathlib import Path
import pytest
from app.csharp_semantics import parse_source,enrich

FIXTURE=Path(__file__).parent/'fixtures'/'accommodation_semantics.cs'

class SemanticDB:
    def __init__(self,items):
        self.nodes={str(i):{'id':str(i),'name':n['name'],'kind':n['kind'],'path':n['path'],'line':n['line']} for i,n in enumerate(items)}
        self.edges=[];self.calls=[]
    def stream(self,q,**params):return iter(list(self.nodes.values()))
    def run(self,q,**params):
        self.calls.append((q,params))
        if 'SET n += row' in q:
            for row in params['rows']:self.nodes[row['id']]=row
        if 'MERGE (a)-[r:HAMTAYAR_LINK' in q:self.edges+=params['rows']
        return []


def test_user_generic_base_and_nine_injected_types():
    result=parse_source(FIXTURE.read_text(),'controller.cs');owner=result['types'][0]
    assert not result['has_syntax_errors']
    assert owner['bases'][0]['name']=='BaseController' and owner['bases'][0]['arity']==5
    assert len(owner['fields'])==9
    assert {d['name'] for d in owner['fields']}=={'_mapper','_accommodationService','_logger','_permissionService','_userPrincipal','_userService','_personService','_accommodationContractService','_accommodationTypeService'}
    assert '_accommodationService' in owner['uses']


def test_enrich_resolves_generic_base_and_service_types(tmp_path):
    source=tmp_path/'controller.cs';source.write_text(FIXTURE.read_text())
    items=parse_source(source.read_text(),'controller.cs')['types'];db=SemanticDB(items)
    report=enrich(db,'p','v',tmp_path,[str(source)])
    assert report['services']==9 and report['unmatched']==0
    base=next(n for n in db.nodes.values() if n['name']=='BaseController')
    assert any(e['a']=='0' and e['b']==base['id'] and e['kind']=='INHERITS' and 'AccommodationSimpleViewModel>' in e['declared_type'] for e in db.edges)
    services=[n for n in db.nodes.values() if n['kind']=='Service']
    assert len(services)==9 and any(n['name']=='IYashilLogger<Accommodation>' for n in services)
    assert any(e['kind']=='USES_SERVICE' for e in db.edges)
    assert any(e['kind']=='DECLARED_TYPE' for e in db.edges)
    assert all(params['index']=='v' for q,params in db.calls if 'DELETE r' in q)
    assert all(e['a']!='foreign' for e in db.edges)


def test_partial_across_files_and_shadowed_locals(tmp_path):
    a='namespace N; public partial class C : B { readonly IService _s; public C(IService s){this._s=s;} } class B {} interface IService {}'
    b='namespace N; public partial class C { void M(){_s.Go();} }'
    facts=[];paths=[]
    for name,content in [('a.cs',a),('b.cs',b)]:
        p=tmp_path/name;p.write_text(content);paths.append(str(p));facts+=parse_source(content,name)['types']
    db=SemanticDB(facts);enrich(db,'p','v',tmp_path,paths)
    owner_ids={n['id'] for n in db.nodes.values() if n['name']=='C'}
    assert {e['a'] for e in db.edges if e['kind']=='INHERITS'}==owner_ids
    assert {e['a'] for e in db.edges if e['kind']=='INJECTS'}==owner_ids
    assert {e['a'] for e in db.edges if e['kind']=='USES_SERVICE'}==owner_ids
    parsed=parse_source('class C { IService _s; public C(IService s){_s=s;} void M(IService _s){_s.Go();} }','c.cs')
    assert '_s' not in parsed['types'][0]['uses']


def test_ambiguous_imports_do_not_guess(tmp_path):
    source=tmp_path/'c.cs';source.write_text('using A; using B; class C: Parent {} namespace A { class Parent {} } namespace B { class Parent {} }')
    facts=parse_source(source.read_text(),'c.cs')['types'];db=SemanticDB(facts);enrich(db,'p','v',tmp_path,[str(source)])
    ref=next(n for n in db.nodes.values() if n['kind']=='ExternalType')
    assert ref['resolution']=='ambiguous'
    assert any(e['kind']=='BASE_TYPE' for e in db.edges)
    assert not any(e['kind']=='INHERITS' for e in db.edges)


def test_generic_nested_arguments_qualified_alias_and_interface(tmp_path):
    source=tmp_path/'c.cs';source.write_text('using Alias = A.Parent; class C : Alias, A.IFoo {} namespace A { class Parent {} interface IFoo {} } class D : A.Generic<System.Collections.Generic.Dictionary<string,int>, System.Collections.Generic.List<int>> {} namespace A { class Generic<T,U> {} }')
    facts=parse_source(source.read_text(),'c.cs')['types'];db=SemanticDB(facts);enrich(db,'p','v',tmp_path,[str(source)])
    assert any(e['kind']=='IMPLEMENTS' for e in db.edges)
    assert sum(e['kind']=='INHERITS' for e in db.edges)==2


def test_non_constructor_assignments_and_scalar_params_not_services():
    source='class C { int _count; IService _s; public C(int n){_count=n;} void M(IService service){ _s=service; } }'
    assert not parse_source(source,'c.cs')['types'][0]['fields']


def test_parameter_positions_survive_publication():
    from app.publication import node_row
    row=node_row({'id':'x','labels':['Parameter'],'props':{'name':'service','path':'/repo/c.cs','function_line_number':20}},'p','v','/repo/')
    assert row['line']==20 and row['end']==20


def test_global_alias_does_not_bind_shadow_namespace(tmp_path):
    source=tmp_path/'c.cs';source.write_text("using Alias = global::A.Parent;\nnamespace A {\nclass Parent {}\n}\nnamespace N {\nclass C : Alias {}\nnamespace A {\nclass Parent {}\n}\n}")
    facts=parse_source(source.read_text(),'c.cs')['types'];db=SemanticDB(facts);enrich(db,'p','v',tmp_path,[str(source)])
    parent_id=str(next(i for i,n in enumerate(facts) if n['qualified']=='A.Parent'))
    assert any(e['kind']=='INHERITS' and e['b']==parent_id for e in db.edges)
