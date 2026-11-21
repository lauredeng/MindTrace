"""SQLite transactional workspace adapter and durable, fenced task queue.

Domain records retain their validated shape during incremental migration. Indexes,
job leases and invocation reservations are relational and cross-process atomic.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


class ConflictError(ValueError):pass


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class Repository:
    def __init__(self,path,*,clock=time.time):
        self.path=Path(path).resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.clock=clock
        with self.connect() as db:
            try:current=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
            except sqlite3.OperationalError:current=0
            if current and current>2:raise RuntimeError('数据库来自更新版本，当前程序不会降级覆盖。')
            if current==2:return
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workspaces(
                id TEXT PRIMARY KEY,scope TEXT NOT NULL UNIQUE,version INTEGER NOT NULL,payload TEXT NOT NULL,updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS record_index(
                workspace_id TEXT NOT NULL REFERENCES workspaces(id),collection TEXT NOT NULL,id TEXT NOT NULL,
                student_id TEXT,batch_id TEXT,submission_id TEXT,payload TEXT NOT NULL,
                PRIMARY KEY(workspace_id,collection,id));
            CREATE INDEX IF NOT EXISTS idx_student_records ON record_index(workspace_id,student_id,collection);
            CREATE TABLE IF NOT EXISTS imports(source_hash TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),batch_id TEXT NOT NULL,
                submission_id TEXT NOT NULL,stage TEXT NOT NULL CHECK(stage IN ('quick','deep')),
                input_key TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,fence INTEGER NOT NULL DEFAULT 0,
                lease_owner TEXT,lease_until REAL NOT NULL DEFAULT 0,next_retry_at REAL NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,updated_at REAL NOT NULL,error TEXT);
            CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status,next_retry_at,lease_until);
            CREATE TABLE IF NOT EXISTS job_events(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL REFERENCES jobs(id),
                status TEXT NOT NULL,occurred_at REAL NOT NULL,message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS invocations(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),
                units INTEGER NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL,settled_at REAL);
            CREATE INDEX IF NOT EXISTS idx_invocations_time ON invocations(created_at);
            CREATE TABLE IF NOT EXISTS worker_heartbeats(owner TEXT PRIMARY KEY,seen_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS assets(workspace_id TEXT NOT NULL REFERENCES workspaces(id),hash TEXT NOT NULL,
                kind TEXT NOT NULL,bytes INTEGER NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL,
                PRIMARY KEY(workspace_id,hash,kind));
            CREATE TABLE IF NOT EXISTS asset_owners(workspace_id TEXT NOT NULL,hash TEXT NOT NULL,kind TEXT NOT NULL,
                owner TEXT NOT NULL,PRIMARY KEY(workspace_id,hash,kind,owner),
                FOREIGN KEY(workspace_id,hash,kind) REFERENCES assets(workspace_id,hash,kind));
            INSERT OR IGNORE INTO schema_migrations VALUES(2,strftime('%s','now'));
            COMMIT;
            ''')

    @contextmanager
    def connect(self,*,write=False):
        db=sqlite3.connect(self.path,timeout=15,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        try:
            if write:db.execute('BEGIN IMMEDIATE')
            yield db
            if write:db.commit()
        except BaseException:
            if write:db.rollback()
            raise
        finally:db.close()

    def _write(self,db,workspace,scope,expected):
        from core.classroom import validate_workspace
        clean=validate_workspace(workspace)
        row=db.execute('SELECT id,version FROM workspaces WHERE scope=?',(scope,)).fetchone()
        if row and (row['id']!=clean['id'] or row['version']!=expected):
            raise ConflictError('记录已由另一窗口更新，请刷新后继续。')
        if not row and expected!=0:raise ConflictError('未找到对应存储版本。')
        clean['storage_version']=expected+1
        db.execute('INSERT INTO workspaces VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload,updated_at=excluded.updated_at',
                   (clean['id'],scope,expected+1,encode(clean),self.clock()))
        db.execute('DELETE FROM record_index WHERE workspace_id=?',(clean['id'],))
        for collection,items in clean.items():
            if not isinstance(items,list):continue
            for record in items:
                if not isinstance(record,dict) or not record.get('id'):continue
                db.execute('INSERT INTO record_index VALUES(?,?,?,?,?,?,?)',
                    (clean['id'],collection,record['id'],record.get('student_id'),record.get('batch_id'),record.get('submission_id'),encode(record)))
        return clean

    def save(self,w,scope,*,expected=None):
        with self.connect(write=True) as db:
            clean=self._write(db,w,str(scope),w['storage_version'] if expected is None else expected)
        w['storage_version']=clean['storage_version']
        return clean

    def load(self,*,scope=None,workspace_id=None):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM workspaces WHERE '+('scope=?' if scope is not None else 'id=?'),
                           (str(scope) if scope is not None else workspace_id,)).fetchone()
        if row is None:return None
        from core.classroom import validate_workspace
        return validate_workspace(json.loads(row['payload']))

    def mutate(self,workspace_id,operation):
        with self.connect(write=True) as db:
            row=db.execute('SELECT * FROM workspaces WHERE id=?',(workspace_id,)).fetchone()
            if row is None:raise ValueError('工作区不存在。')
            w=json.loads(row['payload'])
            result=operation(w)
            clean=w if encode(w)==row['payload'] else self._write(db,w,row['scope'],row['version'])
        return clean,result

    def import_json(self,path,*,scope=None):
        from core.classroom import validate_workspace
        raw=Path(path).read_bytes()
        fingerprint=hashlib.sha256(raw).hexdigest()
        rows=json.loads(raw)
        if not isinstance(rows,list) or len(rows)!=1:raise ValueError('请选择单个工作区备份。')
        w=validate_workspace(rows[0])
        with self.connect(write=True) as db:
            old=db.execute('SELECT workspace_id FROM imports WHERE source_hash=?',(fingerprint,)).fetchone()
            if old:return old['workspace_id']
            exists=db.execute('SELECT id FROM workspaces WHERE id=?',(w['id'],)).fetchone()
            if exists:raise ConflictError('该工作区已有数据，请先对比，不覆盖新的学习记录。')
            from core.identities import attach
            for batch in w['batches']:attach(batch,w['submissions'])
            w['storage_version']=0
            self._write(db,w,str(scope or Path(path).resolve()),0)
            db.execute('INSERT INTO imports VALUES(?,?,?)',(fingerprint,w['id'],self.clock()))
        return w['id']

    def query_records(self,workspace_id,collection,*,student_id=None,limit=100,offset=0):
        if not 1<=limit<=200 or offset<0:raise ValueError('分页参数无效。')
        sql='SELECT payload FROM record_index WHERE workspace_id=? AND collection=?'
        args=[workspace_id,collection]
        if student_id is not None:sql+=' AND student_id=?';args.append(student_id)
        sql+=' ORDER BY id LIMIT ? OFFSET ?';args.extend([limit,offset])
        with self.connect() as db:return [json.loads(r['payload']) for r in db.execute(sql,args)]

    def _enqueue(self,db,w,batch_id,sub,stage):
        from core import product as p
        payload={'fingerprint':sub['fingerprint'],'reference_revision':sub.get('reference_revision'),
                 'grading_revision':sub.get('grading_revision'),
                 'engine_version':p.QUICK_VERSION if stage=='quick' else p.DEEP_VERSION}
        if stage=='deep':payload['quick_id']=(p.latest(sub,'quick_checks') or {}).get('id')
        key=p.digest([w['id'],batch_id,sub['id'],stage,payload])
        now=self.clock();job_id=str(uuid4())
        db.execute('INSERT OR IGNORE INTO jobs(id,workspace_id,batch_id,submission_id,stage,input_key,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (job_id,w['id'],batch_id,sub['id'],stage,key,encode(payload),'queued',now,now))
        return db.execute('SELECT id FROM jobs WHERE input_key=?',(key,)).fetchone()['id']

    def enqueue_batch(self,workspace_id,batch_id,*,retry_failed=False):
        from core import product as p
        with self.connect(write=True) as db:
            saved=db.execute('SELECT payload FROM workspaces WHERE id=?',(workspace_id,)).fetchone()
            if saved is None:raise ValueError('请先保存工作区。')
            w=json.loads(saved['payload']);batch=next(b for b in w['batches'] if b['id']==batch_id)
            count=0
            for sub in w['submissions']:
                if sub['id'] not in batch['submission_ids'] or p.effective(w,sub)['confirmed']:continue
                quick=p.latest(sub,'quick_checks')
                stage='quick'
                if quick and quick.get('fingerprint')==sub['fingerprint']:
                    if not p.needs_deep(sub,quick):continue
                    stage='deep'
                    analysis=p.current_deep(sub)
                    if analysis and analysis.get('quick_id')==quick['id']:continue
                job_id=self._enqueue(db,w,batch_id,sub,stage)
                if retry_failed:
                    db.execute("UPDATE jobs SET status='queued',attempts=0,error=NULL,next_retry_at=0,updated_at=? WHERE id=? AND status IN ('failed','blocked','cancelled')",(self.clock(),job_id))
                count+=1
        return count

    def claim(self,owner,*,lease_seconds=600):
        now=self.clock()
        with self.connect(write=True) as db:
            db.execute('INSERT INTO worker_heartbeats VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET seen_at=excluded.seen_at',(owner,now))
            row=db.execute("SELECT * FROM jobs WHERE ((status IN ('queued','retry_wait') AND next_retry_at<=?) OR (status='running' AND lease_until<=?)) ORDER BY updated_at,created_at LIMIT 1",(now,now)).fetchone()
            if row is None:return None
            if row['status']=='running':
                db.execute("UPDATE invocations SET status='unknown_after_restart',settled_at=? WHERE job_id=? AND status='reserved'",(now,row['id']))
            db.execute("UPDATE jobs SET status='running',lease_owner=?,lease_until=?,fence=fence+1,attempts=attempts+1,updated_at=? WHERE id=?",
                       (owner,now+lease_seconds,now, row['id']))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone())

    def _active(self,db,job):
        return db.execute("SELECT * FROM jobs WHERE id=? AND status='running' AND fence=? AND lease_owner=? AND lease_until>?",
                          (job['id'],job['fence'],job['lease_owner'],self.clock())).fetchone()

    def renew(self,job,*,lease_seconds=600):
        with self.connect(write=True) as db:
            if not self._active(db,job):return False
            db.execute('UPDATE jobs SET lease_until=?,updated_at=? WHERE id=?',
                       (self.clock()+lease_seconds,self.clock(),job['id']))
            db.execute('INSERT INTO worker_heartbeats VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET seen_at=excluded.seen_at',
                       (job['lease_owner'],self.clock()))
        return True

    def finish(self,job,record):
        """Commit result, derived state, next job and fencing check atomically."""
        from core import product as p
        with self.connect(write=True) as db:
            if not self._active(db,job):return False
            saved=db.execute('SELECT * FROM workspaces WHERE id=?',(job['workspace_id'],)).fetchone()
            w=json.loads(saved['payload'])
            sub=next(s for s in w['submissions'] if s['id']==job['submission_id'])
            payload=json.loads(job['payload'])
            valid=(sub['fingerprint']==payload['fingerprint'] and sub.get('reference_revision')==payload['reference_revision']
                   and sub.get('grading_revision')==payload.get('grading_revision')
                   and not p.effective(w,sub)['confirmed'])
            if job['stage']=='deep':valid=valid and (p.latest(sub,'quick_checks') or {}).get('id')==payload.get('quick_id')
            status='completed' if valid else 'stale'
            if valid:
                key='quick_checks' if job['stage']=='quick' else 'analyses'
                if not any(r['id']==record['id'] for r in sub.get(key,[])):sub.setdefault(key,[]).append(record)
                if job['stage']=='quick' and p.needs_deep(sub,record):self._enqueue(db,w,job['batch_id'],sub,'deep')
                p.sync_notebook(w,sub['id'])
                batch=next(b for b in w['batches'] if b['id']==job['batch_id'])
                batch['status']=p.batch_execution(w,batch['id'])['status']
                self._write(db,w,saved['scope'],saved['version'])
            db.execute('UPDATE jobs SET status=?,lease_until=0,updated_at=? WHERE id=?',(status,self.clock(),job['id']))
            db.execute('INSERT INTO job_events(job_id,status,occurred_at,message) VALUES(?,?,?,?)',
                       (job['id'],status,self.clock(),'结果已保存' if valid else '作答或教师结论已更新，未覆盖'))
        return valid

    def defer(self,job,*,reason,delay=None,terminal=False):
        with self.connect(write=True) as db:
            if not self._active(db,job):return False
            status='failed' if terminal else 'blocked' if delay is None else 'retry_wait'
            db.execute('UPDATE jobs SET status=?,error=?,next_retry_at=?,lease_until=0,updated_at=? WHERE id=?',
                       (status,str(reason)[:2000],self.clock()+max(1,delay or 0),self.clock(),job['id']))
            db.execute('INSERT INTO job_events(job_id,status,occurred_at,message) VALUES(?,?,?,?)',
                       (job['id'],status,self.clock(),str(reason)[:2000]))
        return True

    def cancel_batch(self,workspace_id,batch_id):
        with self.connect(write=True) as db:
            db.execute("UPDATE jobs SET status='cancelled',fence=fence+1,updated_at=? WHERE workspace_id=? AND batch_id=? AND status IN ('queued','retry_wait','blocked','running')",(self.clock(),workspace_id,batch_id))

    def jobs(self,workspace_id,batch_id):
        with self.connect() as db:
            rows=db.execute('SELECT id,submission_id,stage,status,attempts,next_retry_at,lease_until,error FROM jobs WHERE workspace_id=? AND batch_id=? ORDER BY created_at',(workspace_id,batch_id))
            return [dict(row) for row in rows]

    def worker_available(self):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM worker_heartbeats WHERE seen_at>? LIMIT 1',(self.clock()-660,)).fetchone() is not None

    def admit(self,job_id,units,*,minute=30,daily=300,daily_units=2000000,concurrent=2):
        from core.limits import UsageLimitError
        now=self.clock();day=int(now//86400)*86400
        with self.connect(write=True) as db:
            if concurrent<=0:raise UsageLimitError('后台调用额度已关闭。',reason='disabled')
            active=db.execute("SELECT COUNT(*) FROM invocations i JOIN jobs j ON i.job_id=j.id WHERE i.status='reserved' AND j.lease_until>?",(now,)).fetchone()[0]
            if active>=concurrent:raise UsageLimitError('后台处理繁忙，稍后自动继续。',reason='busy',retry_after=3)
            sums=db.execute('SELECT COUNT(*) AS n,COALESCE(SUM(units),0) AS units FROM invocations WHERE created_at>=?',(day,)).fetchone()
            if sums['n']>=daily or sums['units']+units>daily_units:
                raise UsageLimitError('今日后台处理额度已用完，进度已保存。',reason='daily')
            recent=db.execute('SELECT created_at FROM invocations WHERE created_at>? ORDER BY created_at',(now-60,)).fetchall()
            if minute<=0:raise UsageLimitError('后台调用额度已关闭。',reason='disabled')
            if len(recent)>=minute:
                raise UsageLimitError('后台正在等待短时额度恢复。',reason='minute',retry_after=max(1,recent[-minute]['created_at']+60-now))
            invocation=str(uuid4())
            db.execute('INSERT INTO invocations VALUES(?,?,?,?,?,NULL)',(invocation,job_id,units,'reserved',now))
        return invocation

    def settle(self,invocation,status):
        with self.connect(write=True) as db:
            db.execute('UPDATE invocations SET status=?,settled_at=? WHERE id=?',(status,self.clock(),invocation))

    def append_usage(self,workspace_id,events):
        if not events:return
        with self.connect(write=True) as db:
            row=db.execute('SELECT * FROM workspaces WHERE id=?',(workspace_id,)).fetchone()
            w=json.loads(row['payload']);known={event['id'] for event in w['usage']}
            incoming=[event for event in events if event['id'] not in known]
            if incoming:
                w['usage'].extend(incoming)
                self._write(db,w,row['scope'],row['version'])

    def backup(self,target):
        target=Path(target).resolve()
        if target==self.path:raise ValueError('备份不能覆盖当前数据库。')
        target.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as source:
            destination=sqlite3.connect(target)
            try:source.backup(destination)
            finally:destination.close()
        return target

    def stage_asset(self,workspace_id,ref,size,*,owner,kind='image',budget=512*1024*1024):
        with self.connect(write=True) as db:
            prior=db.execute('SELECT bytes FROM assets WHERE workspace_id=? AND hash=? AND kind=?',(workspace_id,ref,kind)).fetchone()
            if prior is None:
                total=db.execute('SELECT COALESCE(SUM(bytes),0) FROM assets WHERE workspace_id=?',(workspace_id,)).fetchone()[0]
                if total+size>budget:raise ValueError('课堂材料存储额度已满，请联系管理员归档。')
                db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',(workspace_id,ref,kind,size,'staged',self.clock()))
            elif prior['bytes']!=size:raise ValueError('材料校验不一致。')
            db.execute('INSERT OR IGNORE INTO asset_owners VALUES(?,?,?,?)',(workspace_id,ref,kind,owner))

    def ready_asset(self,workspace_id,ref,kind='image'):
        with self.connect(write=True) as db:
            db.execute("UPDATE assets SET status='ready' WHERE workspace_id=? AND hash=? AND kind=?",(workspace_id,ref,kind))

    def owns_asset(self,workspace_id,ref,owner):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM asset_owners o JOIN assets a USING(workspace_id,hash,kind) WHERE o.workspace_id=? AND o.hash=? AND o.owner=? AND a.status='ready'",(workspace_id,ref,owner)).fetchone() is not None
