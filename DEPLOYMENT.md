> V1.2更新：默认界面已收敛为教师批改/学情/历史与学生解题/错题本/错因。新增批次、错题本、来源与修订列表仍保存在原classroom_v1.json；旧schema补空，不自动迁移v0.2独立文件。具体已验收范围见 V12_ACCEPTANCE.md。

# MindTrace 管理员配置与部署
当前版本含跨浏览器课堂协作，2026-11-07。运行方式与验证清单见 README.md、V1_ACCEPTANCE.md。

## 课堂协作（本轮已实现）
教师从“课堂连接”创建独立课堂，私下发放绑定单个学生的学习码；凭教师恢复码可在另一浏览器恢复教师工作区。角色由服务端校验，不使用匿名编号充当密码。详见 CROSS_BROWSER_ACCEPTANCE.md。
MINDTRACE_CLASSROOM_DIR 指向可写持久目录；默认 MINDTRACE_DATA_DIR/classrooms。访问码摘要与学习JSON分开保存，截图/日志/业务导出不得包含访问码原文。学习码是持有者凭证，可重新生成撤销旧码，不是实名账号。
此实现限单实例单进程。并发独立修改采用三方合并，同字段冲突拒绝覆盖；页面会提示更新，由用户刷新读取，不自动中断模型调用。多实例需要数据库或跨进程事务，尚未实现。

## 服务端配置
普通教师、学生、评委使用部署后网页，不需要自行申请 Key。
读取顺序：非空进程环境变量 → Streamlit Secrets → 仅 development 模式的项目 .env。

本机已配置的实际凭据由应用运行时读取。不要发到聊天、命令参数、Git或源码包。托管时由管理员在平台私有环境变量中填写 DEEPSEEK_API_KEY，或使用平台 Streamlit Secrets；模板在 .streamlit/secrets.example.toml。本机使用 Secrets 可自行新建 .streamlit/secrets.toml，它是明文且已被忽略。

默认 MINDTRACE_ENV=production；start.bat 显式设为 development，以保留本机 .env 后备。公网请使用 production、开发者开关0。MINDTRACE_ENABLE_DEVELOPER_MODE=1 才显示折叠开发者设置，用户还须主动勾选才临时覆盖服务端Key；这不是身份认证。

文本与图片模型分别由 DEEPSEEK_MODEL / DEEPSEEK_VISION_MODEL 配置，当前真实响应标识 deepseek-flash。不可用模型或视觉能力会明确报错，不回退预设识别。供应商模型可能更新，没有锁定不可变快照。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| DEEPSEEK_TIMEOUT_SECONDS | 90 | 单次超时，允许5–180秒 |
| DEEPSEEK_MAX_RETRIES | 0 | 网络/限流/5xx重试，允许0–2，每次独立准入 |
| DEEPSEEK_INPUT_PRICE_PER_MILLION | 空 | 适用输入单价，留空则不估费用 |
| DEEPSEEK_OUTPUT_PRICE_PER_MILLION | 空 | 适用输出单价，留空则不估费用 |
| DEEPSEEK_PRICE_CURRENCY | CNY | 估算币种标签 |

tokens来自响应；费用按管理员单价粗估，未计算缓存折扣，不是账单或资金上限。

## 已执行的额度与输入限制
| 配置 | 默认值 | 范围 |
| --- | --- | --- |
| MINDTRACE_SESSION_MINUTE | 6 | 每会话每滚动60秒 |
| MINDTRACE_SESSION_DAY | 50 | 每会话每日 |
| MINDTRACE_GLOBAL_MINUTE | 30 | 当前进程每滚动60秒 |
| MINDTRACE_GLOBAL_DAY | 300 | 当前进程每日 |
| MINDTRACE_DAILY_UNITS | 2000000 | 当前进程每日保守预算 |
| MINDTRACE_CONCURRENT | 2 | 当前进程同时执行请求数 |

每日按UTC重置。失败与重试各自计次；被限流的请求不发出。预算单位为 max_tokens + 输入UTF-8字节 + 每图预留16384，是准入估计，不是实际 tokens 或人民币。
限制器在进程内共享，刷新可更换会话，重启会清零，多副本不共享。公开使用还需供应商开支控制、入口限流和持久预算。

