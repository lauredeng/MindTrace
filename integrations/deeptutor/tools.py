"""Local business adapters hosted by the official registry/loader, not an Agent loop."""
import asyncio
import json
from deeptutor.core.tool_protocol import BaseTool,ToolDefinition,ToolParameter,ToolResult,ToolPromptHints
from pathlib import Path
import os


class MathTool(BaseTool):
    deferred=True
    def get_prompt_hints(self,language='en'):
        return ToolPromptHints(short_description=self.get_definition().description,
            guideline='面向学生用数学语言解释结果和适用条件，不堆砌工具名、状态码或实现术语。computed表示计算完成；未给expected时不需要判正误，不能称作证据不足。不支持某项核验仍可继续合理讲解，不能因此判错。')
    def get_definition(self):
        return ToolDefinition(name='mindtrace_math',
            description='使用官方SymPy确定性核验高中数学模型。支持三角/对数/指数表达式、求导、方程、不等式、方程组、数列求和、向量、距离和集合。必须说明建模条件；不支持或超时不等于学生做错。',
            parameters=[ToolParameter(name='request_json',type='string',description=
                'JSON对象，operation为evaluate/derivative/equation/inequality/system/sum/dot/cross/norm/distance/set。'
                '表达式用x,y,z,a,b,t,n,k及sin,cos,exp,log,sqrt,binomial,factorial。'
                '求导示例 {"operation":"derivative","expression":"log(x)-a*x","variable":"x"}。'
                '其他字段domain/equations/variables/lower/upper/left/right/expected，按任务传入。')])
    async def execute(self,**kwargs):
        from core.math_kernel import check
        try:
            raw=kwargs.get('request_json','')
            if not isinstance(raw,str) or len(raw)>8000:raise ValueError()
            request=json.loads(raw)
            result=await asyncio.to_thread(check,request)
            if result.get('status')=='computed' and 'expected' not in request:
                result.pop('verdict',None)
                result['interpretation']='计算已完成；未提供待比较的答案，不适用正误判定。'
            result['scope']='仅核验给定数学模型；不证明自然语言建模、几何图形关系或完整证明正确。'
            return ToolResult(content=json.dumps(result,ensure_ascii=False),success=True)
        except (ValueError,TypeError):return ToolResult(content='数学请求格式无效；未据此判断作答正误。',success=False)

class EvidenceTool(BaseTool):
    deferred=True
    def get_definition(self):
        return ToolDefinition(name='mindtrace_learning_evidence',
            description='读取当前学生的最新学习证据画像。数据来自本人原答、教师确认、订正和独立验证，不是推测的掌握概率；按证据来源区分辅导后完成与独立完成。')
    async def execute(self,**kwargs):
        from deeptutor.multi_user.context import get_current_user
        from core.tutor_learning import workspace
        from core.learning_records import profile
        try:
            binding=bridge_store().for_user(get_current_user().id)
            data=profile(workspace(binding),binding['student_id'])
            # Bound prompt cost; detailed evidence remains in the classroom.
            data['points']=data['points'][:12]
            for point in data['points']:point['evidence']=point['evidence'][-6:]
            data.pop('valid_events',None)
            return ToolResult(content=json.dumps(data,ensure_ascii=False),success=True)
        except ValueError:return ToolResult(content='当前学生证据不可用，不推测学习画像。',success=False)



def bridge_store():
    from core.tutor_bridge import BridgeStore
    return BridgeStore(Path(os.environ['DEEPTUTOR_HOME'])/'mindtrace-bridge.sqlite3')


class SourceTool(BaseTool):
    deferred=True
    def get_definition(self):
        return ToolDefinition(name='mindtrace_source',description='读取当前学生本人的原题、教师最新反馈与订正状态。课堂材料更新后必须以此工具的当前结果为准；不访问其他学生。',
            parameters=[ToolParameter(name='submission_id',type='string',description='已知的MindTrace作答ID',required=True)])
    async def execute(self,**kwargs):
        from deeptutor.multi_user.context import get_current_user
        from core.tutor_bridge import source
        try:
            bridge=bridge_store();principal=bridge.for_user(get_current_user().id)
            record=source(principal,str(kwargs.get('submission_id','')))
            bridge.mark_assisted(principal['id'],record['submission_id'])
            return ToolResult(content=json.dumps(record,ensure_ascii=False),success=True)
        except (ValueError,StopIteration):
            return ToolResult(content='题目不存在或不属于当前学生。',success=False)
