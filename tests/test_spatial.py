"""Regression tests for the browser workspace (not evidence of field safety)."""
import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.app import spatial as s
from backend.app.parser import parse_sop
from backend.app.llm import LLMAdapter

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
    def test_unrelated_future_maintenance_does_not_change_basis(self):
        w=fixture();p=w['plans'][2];before=s.basis(w,p)
        next(e for e in w['equipment'] if e['id']=='A-01')['maintenance'].append({'id':'future','start':'2030-01-01T00:00:00Z','end':'2030-01-01T01:00:00Z','reason':'远期维护'})
        self.assertEqual(before,s.basis(w,p))
    def test_negated_and_proposed_controls_are_not_satisfied(self):
        parsed=parse_sop('1. 未检查通风柜，尚未配备护目镜。\n2. 拟采用通风柜并计划补充实验服。')
        self.assertEqual(parsed['steps'][0].ventilation, None)
        self.assertEqual(parsed['steps'][0].requires_ppe, [])
        states={(item['subject'], item['state']) for item in parsed['control_assertions']}
        self.assertIn(('ventilation','negated'), states)
        self.assertIn(('护目镜','negated'), states)
        self.assertIn(('ventilation','proposed'), states)
        self.assertEqual(parsed['steps'][1].controls, [])
    def test_postfix_negation_and_history_are_not_aggregated(self):
        parsed=parse_sop('1. 通风柜未检查，废液类别未确认。\n2. 上周已检查通风柜。')
        self.assertIsNone(parsed['ventilation'])
        self.assertEqual(parsed['waste_streams'], [])
        self.assertEqual({item['state'] for item in parsed['control_assertions']}, {'negated', 'historical'})
    def test_model_reordering_without_source_span_is_ignored(self):
        parsed=parse_sop('1. 在通风柜中操作。\n2. 按类别分流废液。')
        original=[step.instruction for step in parsed['steps']]
        merged,used=s._merge_model_parse(parsed, {'steps':[{'order':2,'instruction':'按类别分流废液。'},{'order':1,'instruction':'在通风柜中操作。'}]})
        self.assertFalse(used)
        self.assertEqual([step.instruction for step in merged['steps']],original)
    def test_anchored_model_is_candidate_and_cannot_promote_missing_control(self):
        parsed=parse_sop('1. 未检查通风柜，尚未配备护目镜。')
        merged,used=s._merge_model_parse(parsed, {'steps':[{
            'order':1,'instruction':'未检查通风柜，尚未配备护目镜。',
            'documentRevisionId':parsed['document_revision_id'],'sourceLine':1,
            'sourceTextHash':parsed['steps'][0].source_text_hash,
            'ventilation':'通风柜','requires_ppe':['护目镜']}]})
        self.assertTrue(used)
        self.assertIsNone(merged['ventilation'])
        self.assertEqual(merged['ppe'],[])
        self.assertTrue(merged['model_candidates'])
    def test_task_does_not_verify_document(self):
        w=fixture();changed=s.apply_operation(w,'update_task',{'id':w['tasks'][0]['id'],'status':'done','note':'提交材料'},'负责人')
        self.assertEqual(w['documents'],changed['documents'])
    def test_task_return_cancel_reopen_lifecycle_is_audited(self):
        w=fixture(); task_id=w['tasks'][0]['id']
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'submitted','note':'负责人已提交材料'},'负责人')
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'returned','note':'请补充当前规格版本的检查记录'},'安全负责人')
        self.assertEqual(w['tasks'][0]['status'],'returned')
        self.assertIn('退回补充',w['events'][-1]['summary'])
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'reopened','note':'已按退回意见重开'},'负责人')
        self.assertEqual(w['tasks'][0]['status'],'reopened')
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'cancelled','note':'实验已取消，不再补证'},'负责人')
        self.assertEqual(w['tasks'][0]['status'],'cancelled')
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'reopened','note':'需要重新执行该检查'},'负责人')
        self.assertEqual(w['tasks'][0]['status'],'reopened')

    def test_task_terminal_transition_and_reason_are_enforced(self):
        w=fixture(); task_id=w['tasks'][0]['id']
        with self.assertRaises(ValueError):
            s.apply_operation(w,'update_task',{'id':task_id,'status':'returned','note':''},'负责人')
        w=s.apply_operation(w,'update_task',{'id':task_id,'status':'done','note':'已完成'},'负责人')
        with self.assertRaises(ValueError):
            s.apply_operation(w,'update_task',{'id':task_id,'status':'submitted','note':'重新提交'},'负责人')
    def test_duplicate_ai_task_is_rejected(self):
        w=fixture(); task={'id':'ai-task-1','title':'补充检查证据','planId':'EXP-001','equipmentId':'F-01','owner':'陈同学','dueAt':'2026-10-09T18:00:00+08:00','status':'open','note':'来源 SOP L1','sourceId':'EXP-001:EVIDENCE:F-01','sourceLine':1,'documentIds':[],'actionKind':'evidence','actionTarget':{'type':'evidence','planId':'EXP-001','equipmentId':'F-01'}}
        w=s.apply_operation(w,'save_task',{'task':task},'负责人')
        duplicate=dict(task,id='ai-task-2')
        with self.assertRaises(ValueError): s.apply_operation(w,'save_task',{'task':duplicate},'负责人')
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

    def test_llm_http_failure_is_secret_free_and_explained(self):
        with patch.dict(os.environ, {
            'LABSAFETY_LLM_BASE_URL':'https://example.invalid/v1',
            'LABSAFETY_LLM_MODEL':'gpt-6.1-sol',
            'LABSAFETY_LLM_API_KEY':'test-token',
            'LABSAFETY_LLM_ENABLED':'1',
        }), patch('backend.app.llm.urllib.request.urlopen', side_effect=urllib.error.HTTPError(
            'https://example.invalid/v1/chat/completions', 401, 'Invalid token', {}, None
        )):
            result=LLMAdapter().summarize({'title':'测试计划'}, {'results':[]})
        self.assertTrue(result.degraded)
        self.assertEqual(result.provider,'offline')
        self.assertEqual(result.reason,'远程模型返回 HTTP 401')
        self.assertNotIn('test-token', result.text)

    def test_llm_prefers_responses_api_and_reads_output_text(self):
        calls=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return '{"output_text":"模型总结：请人工复核"}'.encode('utf-8')
        def fake_urlopen(request, timeout=0):
            calls.append((request.full_url, json.loads(request.data.decode('utf-8'))))
            return Response()
        with patch.dict(os.environ, {
            'LABSAFETY_LLM_BASE_URL':'https://example.invalid/v1',
            'LABSAFETY_LLM_MODEL':'gpt-6.1-sol',
            'LABSAFETY_LLM_API_KEY':'test-token',
            'LABSAFETY_LLM_ENABLED':'1',
        }), patch('backend.app.llm.urllib.request.urlopen', side_effect=fake_urlopen):
            result=LLMAdapter().summarize({'title':'测试计划'}, {'results':[]})
        self.assertFalse(result.degraded)
        self.assertEqual(result.text,'模型总结：请人工复核')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],'https://example.invalid/v1/responses')
        self.assertIn('instructions',calls[0][1])
        self.assertIn('input',calls[0][1])
        self.assertEqual(calls[0][1]['reasoning'],{'effort':'low'})
        self.assertNotIn('messages',calls[0][1])
        self.assertNotIn('temperature',calls[0][1])

    def test_llm_reads_responses_output_blocks(self):
        self.assertEqual(
            LLMAdapter._response_text({'output':[{'type':'message','content':[
                {'type':'output_text','text':'第一段'},
                {'type':'output_text','text':{'value':'第二段'}},
            ]}]}),
            '第一段\n第二段',
        )

    def test_llm_falls_back_to_chat_only_when_responses_is_unsupported(self):
        calls=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return '{"choices":[{"message":{"content":"兼容网关总结"}}]}'.encode('utf-8')
        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            if request.full_url.endswith('/responses'):
                raise urllib.error.HTTPError(request.full_url, 404, 'unsupported', {}, None)
            return Response()
        with patch.dict(os.environ, {
            'LABSAFETY_LLM_BASE_URL':'https://example.invalid/v1',
            'LABSAFETY_LLM_MODEL':'gpt-6.1-sol',
            'LABSAFETY_LLM_API_KEY':'test-token',
            'LABSAFETY_LLM_ENABLED':'1',
        }), patch('backend.app.llm.urllib.request.urlopen', side_effect=fake_urlopen):
            result=LLMAdapter().summarize({'title':'测试计划'}, {'results':[]})
        self.assertFalse(result.degraded)
        self.assertEqual(result.text,'兼容网关总结')
        self.assertEqual(calls,[
            'https://example.invalid/v1/responses',
            'https://example.invalid/v1/chat/completions',
        ])

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
    def test_restore_snapshots_before_replace_and_ignores_imported_revision(self):
        initialize(self.store);candidate=self.store.read();candidate['name']='恢复后的工作区';candidate['revision']=999
        restored=self.store.restore(expected_revision=1,request_id='restore-0001',candidate=candidate,actor='测试负责人')
        self.assertEqual(restored['revision'],2);self.assertEqual(restored['name'],'恢复后的工作区')
        snapshots=self.store.snapshots();self.assertEqual(len(snapshots),1);self.assertEqual(snapshots[0]['revision'],1)
        before=self.store.snapshot(snapshots[0]['snapshotId']);self.assertEqual(before['workspace']['name'],fixture()['name'])
        retry=self.store.restore(expected_revision=1,request_id='restore-0001',candidate=candidate,actor='测试负责人')
        self.assertEqual(retry,restored);self.assertEqual(len(self.store.snapshots()),1)
    def test_restore_rejects_stale_revision_without_snapshot(self):
        initialize(self.store);candidate=self.store.read();candidate['name']='过期恢复'
        with self.assertRaises(HTTPException) as result:self.store.restore(expected_revision=0,request_id='restore-0002',candidate=candidate,actor='测试负责人')
        self.assertEqual(result.exception.status_code,409);self.assertEqual(self.store.snapshots(),[])
    def test_job_cancel_is_persisted_and_terminal_states_are_immutable(self):
        queued=self.store.begin_job(job_id='job-cancel-01',kind='analysis',plan_id='EXP-001',idempotency_key='idem-cancel-01')
        self.assertEqual(queued['status'],'queued')
        cancelled=self.store.cancel_job('job-cancel-01',reason='测试取消')
        self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(cancelled['error'],'测试取消')
        self.assertEqual(self.store.cancel_job('job-cancel-01')['status'],'cancelled')
        with self.assertRaises(HTTPException) as result:self.store.set_job_running('job-cancel-01')
        self.assertEqual(result.exception.status_code,409)
        succeeded=self.store.begin_job(job_id='job-success-01',kind='analysis',plan_id='EXP-001',idempotency_key='idem-success-01')
        self.store.set_job_running(succeeded['jobId'])
        self.store.finish_job(succeeded['jobId'],status='succeeded',result={'ok':True})
        with self.assertRaises(HTTPException) as result:self.store.cancel_job(succeeded['jobId'])
        self.assertEqual(result.exception.status_code,409)
    def test_running_job_is_marked_failed_when_a_new_store_opens_after_restart(self):
        created=self.store.begin_job(job_id='job-restart-01',kind='analysis',plan_id='EXP-001',idempotency_key='idem-restart-01')
        self.store.set_job_running(created['jobId'])
        restarted=s.WorkspaceStore(self.path)
        recovered=restarted.job(created['jobId'])
        self.assertEqual(recovered['status'],'failed')
        self.assertIn('服务重启',recovered['error'])
        self.assertIsNotNone(recovered['finishedAt'])
    def test_failed_job_is_queryable_after_explicit_failure(self):
        created=self.store.begin_job(job_id='job-fail-01',kind='analysis',plan_id='EXP-001',idempotency_key='idem-fail-01')
        self.store.set_job_running(created['jobId'])
        failed=self.store.finish_job(created['jobId'],status='failed',error='解析器异常')
        self.assertEqual(failed['status'],'failed');self.assertEqual(failed['error'],'解析器异常')
        self.assertEqual(s.WorkspaceStore(self.path).job(created['jobId'])['status'],'failed')

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();s._store=s.WorkspaceStore(str(Path(self.temp.name)/'api.db'))
        app=FastAPI();app.include_router(s.router)
        # Mount the legacy review endpoint explicitly so this isolated API
        # test exercises the real handler without opening the production DB.
        from backend.app import main as legacy
        app.post('/reviews/from-sop', response_model=legacy.Review, status_code=201)(legacy.create_review_from_sop)
        self.legacy=legacy
        from backend.app.db import SQLiteRepository
        from backend.app.service import AegisService
        self.service=AegisService(repo=SQLiteRepository(':memory:'))
        self.service_patch=patch.object(legacy, 'service', self.service);self.service_patch.start()
        self.client=TestClient(app)
        self.env=patch.dict(os.environ,{'AEGIS_WORKSPACE_TOKEN':''});self.env.start()
    def tearDown(self):
        self.env.stop();self.client.close();self.service_patch.stop();s._store=None;self.temp.cleanup()
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
    def test_server_role_controls_approval(self):
        initialize(s.store())
        with patch.dict(os.environ,{'AEGIS_WORKSPACE_ROLE':'researcher'}):
            response=self.client.post('/api/spatial/actions',json={'expectedRevision':1,'requestId':'role-deny-0001','type':'approve','payload':{'planId':'EXP-003','expectedPlanRevision':1,'comment':'尝试越权复核'}})
        self.assertEqual(response.status_code,403)
    def test_clean_workspace_can_complete_web_lifecycle_without_examples(self):
        def act(revision, request_id, action, payload):
            response=self.client.post('/api/spatial/actions',json={'expectedRevision':revision,'requestId':request_id,'type':action,'payload':payload})
            self.assertEqual(response.status_code,200,response.text);return response.json()
        lab={'id':'lab-clean','name':'空白验证实验室','description':'clean acceptance','width':12,'depth':10}
        act(0,'clean-lab-01','save_lab',{'lab':lab})
        equipment={'id':'eq-clean-01','labId':'lab-clean','code':'C-01','name':'清洁操作台','kind':'bench','x':0,'z':0,'rotation':0,'capacity':1,'status':'available','owner':'验证负责人','description':'新工作区录入','requiresEvidence':False,'specVersion':1,'maintenance':[]}
        act(1,'clean-eq-01','save_equipment',{'equipment':equipment})
        source='第一步：准备样品\n第二步：完成记录'
        plan={'id':'plan-clean-01','code':'CLEAN-001','labId':'lab-clean','name':'清洁环境新计划','owner':'验证负责人','revision':1,'source':source,'sourceName':'clean-source.txt','steps':[{'id':'clean-step-1','text':'第一步：准备样品','line':1,'equipmentIds':['eq-clean-01'],'confirmed':False},{'id':'clean-step-2','text':'第二步：完成记录','line':2,'equipmentIds':[],'confirmed':False}],'reservations':[{'id':'clean-res-1','equipmentId':'eq-clean-01','start':'2026-10-09T09:00:00+08:00','end':'2026-10-09T10:00:00+08:00'}],'archived':False}
        state=act(2,'clean-plan-01','save_plan',{'plan':plan});state=act(3,'clean-confirm','confirm_steps',{'planId':'plan-clean-01'});self.assertEqual(state['statuses']['plan-clean-01'],'ready')
        task={'id':'clean-task-01','title':'完成清洁环境记录','planId':'plan-clean-01','equipmentId':'eq-clean-01','owner':'验证负责人','dueAt':'2026-10-09T18:00:00+08:00','status':'open','note':'来自清洁环境验收'}
        state=act(4,'clean-task-01','save_task',{'task':task});state=act(5,'clean-approve','approve',{'planId':'plan-clean-01','expectedPlanRevision':2,'comment':'已核对清洁环境工作流'})
        self.assertEqual(state['statuses']['plan-clean-01'],'approved')
        plan['revision']=3;plan['archived']=True;plan['steps']=[dict(step,confirmed=True) for step in plan['steps']]
        state=act(6,'clean-archive','save_plan',{'plan':plan,'expectedPlanRevision':2});self.assertEqual(state['statuses']['plan-clean-01'],'archived')
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
        runs=self.client.get('/api/spatial/plans/EXP-001/analysis/runs').json()['runs'];self.assertEqual(len(runs),1);self.assertEqual(runs[0]['trace']['runId'],r.json()['trace']['runId'])
        evaluations=self.client.get('/api/spatial/plans/EXP-001/evaluations').json()['evaluations']
        self.assertEqual(len(evaluations),1);self.assertEqual(evaluations[0]['evaluationId'],r.json()['evaluationId']);self.assertEqual(evaluations[0]['basis'],s.basis(before,before['plans'][0]))
    def test_job_cancel_api_persists_state_and_is_role_gated(self):
        job=s.store().begin_job(job_id='api-cancel-01',kind='analysis',plan_id='EXP-001',idempotency_key='api-cancel-01')
        response=self.client.post('/api/spatial/jobs/'+job['jobId']+'/cancel')
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['status'],'cancelled')
        self.assertEqual(self.client.get('/api/spatial/jobs/'+job['jobId']).json()['status'],'cancelled')
        with patch.dict(os.environ,{'AEGIS_WORKSPACE_ROLE':'researcher'}):
            denied=self.client.post('/api/spatial/jobs/'+job['jobId']+'/cancel')
        self.assertEqual(denied.status_code,403)
    def test_analysis_failure_finishes_job_as_failed(self):
        initialize(s.store())
        with patch('backend.app.parser.parse_sop', side_effect=RuntimeError('解析器异常')):
            response=self.client.post('/api/spatial/plans/EXP-001/analysis')
        self.assertEqual(response.status_code,500,response.text)
        job=self.client.get('/api/spatial/jobs/analysis:EXP-001:v1')
        self.assertEqual(job.status_code,200);self.assertEqual(job.json()['status'],'failed');self.assertIn('RuntimeError',job.json()['error'])
        retry=self.client.post('/api/spatial/plans/EXP-001/analysis?retry=true')
        self.assertEqual(retry.status_code,200,retry.text);self.assertEqual(retry.json()['job']['status'],'succeeded')
    def test_analysis_retry_reruns_succeeded_revision_without_rewriting_plan(self):
        initialize(s.store())
        with patch.dict(os.environ,{'LABSAFETY_LLM_API_KEY':''}):
            first=self.client.post('/api/spatial/plans/EXP-001/analysis')
            self.assertEqual(first.status_code,200,first.text)
            second=self.client.post('/api/spatial/plans/EXP-001/analysis?retry=true')
        self.assertEqual(second.status_code,200,second.text)
        self.assertNotEqual(first.json()['job']['jobId'],second.json()['job']['jobId'])
        self.assertEqual(second.json()['planRevision'],first.json()['planRevision'])
        self.assertEqual(len(self.client.get('/api/spatial/plans/EXP-001/analysis/runs').json()['runs']),2)
        self.assertEqual(s.store().read()['revision'],1)
    def test_relationship_graph_supports_plan_type_and_time_filters(self):
        initialize(s.store())
        response=self.client.get('/api/spatial/graph?planId=EXP-001&types=plan,step,equipment&dateFrom=2026-10-09T09:00:00%2B08:00&dateTo=2026-10-09T09:30:00%2B08:00')
        self.assertEqual(response.status_code,200,response.text)
        graph=response.json();self.assertEqual(graph['planId'],'EXP-001')
        self.assertTrue(graph['nodes']);self.assertTrue(all(node['type'] in {'plan','step','equipment'} for node in graph['nodes']))
        self.assertTrue(any(edge['relation']=='reserves' for edge in graph['edges']))
        self.assertTrue(any(node['id']=='equipment:C-01' for node in graph['nodes']))
    def test_relationship_graph_local_neighbourhood_and_invalid_filters(self):
        initialize(s.store())
        response=self.client.get('/api/spatial/graph?planId=EXP-001&nodeId=plan:EXP-001&hops=1')
        self.assertEqual(response.status_code,200,response.text)
        graph=response.json();self.assertIn('plan:EXP-001',{node['id'] for node in graph['nodes']})
        self.assertTrue(all(edge['from'] in {node['id'] for node in graph['nodes']} and edge['to'] in {node['id'] for node in graph['nodes']} for edge in graph['edges']))
        self.assertEqual(self.client.get('/api/spatial/graph?dateFrom=bad').status_code,422)
        self.assertEqual(self.client.get('/api/spatial/graph?hops=3').status_code,422)
    def test_restore_api_is_role_gated_and_creates_snapshot(self):
        initialize(s.store());candidate=s.store().read();candidate['name']='服务端恢复验收';candidate['revision']=700
        response=self.client.post('/api/spatial/restore',json={'expectedRevision':1,'requestId':'api-restore-01','confirm':'RESTORE','workspace':candidate})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['workspace']['revision'],2)
        listed=self.client.get('/api/spatial/snapshots').json()['snapshots'];self.assertEqual(len(listed),1)
        detail=self.client.get('/api/spatial/snapshots/'+listed[0]['snapshotId']);self.assertEqual(detail.status_code,200);self.assertEqual(detail.json()['workspace']['name'],fixture()['name'])
        stale=self.client.post('/api/spatial/restore',json={'expectedRevision':1,'requestId':'api-restore-02','confirm':'RESTORE','workspace':candidate})
        self.assertEqual(stale.status_code,409)
        with patch.dict(os.environ,{'AEGIS_WORKSPACE_ROLE':'researcher'}):
            denied=self.client.post('/api/spatial/restore',json={'expectedRevision':2,'requestId':'api-restore-03','confirm':'RESTORE','workspace':candidate})
        self.assertEqual(denied.status_code,403)
    def test_review_endpoint_rejects_unanchored_model_reordering(self):
        with patch.object(self.service.llm, 'extract_sop', return_value={'steps':[{'order':2,'instruction':'第二步：完成转移操作'},{'order':1,'instruction':'第一步：准备样品'}]}):
            response=self.client.post('/reviews/from-sop',json={'title':'来源绑定测试','room':'测试室','sop_text':'第一步：准备样品\n第二步：完成转移操作'})
        self.assertEqual(response.status_code,201)
        self.assertEqual([step['instruction'] for step in response.json()['steps']],['第一步：准备样品','第二步：完成转移操作'])

if __name__=='__main__':unittest.main()
