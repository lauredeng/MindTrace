# MindTrace v0.2 实际验收报告

日期：2026-11-06（Asia/Shanghai）

## 结论

已在原 MVP v0.1 工程内升级，未重新创建项目。依赖安装完成，Streamlit 已实际启动于 http://127.0.0.1:8501 ，健康接口返回 HTTP 200 / ok。教师工作流与本地数学验证、复核、JSON 保存可实际运行。

**41 项自动测试通过；实际 Chrome 浏览器 8 个流程检查通过。未配置 DeepSeek Key，因此真实付费模型调用和手写 OCR 准确率尚未验证。**

## 已交付

- 教师批量分析为默认首页；深绿侧栏、浅色卡片、教学主视觉、分步导入、空状态、指标与结果筛选。
- CSV 先预览再显式提交，刷新不会重新分析或重复保存；必需字段、空值、大小、条数均有校验。
- SymPy 使用有界 AST 解析，替换输入 sympify；对零分母、超大幂、变量分母和执行型输入返回未验证。
- 数学证据逐份复核，教师结论和备注保存到批次；证据 JSON 可导出，历史批次可恢复。
- 原子 JSON 写入保留，追加与复核使用进程内锁；同批次重复保存去重，损坏 JSON 不覆盖。
- 学生错因证据、动态追问与自适应提示、独立变式训练和探索版学习画像；辅导与练习均可本地留档。
- 图片真实 API 请求链：图片内容校验 → base64 image_url → DeepSeek JSON 返回 → 逐行原文及不确定处 → 原图对照及可编辑条目 → 教师勾选确认 → 数学分析。
- 图片无预设转写、无伪造置信度、无接口失败时的演示回退。JSON 保存原始转写、图片指纹、教师更正条目与确认时间。
- 本地 .env 模板、启动脚本、真实 API 检查脚本、说明文档与截图已补齐。

## 实际测试结果

| 检查 | 真实结果 |
| --- | --- |
| 自动回归 | 41 passed in 9.28s |
| 依赖检查 | No broken requirements found |
| Python 编译检查 | app.py、core、scripts 均通过 |
| Streamlit 健康检查 | HTTP 200，正文 ok |
| Chrome 桌面首页 | 通过 |
| Chrome 真实样例批量分析 | 通过 |
| Chrome 教师复核保存 | 通过 |
| Chrome 无 Key 学生诊断 | 通过，运行本地证据，不生成 AI 回答 |
| Chrome 变式题生成 | 通过 |
| Chrome 学习画像 / 历史记录 | 通过 |
| Chrome 390 px 手机首次打开 | 通过，侧栏收起，无页面横向溢出 |
| 浏览器未捕获异常 | 0 |
| DeepSeek 实际连接检查脚本 | SKIPPED：未配置 Key，未发起调用 |
| 真实手写 OCR 准确率 | 未测试，无可报告数值 |

12 条人工样例的本机实时结果：**6 条正确、6 条不一致、0 条未验证**；不一致中 **5 条符合遗漏内层导数模式，1 条仅能确定结果不一致**。这些是构造样例结果，不能视为真实班级效果。

测试证据：
- [pytest 结果](artifacts/pytest-results.xml)
- [Chrome 结果](artifacts/browser-report.json)
- [实际安装版本](artifacts/installed-versions.txt)
- [桌面首页](artifacts/home-desktop.png)
- [分析结果](artifacts/teacher-results.png)
- [复核页面](artifacts/evidence-review.png)
- [手机页面](artifacts/home-mobile.png)

自动测试使用临时数据；Chrome 验收会保存明确标记为人工样例的批次。样例默认不进入认知画像。API 协议测试采用 httpx 隔离传输，OCR 确认测试采用显式测试草稿，**二者都不是实际识别结果或实测模型效果**。

本机初次安装遇到 Python 应用执行别名不可用、venv ensurepip 失败及受限临时目录问题，已经使用实际 Python 3.14.6 安装路径补齐独立虚拟环境和 pip，并在本机环境完成所有测试。最终启动脚本直接使用项目 .venv，不依赖 python 别名。

新版 Streamlit 的 use_container_width 弃用提示已通过 width='stretch' 修正；早期提示仍保留在历史启动日志中。

## DeepSeek 接口核对

对照官方文档：
- [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [当前模型示例](https://api-docs.deepseek.com/quick_start/pricing)
- [图片输入](https://api-docs.deepseek.com/guides/vision/)
- [JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)

默认模型更新为文档当前示例 deepseek-flash。SDK 实际序列化后的 /chat/completions 路径、模型字段、messages，以及 image_url base64 图片块已通过协议检查。空内容、截断输出、401、402、429 和服务端错误均不会被当成成功，也不会直接暴露服务端原始错误正文。

实际账户权限、网络、费用和模型识别能力需要 Key 后实测，不能由协议测试代替。

## 仍有的限制

1. 没有真实 Key，本轮未验证 DeepSeek 实际返回、延迟、费用、手写识别准确率和动态追问质量。
2. 独立数学验证仅覆盖有界多项式求导，不覆盖三角函数、方程、不等式、跨页关联和完整手写推导。识别出文字不意味着该题已验证。
3. 认知画像是答题与对话证据汇集，不是经过教学实验验证的稳定能力模型；不生成未经支持的掌握度分数。
4. 图片只在当前会话保留；JSON 中的图像指纹不能还原原图，跨次复核需自行保留匿名原图。
5. 本地单用户、单进程原型，没有账号、班级权限、跨进程事务和数据保留策略。

## 推荐的下一阶段顺序

1. 在本目录 .env 的 DEEPSEEK_API_KEY= 后填入密钥，刷新后点击左侧“检查 DeepSeek 连接”；不要把密钥发送到聊天。
2. 用授权匿名手写图片进行真实小样本验收，人工标注原文，统计漏题、公式错误、更正耗时、延迟和成本；先校准识别，再扩大批量。
3. 加入多页作业关联、题型分流与逐步推导证据；进一步建立有独立新题支持的学习状态转移。
4. 面向多人服务前加入身份认证、班级隔离、数据库事务和备份机制。



## 网页会话配置补充验收（2026-11-06）

访问者可在左侧“连接与配置”填写自己本次会话的 DeepSeek API Key，并点击按钮清除。显式会话密钥只逐次传入 API，固定发往官方接口，不写入 .env / os.environ / 业务 JSON / 导出包。
共享模式 MINDTRACE_SHARED_MODE=1 禁止回退使用所有者的密钥，业务数据在各自 Streamlit 会话中隔离，不读取或写入共同的历史文件。个人工作区的 JSON 持久化功能保留。
最终 49 项隔离测试通过（7.83 秒），包括密码输入遮挡、清除、保存结果不含 Key、两个访客隔离、共享模式禁止读取服务器凭据与记录、请求鉴权分别传递给正确用户。未使用真实密钥，未调用真实 API，未截图配置页面。
结果文件：artifacts/pytest-visitor-results.xml。
当前仍未部署公网 URL；本机地址不是可发给他人使用的共享链接。正式部署须使用 HTTPS 与共享模式。
