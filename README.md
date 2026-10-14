<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/hero-dark.svg">
    <img src="docs/assets/readme/hero-light.svg" alt="AegisLab 实验哨兵 — AI × 空间建模 × 场景创新" width="100%">
  </picture>
</p>

<h3 align="center">高校实验场景感知与智能预审平台</h3>
<p align="center">以 AI 连接实验语义、空间关系与决策行动。</p>

<p align="center">
  <a href="#overview"><img alt="AI + Scenario Innovation" src="https://img.shields.io/badge/AI-Scenario_Innovation-2563EB?style=flat-square&labelColor=334155"></a>
  <a href="#spatial"><img alt="3D Spatial Modeling" src="https://img.shields.io/badge/3D-Spatial_Modeling-0284C7?style=flat-square&labelColor=334155&logo=threedotjs&logoColor=white"></a>
  <a href="#architecture"><img alt="React" src="https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB"></a>
  <a href="#architecture"><img alt="Three.js" src="https://img.shields.io/badge/Three.js-20232A?style=flat-square&logo=threedotjs&logoColor=white"></a>
  <a href="#architecture"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white"></a>
  <a href="https://github.com/fanyangzi/AegisLab/actions/workflows/desktop-web.yml"><img alt="Web workspace verification" src="https://github.com/fanyangzi/AegisLab/actions/workflows/desktop-web.yml/badge.svg?branch=main"></a>
</p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>
<p align="center">
  <a href="#overview">项目介绍</a> ·
  <a href="#highlights">核心优势</a> ·
  <a href="#spatial">AI + 空间建模</a> ·
  <a href="#workflow">工作流</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#architecture">技术架构</a>
</p>

<p align="center">
  <a href="docs/assets/readme/workspace.png"><img src="docs/assets/readme/workspace.png" alt="AegisLab 完整空间工作区：实验室、设备、导航、对象详情与计划时间栏" width="100%"></a>
  <br><sub>空间工作区 · 完整产品界面 · 示例工作区</sub>
</p>

<a id="overview"></a>
## 项目介绍

**实验哨兵（AegisLab）** 是面向高校实验室的**场景感知型智能预审平台**。系统将大模型语义建模与三维空间、关系图谱、证据核验和变更推演结合，让实验描述转化为可关联、可分析、可协同处理的场景信息。

实验预审需要同时理解**做什么、用什么、具备哪些条件，以及变化后会影响什么**。AegisLab 以实验为中心，将 SOP 中的步骤、物料、设备与控制线索组织为带有原文依据的语义结构，再与资源台账、使用时段及检查结果关联，为师生和实验室管理人员提供从场景认知到决策支持的连续工作流。

> **AI + 场景创新：让实验从静态文档，进入可关联、可推演、可协同决策的数字场景。**

当前案例以高校化学实验、样品前处理和分析测试为主要切入点。产品通过网址访问，适用于实验发起人、教师、设备管理员与授权复核人员。

<a id="highlights"></a>
## 核心优势

| 核心能力 | 关键机制 | 应用价值 |
| :--- | :--- | :--- |
| **大模型驱动的实验语义建模** | 将大模型抽取与原文锚定、结构校验结合，组织步骤、物料、设备及控制条件，区分否定、拟采用和待确认信息。 | 把自然语言实验描述转化为能够参与预审的结构化语义。 |
| **语义—空间映射** | 将实验中的设备引用映射到台账与三维对象，联动步骤、资源依赖和使用时段。 | 让语义分析落到具体实验室、具体设备与具体使用情境。 |
| **证据关联研判** | 融合模型解释、规则结果与资源证据，核对对象、规格和有效区间，通过关系图定位相关条件与来源。 | 从问题提示进一步说明影响对象、判断依据和证据缺口。 |
| **多方案变更推演** | 围绕替代资源、时段调整与补证路径组织隔离候选，重算约束并比较影响，支持继续编辑和提交。 | 在修改正式计划前，比较不同选择所改变的条件与待办事项。 |
| **场景化行动建议** | 将分析结果组织为绑定原文、设备与检查项的建议，连接来源追踪、空间定位、补证任务与变更方案。 | 让 AI 分析从一段解释进入可继续操作的业务流程。 |
| **人机协同决策** | 以授权确认衔接任务指派、证据核验与审批，保留决策依据，并在相关条件变化后更新复核状态。 | 将预审、协作与持续复核围绕同一项实验连接起来。 |

### AegisLab Copilot · 从语义到行动

Copilot 将一次预审组织为三类相互关联的输出：**实验语义结构**（步骤、物料与控制线索）、**关联研判依据**（规则结果、资源证据与原文位置）、**场景化行动建议**（定位对象、补充证据、建立候选与发起复核）。大模型解析与解释、场景查询和规则核验协同工作，用户在同一上下文中确认并推进后续行动。

**价值不止于生成答案，而在于把答案连接到实验对象、判断依据和实际行动。**

<a id="spatial"></a>
## AI + 空间建模：从几何场景到语义工作空间

**几何模型描述“在哪里”，语义模型连接“做什么、依赖什么、为什么需要处理”。**

房间尺寸、设备类别与布局配置构成三维空间；实验语义、资源引用、检查结果与行动入口构成业务语义层。两层通过设备与计划的统一标识关联，让同一个对象同时具备空间位置、实验上下文和可追溯的处理记录。

| 同一工作区的三种视图 | 场景价值 |
| :--- | :--- |
| **空间 · Space** | 将实验步骤与设备依赖放回实验室中，选取对象即可进入关联计划与处理入口。 |
| **关系 · Graph** | 沿计划、步骤、资源、条件和资料展开依赖与依据，支持邻域、类型及路径查询。 |
| **时间 · Timeline** | 在使用时段中审视资源容量、维护窗口与证据有效性，为安排调整提供约束上下文。 |