新工作区题目最多4000字、步骤最多30条且合计8000字、最终答案2000字；请求文本另有64000字节上限和输出上限。图片最多5张、每张8 MB，一次视觉请求一张，另核验实际格式/尺寸；识别后必须确认，不自动归属未知编号。所有导入仍受大小/记录数/字段校验，旧版格式保持原有限制。
辅导最多3次主动追问、20轮记录，服务额度仍可能更早触发。达到限制后仍可查看证据和复核；旧版局部数学功能可用。

## JSON 与会话
development 且非 shared 模式：新记录 .local_data/classroom_v1.json；匿名原图 classroom_images/哈希.image；旧 runs.json / student_sessions.json 保留。MINDTRACE_DATA_DIR 可改存储目录。
写入使用进程锁、临时文件原子替换、存储版本检查，陈旧会话不会覆盖更新文件；出现冲突请先下载备份再刷新。它不能代替跨进程事务与身份权限。

未连接协作课堂时，production 默认每个浏览器会话隔离且只在内存，刷新、断线、服务重启可能丢失。不要设为共享本机JSON后公开真实班级数据。编号切换仅供演示，不是登录。教师可下载工作区备份，目前没有新工作区全量恢复页面；跨浏览器已有单任务导出/导入和反馈导出/导入。
任务包裁去整页转写与原图；导入反馈不能证明提交者身份或独立完成。模型返回、教师备注和匿名作答仍属需要保管的教学数据。

后续部署增强（尚未实现）：
1. 单实例持久卷加Python自带SQLite，以事务存JSON业务对象并备份。
2. 在已实现的课堂码范围校验基础上补实际用户管理、凭证恢复及正式安全测试。
3. 无持久卷托管使用持久托管SQL；把JSON或SQLite放临时盘无法解决重启丢失。
4. 扩容时再持久化共享额度和入口限流，避免提前引入完整账号框架。

## 启动、分享与待验收
双击 start.bat 后 http://127.0.0.1:8501 仅本机可用。源码包也不是在线应用。异地访客需要正式托管的HTTPS域名；当前未发布公网地址。
隔离浏览器验收用8503端口和 artifacts 内测试工作区，不是用户正式数据。

本机已实际验证真实文本/视觉调用、JSON状态闭环与两轮浏览器页面；真实手写质量仍未知。正式部署后必须检查私有配置注入、出站接口、HTTPS/WebSocket、额度、实际延迟费用、持久盘、重启与备份恢复、真实并发和访问权限。

## Streamlit Community Cloud 免费部署（参赛演示）
源码放 GitHub 私有仓库（`.gitignore` 已排除 `.env`、`.local_data/`、`artifacts/`、`exports/`、`.venv/`、`.streamlit/secrets.toml` 等本机数据与凭据）。仓库根目录需保留：`app.py`（入口）、`requirements.txt`、`packages.txt`（内容为 `poppler-utils`，云端用它安装 pdfinfo/pdftoppm）、`.streamlit/config.toml` 与匿名样例 `data/demo.csv`、`data/highschool_examples.json`。

部署时选 `main` 分支与 `app.py`。Advanced settings → Secrets 只填平台私有后台，例如 `.streamlit/secrets.example.toml` 的键：`DEEPSEEK_API_KEY`，其余 `DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`/`DEEPSEEK_VISION_MODEL` 与 `MINDTRACE_*` 用示例默认值即可（默认 `MINDTRACE_ENV=production`、开发者开关 0）。不要把 Key 写进仓库或聊天。

免费版限制：production 未连课堂时按浏览器会话内存存储，刷新/休眠/重启即丢，所以演示用匿名样例与当前会话流程；长期保存试卷与错题需另配持久卷，Community Cloud 免费层不提供。应用闲置约 12 小时后休眠，访客打开页面即唤醒；托管免费，DeepSeek 调用按账户计费。改代码推到同一分支即更新线上链接。


