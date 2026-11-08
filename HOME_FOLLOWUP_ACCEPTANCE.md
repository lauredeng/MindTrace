# 首页预选、上传框与继续追问预览

2026-11-07，承接 FIVE_FIXES_ACCEPTANCE.md 后续反馈；本文件的首页交互取代上一轮“无预选”说明。

- 首页等宽等高的教师/学生卡片支持整卡点击预选，默认教师蓝色渐变；点另一张只切换预选，不导航。点击对应进入按钮才切换工作空间。键盘可聚焦并激活原生按钮。
- 上传框保留真实 Streamlit 上传控件与校验/识别流程，修正默认按钮与说明位置。桌面左侧拖拽提示和真实输入限制，右侧原生上传按钮；手机改为上下排列。未调用模型，也没有将预设内容伪装成识别结果。
- 从错题本点击“继续向 AI 追问”实际进入 AI解题与辅导，原题、原始解答、当前数学问题及教师意见自动带入；右侧提供提示/分步/完整讲解、四级提示、主动提问与输入问题。已有解析会显示，点击跳转本身不发起新的付费请求。未新增对话结果。
- 普通界面参考解数学核验状态改为中文，追问区标题简化为“继续追问这道题”。

自动回归155项通过：artifacts/pytest-home-upload.xml。
真实 Chrome 专项：scripts/browser_home_followup.py，验证可逆预选、进入按钮、上传框左右位置、详情带题跳转和追问输入；截图已实际查看。390px另外核验首页卡片文字未被截断、上传上下布局、页面无横向溢出。

截图使用独立构造验收数据，不代表真实学生或模型准确率；未改动用户学习数据，未读取/显示实际密钥。

- [预选教师](artifacts/home-followup/02-teacher-preselected.png)
- [预选学生](artifacts/home-followup/01-student-preselected.png)
- [上传框](artifacts/home-followup/03-upload.png)
- [从错题本进入继续追问的真实页面](artifacts/home-followup/04-followup-page.png)
- [手机上传框](artifacts/home-followup/06-mobile-upload.png)


## 首页整卡与悬停动效补充

教师、学生各自的介绍和进入区域改为同一张连续卡片；选中背景覆盖整张卡，去掉内部独立块的边框和背景。鼠标悬停整卡轻微上浮4px并放大至1.015倍，增加柔和阴影；触屏及系统减少动态效果设置不强制启用动效。预选与进入行为保留。

定向回归1项通过；真实 Chrome 检查整卡背景、透明内层、悬停尺寸变化、切换预选后进入，以及390px无横向溢出通过。脚本 scripts/browser_home_unified.py。截图 artifacts/home-unified/01-teacher.png 和02-student.png；仅首页，不含用户学习内容。无新模型调用。
