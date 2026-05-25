# AstrBot NewAPI Suite - QQ 群管与 NewAPI 站长助手插件

AstrBot NewAPI Suite 是一个面向 NewAPI / One API / OpenAI 中转站站长的 QQ 群管理机器人插件。它基于 AstrBot 和 NapCat / aiocqhttp / OneBot 生态，把 QQ 群管理、NewAPI 用户绑定、余额管理、兑换码、消耗统计、知识库问答和分层菜单管理整合到一个插件里。

如果你正在运营 NewAPI 站点，希望 QQ 群里的用户可以自助绑定账号、查询余额、领取兑换码、查看 API 调用教程，并且希望管理员可以通过清晰的菜单和命令管理群与站点，这个插件就是为这个场景做的。

关键词：AstrBot 插件、NewAPI 插件、One API 群管、QQ 群机器人、NapCat 机器人、aiocqhttp、OneBot、NewAPI 余额管理、NewAPI 兑换码、QQ群管理机器人、站长助手、菜单管理、知识库机器人。

## 这个插件是做什么的？

它让你的 QQ 机器人变成 NewAPI 站点的群管家：

- 用户在 QQ 里绑定自己的 NewAPI 网站 ID。
- 用户可以在群聊或私聊里查询余额、今日消耗、绑定状态。
- 管理员可以在 QQ 里给用户加余额、扣余额、查询消耗、生成兑换码。
- 新人进群后自动提示绑定流程。
- 成员退群后自动解绑，并可恢复 NewAPI 用户组。
- 入群审批可以按规则自动放行、关键词审核、NewAPI ID/用户名审核或转人工。
- 机器人内置 NewAPI API 调用教程知识库，用户问“怎么接入 API”时可以直接回答。
- 管理员可以按层级菜单进入对应模块，使用明确命令完成配置和管理。

## 核心功能

### NewAPI 用户绑定

- `/绑定 网站ID`
- 二次确认绑定，减少用户填错 ID。
- `/自助解绑`
- 绑定审计记录，方便管理员追查谁绑定过哪个网站 ID。
- 支持 QQ 号和 NewAPI 网站 ID 互查。

### 余额与额度管理

- 用户查询当前 NewAPI 余额。
- 管理员给用户加余额、扣余额。
- 支持按 QQ 号或网站 ID 定位用户。
- 支持记录管理员调整原因。
- 余额显示倍率可配置，避免直接暴露 NewAPI 内部 quota。

### 消耗统计与排行榜

- `/今日消耗`
- 管理员查询指定用户今日消耗。
- 管理员查询全站今日消耗。
- 今日消耗排行榜。
- 基于 NewAPI 管理 API 实时读取日志，不需要用户自己上后台。

### NewAPI 原生兑换码

- 管理员在 QQ 里生成 NewAPI 原生兑换码。
- 可指定活动名、金额和数量。
- 生成后直接把兑换码发给用户，用户自行到 NewAPI 网站兑换。

### 群管理

- 进群欢迎语。
- 进群后提示绑定 NewAPI 账号。
- 可配置是否 @ 新人、是否私聊新人。
- 退群自动解绑。
- 退群后恢复 NewAPI 用户组。
- 群内禁言、解除禁言、全体禁言、全体解禁等管理动作。

### 入群审批

支持多种审批模式：

- `auto_approve`：自动同意。
- `keyword`：申请理由命中关键词才同意。
- `newapi_user`：申请理由包含有效 NewAPI 网站 ID 或用户名才同意。
- `manual`：只通知管理员，不自动处理。
- `reject`：自动拒绝。

也可以配置 QQ 黑名单、关键词黑名单、拒绝理由、审批通知群、管理员私聊通知。

### 好友申请与群邀请

- 自动同意好友申请，方便用户私聊绑定。
- 可选择是否自动同意机器人入群邀请。
- 支持黑名单和管理员通知。
- 可以替代部分 relationship 类插件，减少插件冲突。

### 知识库与 API 教程

插件自带一批 NewAPI API 调用方式知识库，包括：

