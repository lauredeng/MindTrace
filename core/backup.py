"""Consistent DB backup plus hashed evidence; explicit restore into a new folder."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
from core.repository import Repository


def checksum(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def create(repository,data_root,target):
    root=Path(data_root).resolve();target=Path(target).resolve()
    if target.is_relative_to(root):raise ValueError('备份请放在运行数据目录之外。')
    target.mkdir(parents=True,exist_ok=False)
    manifest={'version':1,'status':'incomplete','source_root':str(root),'files':[]}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    database=repository.backup(target/'mindtrace.db')
    connection=sqlite3.connect(database)
    try:workspaces=connection.execute('SELECT scope,payload FROM workspaces').fetchall()
    finally:connection.close()
    for scope,payload in workspaces:
        workspace=json.loads(payload);location=Path(scope)
        directory=location.parent/('images' if location.name=='workspace.json' else 'classroom_images')
        images={s['image_ref'] for s in workspace['submissions'] if s.get('image_ref')}
        images.update(ref for a in workspace.get('correction_attempts',[]) for ref in a.get('attachment_refs',[]))
        originals=set()
        for batch in workspace['batches']:
            for material in batch.get('materials',[]):
                for page in material['pages']:
                    images.add(page['original_image']);originals.add(page['original_file'])
        for folder,refs in ((directory,images),(directory/'originals',originals)):
            for ref in refs:
                file=folder/(ref+'.image')
                if not file.resolve().is_relative_to(root) or not file.is_file() or checksum(file)!=ref:
                    raise ValueError('数据库引用的原始材料不完整，未生成完整备份。')
    manifest['files'].append({'path':'mindtrace.db','sha256':checksum(database)})
    candidates=list(root.glob('classrooms/*/access.json'))+list(root.glob('classrooms/*/images/**/*.image'))+list(root.glob('classroom_images/**/*.image'))
    for source in candidates:
        if source.is_symlink() or not source.resolve().is_relative_to(root):raise ValueError('备份发现目录外引用，未继续。')
        if source.suffix=='.image' and (not re.fullmatch('[a-f0-9]{64}',source.stem) or checksum(source)!=source.stem):
            raise ValueError('原始材料校验失败，未生成完整备份。')
        relative=source.relative_to(root)
        dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        manifest['files'].append({'path':relative.as_posix(),'sha256':checksum(dest)})
    manifest['status']='complete'
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def restore(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=1 or manifest.get('status')!='complete':raise ValueError('不是完整可恢复的备份。')
    for entry in manifest['files']:
        relative=Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('备份文件路径无效。')
        file=source/entry['path']
        if not file.resolve().is_relative_to(source) or file.is_symlink() or checksum(file)!=entry['sha256']:
            raise ValueError('备份内容校验失败。')
    target.mkdir(parents=True,exist_ok=False)
    for entry in manifest['files']:
        dest=target/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/entry['path'],dest)
    repository=Repository(target/'mindtrace.db')
    oldroot=Path(manifest['source_root'])
    with repository.connect(write=True) as db:
        for row in db.execute('SELECT id,scope FROM workspaces').fetchall():
            try:relative=Path(row['scope']).relative_to(oldroot)
            except ValueError:continue
            db.execute('UPDATE workspaces SET scope=? WHERE id=?',(str(target/relative),row['id']))
    return repository
