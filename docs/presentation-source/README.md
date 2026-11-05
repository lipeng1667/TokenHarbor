# 官网交流页面源文件

两份交付仍使用原路径：

- `../team-background.html`：团队技术背景，11 个内容章节。
- `../tokenharbor-presentation.html`：团队背景与 TokenHarbor 规划，共 21 个内容章节。

页面为连续滚动的原生 HTML，不再嵌入整页截图、SVG 字形路径或幻灯片画布。标题、正文、表格和架构节点都可选择、搜索与替换。桌面多列内容在手机端重新排列，文字保持正常阅读字号。

## 内容维护

| 文件 | 作用 |
| --- | --- |
| `team-sections.html` | 团队背景 11 章的正文、表格与架构节点 |
| `platform-sections.html` | TokenHarbor 10 章的产品与技术规划 |
| `viewer.css` | 排版、流程图、响应式与打印样式 |
| `viewer.js` | 目录关闭、当前位置提示与打印按钮增强 |
| `../../scripts/build-presentations.py` | 组装品牌页首、目录和正文，生成两个单文件 HTML |
| `content-notes.md` | 内部来源、改写口径与待确认事项，不嵌入对外页面 |

在项目根目录执行：

```sh
python3 scripts/build-presentations.py
```

修改上述 HTML 片段即可更新文案。架构图使用 `.node`、`.flow-column`、`.flow-row`、`.branch-grid` 等普通 HTML 元素，布局由 CSS 负责。无需图像工具、坐标编辑或重做 PPT。生成脚本仅依赖 Python 标准库。

## 使用与官网接入

生成的 HTML 内含样式与少量增强脚本，可直接在本地浏览器打开。禁用 JavaScript 时，正文、表格、架构与原生目录锚点仍可阅读使用。页面不加载外部字体、图片或分析脚本，也不依赖本地 PPT、PDF 或项目规划文档。

正式网址、官网模板与发布流程尚未指定，本次仅生成并验证本地文件，没有部署。后续可以将选定 HTML 放入指定静态路径，也可把正文片段和 CSS 接入现有官网模板。页首品牌为文字“申行科技”，没有自造 Logo、联系方式或官网域名。

## 内容口径

历史资料中的旧公司名、过时年份、旧市场规模曲线和未核实的业绩数字已从两份对外 HTML 移除，以系统职责、流程比较和技术经验替代。没有将旧业绩换名归给申行科技，也没有补造新年份或当前性能。TokenHarbor 相关能力继续标明规划状态。

原始 PPT/PDF、`original/`、`background.svg` 和 `background-architecture.svg` 仅保留本地，用于内部追溯，**不随此次提交，当前构建也不需要这些资料**。原始资料与既有项目规划未改写。
