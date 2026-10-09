"""Verify built same-origin HTTP routing with TestClient, not a real deployment."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless((ROOT / 'dist/index.html').exists(), 'Run npm run build first')
class ServeWebTests(unittest.TestCase):
    def test_built_website_and_all_api_guards(self):
        with tempfile.TemporaryDirectory(prefix='aegis-serve-test-') as tmp:
            env={**os.environ,'AEGIS_SERVE_WEB':'1','AEGIS_WORKSPACE_TOKEN':'',
                 'AEGIS_SPATIAL_DB_PATH':str(Path(tmp)/'spatial.db'),
                 'LABSAFETY_DB_PATH':str(Path(tmp)/'legacy.db'),
                 'LABSAFETY_LLM_API_KEY':''}
            code='''
import os,re
from fastapi.testclient import TestClient
from backend.app.main import app
with TestClient(app) as c:
    root=c.get('/')
    assert root.status_code==200 and '<div id="root">' in root.text
    asset=re.search(r'src="(/assets/[^\"]+)"',root.text).group(1)
    assert c.get(asset).status_code==200
    assert c.get('/api/spatial').json()['workspace']['revision']==0
    assert c.get('/api/spatial',headers={'Origin':'https://untrusted.example'}).status_code==403
    os.environ['AEGIS_WORKSPACE_TOKEN']='test-only-token'
    assert c.get('/').status_code==200
    assert c.get('/api/spatial').status_code==401
    assert c.get('/reviews').status_code==401
    assert c.get('/api/spatial',headers={'Authorization':'Bearer test-only-token'}).status_code==200
'''
            result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