- NewAPI 怎么调用接口。
- OpenAI SDK 怎么接入 NewAPI。
- curl 调用 `/v1/chat/completions`。
- Node.js / JavaScript 调用示例。
- API Key / 令牌应该怎么填。
- 怎么查看可用模型。
- NewAPI 余额和 quota 的关系。
- 常见 API 报错排查。
- 第三方软件里 Base URL 怎么填。

管理员也可以继续添加自己的知识库内容。查询知识库时可以用 LLM 润色，让回答更适合发在 QQ 群里。

### 联网搜索

可选 Tavily 或 Brave Search API。

- 默认关闭，避免不必要的 API 消耗。
- 可配置是否仅管理员可用。
- 可配置是否读取网页正文。
- 可用于知识库未命中时兜底搜索。

### 分层菜单管理

插件采用“主菜单 → 模块菜单 → 具体命令”的管理方式，方便管理员按模块操作，而不是记一长串命令。

推荐管理路径：

```text
/菜单
/管理员帮助
/绑定帮助
/群管帮助
/知识库帮助
/配置查看
```

常见管理任务可以这样进入：

- 用户和余额：`/管理员帮助`
- 绑定说明：`/绑定帮助`
- 兑换码发放：`/兑换码帮助`
- 群管理与入群审批：`/群管帮助`
- 知识库维护：`/知识库帮助`
- 插件配置：`/配置查看`、`/配置设置`

## 适用场景

- NewAPI 站长运营 QQ 用户群。
- One API / NewAPI 中转站需要群内余额查询和兑换码发放。
- 想让 QQ 群机器人承担一部分客服和群管工作。
- 想减少多个插件之间的冲突，用一个插件覆盖主要群管和站点联动功能。
- 想让管理员不打开 WebUI，也能通过 QQ 菜单和命令完成大部分配置。

## 环境要求

- AstrBot v4 及以上。
- QQ 平台建议使用 NapCat / aiocqhttp / OneBot。
- Python 依赖见 `requirements.txt`。
- NewAPI 数据库访问权限。
- NewAPI 管理 API 访问令牌。

推荐给机器人单独创建一个 NewAPI 管理账号，不要直接使用个人主账号 token。

## 安装教程

### 1. 下载插件

把本仓库放到 AstrBot 插件目录：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/jiusimeng8-cmd/astrbot_plugin_newapi.git
```

如果你不是 Docker 部署，请把路径换成自己的 AstrBot `data/plugins` 目录。

### 2. 安装依赖

进入插件目录：

```bash
cd /AstrBot/data/plugins/astrbot_plugin_newapi
pip install -r requirements.txt
```

Docker 部署时通常需要在 AstrBot 容器内执行。

### 3. 配置 `.env`

复制示例文件：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_database_user
DB_PASS=your_database_password
DB_NAME=your_database_name

BOT_API_BASE_URL=https://your-newapi-domain.com
BOT_API_ACCESS_TOKEN=sk-your-bot-admin-token
BOT_API_ADMIN_USER_ID=1
```

说明：

- `DB_*` 是 NewAPI 使用的数据库连接信息。
- `BOT_API_BASE_URL` 是你的 NewAPI 网站地址，不要带最后的 `/`。
- `BOT_API_ACCESS_TOKEN` 是机器人专用管理员账号的 NewAPI 令牌。
- `BOT_API_ADMIN_USER_ID` 是机器人管理员账号在 NewAPI 里的网站 ID。

兼容旧变量名：

- `API_BASE_URL`
- `API_ACCESS_TOKEN`
- `API_ADMIN_USER_ID`

如果同时设置，优先使用 `BOT_*`。

### 4. 重启 AstrBot

```bash
docker restart astrbot
```

或按你的部署方式重启 AstrBot。

启动后，插件会自动创建所需数据表，并同步内置 API 调用知识库。

## 快速开始

### 用户绑定账号

用户发送：

```text
/绑定 32
```

机器人会提示确认。用户确认无误后发送：

```text
确认绑定
```

绑定后可查询余额：

```text
/查询余额
```

### 管理员加余额

```text
/调整余额 32 10 补单
```

表示给网站 ID `32` 增加 10 NewAPI 余额。

