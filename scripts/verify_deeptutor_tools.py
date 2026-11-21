"""Exercise official grant-filtered loading and dispatch; no model request."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_deeptutor  # Same explicit local runtime and data paths.
from scripts.prepare_tutor_fixture import prepare
from integrations.deeptutor.server import bridge
from integrations.deeptutor.runtime import user_scope,provision
from deeptutor.runtime.providers.view import build_tool_view
from deeptutor.runtime.providers.scope import ToolScope
from deeptutor.runtime.registry.tool_registry import get_tool_registry


async def main():
    fixture=prepare()
    principal,_=bridge.exchange(bridge.ticket(fixture['student_code']))
    principal=provision(bridge,principal)
    with user_scope(principal):
        view=await build_tool_view(base_registry=get_tool_registry(),
            scope=ToolScope(owner_id=principal['dt_user_id'],workspace_mcp=frozenset(),session_id='mindtrace-tools-contract'),language='zh')
        names={t.name for t in view.pool}
        expected={'mindtrace_source','mindtrace_math','mindtrace_learning_evidence'}
        assert expected.issubset(names),(names,expected)
        assert view.loader is not None
        schemas=[];view.attach(schemas)
        loaded=view.loader.load(sorted(expected))
        assert not loaded['unknown']
        cases=[({'operation':'derivative','expression':'log(x)-a*x','variable':'x'},'-a + 1/x'),
               ({'operation':'evaluate','expression':'sin(x)^2+cos(x)^2'},'1'),
               ({'operation':'evaluate','expression':'binomial(10,3)/2^10'},'15/128')]
        for request,answer in cases:
            result=await view.registry.execute('mindtrace_math',request_json=json.dumps(request))
            data=json.loads(result.content)
            assert result.success and data['status']=='computed' and data['result']==answer,data
        own=await view.registry.execute('mindtrace_source',submission_id=fixture['submission_id'])
        assert own.success and json.loads(own.content)['submission_id']==fixture['submission_id']
        peer=await view.registry.execute('mindtrace_source',submission_id=fixture['peer_submission_id'])
        assert not peer.success
        evidence=await view.registry.execute('mindtrace_learning_evidence')
        assert evidence.success and json.loads(evidence.content)['student_id']=='DEMO-001'
        invalid=await view.registry.execute('mindtrace_math',request_json=json.dumps({'operation':'evaluate','expression':"__import__('os')"}))
        assert not invalid.success or json.loads(invalid.content)['status']!='computed'
    print(json.dumps({'official_loader':True,'math_cases':len(cases),'peer_denied':True,'model_calls':0}))


if __name__=='__main__':asyncio.run(main())
