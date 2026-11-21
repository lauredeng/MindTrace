"""Authoritative student submission command shared by local and HTTP modes."""
from core import collaboration as collab,classroom as c,storage,learning_records as learning
from core.background import configured_repository


def submit(code,data):
    access=collab.resolve(code)
    if access['role']!='student':raise ValueError('请使用学生学习码提交作答。')
    path=collab._folder(access['class_id'])/'workspace.json'
    def operation(w):
        sub=learning.owned_submission(w,data['submission_id'],access['student_id'])
        if (sub['fingerprint']!=data['expected_fingerprint'] or
            sub.get('reference_revision')!=data.get('expected_reference_revision') or
            sub.get('grading_revision')!=data.get('expected_grading_revision')):
            raise ValueError('题目或批改依据已更新，请刷新后再提交。')
        repo=configured_repository()
        refs=data.get('attachment_refs',[])
        if repo and any(not repo.owns_asset(w['id'],ref,access['student_id']) for ref in refs):
            raise ValueError('附件不属于当前学生。')
        if not repo and refs:
            raise ValueError('请先启用持久材料存储，再提交课堂订正附件。文字订正仍可使用。')
        attempt=learning.submit_correction(w,sub['id'],access['student_id'],data['steps'],data['answer'],
            command_id=data['command_id'],independent=data.get('independent',True),hint_used=data.get('hint_used',False),
            answer_revealed=data.get('answer_revealed',False),origin=data.get('origin','correction'),
            parent_id=data.get('parent_id'),attachment_refs=refs)
        # Confirmed objective references are deterministic server-side evidence.
        # Proofs, missing references and undecidable expressions stay for review.
        if learning.latest_assessment(w,attempt) is None:learning.compare_correction(w,attempt['id'])
        return attempt
    repository=configured_repository()
    if repository:
        w=c.load(path)
        _,result=repository.mutate(w['id'],operation)
        return result
    with storage.LOCK:
        w=c.load(path);result=operation(w);c.save(w,path)
        return result
