# TokenHarbor

多家大模型统一 API 与按量计费平台，当前处于项目规划阶段。

## 项目文档

[打开团队背景与 TokenHarbor 技术方案](docs/tokenharbor-presentation.html)

[打开团队技术背景](docs/team-background.html)

两份文档均为面向申行科技企业交流的连续滚动 HTML，分别包含 21 个和 11 个内容章节。标题、正文、表格及架构节点均为原生 HTML，可搜索、复制与维护，手机端会重新排版。支持目录锚点和打印，单文件可离线打开。

团队背景按技术经验重新整理，移除了旧公司名、过时年份及未核实的业绩数字。TokenHarbor 的客户价值、技术架构、最少输入的智能管理、三项技术亮点、收益验证与实施路径继续明确为规划方案。本次未部署到官网。

文案分别维护在 `docs/presentation-source/team-sections.html` 和 `platform-sections.html`，运行 `python3 scripts/build-presentations.py` 生成交付文件。完整维护方式见 [源文件说明](docs/presentation-source/README.md)。

[打开项目规划与技术设计（HTML）](docs/project-plan.html)

下载仓库后，用浏览器直接打开 `docs/project-plan.html`。文档可离线阅读，包含响应式目录、架构示意、异常处理矩阵和打印样式；无需安装依赖或启动服务。GitHub 文件页显示源码，浏览完整排版请下载后本地打开。

文档覆盖项目背景、客户与商业假设、MVP 边界、总体架构、SSE 生命周期、供应商适配、路由与限流、计量与账务、幂等和对账、安全隐私、成本与恢复、技术选型、路线与验收、风险及待决策项。

所有未确认的选型和商业规则均标为建议或待决策；金额算例不代表官方报价。技术来源和访问日期见文档末章。

当前仓库只包含规划文档，尚无业务实现、部署或生产计费能力。