扣余额可以传负数：

```text
/调整余额 32 -5 违规扣除
```

### 生成兑换码

```text
/生成兑换码 周末福利 10 5
```

表示生成 5 张，每张 10 余额，活动名为“周末福利”的 NewAPI 原生兑换码。

### 查看消耗

用户查自己：

```text
/今日消耗
```

管理员查全站：

```text
/全站今日消耗
```

管理员查排行：

```text
/今日消耗排行
```

### 查询知识库

```text
知识库 NewAPI 怎么调用接口
```

或：

```text
问答 OpenAI SDK 怎么接入 NewAPI
```

### 管理员菜单配置

查看总菜单：

```text
/菜单
```

查看管理员菜单：

```text
/管理员帮助
```

查看配置：

```text
/配置查看
/配置查看 审批
/配置查看 欢迎
/配置查看 知识库
```

修改配置：

```text
/配置设置 审批模式 自动放行
/配置设置 自动同意好友 开启
/配置设置 入群私聊绑定 开启
/配置设置 自动问答 关闭
```

## 常用命令表

| 命令 | 权限 | 说明 |
| --- | --- | --- |
| `/绑定 网站ID` | 用户 | 绑定 QQ 与 NewAPI 网站 ID |
| `确认绑定` | 用户 | 确认待绑定账号 |
| `/查询余额` | 用户 | 查询当前绑定账号余额 |
| `/今日消耗` | 用户 | 查询自己的今日消耗 |
| `/自助解绑` | 用户 | 解除自己的绑定 |
| `/签到` | 用户 | 每日签到，支持同步 NewAPI 配置 |
| `/生成兑换码 活动名 金额 [数量]` | 管理员 | 生成 NewAPI 原生兑换码 |
| `/调整余额 ID 金额 [备注]` | 管理员 | 加余额或扣余额 |
| `/查询 ID或QQ` | 管理员 | 查询绑定和站点用户信息 |
| `/配置查看 [模块]` | 管理员 | 查看插件配置 |
| `/配置设置 配置项 值` | 管理员 | 修改白名单内配置 |
| `/确认执行 ID` | 管理员 | 确认高风险操作 |
| `/取消执行 ID` | 管理员 | 取消待确认操作 |

## 配置模块

插件配置在 AstrBot WebUI 里维护，主要模块：

- `binding_settings`：绑定、最低 QQ 等级、余额显示倍率、换绑冷却。
- `check_in_settings`：签到开关、同步 NewAPI 签到配置、奖励模板。
- `group_leave_settings`：退群监听和用户组恢复。
- `group_welcome_settings`：进群欢迎、绑定提示、私聊新人。
- `join_approval_settings`：入群审批规则。
- `relationship_request_settings`：好友申请和群邀请处理。
- `knowledge_settings`：知识库 LLM 润色。
- `web_search_settings`：联网搜索。
- `auto_answer_settings`：自动工具问答。
- `usage_stats_settings`：NewAPI 消耗统计。

## 安全建议

- 不要提交 `.env`、数据库备份、日志或真实 token。
- 给机器人单独创建 NewAPI 管理账号，并控制权限。
- 自动同意机器人入群邀请要谨慎开启。
- 公开群建议关闭不必要的主动回复，避免机器人打扰群聊。

## 常见问题

### 机器人不回复怎么办？

先确认 AstrBot 和 NapCat / aiocqhttp 已连接，再看 AstrBot 后台日志。常见原因是机器人没有被 @、插件未启用、命令权限不足或 LLM provider 不可用。

### 绑定错了别人的网站 ID 怎么办？

用户可以 `/自助解绑` 后重新绑定。管理员也可以查询绑定审计记录并手动处理。

### 为什么私聊新人失败？

QQ 限制未添加好友时可能不能主动私聊新人。建议开启自动同意好友申请，并在群欢迎语里提示用户主动私聊机器人绑定。

### Base URL 应该填什么？

第三方软件选择 OpenAI Compatible 时，Base URL 通常填：

```text
https://你的NewAPI域名/v1
```

API Key 填用户自己的 NewAPI 令牌。

## License

AGPL-3.0
