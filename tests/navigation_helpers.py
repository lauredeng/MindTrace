"""Internal routes exercise retained compatibility code without public legacy menus."""
def route(at,page):
    student=('AI解题与辅导','AI 解题与辅导','我的错题本','错因分析','学生辅导体验','学习认知画像','专项练习','学习档案','我的学习','拍题辅导')
    role='产品首页' if page=='产品首页' else '学生学习空间' if page in student else '教师工作空间'
    at.session_state['experience_destination']=(role,page)
    at.run()
    assert not at.exception

def main_labels(at):
    return [b.label for b in at.sidebar.button if b.key and b.key.startswith('nav_')]
