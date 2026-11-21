# 官方 DeepTutor 接入记录

## 实施范围与版本

本开发版采用路线 A：保留 MindTrace 教师端、课堂数据、错题本、订正与 Py-FSRS；学生教学改为调用官方 DeepTutor 服务与官方 React 教学界面。未重写官方教学循环。研究源码位于应用目录之外的 `D:/Agent/_education_source_research/DeepTutor`，固定 commit 为 `341af371bf8143b2da3569084edf8e6cb46d7404`，发行版本标识为 1.7.4，许可证 Apache-2.0。Python 运行环境与原教师端隔离，依赖快照在 `integrations/deeptutor/requirements.lock.txt`。

## 直接复用与连接方式

| 能力 | 官方源码与实际接入 |
| --- | --- |
| 教学执行、工具调用、恢复 | `deeptutor/app/service.py`、`api/routers/unified_ws.py`；使用官方 WebSocket、持久 turn 和事件流 |
| 学习状态与路径 | `deeptutor/learning/service.py`、`learning/storage.py`；每个学生、原题及依据版本建立原生 topic、module、knowledge points、session |
| 原题与教师反馈 | 官方 `DeepTutorApp.add_record()` 创建原生 notebook record；学习 topic 引用该 record；模型可通过官方 `list_favorites` 读取 |
| 学习记忆 | 官方 `services/memory/store.py`、`trace.py`；保留官方记忆读取、写入和追溯工具；来源关联写入真实 trace |
| 身份与模型授权 | 官方用户作用域、服务端模型目录、学生 grant；学生不能修改管理配置或取得模型密钥 |
| 界面 | 官方 MasteryStudy、ChatWorkspace 与对话组件；增加 `/mindtrace` 入口和原题/订正侧栏 |
| 错题与教师回传 | `core/tutor_bridge.py` 和 `integrations/deeptutor/server.py` 连接现有 `learning_records`、课堂 SQLite；不建立第二套教师成绩 |
| 间隔复习 | 原 `core/review_scheduler.py` 继续直接调用官方 `fsrs==6.3.3` 的 Scheduler/Card/ReviewLog；未改用 DeepTutor 内部的其他调度策略 |

`MindTraceSourceTool` 通过官方工具协议注册为只读、延迟加载工具，读取本人最新资料。注册不等于模型每轮必定调用；本次真实教学实际使用的是官方 `list_favorites`，不把未观测的工具选择描述成已验证。

## 本地模型与运行

已核对原项目与本开发版被忽略的 `.env`：原有 DeepSeek 配置可用。教学服务使用独立 `MINDTRACE_TUTOR_API_KEY/BASE_URL/MODEL`，当前沿用原 DeepSeek 配置；Qwen `qwen3.8-flash` 继续用于已有识别流程。真实值不写入本文、源码或源码导出。教学模型密钥在服务端官方模型目录中保存，部署时仍须保护运行目录及备份。

首次在新设备安装：先按 README 建立原产品环境，再执行 `powershell -ExecutionPolicy Bypass -File scripts/install_deeptutor.ps1`。安装脚本拉取固定版本到独立研究目录，使用独立虚拟环境，安装官方前端；已有不同 commit 的目录会拒绝覆盖。

本机依赖已安装。`start.bat` 默认连接教学服务，原产品入口为 `http://127.0.0.1:8501`，官方教学界面为 `http://127.0.0.1:8592/mindtrace`，服务为 `http://127.0.0.1:8591`。学生从已连接课堂的原题进入；也可在学习空间输入自己的学生课堂学习码。课堂授权一次性交换后使用 HttpOnly Cookie，课堂码不进入 URL 或浏览器持久存储。打开原题不调用模型；发送问题才产生教学请求。

`start_development.ps1 -LegacyTutor` 可临时回到旧学生辅导入口；教师业务代码和历史数据不因此迁移或删除。此开关用于回滚，不代表两套教学循环同时运行。

