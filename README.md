# MindTrace 循理 AI · 产品开发版

线上产品入口：[MindTrace 循理 AI](https://mindtrace-zoedeng.streamlit.app/)

原完整项目目录：`D:/Agent/mindtrace_mvp_v0.1(1)/mindtrace_mvp`。原文件及本地配置仍保留在该目录。本开发版已关联原GitHub仓库并保留提交历史，当前开发分支为 `work/phase-01`；尚未推送或更新线上。

面向高中数学的教师批改与学生学习产品。此目录从完整产品源码整理而来，目前已恢复必要核心测试和开发工具；不包含旧演示文稿、视频或真实运行数据。升级设计见 `docs/02_target_architecture.md`。

## 产品功能

- 教师端：作业图片/PDF导入、学生编号匹配、参考答案管理、批量批改、班级题目统计、原卷复核与历史记录。
- 学生端：文字、图片与PDF提问，分步辅导、持续追问、错题本、原题订正、FSRS复习与证据画像。
- 课堂联动：课堂连接、学生作答归属、教师批改结果与学生学习记录衔接。演示学号入口不提供真实身份认证。
- 持久后台：SQLite事务、独立批改worker、自动等待与恢复、教师反馈同步、材料隔离与可验证备份。

## 目录

| 文件或目录 | 用途 |
| --- | --- |
| `app.py` | Streamlit应用入口及工作区整合 |
| `core/` | 模型调用、识别、批改、参考答案、数学工具、课堂协作、存储和额度控制 |
| `api/` | 独立后端的课堂授权、学习命令与材料访问接口 |
| `ui/` | 教师端、学生端、首页、上传与结果等界面 |
| `ui/components/` | 题目热力图及错因图表组件 |
| `assets/style.css` | 产品样式 |
| `data/` | 产品仍会读取的匿名示例及CSV模板，不含个人学习记录 |
| `.streamlit/config.toml` | 页面、服务和上传配置 |
| `.streamlit/secrets.example.toml` | 服务端配置空模板 |
| `.env.example` | 本地开发环境变量空模板 |
| `requirements.txt` / `requirements.lock.txt` | 安装入口 / 已验证依赖快照 |
| `requirements.in` / `requirements-dev.txt` | 直接依赖范围 / 浏览器验收依赖 |
| `packages.txt` | Linux部署时的系统依赖 |
| `tests/` / `scripts/` | 离线核心回归、浏览器验收与安全源码导出 |
| `start.bat` | Windows本地启动入口 |

## 本地启动

学生教学现接入独立的官方 DeepTutor 运行时及界面，保留教师端与课堂错题、订正、Py-FSRS。新学习空间已提供错题、完整复习流程和学习证据；数学及课堂工具通过官方插件加载。新设备还需执行 `powershell -ExecutionPolicy Bypass -File scripts/install_deeptutor.ps1` 安装独立教学环境，再使用 `start.bat`。本机已安装；验证与当前边界见 `docs/08_deeptutor_integration.md`、`docs/09_student_learning_upgrade.md`。公开链接尚未更新。

在此目录打开终端，执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\start.bat
```

浏览器访问 `http://127.0.0.1:8501`。本机已建立此项目独立 `.venv`（Python 3.14.6）；新设备按上述步骤创建环境。当前依赖快照已在本机检查，GitHub Linux回归配置已添加，尚未在远程运行。

PDF解析依赖Poppler，需要保证 `pdfinfo`、`pdftoppm` 可通过PATH调用。`packages.txt` 中的 `poppler-utils` 用于Linux/Streamlit部署，Windows需另行安装并配置路径。

## 配置AI服务

本机开发版已沿用原项目的服务端模型配置；密钥文件被忽略且不进入源码导出。新设备使用AI识别、批改与辅导前，按以下任一方式配置：

- 本地：复制 `.env.example` 为 `.env`，填写自己的服务端配置，再通过 `start.bat` 启动；该入口启用development模式。
- Streamlit：在托管平台的私有Secrets中填写配置，参照 `.streamlit/secrets.example.toml`；默认production模式不读取项目 `.env`。
- 也可使用进程环境变量，优先级高于Streamlit Secrets。

模板保留当前代码使用的模型名称与接口地址。实际可用模型及其图像能力须以所用服务为准。没有密钥仍可打开界面，AI功能需要有效配置。

## 数据与部署

本地development模式默认将新数据保存至 `.local_data/`。可用 `MINDTRACE_DATA_DIR` 指定存储位置；课堂数据默认位于其下的 `classrooms/`，可通过 `MINDTRACE_CLASSROOM_DIR` 单独指定。

production未连接课堂时默认使用会话内存；课堂协作需要服务端存储。长期部署应配置持久化存储。当前JSON存储适用于单实例，不应直接视作支持多实例扩容的数据库方案。

不要提交 `.env`、`.streamlit/secrets.toml` 或真实学生资料。原项目的密钥、课堂访问码及历史记录没有迁入本目录。

当前分支 `work/phase-01` 关联 `https://github.com/lauredeng/MindTrace.git`，保留原提交历史。开发中的修改不会自动同步线上；验收后才提交/推送到Streamlit实际绑定分支。原目录仍保留。

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

测试使用真实安装的SDK/数学依赖和离线模型回复，禁止外部模型调用，不证明真实OCR准确率。浏览器验收安装 `requirements-dev.txt`，将正常应用运行在8561，独立 `tests/ui_fixture.py` 运行在8562，再执行 `scripts/verify_ui.py`。样例页面明确标注构造材料，不代表真实批改效果；它不是线上产品入口。

首批修改和验证范围见 `docs/03_phase01_acceptance.md`。`docs/00_audit_offline_checks.py` 为修改前的历史审计复现，含已修复问题的旧断言；正式回归请使用 `tests/`。

批改可靠性第一轮记录见 `docs/04_batch_reliability.md`；后续已加入独立持久后台、订正、画像与官方FSRS，见 `docs/05_platform_upgrade.md`。本机完整启动、独立后端与恢复步骤见 `docs/06_development_and_recovery.md`。新版能力需要相应启动配置，不会通过前端代码上传自动完成后端部署。

## 整理范围

保留全部运行模块，包括仍被引用的兼容模块。新版以小规模课堂为目标，保留工作区聚合兼容适配；不宣称已完成企业级全量关系化、多实例扩容或真实识别效果评测。

整理时排除的旧中间产物仍在原目录。现在已恢复Git历史、独立环境、必要核心测试和开发工具；缓存、原图及运行资料、截图和导出文件仍通过 `.gitignore` 排除。真实密钥和学生历史数据没有复制进来。
