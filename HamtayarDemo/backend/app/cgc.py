import os
import json
import subprocess
import threading
import time
from pathlib import Path
from .config import CGC, RUNTIME, setting

class CGCAdapter:
    def command(self, *args):
        exe=Path(CGC)
        if not exe.is_file():
            raise ValueError('CGC executable not found. Set CGC_EXECUTABLE in HamtayarDemo/.env')
        python = exe.parent / ('python.exe' if os.name == 'nt' else 'python')
        if not python.is_file():
            raise ValueError('Configure a CGC executable inside its Python virtual environment')
        # This CGC commit hardcodes Path.home(), ignoring CGC_HOME. Redirect only
        # the child interpreter's profile before importing CGC; upstream stays intact.
        bootstrap = "import os,pathlib,runpy; pathlib.Path.home=classmethod(lambda cls: pathlib.Path(os.environ['HAMTAYAR_CGC_PROFILE'])); runpy.run_module('codegraphcontext',run_name='__main__')"
        return [str(python), '-c', bootstrap, *args]
    def environment(self, job):
        home=RUNTIME/'cgc'/job
        home.mkdir(parents=True,exist_ok=True)
        env=os.environ.copy()
        env.update({'HAMTAYAR_CGC_PROFILE':str(home),'DEFAULT_DATABASE':'neo4j','CGC_RUNTIME_DB_TYPE':'neo4j','ENABLE_APP_LOGS':'INFO','CGC_IGNORE_PROJECT_ENV':'1','CGC_LOAD_PROJECT_ENV':'0','SCIP_INDEXER':'false','ENABLE_AUTO_WATCH':'false','PYTHONUNBUFFERED':'1'})
        for suffix, default in [('URI','bolt://127.0.0.1:7689'),('USERNAME','neo4j'),('DATABASE','neo4j'),('PASSWORD','')]:
            env['NEO4J_'+suffix]=setting('STAGING_NEO4J_'+suffix,default)
        return env
    def inspect(self):
        result={}
        for name,args in [('version',['--version']),('help',['--help']),('index',['index','--help']),('find',['find','--help']),('analyze',['analyze','--help'])]:
            try:
                p=subprocess.run(self.command(*args),env=self.environment('diagnostics'),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
                result[name]={'exit_code':p.returncode,'output':p.stdout[-20000:]}
            except (ValueError,OSError,subprocess.TimeoutExpired) as e:
                result[name]={'error':str(e)}
        return result
    def index(self, workspace, job, cancelled, log):
        flags={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
        from .index_policy import settings
        policy=settings()
        env=self.environment(job)
        env['PARALLEL_WORKERS']=str(policy['workers'])
        profile=RUNTIME/'cgc'/job
        policy_path=profile/'policy.json'; report_path=profile/'report.json'
        policy_path.write_text(json.dumps(policy),encoding='utf-8')
        python=self.command('--version')[0]
        command=[python,str(Path(__file__).with_name('cgc_runner.py')),str(workspace),str(policy_path),str(report_path)]
        log(f'CGC settings: workers={policy["workers"]}, per-file filter={policy["max_bytes"]} bytes, timeout={policy["timeout"]}s; exclusions={policy["patterns"]}')
        log('Indexing executes a full selected-scope pass. Existing file counts are not completion percentages.')
        process=subprocess.Popen(command,cwd=workspace,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',**flags)
        def consume():
            for line in process.stdout:
                for key in ('STAGING_NEO4J_PASSWORD','NEO4J_PASSWORD','LLM_API_KEY'):
                    secret=setting(key)
                    if secret:
                        line=line.replace(secret,'[REDACTED]')
                log(line.rstrip()[:2000])
        reader=threading.Thread(target=consume,daemon=True);reader.start()
        deadline=time.monotonic()+policy['timeout']
        while process.poll() is None:
            if cancelled.is_set() or time.monotonic()>deadline:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
                else:
                    import signal
                    os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=15);reader.join(timeout=5)
                if report_path.is_file():
                    report=json.loads(report_path.read_text(encoding='utf-8'))
                    report['outcome']='cancelled' if cancelled.is_set() else 'timed_out'
                    temp=report_path.with_suffix('.tmp')
                    temp.write_text(json.dumps(report),encoding='utf-8');temp.replace(report_path)
                raise ValueError('Cancelled' if cancelled.is_set() else f'CGC indexing timed out after {policy["timeout"]} seconds; inspect the last active stage/file in the indexing report. Adjust scope before increasing INDEX_TIMEOUT_SECONDS.')
            cancelled.wait(.25)
        reader.join(timeout=5)
        if process.returncode:
            raise ValueError(f'CGC failed with exit code {process.returncode}; inspect sanitized logs')

        if not report_path.is_file():
            raise ValueError('CGC did not return an indexing report')
        report=json.loads(report_path.read_text(encoding='utf-8'))
        if report.get('outcome')!='completed':
            raise ValueError('CGC did not complete all indexing phases')
        return report