## 权限、版本与持久化

- 课堂业务数据仍在 `.local_data/development`；官方会话、学习状态、记忆及桥接映射在 `.local_data/deeptutor`。两者均需纳入部署备份；原课堂备份工具不会自动覆盖另一个服务的全部文件。
- 一次性入口 90 秒有效，仅保存摘要；浏览器授权 24 小时，后续 HTTP/WS 命令重新校验课堂授权。撤销学生入口后旧授权失效。
- 只传本人单题文本、作答和反馈，不传可能包含他人材料的整卷图片/转写。跨学生题目访问拒绝。
- 教师修改材料或评分依据后，旧教学会话不能继续启动新轮次；重新从课堂打开会建立新版本。旧记录作为历史保存，仍需后续加强原生记忆中旧结论的失效标记与跨版本检索约束。
- 订正复用现有幂等命令、材料版本检查和课堂持久化，保留原始答案。得到提示后的作答不能当作独立掌握证据。
- 学生禁用任意系统执行、MCP 和 CLI 接入；不会为了复用官方 Agent 而开放主机执行权限。

## 已执行验证

1. 匿名构造课堂中的真实浏览器流程：原生教学界面打开、读取教师确认反馈、提交订正、教师数据中读取回传、另一学生访问拒绝。`scripts/verify_deeptutor_ui.py` 不调用模型；不会将构造数据当作真实准确率样本。
2. 显式运行 `scripts/verify_deeptutor_live.py --live`：使用现有 DeepSeek，发送一次学生问题；原生 Agent 实际调用 notebook 工具，正确解释 `f(x)=ln(x)-a*x, a>0` 的漏项、驻点、单调性和最大值 `-ln(a)-1`。服务端事件在约 18.06 秒完成，4 轮、3 次工具操作。原生用量记录含 5 次内部模型请求（其中 1 次失败、4 次完成），总用量记录约 73,412 token，含缓存及估算部分；不能将其描述为仅一次 API 调用或精确账单。没有自动重跑付费验证。
3. 官方记忆来源引用、文档、存储和教学有界记忆测试：76 项通过。官方前端类型检查通过。
4. 桥接测试覆盖一次性票据、凭据摘要存储、本人题目归属、撤销、来源版本与会话持久映射。项目完整离线回归 362 项通过，89.40 秒；仅有一项 Starlette/httpx 未来兼容性弃用提醒。
5. 官方推理档位处理测试 19 项通过，额外执行 null 与空数组输出一致的回归检查通过。官方前端最终类型检查通过；教学页面与回传浏览器流程 5 项通过、无浏览器运行异常，不调用模型。

## 必须区分的边界

当前实现证明官方教学运行时已经接通课堂原题及订正链路，不能据单题样例声称所有高中题型准确、全面达到 DeepTutor 所有能力或已完成生产验收。原生 L2/L3 记忆整理能力可用，但尚未为课堂建立自动后台整理计划；没有声称已实现自动长期画像。现有证据画像与官方学习状态保持不同语义，未把“看过讲解”变成教师确认成绩。

官方自身的练习/复习机制与产品 Py-FSRS 是不同机制。初次接入时学习空间仅显示FSRS到期数量；后续已在同一学习空间补齐独立作答、教师核验刷新与官方FSRS调度，详见 `09_student_learning_upgrade.md`。官方上传入口尚未整体接入 Qwen OCR，已有图片/PDF识别仍走原产品入口。

前端覆盖层另修复了固定版本普通学生模型选项中 `supported_reasoning_efforts=null` 导致页面崩溃的问题，仅为数组空值保护，未替换教学算法。可复现覆盖操作在 `scripts/prepare_deeptutor_web.py`，保留官方版权及许可证。

本次修改在本地开发版；未推送 GitHub，也未更新公开 Streamlit 链接。部署此架构需要独立的教学后端与 React 前端服务，不能仅依靠 Streamlit Cloud 的一次源码更新完成。
