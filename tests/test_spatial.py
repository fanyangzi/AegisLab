"""Regression tests for the browser workspace (not evidence of field safety)."""
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.app import spatial as s

TEMPLATE = json.loads((Path(__file__).resolve().parents[1] / 'data/spatial-example.json').read_text())

def fixture():
    return copy.deepcopy(TEMPLATE)

def initialize(store):
    return store.mutate(0, 'initial-0001', 'initialize', {'workspace': fixture()}, '测试负责人')

class DomainTests(unittest.TestCase):
    def test_empty_is_not_fake_success(self):
        self.assertEqual(s.envelope(s.empty_workspace())['checks'], [])
    def test_fixture_valid(self):
        s.validate_workspace(fixture())
    def test_unknown_is_not_pass(self):
        checks=s.check_workspace(fixture())
        self.assertTrue(any(c['code']=='EVIDENCE' and c['planId']=='EXP-001' and c['state']=='unknown' for c in checks))
    def test_half_open_times(self):
        self.assertFalse(s.overlap({'start':'2026-10-09T09:00:00Z','end':'2026-10-09T10:00:00Z'},{'start':'2026-10-09T10:00:00Z','end':'2026-10-09T11:00:00Z'}))
    def test_capacity_two(self):
        w=fixture();w['equipment'][0]['capacity']=2
        self.assertFalse(any(c['code']=='CAPACITY' and c['equipmentId']=='F-01' and c['state']=='blocked' for c in s.check_workspace(w)))
    def test_maintenance(self):
        w=fixture();next(e for e in w['equipment'] if e['id']=='A-01')['maintenance']=[{'id':'m','start':'2026-10-09T08:30:00+08:00','end':'2026-10-09T09:00:00+08:00','reason':'检查'}]
        self.assertTrue(any(c['planId']=='EXP-003' and c['code']=='AVAILABILITY' and c['state']=='blocked' for c in s.check_workspace(w)))
    def test_wrong_evidence_version(self):
        w=fixture();next(e for e in w['equipment'] if e['id']=='A-01')['specVersion']=2
        self.assertTrue(any(c['planId']=='EXP-003' and c['code']=='EVIDENCE' and c['state']=='unknown' for c in s.check_workspace(w)))
    def test_replacement_requires_source_reconciliation(self):
        w=fixture();w['plans'][0]['reservations'][0]['equipmentId']='F-02'
        self.assertTrue(any(c['planId']=='EXP-001' and c['code']=='BINDING' for c in s.check_workspace(w)))
    def test_approval_rechecks_conditions(self):
        with self.assertRaises(ValueError):s.apply_operation(fixture(),'approve',{'planId':'EXP-001','expectedPlanRevision':1,'comment':'不能跳过条件'},'负责人')
    def test_eligible_review_is_recorded(self):
        w=s.apply_operation(fixture(),'approve',{'planId':'EXP-003','expectedPlanRevision':1,'comment':'已核对登记范围'},'负责人')
        self.assertEqual(s.envelope(w)['statuses']['EXP-003'],'approved')
    def test_device_change_invalidates_review(self):
        w=s.apply_operation(fixture(),'approve',{'planId':'EXP-003','expectedPlanRevision':1,'comment':'已核对登记范围'},'负责人')
        e=copy.deepcopy(next(e for e in w['equipment'] if e['id']=='A-01'));e['status']='unavailable'
        w=s.apply_operation(w,'save_equipment',{'equipment':e},'负责人')
        self.assertEqual(s.envelope(w)['statuses']['EXP-003'],'recheck')
    def test_new_equipment_is_automatically_placed(self):
        w=fixture()
        created=[]
        for index in range(3):
            e={'id':f'new-{index}','labId':'lab-201','code':f'N-{index:02d}','name':f'新资源 {index}',
               'kind':'bench','x':0,'z':0,'rotation':0,'capacity':1,'status':'unknown','owner':'',
               'description':'由工作区负责人添加','requiresEvidence':True,'specVersion':1,'maintenance':[]}
            w=s.apply_operation(w,'save_equipment',{'equipment':e},'负责人')
            created.append(next(item for item in w['equipment'] if item['id']==e['id']))
        self.assertEqual(len({(item['x'],item['z']) for item in created}),3)
        for item in created:
            self.assertTrue(all(not s.equipment_overlaps(item, other) for other in w['equipment'] if other['id'] != item['id']))

    def test_explicit_origin_can_disable_automatic_placement(self):
        w=fixture()
        e={'id':'origin-1','labId':'lab-201','code':'N-ORIGIN','name':'原点资源',
           'kind':'waste','x':0,'z':0,'rotation':0,'capacity':1,'status':'unknown','owner':'',
           'description':'测试显式坐标','requiresEvidence':False,'specVersion':1,'maintenance':[]}
        w=s.apply_operation(w,'save_equipment',{'equipment':e,'autoPlace':False},'负责人')
        saved=next(item for item in w['equipment'] if item['id']==e['id'])
        self.assertEqual((saved['x'],saved['z']),(0,0))

    def test_new_equipment_requires_existing_lab(self):
        w=fixture()
        e={'id':'missing-lab','labId':'does-not-exist','code':'N-MISSING','name':'孤立资源',
           'kind':'bench','x':0,'z':0,'rotation':0,'capacity':1,'status':'unknown','owner':'',
           'description':'测试错误','requiresEvidence':False,'specVersion':1,'maintenance':[]}
        with self.assertRaises(ValueError):
            s.apply_operation(w,'save_equipment',{'equipment':e},'负责人')
    def test_visual_change_preserves_basis(self):
        w=fixture();p=w['plans'][2];before=s.basis(w,p);next(e for e in w['equipment'] if e['id']=='A-01')['x']-=.2
        self.assertEqual(before,s.basis(w,p))
    def test_task_does_not_verify_document(self):
        w=fixture();changed=s.apply_operation(w,'update_task',{'id':w['tasks'][0]['id'],'status':'done','note':'提交材料'},'负责人')
        self.assertEqual(w['documents'],changed['documents'])
    def test_invalid_source_reference(self):
        w=fixture();w['plans'][0]['steps'][0]['line']=999
        with self.assertRaises(ValueError):s.validate_workspace(w)
    def test_cross_lab_reference(self):
        w=fixture();w['laboratories'].append({'id':'another','name':'another','description':'','width':15,'depth':11});w['equipment'][0]['labId']='another'
        with self.assertRaises(ValueError):s.validate_workspace(w)
    def test_no_timezone(self):
        w=fixture();w['plans'][0]['reservations'][0]['start']='2026-10-09T09:00:00'
        with self.assertRaises(ValueError):s.validate_workspace(w)
    def test_extra_schema_fields(self):
        w=fixture();w['equipment'][0]['autoApprove']=True
        with self.assertRaises(ValueError):s.validate_workspace(w)
    def test_source_edit_is_unconfirmed(self):
        w=fixture();p=copy.deepcopy(w['plans'][0]);p['source']='改写的计划';p['steps']=[{'id':'s','line':1,'text':p['source'],'equipmentIds':[],'confirmed':True}]
        changed=s.apply_operation(w,'save_plan',{'plan':p,'expectedPlanRevision':1},'负责人')
        self.assertFalse(changed['plans'][0]['steps'][0]['confirmed'])
    def test_stale_branch(self):
        w=fixture();p=w['plans'][0];branch={'id':'b','name':'方案','planId':p['id'],'baseRevision':1,'baseBasis':s.basis(w,p),'reservations':p['reservations'],'createdAt':s.now()}
        w=s.apply_operation(w,'save_branch',{'branch':branch},'负责人');w['equipment'][0]['status']='unavailable'
        with self.assertRaises(ValueError):s.apply_operation(w,'apply_branch',{'id':'b'},'负责人')
    def test_typescript_python_parity(self):
        path=Path(__file__).with_name('web-parity.json')
        if not path.exists():self.skipTest('Generate with node scripts/test-web.mjs --parity')
        js=json.loads(path.read_text());w=fixture();py=s.envelope(w)
        self.assertEqual(js['basis'],[s.basis(w,p) for p in w['plans']])
        self.assertEqual(js['checks'],[{'id':c['id'],'state':c['state']} for c in py['checks']])
        self.assertEqual(js['statuses'],[py['statuses'][p['id']] for p in w['plans']])

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=str(Path(self.temp.name)/'workspace.db');self.store=s.WorkspaceStore(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_restart_preserves_state(self):
        initialize(self.store);self.assertEqual(s.WorkspaceStore(self.path).read()['revision'],1)
    def test_optimistic_concurrency_rejects_stale_write(self):
        initialize(self.store)
        with self.assertRaises(HTTPException) as result:self.store.mutate(0,'stale-001','confirm_steps',{'planId':'EXP-004'},'负责人')
        self.assertEqual(result.exception.status_code,409);self.assertEqual(self.store.read()['revision'],1)
    def test_request_retry_is_idempotent(self):
        initialize(self.store);self.store.mutate(1,'repeat-0001','confirm_steps',{'planId':'EXP-004'},'负责人')
        again=self.store.mutate(1,'repeat-0001','confirm_steps',{'planId':'EXP-004'},'负责人')
        self.assertEqual(again['revision'],2)
    def test_request_id_cannot_be_reused_for_different_payload(self):
        initialize(self.store);self.store.mutate(1,'repeat-0002','confirm_steps',{'planId':'EXP-004'},'负责人')
        with self.assertRaises(HTTPException):self.store.mutate(2,'repeat-0002','confirm_steps',{'planId':'EXP-003'},'负责人')
    def test_failed_transaction_does_not_modify_workspace(self):
        initialize(self.store);before=self.store.read()
        with self.assertRaises(ValueError):self.store.mutate(1,'failed-001','approve',{'planId':'EXP-001','expectedPlanRevision':1,'comment':'bad'},'负责人')
        self.assertEqual(before,self.store.read())

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();s._store=s.WorkspaceStore(str(Path(self.temp.name)/'api.db'))
        app=FastAPI();app.include_router(s.router);self.client=TestClient(app)
        self.env=patch.dict(os.environ,{'AEGIS_WORKSPACE_TOKEN':''});self.env.start()
    def tearDown(self):
        self.env.stop();self.client.close();s._store=None;self.temp.cleanup()
    def test_empty_api(self):self.assertEqual(self.client.get('/api/spatial').status_code,200)
    def test_save_lab_roundtrip_and_auto_place_resource(self):
        lab={'id':'lab-api','name':'API 测试实验室','description':'浏览器创建','width':10,'depth':8}
        response=self.client.post('/api/spatial/actions',json={'expectedRevision':0,'requestId':'api-lab-0001','type':'save_lab','payload':{'lab':lab}})
        self.assertEqual(response.status_code,200)
        snapshot=response.json();self.assertEqual(snapshot['workspace']['revision'],1)
        self.assertEqual(snapshot['workspace']['laboratories'][0]['id'],'lab-api')
        equipment={'id':'equipment-api','labId':'lab-api','code':'API-01','name':'测试操作台','kind':'bench','x':0,'z':0,'rotation':0,'capacity':1,'status':'unknown','owner':'','description':'','requiresEvidence':False,'specVersion':1,'maintenance':[]}
        response=self.client.post('/api/spatial/actions',json={'expectedRevision':1,'requestId':'api-eq-0001','type':'save_equipment','payload':{'equipment':equipment}})
        self.assertEqual(response.status_code,200)
        saved=response.json()['workspace']['equipment'][0]
        self.assertEqual(saved['labId'],'lab-api')
        self.assertEqual((saved['x'],saved['z']),(0.0,0.0))
    def test_other_origin_denied(self):self.assertEqual(self.client.get('/api/spatial',headers={'Origin':'https://evil.example'}).status_code,403)
    def test_token_mode(self):
        with patch.dict(os.environ,{'AEGIS_WORKSPACE_TOKEN':'test-owner-token'}):
            self.assertEqual(self.client.get('/api/spatial').status_code,401)
            self.assertEqual(self.client.get('/api/spatial',headers={'Authorization':'Bearer test-owner-token'}).status_code,200)
    def test_utf8_text_import(self):
        r=self.client.post('/api/spatial/import-text?filename=test.md',content='计划文本\n检查 F-01'.encode())
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['locator'],'extracted-text-lines')
    def test_unsupported_type_denied(self):self.assertEqual(self.client.post('/api/spatial/import-text?filename=evil.exe',content=b'abc').status_code,422)
    def test_scanned_pdf_empty_text_not_fabricated(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=200,height=200);f=io.BytesIO();writer.write(f)
        r=self.client.post('/api/spatial/import-text?filename=scan.pdf',content=f.getvalue())
        self.assertEqual(r.status_code,422)
    def test_docx_import_retains_table_order(self):
        from docx import Document
        doc=Document();doc.add_paragraph('第一段');table=doc.add_table(rows=1,cols=2);table.cell(0,0).text='设备';table.cell(0,1).text='F-01';doc.add_paragraph('第二段');f=io.BytesIO();doc.save(f)
        r=self.client.post('/api/spatial/import-text?filename=test.docx',content=f.getvalue())
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['text'],'第一段\n设备 | F-01\n第二段')
    def test_analysis_cannot_mutate_workspace(self):
        initialize(s.store());before=s.store().read()
        with patch.dict(os.environ,{'LABSAFETY_LLM_API_KEY':''}):r=self.client.post('/api/spatial/plans/EXP-001/analysis',json={})
        self.assertEqual(r.status_code,200);self.assertEqual(s.store().read(),before);self.assertTrue(r.json()['degraded'])

if __name__=='__main__':unittest.main()
