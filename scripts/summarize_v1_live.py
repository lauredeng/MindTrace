"""Generate a factual small-sample comparison from saved real calls."""
import json
from pathlib import Path
root=Path.cwd();out=root/'artifacts/v1-live'
def read(name):
    return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
math=read('math');extra=read('math-extra-10');base=read('baseline');vision=read('vision');learning=read('learning')
checks=math['checks']+extra['checks']
all_usage=[u for r in (math,extra,base,vision,learning) for u in r['usage']]
rows=['# V1 真实模型与同模型对照记录','',
'日期：2026-11-07。以下数值来自实际 DeepSeek 响应及保存的测试结果，不来自 Mock。题目是开发构造材料与可审查参考标注，尚无独立教师盲评标注集。',
'','## 覆盖测试','',
'| 指标 | 结果 |','| --- | --- |',
f"| 完成结构化分析 | {sum(c['status']=='completed' for c in checks)} / {len(checks)} |"]
for key,label in [('overall_match','整体状态与参考一致'),('first_error_match','首错位置与参考一致'),('final_answer_match','最终答案判断与参考一致')]:
    rows.append(f"| {label} | {sum(c.get('result',{}).get(key,False) for c in checks)} / {len(checks)} |")
rows+=['','覆盖十个高中模块及不同正确解法、最终正确但过程错误、连带错误、缺条件证明和跨题重复模式。14题样本简单且小，不能外推真实班级正确率。几何证明没有形式化验证。',
'','## 公平的小样本对照','',
'A与B均使用配置的同款模型、相同题目与原始步骤、同一份明确的结构化诊断说明；B额外加入可用的局部工具证据并经过字段/引用校验。没有向模型提供参考标注。',
'','| 题目 | A直接模型：状态/首错/答案 | B工作流：状态/首错/答案 |','| --- | --- | --- |']
by_id={c['name']:c for c in checks}
for a in base['checks']:
    b=by_id[a['name']]
    def bits(row):
        return ' / '.join('一致' if row.get('result',{}).get(k) else '不一致/未完成' for k in ('overall_match','first_error_match','final_answer_match'))
    rows.append('| '+a['name']+' | '+bits(a)+' | '+bits(b)+' |')
rows+=['','本次4对样本中，两者均与参考标注一致，**没有证明 MindTrace 的数学判断优于直接模型**。当前可确认增量是可选工具、原文引用校验、复核版本、任务与反馈链路。尚未进行真实教师操作用时和复核成本实验，不报告虚构效率提升。',
'','响应模型标识：'+', '.join(sorted({u['model'] for u in math['usage']+base['usage']}))+'。未锁定不可变模型快照；provider可能更新模型，因此不当作长期可复现的固定版本实验。',
'','## 真实图片输入','']
for c in vision['checks']:
    r=c['result']
    rows.append(f"- {c['name']}：真实视觉请求完成，提取 {r['records_count']} 题，测试编号完整恢复={r['all_ids_recovered']}。")
rows+=['','图片均由测试脚本排版生成，其中一张含长方体示意图。**不是学生手写照片**；没有测试手写字符准确率、拍照模糊、遮挡或真实归属准确率。自动恢复编号不等于所有数学字符均准确，界面仍要求人工校对。',
'','## 真实教学链路','',
'追问、基于新回答的提示、针对性变式和评分均调用真实接口。先只回放最终参考答案，模型指出缺少题目要求的解释；再回放完整参考过程后得到正确判断。两次都已标记看过答案，最终状态：'+learning.get('closed_loop_state','未完成')+'。',
'参考解回放只是接口和状态机检查，不是真实学生独立完成，更不是教学效果试验。局部工具不适用的题，AI生成练习与评分仍需教师复核。',
'','## 使用量（不是实际账单）','',
f"- 本轮记录的真实请求尝试：{len(all_usage)}；来源包含14道诊断、4次直接模型对照、2次视觉和5次辅导/训练/评分。",
f"- 响应报告的输入 tokens：{sum(u.get('prompt_tokens') or 0 for u in all_usage)}。",
f"- 响应报告的输出 tokens：{sum(u.get('completion_tokens') or 0 for u in all_usage)}。",
'- 未配置账户适用单价，因此不编造人民币成本；缓存折扣也未建模。管理员可配置单价作估算。',
'','原始证据位于 artifacts/v1-live/，不含凭据。源码包不携带该目录或任何学习记录。']
(root/'V1_COMPARISON.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
print('Factual comparison written. Recorded calls:',len(all_usage))