三种视图共享计划、设备和工作区数据，Copilot 的对象与来源动作也指向同一套业务身份。用户可以在空间中定位问题、沿关系追溯依据，再进入时间与候选方案比较，而无需重新拼接上下文。

**空间负责定位，图谱解释关联，时间呈现约束，Copilot 把分析连接到行动。**

<a id="workflow"></a>
## 从场景认知到预审决策

<p align="center"><img src="docs/assets/readme/workflow-zh.svg" alt="实验语义建模 → 语义空间映射 → 证据关联研判 → 多方案变更推演 → 人机协同决策" width="100%"></p>

1. **实验语义建模**：导入 TXT、Markdown、DOCX 或带文本层的 PDF，将原文解析为步骤、对象与控制线索，形成带来源的待确认结构。
2. **语义空间映射**：把确认后的设备引用连接到实验室资源，并关联使用安排、检查资料与对象关系。
3. **证据关联研判**：规则核验具体条件，模型辅助解释风险与缺口，关系图提供相关对象和依据的追溯路径。
4. **多方案变更推演**：建立替代资源、时间调整或补证候选，比较变化前后的检查结果与受影响事项。
5. **人机协同决策**：用户采纳建议并推进任务，授权人员完成复核，系统保留处理过程并随关联条件变化重新检查。

例如，一份实验 SOP 涉及溶剂操作、通风柜和设备检查记录。系统将步骤中的对象与控制线索关联到实验室资源，结合规则与证据呈现待处理问题。用户从问题定位到具体设备和原文，再进入补证任务或替代资源方案，比较后完成复核。**模型分析、空间交互与业务动作在同一项实验中相互衔接。**

<a id="quick-start"></a>
## 快速开始

### 1. 安装环境

使用 **Node.js 22.12+（22.x）** 和 **Python 3.12**。以下为 macOS / Linux 命令：

```bash
git clone https://github.com/fanyangzi/AegisLab.git
cd AegisLab

npm ci
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
test -f .env || cp .env.example .env
```

Windows 可使用 `.venv\Scripts\Activate.ps1` 激活虚拟环境。已有 `.env` 请保留，按 [配置示例](.env.example) 补充需要的字段。

### 2. 启动网页

**终端一：启动 API**

```bash
source .venv/bin/activate
uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
```

**终端二：启动前端**

```bash
npm run dev
```

在浏览器打开 **http://127.0.0.1:5173/**。开发环境建议将 `VITE_API_BASE_URL` 留空，由 Vite 代理 `/api` 请求。

首次进入后，可建立自己的实验室与设备，也可主动导入示例工作区，再从一份计划开始体验空间、关系、时间与 Copilot 智能预审。

### 3. 连接模型

在服务端 `.env` 中填写模型服务配置，保存后重启 API：

```dotenv
LABSAFETY_LLM_ENABLED=1
LABSAFETY_LLM_BASE_URL=
LABSAFETY_LLM_MODEL=
LABSAFETY_LLM_API_KEY=
```

`BASE_URL` 填写兼容模型 API 的基础地址，`MODEL` 填写该服务提供的模型标识，`API_KEY` 填写自己的服务凭据。适配器优先使用 Responses 接口，并对不支持该接口的服务尝试 Chat Completions。

在计划中打开 AI 辅助预审即可触发 Copilot 分析。**模型承担语义建模与问题解释，场景与规则服务提供关联核验，授权人员完成决策。** 密钥仅放在服务端，不写入 `VITE_*` 变量或 Git。

<details>
<summary><strong>部署为同源网站</strong></summary>

```bash
npm run build
AEGIS_SERVE_WEB=1 uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

浏览器打开 **http://127.0.0.1:8000/**，由 FastAPI 同时提供网页和 API。先停止占用同一端口的开发服务。公网部署配置 HTTPS 与访问控制；可通过 `AEGIS_WORKSPACE_TOKEN` 配置工作区访问令牌，并在网页设置中连接。

</details>

<a id="architecture"></a>
## 技术架构

| 层次 | 技术与职责 | 代码入口 |
| :--- | :--- | :--- |
| **网页工作区** | React、TypeScript、Vite；页面、对象选择、表单与跨视图上下文。 | [`src/web/`](src/web/) |
| **空间建模与交互** | Three.js；参数化设备、场景建模、相机、选取与标签。 | [`Scene.tsx`](src/web/Scene.tsx) |
| **大模型与语义建模** | 模型适配、实验要素抽取、语义候选校验、来源锚定与问题解释。 | [`llm.py`](backend/app/llm.py) · [`parser.py`](backend/app/parser.py) |
| **场景核验与行动服务** | FastAPI；资源与证据核验、关系查询、候选推演、任务协作与授权决策。 | [`spatial.py`](backend/app/spatial.py) |
| **数据与后台任务** | SQLite、修订与幂等、持久化任务和独立 Worker。 | [`worker.py`](backend/worker.py) |

<details>
<summary><strong>开发检查</strong></summary>

```bash
npm run test:parity
npm run build
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/smoke.py
```

覆盖前后端领域规则对照、接口、资料处理、协作状态、权限、并发与持久化等工程路径。

</details>

## 参与项目

欢迎通过 [Issues](https://github.com/fanyangzi/AegisLab/issues) 提交使用反馈、场景需求或问题复现，通过 [Pull Requests](https://github.com/fanyangzi/AegisLab/pulls) 参与开发。设备类别与知识来源可查阅 [设备调研](docs/equipment-taxonomy-research.md) 和 [来源登记](data/knowledge_sources.json)。

<p align="center"><strong>实验哨兵 · AegisLab</strong><br><sub>知微守安队 · AI + 场景创新</sub></p>
