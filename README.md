# AstrBot Issue Agent 协同桥 (astrbot_plugin_issue_agent)

<div align="center">

**通过自然语言与人机双向协同，将 IM 消息自动转化为 GitHub Issue 并无缝调度云端 AI Coding Agent（如 Google Jules、Devin 等）。**

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue.svg)](https://github.com/AstrBotDevs/AstrBot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## 🌟 核心特性

- 🗣️ **自然语言立项（无生硬命令）**：结合 AstrBot 的大模型函数调用（LLM Tool），在群聊中自然说出需求（如*“让 Jules 帮我写一个查天气的插件”*），机器人自动提取需求细节并向目标仓库创建 Issue。
- 🏷️ **通用 Agent 调度机制**：通过可配置的 Issue 标签（如 `jules`、`devin`、`copilot`、`sweep`），可自由无缝切换后端的各种云端 AI 编程智能体。
- 🛡️ **严格的权限控制**：支持管理员 ID 白名单，杜绝群内非授权成员乱用指令消耗你的 GitHub 或云端 AI 配额。
- ⏳ **非阻塞异步后台运行**：立项后立即在群聊中回复，不卡顿日常对话，后台协程异步轮询或监听任务进度。
- 🤝 **人机双向交互决策（Human-in-the-Loop）**：当云端 Agent 提出设计方案或疑问时，插件在群里主动 **@ 管理员**；管理员直接在群里回复意见，插件自动将决策回传至 GitHub Issue 评论区唤醒 Agent 继续执行。
- 🎭 **Bot 原生人设转述**：云端 Agent 产出的技术性日志和决策请求，均会经过 AstrBot 当前使用的大模型与人设提示词润色，保持与机器人说话风格高度统一。
- 🚀 **交付验收与 PR 通知**：Agent 完成代码编写并提交 Pull Request 后，第一时间在群里 @ 管理员验收。

---

## 🚀 快速上手

### 1. 安装方式

#### 方式一：通过 AstrBot WebUI 安装
1. 打开 AstrBot 管理控制台。
2. 进入 **插件** $\to$ **从 GitHub 安装**。
3. 输入本仓库地址：`https://github.com/Anon2Tokyo/astrbot_plugin_issue_agent` 并安装。

#### 方式二：手动克隆安装
```bash
cd AstrBot/data/plugins
git clone https://github.com/Anon2Tokyo/astrbot_plugin_issue_agent.git
pip install -r astrbot_plugin_issue_agent/requirements.txt
```

---

### 2. 插件配置项说明

在 AstrBot WebUI 插件设置或 `_conf_schema.json` 中配置：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :---: | :---: | :--- |
| `github_token` | `string` | `""` | 必填。具备 `repo` 权限的 GitHub 个人访问令牌（PAT）。 |
| `default_repo` | `string` | `""` | 默认目标仓库，格式 `owner/repo`（例如 `Anon2Tokyo/my-repo`）。 |
| `agent_label` | `string` | `"jules"` | 触发云端 Agent 的标签。Jules 填 `jules`，Devin 填 `devin`。 |
| `admin_ids` | `string` | `""` | 允许调度 Agent 的管理员 ID（如 QQ 号），多个用逗号分隔。 |
| `poll_interval`| `int` | `20` | 后台检查 Issue 评论与 PR 动态的轮询间隔（秒）。 |
| `enable_persona_rewrite` | `bool` | `true` | 是否使用 Bot 当前的角色人设重新润色 Agent 汇报内容。 |
| `auto_at_admin` | `bool` | `true` | 检测到需要确认方案或完工时，是否在群里自动 @ 管理员。 |

---

## 💬 使用示例

### 1. 自然语言发起编程任务
> **你**：让 Jules 给我们仓库写一个天气查询插件，包含 `/weather` 指令，使用 wttr.in 接口。  
> **Bot（保持人设回复）**：主人放心~ 已经将任务分派给 Jules 并在 `Anon2Tokyo/my-repo` 建立了 Issue #12，云端沙箱正在分析代码，有进展我随时向你汇报哦！

### 2. 方案待确认与双向决策
> **Bot**：@你 主人，Jules 已经完成技术选型，正在确认配置方案：建议将默认城市设置为‘北京’，超时时间设为 10 秒。请问你是否同意该方案？  
> **你**：同意，不过默认城市改成‘上海’吧。  
> **Bot**：✅ 已将您的决策意见同步回 GitHub #12，云端 Agent 正在继续推进！

### 3. 代码交付与验收
> **Bot**：@你 报告主人！Jules 已经完成插件开发并通过了所有单元测试，已提交 Pull Request：`feat: add weather query plugin (#13)`，快去 GitHub 验收吧！🎉

---

## 🛠️ 管理指令组（可选）

除了自然语言交互外，还提供了轻量级的后台查看指令：

* `/agent tasks`：查看当前正在后台跟踪的所有云端 Agent 任务状态。
* `/agent cancel <repo#number>`：取消对特定任务的后台跟踪。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。欢迎提交 Issue 与 Pull Request！
