# AstrBot NewAPI Suite

面向 NewAPI 站长的 AstrBot QQ 群管插件。它把 QQ 群、NewAPI 用户系统、余额管理、知识库和自然语言管理放在一个插件里，适合用机器人承担群管和站点助手的角色。

## 功能

- QQ 用户绑定 NewAPI 网站 ID，支持确认绑定、自助解绑和绑定审计。
- 查询余额、管理员加余额/扣余额、今日消耗、全站消耗和排行榜。
- NewAPI 原生兑换码生成与发放。
- 进群欢迎、绑定提示、退群自动解绑和用户组恢复。
- 入群审批规则：自动放行、关键词、NewAPI ID/用户名命中、人工、自动拒绝。
- 好友申请和机器人入群邀请处理。
- 管理员私聊自然语言管理模式。
- 本地知识库、LLM 润色、可选 Tavily / Brave 联网搜索。
- 内置 API 调用方式知识库，方便用户询问 NewAPI 接入方法。

## 安装

1. 将本仓库放入 AstrBot 的 `data/plugins/astrbot_plugin_newapi`。
2. 在插件目录创建 `.env`，可参考 `.env.example`。
3. 安装依赖：

```bash
pip install -r requirements.txt
```

4. 重启 AstrBot，在 WebUI 的插件列表中启用本插件。

## 环境变量

插件需要连接 NewAPI 数据库，并调用 NewAPI 管理 API。推荐给机器人单独创建一个权限受控的管理员账号。

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

兼容旧变量名：`API_BASE_URL`、`API_ACCESS_TOKEN`、`API_ADMIN_USER_ID`。如果同时设置，优先使用 `BOT_*`。

## 常用命令

用户：

- `/绑定 网站ID`
- `确认绑定`
- `/查询余额`
- `/今日消耗`
- `/自助解绑`
- `知识库 你的问题`

管理员：

- `/查询 网站ID或QQ号`
- `/调整余额 网站ID或QQ号 金额 [备注]`
- `/生成兑换码 活动名 金额 [数量]`
- `/配置查看 [模块]`
- `/配置设置 配置项 值`
- `/小鱼管理 自然语言管理需求`
- 私聊发送 `进入管理模式` 后，可在 10 分钟内直接说管理需求。

示例：

```text
进入管理模式
把入群审批改成自动放行
给网站ID 32 加余额 10，备注补单
查一下全站今日消耗
生成 5 张 10 元兑换码，活动名周末福利
```

## 配置说明

插件配置在 AstrBot WebUI 中维护，主要模块包括：

- `binding_settings`：绑定、余额显示倍率、换绑冷却。
- `check_in_settings`：签到，可同步 NewAPI 后台配置。
- `group_welcome_settings`：进群欢迎与私聊绑定提示。
- `join_approval_settings`：入群审批。
- `relationship_request_settings`：好友申请和群邀请处理。
- `knowledge_settings`：知识库和 LLM 润色。
- `web_search_settings`：联网搜索。
- `auto_answer_settings`：自动工具问答，默认关闭。
- `usage_stats_settings`：消耗统计读取范围。
- `qq_payment_probe_settings`：QQ 私聊收款实验监听，默认建议关闭。

## 安全说明

- 不要提交 `.env`、数据库备份、日志、QQ 钱包调试数据或任何真实 token。
- 自然语言管理只应开放给 AstrBot 管理员。
- QQ 收款/红包自动入账能力不稳定，当前仅保留实验监听代码，不建议生产启用。
- 公开部署时谨慎开启自动同意群邀请。

## License

AGPL-3.0
