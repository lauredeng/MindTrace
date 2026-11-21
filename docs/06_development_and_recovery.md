# 06｜开发版运行、联调与数据恢复

## 本机完整模式

在产品开发版根目录打开PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File scripts/start_development.ps1
```

启动脚本使用独立的.local_data/development目录、SQLite和后台worker；不迁入原目录的Key或学生资料。默认前端端口8561，可传-Port更换。Key与提供商配置仍由管理员通过环境配置；缺Key时保留页面、本地核验及记录，不会伪造AI结果。

worker以隐藏后台进程启动。其PID与日志保存在运行数据目录。关闭浏览器不终止它；要停止实际处理，应先在批次中点击停止后续批改。已经发送的外部请求不能保证撤销计费。重新启动worker会从持久任务继续，已成功步骤不重跑。

## 独立后端模式

后端在持久主机上运行；示例命令仅监听本机，不代表已经完成公网HTTPS配置：

```powershell
$env:MINDTRACE_DATABASE='D:/MindTraceData/mindtrace.db'
$env:MINDTRACE_DATA_DIR='D:/MindTraceData'
$env:MINDTRACE_CLASSROOM_DIR='D:/MindTraceData/classrooms'
$env:MINDTRACE_HEADLESS='1'
.\.venv\Scripts\python.exe -m uvicorn api.app:app --host 127.0.0.1 --port 8570
```

在相同环境的另一个进程运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_worker.py
```

前端使用另一个环境：

```powershell
$env:MINDTRACE_BACKEND_URL='http://127.0.0.1:8570'
$env:MINDTRACE_HEADLESS='0'
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8564
```

在前端「课堂连接」中创建/连接课堂。公网前端必须使用独立后端的HTTPS地址，数据库和材料须位于后端持久磁盘；不能把Community Cloud临时本地文件当作唯一数据源。后台Key在后端配置，前端不持有通用管理员凭据。当前保留的即时答疑/识别适配器仍按现有前端服务端模型配置运行；它们尚未全部转换成持久队列任务。

## 不调用模型的界面预览

```powershell
.\.venv\Scripts\python.exe -m streamlit run tests/platform_fixture.py --server.address 127.0.0.1 --server.port 8563
.\.venv\Scripts\python.exe scripts/verify_learning_ui.py
```

这是明确标注的构造材料预览。它调用真实业务与FSRS，但不能当作真实OCR或判卷效果证据，也不是正式产品入口。

## 正式回归

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

组件/接口测试使用本机线程通信，在限制本机套接字的执行环境中需允许本机通信。当前Starlette对测试客户端的httpx兼容路径有弃用提示，现有检查仍可运行；未为隐藏提示追加另一套HTTP客户端。

## 备份与恢复

```powershell
.\.venv\Scripts\python.exe scripts/manage_backup.py create --database D:/MindTraceData/mindtrace.db --data-root D:/MindTraceData --to D:/MindTraceBackups/backup-001
.\.venv\Scripts\python.exe scripts/manage_backup.py restore --from D:/MindTraceBackups/backup-001 --to D:/MindTraceRestored
```

备份目标必须在运行目录之外，且尚不存在。恢复也只允许新目录。manifest记录数据库及材料校验和；缺失材料、内容变更或越界路径会拒绝生成完整备份/恢复。恢复后将运行环境指向新根目录，并保留原目录直至检查通过。

JSON兼容导入在对应存储scope首次读取时执行，保留原JSON，重复同一源文件不会重复增加记录。若数据库已存在同ID的新资料，拒绝静默覆盖，需人工比对。回退代码时不覆盖新生成的订正、复习日志或数据库；新版schema不能由不支持它的旧程序直接写入。

## 发布边界

当前开发工作没有推送正式main或更新线上应用。公开更新需要独立持久后端地址与部署配置、已有线上数据迁移核对，以及至少一次真实模型契约检查。将前端代码推上Streamlit不会自动配置这些基础设施。
