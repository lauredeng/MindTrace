# 新增第三方依赖与源码边界

本次升级直接安装并调用以下库，未复制未授权的教师批改项目源码。完整运行依赖版本见requirements.lock.txt。

| 依赖 | 固定版本 | 许可证/用途 |
| --- | --- | --- |
| [Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs) / fsrs | 6.3.3 | MIT；官方复习调度、Card、ReviewLog；未安装Optimizer/Torch |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.165.0 | MIT；类型化后端接口 |
| [Uvicorn](https://github.com/Kludex/uvicorn) | 0.54.0 | BSD-3-Clause；ASGI服务进程 |
| [SymPy](https://github.com/sympy/sympy) | 1.14.0（原有锁定依赖） | BSD-3-Clause；直接调用成熟符号计算，新增计算适配器；许可证见licenses/sympy-LICENSE.txt |

上述已安装发行包的许可证原文保存在licenses/下，源码导出同时包含。Py-FSRS研究时检出的commit为e40a5a74799a12c9b15e01559a9b2c9f6be7a648，实施使用其6.3.3发行包。

DeepTutor现已作为独立官方教学运行时及前端接入，固定commit `341af371bf8143b2da3569084edf8e6cb46d7404`，Apache-2.0；原文见 `licenses/deeptutor-LICENSE.txt`，实际依赖快照见 `integrations/deeptutor/requirements.lock.txt`。改动仅增加业务入口和订正侧栏、根布局挂载、推理档位数组空值兼容保护；保留上游许可证、版权与归属。接入边界见 `docs/08_deeptutor_integration.md`。

Oppia仅借鉴已记录的状态组织原则。Anki不作为运行依赖，不复制AGPL源码。Auto-Homework-Grader与GradeFlow未获额外授权，不复制其无明确许可证覆盖的代码；持久队列、重试和权限实现为本项目独立编写。原有依赖的许可证仍按各自发行包执行，当前文件不替代完整第三方合规清单。
