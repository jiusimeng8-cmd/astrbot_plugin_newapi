from typing import Optional, Tuple
import json
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.api.message_components import At

from .newapi_utils import NewApiCore
from .heist_logic import HeistLogic

def require_binding(f):
    """
    检查命令发起者是否绑定网站ID，若未绑定则中断并提示，若已绑定则附加binding对象以便后续使用。
    """
    @wraps(f)
    async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
        user_qq_id = event.get_sender_id()

        # 避免重复获取binding
        if hasattr(event, 'binding'):
            async for item in f(self, event, *args, **kwargs):
                yield item
            return

        binding = await self.core.get_user_by_qq(user_qq_id)

        if not binding:
            result = await self._private_first_result(
                event,
                self._binding_help_text(),
                group_notice="你还没有绑定 NewAPI 网站账号，我把绑定说明私聊你了。",
            )
            if result:
                yield result
            return

        # 附加binding对象到event
        event.binding = binding

        async for item in f(self, event, *args, **kwargs):
            yield item

    return wrapper

@register(
    "NewAPI_plugin",
    "Future-404",
    "集成了核心用户管理与娱乐功能的New API插件套件。",
    "1.1.0"
)
class NewApiSuitePlugin(Star):
    """
    New API 功能套件主插件类，作为功能套件的唯一入口点。
    """
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.core = NewApiCore(config)
        self.heist_handler = HeistLogic(config, self.core)
        self._admin_mode_sessions: dict[int, datetime] = {}
        logger.info("[NewAPI Suite] 插件已实例化，准备进行异步初始化...")

    async def initialize(self):
        init_success = await self.core.initialize()
        if init_success:
            logger.info("[NewAPI Suite] 核心服务初始化成功。" )
        else:
            logger.error("[NewAPI Suite] 核心服务初始化失败。" )
            

    
    def _binding_help_text(self) -> str:
        return (
            "你还没有绑定 NewAPI 网站账号。\n"
            "绑定方式：/绑定 你的网站ID\n"
            "例如：/绑定 32\n\n"
            "为防止填错，绑定会分两步：先发送 /绑定 32，再发送 确认绑定。\n"
            "绑定后，你在 QQ 群里查询余额、充值入账，都会作用到这个网站 ID。\n"
            "请一定填写自己的 ID；如果填成别人的，后续充值也会进入别人的账号。\n"
            "想更换绑定时，可以先发送 /自助解绑，再重新绑定。"
        )

    def _is_group_event(self, event: AstrMessageEvent) -> bool:
        try:
            gid = event.get_group_id()
            return bool(gid)
        except Exception:
            return False

    async def _private_first_result(
        self,
        event: AstrMessageEvent,
        message: str,
        group_notice: str = "我把结果私聊你了，避免在群里刷屏。",
    ):
        if not self._is_group_event(event):
            return event.plain_result(message)

        user_qq_id = event.get_sender_id()
        try:
            await event.bot.send_private_msg(user_id=int(user_qq_id), message=message)
            return event.plain_result(group_notice)
        except Exception as e:
            logger.warning(f"NewAPI 私聊发送失败({user_qq_id}): {e}")
            return event.plain_result("我想私聊你，但发送失败了。请先加机器人好友，或直接私聊机器人使用这个命令。")

    def _public_help_text(self) -> str:
        return (
            "NewAPI 群助手\n"
            "--------------------\n"
            "/绑定帮助 - 查看绑定方式\n"
            "/充值帮助 - 查看充值流程\n"
            "/兑换码帮助 - 查看兑换码说明\n"
            "/知识库帮助 - 查看常见问题查询\n"
            "/搜索 关键词 - 联网搜索\n"
            "/查询余额 - 查询当前 NewAPI 余额\n"
            "/自助解绑 - 解除当前 QQ 的绑定\n\n"
            "也可以直接说：怎么绑定、查余额、我的余额。"
        )

    def _binding_help_menu_text(self) -> str:
        return (
            "绑定帮助\n"
            "--------------------\n"
            "1. 发送：/绑定 你的网站ID\n"
            "2. 看清网站 ID 后，再发送：确认绑定\n\n"
            "例子：\n"
            "/绑定 32\n"
            "确认绑定\n\n"
            "绑定后，查询余额、充值入账都会进入这个网站 ID。请一定填写自己的 ID。"
        )

    def _recharge_help_text(self) -> str:
        return (
            "充值帮助\n"
            "--------------------\n"
            "/充值 金额 [备注] - 创建待审核充值单\n"
            "例子：/充值 20 支付宝已付\n\n"
            "管理员确认后才会入账。支付截图 OCR 还在后续开发中。"
        )

    def _redemption_help_text(self) -> str:
        return (
            "兑换码帮助\n"
            "--------------------\n"
            "本插件只使用 NewAPI 原生兑换码。\n"
            "机器人不会代替用户兑换，避免两边数据库不一致。\n\n"
            "/兑换 兑换码 - 获取网站兑换地址\n"
            "用户需要到 NewAPI 网站钱包页面自行兑换。"
        )

    def _group_admin_help_text(self) -> str:
        return (
            "群管帮助\n"
            "--------------------\n"
            "/禁言 秒数 @用户\n"
            "/解禁 @用户\n"
            "/全体禁言\n"
            "/全体解禁\n\n"
            "管理员也可以用：/小鱼管理 把 QQ号 禁言 10 分钟"
        )

    def _admin_help_text(self) -> str:
        return (
            "NewAPI 管理员帮助\n"
            "--------------------\n"
            "用户与余额：\n"
            "/查询 网站ID或QQ - 查询绑定关系\n"
            "/查余额 网站ID或QQ - 查询任意用户余额\n"
            "/加款 网站ID或QQ 金额 [备注]\n"
            "/扣款 网站ID或QQ 金额 [备注]\n"
            "/查绑定记录 QQ号\n\n"
            "消耗统计：\n"
            "/今日消耗 [网站ID或QQ]\n"
            "/全站今日消耗\n"
            "/今日排行 [数量]\n\n"
            "充值与兑换码：\n"
            "/生成兑换码 活动名 金额 数量 - 创建 NewAPI 原生兑换码\n"
            "/确认充值 订单号\n"
            "/拒绝充值 订单号\n\n"
            "群管理：\n"
            "/禁言 秒数 @用户\n"
            "/解禁 @用户\n"
            "/全体禁言\n"
            "/全体解禁\n\n"
            "自然语言管理：\n"
            "私聊发送：进入管理模式 - 10 分钟内直接说管理需求\n"
            "私聊发送：退出管理模式 - 结束管理会话\n"
            "/小鱼管理 给网站ID 32 加余额 10 备注补单\n"
            "/小鱼管理 扣网站ID 32 余额 3 备注退款\n"
            "/小鱼管理 查 QQ123456 的今日消耗\n"
            "/小鱼管理 把入群审批改成自动放行\n"
            "/小鱼管理 开启自动问答\n"
            "/小鱼管理 设置欢迎语为 {at}欢迎进群，请先绑定账号\n"
            "/小鱼管理 生成 5 张 10 元兑换码，活动名周末福利\n"
            "/小鱼管理 知识库添加：怎么绑定账号？答案：发送 /绑定 网站ID\n"
            "/小鱼管理 搜一下 deepseek 最新模型\n"
            "/小鱼管理 把 123456 禁言 10 分钟\n"
            "/确认执行 ID - 确认扣款、删知识库、全体禁言等高风险操作\n"
            "/取消执行 ID - 取消待确认操作\n\n"
            "QQ 内配置：\n"
            "/配置查看 [审批|欢迎|自动问答|搜索|知识库|签到]\n"
            "/配置设置 入群审批 开启\n"
            "/配置设置 审批模式 自动放行\n"
            "/配置设置 同步NewAPI签到 开启\n"
            "/配置设置 欢迎语 {at}欢迎进群，请先绑定账号\n\n"
            "系统：\n"
            "/pingapi - 查看插件和数据库状态\n\n"
            "知识库：\n"
            "/知识库添加 问题 | 答案 | 关键词\n"
            "/知识库修改 ID | 问题 | 答案 | 关键词\n"
            "/知识库查询 关键词\n"
            "/知识库列表\n"
            "/知识库删除 ID\n\n"
            "联网搜索：\n"
            "/搜索 关键词\n"
            "/读网页 URL\n\n"
            "说明：高权限仍跟 AstrBot 管理员走，不单独再配一套管理员。"
        )

    def _help_text(self, is_admin: bool = False, private: bool = False) -> str:
        if is_admin and private:
            return self._admin_help_text()
        return self._public_help_text()

    @filter.command("帮助", alias={"菜单", "newapi", "NewAPI", "群助手", "群管菜单"})
    async def handle_help_command(self, event: AstrMessageEvent):
        """显示 NewAPI 群助手帮助菜单。"""
        if event.is_admin() and self._is_group_event(event):
            try:
                await event.bot.send_private_msg(user_id=int(event.get_sender_id()), message=self._admin_help_text())
                yield event.plain_result("管理员完整菜单已私聊你了。群里先放简版：\n\n" + self._public_help_text())
                return
            except Exception as e:
                logger.warning(f"管理员帮助私聊失败: {e}")
        result = await self._private_first_result(
            event,
            self._help_text(is_admin=event.is_admin(), private=not self._is_group_event(event)),
            group_notice="菜单已私聊你了。",
        )
        yield result

    @filter.command("绑定帮助")
    async def handle_binding_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._binding_help_menu_text(), group_notice="绑定说明已私聊你了。")

    @filter.command("充值帮助")
    async def handle_recharge_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._recharge_help_text(), group_notice="充值说明已私聊你了。")

    @filter.command("兑换码帮助")
    async def handle_redemption_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._redemption_help_text(), group_notice="兑换码说明已私聊你了。")

    def _knowledge_help_text(self, is_admin: bool = False) -> str:
        text = (
            "知识库帮助\n"
            "--------------------\n"
            "/知识库查询 关键词 - 查询常见问题\n"
            "也可以说：查知识 关键词\n"
        )
        if is_admin:
            text += (
                "\n管理员：\n"
                "/知识库添加 问题 | 答案 | 关键词\n"
                "/知识库修改 ID | 问题 | 答案 | 关键词\n"
                "/知识库列表\n"
                "/知识库删除 ID\n"
            )
        return text

    @filter.command("知识库帮助")
    async def handle_knowledge_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._knowledge_help_text(event.is_admin()), group_notice="知识库说明已私聊你了。")

    @filter.command("群管帮助")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_group_admin_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._group_admin_help_text(), group_notice="群管说明已私聊你了。")

    @filter.command("管理员帮助")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_admin_help_command(self, event: AstrMessageEvent):
        yield await self._private_first_result(event, self._admin_help_text(), group_notice="管理员完整菜单已私聊你了。")

    @filter.command("配置查看", alias={"查看配置", "插件配置"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_config_view(self, event: AstrMessageEvent, module: str = ""):
        yield await self._private_first_result(event, self._config_summary_text(module), group_notice="配置已私聊你了。")

    @filter.command("配置设置", alias={"设置配置"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_config_set(self, event: AstrMessageEvent):
        text = self._normal_text(event)
        for prefix in ("/配置设置", "配置设置", "/设置配置", "设置配置"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        if not text:
            yield event.plain_result("格式：/配置设置 配置项 值\n例：/配置设置 入群审批 开启\n例：/配置设置 审批模式 自动放行")
            return
        parts = re.split(r"\s+", text, maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result("格式：/配置设置 配置项 值\n例：/配置设置 欢迎语 {at}欢迎进群，请先绑定账号")
            return
        yield event.plain_result(self._set_managed_config(parts[0], parts[1]))

    def _normal_text(self, event: AstrMessageEvent) -> str:
        return (getattr(event, "message_str", "") or "").strip()

    def _admin_mode_enter_words(self) -> set[str]:
        return {
            "进入管理模式", "开启管理模式", "打开管理模式", "管理模式",
            "进入管家模式", "开启管家模式", "打开管家模式", "管家模式",
            "进入设置模式", "开启设置模式", "打开设置模式", "设置模式",
            "我要管理", "我要设置", "开始管理", "开始设置",
            "小鱼进入管理", "小鱼开启管理", "小鱼打开管理",
            "进入后台", "打开后台", "管理后台",
        }

    def _admin_mode_exit_words(self) -> set[str]:
        return {
            "退出管理模式", "关闭管理模式", "结束管理模式",
            "退出管家模式", "关闭管家模式", "结束管家模式",
            "退出设置模式", "关闭设置模式", "结束设置模式",
            "不用管理了", "结束管理", "退出管理", "退出后台",
            "退出", "结束", "取消",
        }

    def _admin_mode_help_text(self) -> str:
        return (
            "已进入管理模式。\n"
            "10 分钟内，你可以直接说管理需求，不用每句都带 /小鱼管理。\n\n"
            "例子：\n"
            "查看签到配置\n"
            "把入群审批改成自动放行\n"
            "开启入群私聊绑定\n"
            "给网站ID 32 加余额 10，备注补单\n"
            "生成 5 张 10 元兑换码，活动名周末福利\n\n"
            "退出请发送：退出管理模式"
        )

    def _admin_mode_active(self, user_id: int) -> bool:
        expires_at = self._admin_mode_sessions.get(int(user_id))
        if not expires_at:
            return False
        if datetime.utcnow() >= expires_at:
            self._admin_mode_sessions.pop(int(user_id), None)
            return False
        return True

    def _refresh_admin_mode(self, user_id: int):
        self._admin_mode_sessions[int(user_id)] = datetime.utcnow() + timedelta(minutes=10)

    def _format_template(self, template: str, **kwargs) -> str:
        try:
            return template.format(**kwargs)
        except Exception as e:
            logger.warning(f"NewAPI 模板格式化失败: {e}")
            return template

    def _extract_json_from_text(self, text: str) -> Optional[dict]:
        if not text:
            return None
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
        if fenced:
            cleaned = fenced.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start:end + 1]
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _extract_newapi_identity_from_comment(self, comment: str) -> tuple[Optional[int], Optional[str]]:
        text = comment or ""
        id_patterns = [
            r"(?:网站\s*id|站点\s*id|用户\s*id|newapi\s*id|id)[:：= ]*(\d{1,10})",
            r"\b(\d{1,10})\b",
        ]
        for pattern in id_patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return int(match.group(1)), None

        username_patterns = [
            r"(?:用户名|账号|账户|user|username|name)[:：= ]*([A-Za-z0-9_.@-]{3,64})",
            r"\b([A-Za-z][A-Za-z0-9_.@-]{2,63})\b",
        ]
        for pattern in username_patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() not in {"newapi", "qq", "id", "user", "username"}:
                    return None, candidate
        return None, None

    def _config_registry(self) -> dict:
        return {
            "join_approval_settings.enabled": ("bool", "入群审批开关"),
            "join_approval_settings.mode": ("enum:auto_approve,keyword,newapi_user,manual,reject", "入群审批模式"),
            "join_approval_settings.group_list": ("int_list", "启用审批的群号列表"),
            "join_approval_settings.allow_newapi_identity_match": ("bool", "申请理由命中 NewAPI ID/用户名自动同意"),
            "join_approval_settings.approve_keywords": ("str_list", "入群同意关键词"),
            "join_approval_settings.blacklist_qq": ("int_list", "入群黑名单 QQ"),
            "join_approval_settings.blacklist_keywords": ("str_list", "入群黑名单关键词"),
            "join_approval_settings.reject_reason": ("str", "入群拒绝理由"),
            "join_approval_settings.notify_group_id": ("int", "入群审批通知群号，0 表示不通知群"),
            "join_approval_settings.notify_admin_private": ("bool", "入群审批是否私聊通知管理员"),
            "join_approval_settings.notify_admin_qq_list": ("int_list", "接收入群审批通知的管理员 QQ 列表"),
            "relationship_request_settings.enabled": ("bool", "好友/群邀请处理开关"),
            "relationship_request_settings.auto_agree_friend": ("bool", "自动同意好友申请"),
            "relationship_request_settings.auto_reject_friend": ("bool", "自动拒绝好友申请"),
            "relationship_request_settings.auto_agree_group_invite": ("bool", "自动同意群邀请"),
            "relationship_request_settings.auto_reject_group_invite": ("bool", "自动拒绝群邀请"),
            "relationship_request_settings.friend_blacklist_qq": ("int_list", "好友申请黑名单 QQ"),
            "relationship_request_settings.group_blacklist": ("int_list", "群邀请黑名单群号"),
            "relationship_request_settings.reject_reason": ("str", "好友/群邀请拒绝理由"),
            "relationship_request_settings.notify_admin_private": ("bool", "好友/群邀请是否私聊通知管理员"),
            "relationship_request_settings.notify_admin_qq_list": ("int_list", "好友/群邀请通知管理员 QQ 列表"),
            "group_welcome_settings.enabled": ("bool", "进群欢迎开关"),
            "group_welcome_settings.at_new_member": ("bool", "欢迎语是否 @ 新人"),
            "group_welcome_settings.send_private_message": ("bool", "是否私聊新人绑定流程"),
            "group_welcome_settings.welcome_template": ("str", "群内欢迎语模板"),
            "group_welcome_settings.private_welcome_template": ("str", "私聊绑定流程模板"),
            "auto_answer_settings.enabled": ("bool", "自动问答开关"),
            "auto_answer_settings.only_when_mentioned": ("bool", "群聊是否只在 @ 机器人时自动问答"),
            "auto_answer_settings.group_enabled_list": ("int_list", "允许自动问答的群号列表"),
            "auto_answer_settings.min_query_length": ("int", "自动问答最短触发字数"),
            "auto_answer_settings.trigger_words": ("str_list", "自动问答触发词"),
            "auto_answer_settings.use_knowledge_base": ("bool", "自动问答是否使用知识库"),
            "auto_answer_settings.use_web_search_fallback": ("bool", "知识库未命中时是否联网搜索"),
            "auto_answer_settings.always_include_web_search": ("bool", "自动问答是否总是联网搜索"),
            "web_search_settings.enabled": ("bool", "联网搜索开关"),
            "web_search_settings.provider": ("enum:tavily,brave", "联网搜索提供商"),
            "web_search_settings.fetch_pages": ("bool", "联网搜索是否读取网页正文"),
            "web_search_settings.use_llm_summary": ("bool", "联网搜索是否用 LLM 总结"),
            "web_search_settings.admin_only": ("bool", "联网搜索是否仅管理员可用"),
            "knowledge_settings.enable_llm_polish": ("bool", "知识库是否用 LLM 润色"),
            "knowledge_settings.answer_tone": ("str", "知识库 LLM 回复风格"),
            "check_in_settings.sync_from_newapi": ("bool", "是否同步 NewAPI 后台签到配置"),
            "check_in_settings.enabled": ("bool", "本地签到开关，关闭同步时生效"),
            "check_in_settings.min_display_quota": ("float", "本地签到最小余额，关闭同步时生效"),
            "check_in_settings.max_display_quota": ("float", "本地签到最大余额，关闭同步时生效"),
            "check_in_settings.double_chance": ("float", "签到翻倍概率"),
            "check_in_settings.first_check_in_bonus_enabled": ("bool", "首次签到额外奖励开关"),
            "check_in_settings.first_check_in_bonus_display_quota": ("float", "首次签到额外奖励余额"),
            "qq_payment_probe_settings.enabled": ("bool", "QQ收款实验监听开关"),
            "qq_payment_probe_settings.log_all_private_non_text": ("bool", "是否记录所有私聊非文本事件"),
            "qq_payment_probe_settings.keywords": ("str_list", "QQ收款疑似关键词"),
            "qq_payment_probe_settings.max_log_chars": ("int", "QQ收款日志最大字符数"),
        }

    def _config_aliases(self) -> dict:
        return {
            "入群审批": "join_approval_settings.enabled",
            "审批开关": "join_approval_settings.enabled",
            "审批模式": "join_approval_settings.mode",
            "审批群": "join_approval_settings.group_list",
            "入群群号": "join_approval_settings.group_list",
            "newapi匹配": "join_approval_settings.allow_newapi_identity_match",
            "审批关键词": "join_approval_settings.approve_keywords",
            "入群关键词": "join_approval_settings.approve_keywords",
            "黑名单qq": "join_approval_settings.blacklist_qq",
            "黑名单关键词": "join_approval_settings.blacklist_keywords",
            "拒绝理由": "join_approval_settings.reject_reason",
            "审批通知群": "join_approval_settings.notify_group_id",
            "私聊通知管理员": "join_approval_settings.notify_admin_private",
            "审批管理员": "join_approval_settings.notify_admin_qq_list",
            "好友申请": "relationship_request_settings.enabled",
            "好友申请处理": "relationship_request_settings.enabled",
            "自动同意好友": "relationship_request_settings.auto_agree_friend",
            "好友自动同意": "relationship_request_settings.auto_agree_friend",
            "自动拒绝好友": "relationship_request_settings.auto_reject_friend",
            "好友自动拒绝": "relationship_request_settings.auto_reject_friend",
            "自动同意群邀请": "relationship_request_settings.auto_agree_group_invite",
            "群邀请自动同意": "relationship_request_settings.auto_agree_group_invite",
            "自动进群": "relationship_request_settings.auto_agree_group_invite",
            "自动拒绝群邀请": "relationship_request_settings.auto_reject_group_invite",
            "群邀请自动拒绝": "relationship_request_settings.auto_reject_group_invite",
            "好友黑名单": "relationship_request_settings.friend_blacklist_qq",
            "群邀请黑名单": "relationship_request_settings.group_blacklist",
            "申请拒绝理由": "relationship_request_settings.reject_reason",
            "申请私聊通知": "relationship_request_settings.notify_admin_private",
            "申请通知管理员": "relationship_request_settings.notify_admin_qq_list",
            "欢迎": "group_welcome_settings.enabled",
            "欢迎语": "group_welcome_settings.welcome_template",
            "进群欢迎": "group_welcome_settings.enabled",
            "欢迎at": "group_welcome_settings.at_new_member",
            "私聊新人": "group_welcome_settings.send_private_message",
            "入群私聊绑定": "group_welcome_settings.send_private_message",
            "自动私聊绑定": "group_welcome_settings.send_private_message",
            "私聊欢迎语": "group_welcome_settings.private_welcome_template",
            "私聊绑定流程": "group_welcome_settings.private_welcome_template",
            "自动问答": "auto_answer_settings.enabled",
            "自动回复": "auto_answer_settings.enabled",
            "只在at时回复": "auto_answer_settings.only_when_mentioned",
            "自动问答群": "auto_answer_settings.group_enabled_list",
            "触发词": "auto_answer_settings.trigger_words",
            "知识库自动回答": "auto_answer_settings.use_knowledge_base",
            "问答联网": "auto_answer_settings.use_web_search_fallback",
            "总是联网": "auto_answer_settings.always_include_web_search",
            "联网搜索": "web_search_settings.enabled",
            "搜索提供商": "web_search_settings.provider",
            "读取网页": "web_search_settings.fetch_pages",
            "搜索总结": "web_search_settings.use_llm_summary",
            "搜索仅管理员": "web_search_settings.admin_only",
            "知识库润色": "knowledge_settings.enable_llm_polish",
            "知识库风格": "knowledge_settings.answer_tone",
            "同步newapi签到": "check_in_settings.sync_from_newapi",
            "同步签到": "check_in_settings.sync_from_newapi",
            "签到": "check_in_settings.enabled",
            "签到开关": "check_in_settings.enabled",
            "签到最小奖励": "check_in_settings.min_display_quota",
            "签到最大奖励": "check_in_settings.max_display_quota",
            "签到翻倍概率": "check_in_settings.double_chance",
            "首次签到奖励": "check_in_settings.first_check_in_bonus_enabled",
            "首次签到奖励余额": "check_in_settings.first_check_in_bonus_display_quota",
            "收款监听": "qq_payment_probe_settings.enabled",
            "qq收款监听": "qq_payment_probe_settings.enabled",
            "红包监听": "qq_payment_probe_settings.enabled",
            "转账监听": "qq_payment_probe_settings.enabled",
            "记录所有私聊非文本": "qq_payment_probe_settings.log_all_private_non_text",
            "收款关键词": "qq_payment_probe_settings.keywords",
            "收款日志长度": "qq_payment_probe_settings.max_log_chars",
        }

    def _resolve_config_key(self, key: str) -> Optional[str]:
        raw = str(key or "").strip()
        if raw in self._config_registry():
            return raw
        compact = re.sub(r"\s+", "", raw).lower()
        aliases = {re.sub(r"\s+", "", k).lower(): v for k, v in self._config_aliases().items()}
        return aliases.get(compact)

    def _coerce_config_value(self, value, type_spec: str):
        if type_spec == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in {"true", "1", "yes", "on", "enable", "enabled", "开启", "打开", "启用", "是", "允许", "同意", "需要"}:
                return True
            if text in {"false", "0", "no", "off", "disable", "disabled", "关闭", "禁用", "否", "不", "不用", "不要", "不需要"}:
                return False
            raise ValueError("布尔值只能是 开启/关闭")
        if type_spec == "int":
            return int(value)
        if type_spec == "float":
            return float(value)
        if type_spec == "str":
            return str(value)
        if type_spec in {"int_list", "str_list"}:
            if isinstance(value, list):
                items = value
            else:
                items = [x for x in re.split(r"[,，、\s]+", str(value).strip()) if x]
            if type_spec == "int_list":
                return [int(x) for x in items]
            return [str(x) for x in items]
        if type_spec.startswith("enum:"):
            allowed = type_spec.split(":", 1)[1].split(",")
            text = str(value).strip()
            enum_aliases = {
                "自动放行": "auto_approve",
                "自动同意": "auto_approve",
                "全部允许": "auto_approve",
                "全部同意": "auto_approve",
                "直接放行": "auto_approve",
                "直接同意": "auto_approve",
                "放行": "auto_approve",
                "允许": "auto_approve",
                "关键词": "keyword",
                "关键字": "keyword",
                "关键词审核": "keyword",
                "关键字审核": "keyword",
                "newapi用户": "newapi_user",
                "newapi用户审核": "newapi_user",
                "newapiid": "newapi_user",
                "网站id": "newapi_user",
                "newapi": "newapi_user",
                "人工": "manual",
                "手动": "manual",
                "人工审核": "manual",
                "手动审核": "manual",
                "人工审批": "manual",
                "通知管理员": "manual",
                "拒绝": "reject",
                "自动拒绝": "reject",
                "全部拒绝": "reject",
                "直接拒绝": "reject",
            }
            text = enum_aliases.get(re.sub(r"\s+", "", text).lower(), text)
            if text not in allowed:
                raise ValueError(f"可选值：{', '.join(allowed)}")
            return text
        raise ValueError("不支持的配置类型")

    def _get_config_value(self, key: str):
        current = self.config
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _set_config_value(self, key: str, value):
        section, field = key.split(".", 1)
        if section not in self.config or not isinstance(self.config.get(section), dict):
            self.config[section] = {}
        self.config[section][field] = value
        self.config.save_config()

    def _format_config_value(self, value) -> str:
        if isinstance(value, bool):
            return "开启" if value else "关闭"
        if isinstance(value, list):
            return "空" if not value else ", ".join(str(x) for x in value)
        text = str(value)
        return text if len(text) <= 180 else text[:180] + "..."

    def _config_summary_text(self, module: str = "") -> str:
        module_alias = {
            "审批": "join_approval_settings",
            "入群": "join_approval_settings",
            "申请": "relationship_request_settings",
            "好友": "relationship_request_settings",
            "群邀请": "relationship_request_settings",
            "欢迎": "group_welcome_settings",
            "自动问答": "auto_answer_settings",
            "问答": "auto_answer_settings",
            "搜索": "web_search_settings",
            "联网": "web_search_settings",
            "知识库": "knowledge_settings",
            "签到": "check_in_settings",
            "收款": "qq_payment_probe_settings",
            "红包": "qq_payment_probe_settings",
            "转账": "qq_payment_probe_settings",
        }
        selected = module_alias.get(str(module or "").strip(), str(module or "").strip())
        lines = ["QQ 内配置", "--------------------"]
        for key, (_, label) in self._config_registry().items():
            if selected and not key.startswith(selected):
                continue
            lines.append(f"{label}: {self._format_config_value(self._get_config_value(key))}")
        if len(lines) == 2:
            lines.append("可查看模块：审批、申请、欢迎、自动问答、搜索、知识库、签到")
        return "\n".join(lines)

    def _set_managed_config(self, key: str, value) -> str:
        resolved = self._resolve_config_key(key)
        if not resolved:
            return "这个配置项不在 QQ 管理白名单里。可以发送 /配置查看 查看支持的配置。"
        type_spec, label = self._config_registry()[resolved]
        try:
            coerced = self._coerce_config_value(value, type_spec)
        except Exception as e:
            return f"{label} 设置失败：{e}"
        self._set_config_value(resolved, coerced)
        return f"已更新：{label}\n当前值：{self._format_config_value(coerced)}"

    async def _match_newapi_identity_from_comment(self, comment: str) -> tuple[bool, str]:
        website_user_id, username = self._extract_newapi_identity_from_comment(comment)
        if website_user_id is not None:
            user = await self.core.get_api_user_data(int(website_user_id))
            if user:
                return True, f"命中 NewAPI 网站ID {website_user_id}"
            return False, f"未找到 NewAPI 网站ID {website_user_id}"
        if username:
            user = await self.core.find_api_user_by_username(username)
            if user:
                return True, f"命中 NewAPI 用户名 {username}"
            return False, f"未找到 NewAPI 用户名 {username}"
        return False, "申请理由未包含 NewAPI 网站ID或用户名"

    def _extract_bind_id_from_text(self, text: str) -> Optional[int]:
        patterns = [
            r"(?:绑定|綁定|bind)\s*(?:网站|網站|站点|站號|账号|帳號|id|ID|用户|用戶)?\s*(\d{1,10})",
            r"(?:我的|我)\s*(?:网站|網站|站点|账号|帳號|id|ID)\s*(?:是|为|爲|=|：|:)\s*(\d{1,10})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _natural_intent(self, event: AstrMessageEvent) -> tuple[str, Optional[int]]:
        text = self._normal_text(event)
        compact = re.sub(r"\s+", "", text).lower()
        if not compact or compact.startswith("/"):
            return "", None

        kb_match = re.search(r"(?:查知识|知识库|问答|faq|FAQ)[:： ]*(.+)", text, flags=re.I)
        if kb_match and kb_match.group(1).strip():
            kb_query = kb_match.group(1).strip()
            if re.search(r"^(怎么用|如何使用|帮助|功能|说明|菜单|是什么|有吗|在哪|怎么管理|管理)$", kb_query):
                return "knowledge_help", None
            return "knowledge", kb_query

        bind_id = self._extract_bind_id_from_text(text)
        if bind_id is not None:
            return "bind", bind_id

        help_words = (
            "帮助", "菜单", "命令", "指令", "怎么用", "如何使用", "使用说明",
            "群助手", "群管菜单", "newapi", "new api", "功能列表",
        )
        balance_words = (
            "查询余额", "查余额", "余额", "剩余额度", "我的额度", "查额度", "额度查询",
            "还有多少", "剩多少", "剩几块", "余额多少", "额度多少",
        )
        bind_help_words = (
            "怎么绑定", "如何绑定", "绑定教程", "绑定说明", "我要绑定", "我想绑定",
            "绑定账号", "绑定账户", "绑定网站", "绑定newapi", "绑定 newapi",
        )
        unbind_words = (
            "自助解绑", "解除绑定", "取消绑定", "解绑", "换绑", "重新绑定", "取消账号绑定",
        )
        confirm_bind_words = (
            "确认绑定", "确认綁定", "确定绑定", "確認绑定", "确认bind", "confirmbind",
        )
        knowledge_help_words = (
            "知识库帮助", "知识库怎么用", "知识库如何使用", "知识库功能", "知识库说明",
            "怎么用知识库", "如何使用知识库", "管理知识库", "知识库管理",
        )

        if any(word in compact for word in knowledge_help_words):
            return "knowledge_help", None
        if any(word in compact for word in balance_words):
            return "balance", None
        if any(word in compact for word in confirm_bind_words):
            return "confirm_bind", None
        if any(word in compact for word in unbind_words):
            return "unbind", None
        if any(word in compact for word in bind_help_words):
            return "bind_help", None
        if any(word.lower().replace(" ", "") in compact for word in help_words):
            return "help", None
        return "", None

    async def _route_natural_intent(self, event: AstrMessageEvent, intent: str, value: Optional[int] = None):
        if intent == "help":
            result = await self._private_first_result(
                event,
                self._help_text(is_admin=event.is_admin()),
                group_notice="菜单已私聊你了。",
            )
            yield result
            return

        if intent == "bind_help":
            result = await self._private_first_result(
                event,
                self._binding_help_text(),
                group_notice="我把绑定说明私聊你了。",
            )
            yield result
            return

        if intent == "knowledge_help":
            result = await self._private_first_result(
                event,
                self._knowledge_help_text(event.is_admin()),
                group_notice="知识库说明已私聊你了。",
            )
            yield result
            return

        if intent == "bind":
            async for result in self.handle_bind_command(event, value):
                yield result
            return

        if intent == "confirm_bind":
            async for result in self.handle_confirm_bind_command(event):
                yield result
            return

        if intent == "balance":
            async for result in self.handle_query_balance(event):
                yield result
            return

        if intent == "unbind":
            async for result in self.handle_self_unbind_command(event):
                yield result
            return

        if intent == "knowledge":
            async for result in self.handle_knowledge_query(event, str(value or "")):
                yield result
            return

    @filter.event_message_type(filter.EventMessageType.ALL, priority=80)
    async def handle_natural_language_entry(self, event: AstrMessageEvent):
        """NewAPI natural-language entry for common low-risk user actions."""
        if getattr(event, "_has_send_oper", False):
            return
        intent, value = self._natural_intent(event)
        if not intent:
            return
        async for result in self._route_natural_intent(event, intent, value):
            if result:
                yield result
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=95)
    async def handle_admin_mode_entry(self, event: AstrMessageEvent):
        """Private admin mode: natural language management after explicit opt-in."""
        if getattr(event, "_has_send_oper", False):
            return
        if self._is_group_event(event):
            return

        text = self._normal_text(event).strip()
        if not text or text.startswith("/"):
            return
        compact = re.sub(r"\s+", "", text).lower()
        sender_id = int(event.get_sender_id())

        enter_words = {re.sub(r"\s+", "", w).lower() for w in self._admin_mode_enter_words()}
        exit_words = {re.sub(r"\s+", "", w).lower() for w in self._admin_mode_exit_words()}

        if compact in enter_words:
            if not event.is_admin():
                yield event.plain_result("只有 AstrBot 管理员可以进入管理模式。")
                event.stop_event()
                return
            self._refresh_admin_mode(sender_id)
            yield event.plain_result(self._admin_mode_help_text())
            event.stop_event()
            return

        if compact in exit_words and self._admin_mode_active(sender_id):
            self._admin_mode_sessions.pop(sender_id, None)
            yield event.plain_result("已退出管理模式。")
            event.stop_event()
            return

        if not self._admin_mode_active(sender_id):
            return

        if not event.is_admin():
            self._admin_mode_sessions.pop(sender_id, None)
            yield event.plain_result("权限状态变化，已退出管理模式。")
            event.stop_event()
            return

        self._refresh_admin_mode(sender_id)
        action = await self._parse_llm_admin_action(event, text)
        reply = await self._execute_llm_admin_action(event, action or {})
        yield event.plain_result(reply)
        event.stop_event()

    @filter.command("pingapi")
    async def handle_ping_command(self, event: AstrMessageEvent):
        """响应ping命令，并报告数据库状态。"""
        db_status = "✅ 已连接" if self.core.db_pool is not None else "❌ 连接失败"
        api_check = getattr(self.core, "bot_account_check", {}) or {}
        api_status = "✅ 可用" if api_check.get("ok") else "⚠️ 需检查"
        api_message = api_check.get("message", "尚未检查")
        credential_source = api_check.get("credential_source", getattr(self.core, "api_credential_source", "unknown"))
        admin_user_id = api_check.get("admin_user_id", getattr(self.core, "api_admin_user_id", "未知"))
        reply = f"""🎉 Pong! NewAPI 插件套件 V1.1.0 正在运行！
--------------------
数据库状态: {db_status}
NewAPI机器人账号: {api_status}
账号来源: {credential_source}
机器人网站ID: {admin_user_id}
自检说明: {api_message}"""
        yield event.plain_result(reply)

    async def _parse_llm_admin_action(self, event: AstrMessageEvent, instruction: str) -> Optional[dict]:
        llm_conf = self.config.get('llm_admin_settings', {})
        if not llm_conf.get('enabled', True):
            return {"action": "disabled"}
        provider = self.context.get_using_provider()
        if not provider:
            return {"action": "no_provider"}

        group_hint = ""
        if self._is_group_event(event):
            group_hint = f"当前群号: {event.get_group_id()}\n"

        system_prompt = """你是 AstrBot 的 NewAPI 群管插件的命令解析器。
你只能把管理员的自然语言转成一个 JSON 对象，不要闲聊，不要输出 Markdown。
允许的 action:
- query_balance: 查询余额。字段 identifier(int)
- add_balance: 加 NewAPI 余额。字段 identifier(int), amount(float), reason(string)
- subtract_balance: 扣 NewAPI 余额。字段 identifier(int), amount(float), reason(string)
- confirm_recharge: 确认充值单。字段 order_id(int)
- reject_recharge: 拒绝充值单。字段 order_id(int)
- mute: 群内禁言。字段 user_id(int), seconds(int)
- unmute: 群内解禁。字段 user_id(int)
- whole_ban: 开启全员禁言。字段 enable(bool)
- help_menu: 查看帮助。字段 topic(string，可选：binding,recharge,redemption,knowledge,group,admin)
- usage_today: 查询今日消耗。字段 identifier(int，可选)
- usage_site_today: 查询全站今日消耗。
- usage_ranking: 今日消耗排行。字段 limit(int，可选)
- create_redemption: 生成 NewAPI 原生兑换码。字段 name(string), amount(float), count(int)
- knowledge_query: 查询知识库。字段 keyword(string)
- knowledge_add: 新增知识库。字段 question(string), answer(string), keywords(string)
- knowledge_list: 知识库列表。
- knowledge_delete: 删除知识库。字段 item_id(int)
- web_search: 联网搜索。字段 query(string)
- read_webpage: 阅读网页。字段 url(string)
- binding_audit: 查询绑定记录。字段 qq_id(int)
- config_view: 查看插件配置。字段 module(string，可选：审批,申请,欢迎,自动问答,搜索,知识库)
- config_set: 修改插件配置。字段 key(string), value(any)
- help: 不确定时返回这个。
限制:
- 缺少必要字段时返回 {"action":"help","message":"缺少什么字段"}。
- 禁止编造 QQ 号、网站 ID、订单号、金额。
- 配置修改只能使用常见中文配置名，例如 入群审批、审批模式、自动同意好友、自动同意群邀请、欢迎语、自动问答、联网搜索、知识库润色、收款监听。
- 审批模式 value 优先使用这些机器值：auto_approve, keyword, newapi_user, manual, reject。用户说“全部允许/自动放行/直接同意”就是 auto_approve；“人工审批/手动审核”就是 manual；“只允许 NewAPI ID/用户名命中”就是 newapi_user。
- 用户说“关闭主动回复/别主动回答/取消自动回复”，通常返回 {"action":"config_set","key":"自动问答","value":false}；如果用户明确说“关闭收款/红包/转账监听”，才设置“收款监听”为 false。
示例:
- “把这个群的进群审批改为全部允许” -> {"action":"config_set","key":"审批模式","value":"auto_approve"}
- “关闭收款探针” -> {"action":"config_set","key":"收款监听","value":false}
- “查一下审批配置” -> {"action":"config_view","module":"审批"}
- 只返回 JSON。"""
        prompt = f"{group_hint}管理员原话: {instruction}"
        try:
            resp = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                session_id=f"newapi_llm_admin_{event.get_sender_id()}",
            )
            data = self._extract_json_from_text(getattr(resp, "completion_text", "") if resp else "")
            return data or {"action": "help", "message": "我没有解析出可执行动作。"}
        except Exception as e:
            logger.error(f"NewAPI LLM 管理解析失败: {e}", exc_info=True)
            return {"action": "error", "message": "LLM 解析失败，请稍后再试。"}

    async def _polish_knowledge_answer(self, keyword: str, rows: list[dict]) -> Optional[str]:
        kb_conf = self.config.get('knowledge_settings', {})
        if not kb_conf.get('enable_llm_polish', True):
            return None
        provider = self.context.get_using_provider()
        if not provider:
            return None

        max_chars = int(kb_conf.get('max_source_chars', 3000))
        tone = kb_conf.get('answer_tone', '自然、清楚、有一点人味，但不要编造知识库没有的信息')
        source_parts = []
        for row in rows:
            source_parts.append(f"ID: {row.get('id')}\n问题: {row.get('question')}\n答案: {row.get('answer')}\n关键词: {row.get('keywords') or ''}")
        source = "\n\n---\n\n".join(source_parts)
        if len(source) > max_chars:
            source = source[:max_chars] + "\n...(已截断)"

        system_prompt = (
            "你是 QQ 群里的 NewAPI 知识库助手。\n"
            "你只能根据给定知识库内容回答，不要编造外部信息。\n"
            "如果知识库没有直接答案，就说明没有查到明确答案，并建议联系管理员。\n"
            "回答要简洁、口语化、适合发在 QQ 聊天里。"
        )
        prompt = (
            f"用户查询：{keyword}\n\n"
            f"回复风格：{tone}\n\n"
            f"知识库内容：\n{source}"
        )
        try:
            resp = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                session_id="newapi_knowledge_polish",
            )
            text = getattr(resp, "completion_text", "") if resp else ""
            return text.strip() or None
        except Exception as e:
            logger.warning(f"知识库 LLM 润色失败，回退原始答案: {e}")
            return None

    async def _summarize_web_results(self, query: str, results: list[dict]) -> Optional[str]:
        search_conf = self.config.get('web_search_settings', {})
        if not search_conf.get('use_llm_summary', True):
            return None
        provider = self.context.get_using_provider()
        if not provider:
            return None
        parts = []
        for idx, item in enumerate(results, 1):
            content = item.get("content") or item.get("snippet") or ""
            parts.append(f"[{idx}] {item.get('title')}\nURL: {item.get('url')}\n摘要/正文: {content}")
        source = "\n\n---\n\n".join(parts)
        system_prompt = (
            "你是 QQ 群里的联网搜索助手。只能根据给定搜索结果回答，不要编造来源没有的信息。"
            "回答要简洁清楚，最后列出来源编号和链接。"
        )
        prompt = f"用户搜索：{query}\n\n搜索结果：\n{source}"
        try:
            resp = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                session_id="newapi_web_search",
            )
            text = getattr(resp, "completion_text", "") if resp else ""
            return text.strip() or None
        except Exception as e:
            logger.warning(f"联网搜索 LLM 总结失败，回退原始结果: {e}")
            return None

    def _format_search_results(self, results: list[dict]) -> str:
        lines = ["搜索结果："]
        for idx, item in enumerate(results, 1):
            lines.append(f"{idx}. {item.get('title')}\n{item.get('url')}\n{item.get('snippet') or ''}")
        return "\n\n".join(lines)

    def _web_search_allowed(self, event: AstrMessageEvent) -> Optional[str]:
        search_conf = self.config.get('web_search_settings', {})
        if not search_conf.get('enabled', False):
            return "联网搜索未启用。请管理员先在插件配置里开启 web_search_settings。"
        if search_conf.get('admin_only', False) and not event.is_admin():
            return "联网搜索目前仅管理员可用。"
        provider = str(search_conf.get('provider', 'tavily')).lower()
        if provider == "brave" and not search_conf.get('brave_api_key'):
            return "Brave Search API Key 未配置。"
        if provider != "brave" and not search_conf.get('tavily_api_key'):
            return "Tavily API Key 未配置。"
        return None

    def _today_range_timestamps(self) -> tuple[int, int]:
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(start.timestamp()), int(now.timestamp())

    def _display_usage_amount(self, raw_quota: int) -> float:
        ratio = self.config.get('binding_settings.quota_display_ratio', 500000)
        return raw_quota / ratio

    def _usage_stats_settings(self) -> tuple[int, int]:
        conf = self.config.get('usage_stats_settings', {})
        return int(conf.get('page_size', 100)), int(conf.get('max_pages', 30))

    def _format_usage_summary(self, title: str, stats: dict, target: str = "") -> str:
        amount = self._display_usage_amount(int(stats.get("total_quota") or 0))
        lines = [
            title,
            "--------------------",
        ]
        if target:
            lines.append(target)
        lines.extend([
            f"请求次数: {stats.get('total_requests', 0)}",
            f"消耗 NewAPI 余额: {amount:.4f}",
            f"内部 quota: {stats.get('total_quota', 0)}",
            f"Prompt Tokens: {stats.get('total_prompt_tokens', 0)}",
            f"Completion Tokens: {stats.get('total_completion_tokens', 0)}",
        ])
        if stats.get("truncated"):
            lines.append("提示：日志较多，本次只统计了配置允许的最大页数，结果可能偏小。")
        return "\n".join(lines)

    def _is_bot_mentioned(self, event: AstrMessageEvent) -> bool:
        try:
            self_id = int(event.get_self_id())
        except Exception:
            return False
        return self_id in self._at_user_ids(event)

    def _strip_bot_mention_text(self, event: AstrMessageEvent) -> str:
        text = self._normal_text(event)
        try:
            self_id = str(event.get_self_id())
            text = re.sub(rf"\[CQ:at,qq={re.escape(self_id)}\]", "", text)
        except Exception:
            pass
        return text.strip()

    def _auto_answer_should_trigger(self, event: AstrMessageEvent) -> tuple[bool, str]:
        conf = self.config.get('auto_answer_settings', {})
        if not conf.get('enabled', False):
            return False, ""
        if getattr(event, "_has_send_oper", False):
            return False, ""
        if not isinstance(event, AiocqhttpMessageEvent):
            return False, ""
        text = self._strip_bot_mention_text(event)
        if not text or text.startswith("/"):
            return False, ""
        if len(text) < int(conf.get('min_query_length', 4)):
            return False, ""
        if self._is_group_event(event):
            groups = [int(g) for g in conf.get('group_enabled_list', []) if str(g).isdigit()]
            if groups and int(event.get_group_id()) not in groups:
                return False, ""
            if conf.get('only_when_mentioned', True) and not self._is_bot_mentioned(event):
                return False, ""
        trigger_words = [str(w) for w in conf.get('trigger_words', []) if str(w).strip()]
        if trigger_words and not self._is_bot_mentioned(event):
            compact = re.sub(r"\s+", "", text)
            if not any(w in compact for w in trigger_words):
                return False, ""
        return True, text

    async def _auto_answer_with_tools(self, event: AstrMessageEvent, query: str) -> Optional[str]:
        conf = self.config.get('auto_answer_settings', {})
        sources = []
        kb_rows = []
        if conf.get('use_knowledge_base', True):
            kb_rows = await self.core.search_knowledge_items(query, int(conf.get('kb_result_count', 3)))
            for row in kb_rows:
                sources.append(f"知识库 #{row.get('id')}\n问题: {row.get('question')}\n答案: {row.get('answer')}\n关键词: {row.get('keywords') or ''}")

        search_results = []
        if (not kb_rows or conf.get('always_include_web_search', False)) and conf.get('use_web_search_fallback', False):
            if not self._web_search_allowed(event):
                search_conf = self.config.get('web_search_settings', {})
                search_results = await self.core.web_search(query, search_conf)
                if search_conf.get('fetch_pages', False):
                    for item in search_results[:int(search_conf.get('fetch_page_count', 3))]:
                        item["content"] = await self.core.fetch_webpage_text(item.get("url", ""), int(search_conf.get('max_page_chars', 6000)))
                for idx, item in enumerate(search_results, 1):
                    content = item.get("content") or item.get("snippet") or ""
                    sources.append(f"联网来源 [{idx}]\n标题: {item.get('title')}\nURL: {item.get('url')}\n内容: {content}")

        if not sources:
            return None

        provider = self.context.get_using_provider()
        if not provider:
            if kb_rows:
                row = kb_rows[0]
                return f"{row['question']}\n{row['answer']}"
            return self._format_search_results(search_results) if search_results else None

        max_chars = int(conf.get('max_context_chars', 6000))
        source_text = "\n\n---\n\n".join(sources)
        if len(source_text) > max_chars:
            source_text = source_text[:max_chars] + "\n...(已截断)"
        system_prompt = (
            "你是 QQ 群里的站长助手。你可以使用工具结果回答用户问题。\n"
            "优先相信本地知识库；联网来源只用于补充最新信息。\n"
            "不要编造工具结果里没有的信息。回答要自然、简洁、适合聊天。\n"
            "如果用了联网来源，最后简短列出来源链接。"
        )
        prompt = f"用户问题：{query}\n\n工具结果：\n{source_text}"
        try:
            resp = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                session_id=f"newapi_auto_answer_{event.get_sender_id()}",
            )
            text = getattr(resp, "completion_text", "") if resp else ""
            return text.strip() or None
        except Exception as e:
            logger.warning(f"自动工具路由 LLM 回复失败: {e}")
            if kb_rows:
                row = kb_rows[0]
                return f"{row['question']}\n{row['answer']}"
            return None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def handle_auto_answer_tools(self, event: AstrMessageEvent):
        """OpenCode-style light tool router: KB first, optional web fallback."""
        should, query = self._auto_answer_should_trigger(event)
        if not should:
            return
        answer = await self._auto_answer_with_tools(event, query)
        if not answer:
            return
        yield event.plain_result(answer)
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=99)
    async def handle_qq_payment_probe(self, event: AstrMessageEvent):
        """实验性监听 QQ 私聊红包/转账原始事件，只写日志不入账。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return
        if self._is_group_event(event):
            return

        conf = self.config.get('qq_payment_probe_settings', {})
        if not conf.get('enabled', True):
            return

        raw = event.message_obj.raw_message
        try:
            raw_text = json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            raw_text = str(raw)

        message_text = self._normal_text(event)
        combined = f"{message_text}\n{raw_text}"
        keywords = [str(k) for k in conf.get('keywords', []) if str(k).strip()]
        keyword_hit = any(k.lower() in combined.lower() for k in keywords)

        raw_message = raw if isinstance(raw, dict) else {}
        post_type = raw_message.get("post_type")
        message_type = raw_message.get("message_type")
        message = raw_message.get("message")
        is_plain_text = False
        if post_type == "message" and message_type == "private":
            if isinstance(message, str):
                is_plain_text = "[CQ:" not in message
            elif isinstance(message, list) and message:
                is_plain_text = all(
                    isinstance(seg, dict)
                    and seg.get("type") == "text"
                    and isinstance(seg.get("data"), dict)
                    for seg in message
                )
        non_text_hit = bool(conf.get('log_all_private_non_text', False)) and not is_plain_text
        if not keyword_hit and not non_text_hit:
            return

        max_chars = max(500, min(int(conf.get('max_log_chars', 4000)), 20000))
        snippet = raw_text[:max_chars]
        logger.warning(
            "[NewAPI QQPaymentProbe] 疑似QQ私聊收款事件 sender=%s keyword_hit=%s non_text_hit=%s raw=%s",
            event.get_sender_id(),
            keyword_hit,
            non_text_hit,
            snippet,
        )

    def _parse_wallet_debug_payload(self, text: str) -> Optional[dict]:
        marker = "[NewAPIWalletDebug]"
        if marker not in text:
            return None
        payload = text.split(marker, 1)[1].strip()
        try:
            data = json.loads(payload)
        except Exception:
            return None
        wallet = data.get("walletElement") or {}
        receiver = wallet.get("receiver") or {}
        sender_card = wallet.get("sender") or {}
        title = str(receiver.get("title") or sender_card.get("title") or "")
        amount_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", title.replace(",", ""))
        link_url = str(receiver.get("linkUrl") or sender_card.get("linkUrl") or "")
        trans_match = re.search(r"[?&]transId=([^&]+)", link_url)
        send_uin = str(wallet.get("sendUin") or "")
        return {
            "amount": float(amount_match.group(1)) if amount_match else 0.0,
            "trans_id": trans_match.group(1) if trans_match else "",
            "send_uin": send_uin,
            "status": str(receiver.get("subTitle") or sender_card.get("subTitle") or ""),
            "notice": str(receiver.get("notice") or sender_card.get("notice") or ""),
            "msg_type": wallet.get("msgType"),
            "grab_state": wallet.get("grabState"),
            "grabbed_amount": str(wallet.get("grabbedAmount") or "0"),
        }

    async def _get_onebot_cookies(self, event: AstrMessageEvent, domain: str) -> str:
        if not isinstance(event, AiocqhttpMessageEvent):
            return ""
        try:
            client = event.bot
            for method_name in ("get_cookies", "getCookies"):
                method = getattr(client, method_name, None)
                if not method:
                    continue
                try:
                    result = await method(domain=domain)
                except TypeError:
                    result = await method(domain)
                if isinstance(result, dict):
                    data = result.get("data") if isinstance(result.get("data"), dict) else result
                    return str(data.get("cookies") or "")
                return str(result or "")
        except Exception as e:
            logger.warning(f"获取 OneBot cookie 失败: {e}", exc_info=True)
        return ""

    async def _auto_approve_recharge_order(self, event: AstrMessageEvent, order_id: int, website_user_id: int, amount: float, reason: str) -> str:
        rows = await self.core.mark_recharge_order(order_id, 'APPROVED', int(event.get_self_id() or 0))
        if rows <= 0:
            return "自动入账失败：订单可能已被处理。"
        class _BotEvent:
            def get_sender_id(self_inner):
                return int(event.get_self_id() or 0)
        return await self._admin_adjust_quota(_BotEvent(), website_user_id, amount, reason)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=100)
    async def handle_qq_wallet_recharge_probe(self, event: AstrMessageEvent):
        """把 NapCat WALLET 调试文本转成待确认充值单。"""
        if self._is_group_event(event):
            return
        text = self._normal_text(event)
        payload = self._parse_wallet_debug_payload(text)
        if not payload:
            return

        amount = float(payload.get("amount") or 0)
        trans_id = str(payload.get("trans_id") or "")
        sender_qq = str(payload.get("send_uin") or event.get_sender_id())
        if amount <= 0 or not trans_id:
            logger.warning(f"NewAPI wallet 解析失败: {payload}")
            return
        if str(event.get_sender_id()) != sender_qq:
            logger.warning(f"NewAPI wallet 付款 QQ 与事件发送者不一致: sender={event.get_sender_id()} wallet={sender_qq}")
            return

        binding = await self.core.get_user_by_qq(int(sender_qq))
        if not binding:
            yield event.plain_result(
                "收到一笔 QQ 转账，但你还没有绑定 NewAPI 网站账号。\n"
                "请先发送：/绑定 你的网站ID\n"
                "绑定完成后联系管理员处理这笔转账。"
            )
            event.stop_event()
            return

        detail_status = ""
        detail_record = {}
        tenpay_cookie = await self._get_onebot_cookies(event, "mqq.tenpay.com")
        if tenpay_cookie:
            detail_status, detail_record = await self.core.query_tenpay_transfer_detail(
                trans_id,
                tenpay_cookie,
                str(event.get_self_id() or ""),
            )
            if detail_status == "SUCCESS":
                try:
                    detail_amount = float(detail_record.get("price") or 0) / 100
                    payer_uin = str(detail_record.get("payer_uin") or "")
                    seller_uin = str(detail_record.get("seller_uin") or "")
                    state = str(detail_record.get("state") or "")
                    draw_state = str(detail_record.get("draw_state") or "")
                    if detail_amount > 0:
                        amount = detail_amount
                    if payer_uin and payer_uin != sender_qq:
                        yield event.plain_result("这笔 QQ 转账的付款人与消息发送者不一致，已拦截，请联系管理员。")
                        event.stop_event()
                        return
                    if seller_uin and seller_uin != str(event.get_self_id() or ""):
                        yield event.plain_result("这笔 QQ 转账的收款人不是当前机器人账号，已拦截。")
                        event.stop_event()
                        return
                except Exception as e:
                    logger.warning(f"解析 Tenpay 订单详情失败: {e}", exc_info=True)
                    state = ""
                    draw_state = ""
            else:
                logger.warning(f"查询 Tenpay 订单详情失败: status={detail_status} detail={detail_record}")

        existing = await self.core.find_recharge_order_by_note_keyword(trans_id)
        if existing:
            if detail_status == "SUCCESS" and str(detail_record.get("state") or "") == "3" and str(existing.get("status")) == "PENDING":
                result = await self._auto_approve_recharge_order(
                    event,
                    int(existing["id"]),
                    int(existing["website_user_id"]),
                    float(existing["amount"]),
                    f"QQ转账已收款 transId={trans_id}",
                )
                yield event.plain_result(f"检测到这笔 QQ 转账已确认收款，已自动入账。\n{result}")
            else:
                yield event.plain_result(f"这笔 QQ 转账已经创建过充值单 #{existing['id']}，请勿重复提交。")
            event.stop_event()
            return

        order_status = "PENDING"
        note = f"QQ转账 transId={trans_id}; status={payload.get('status')}; notice={payload.get('notice')}"
        if detail_status == "SUCCESS":
            note = (
                f"{note}; tenpay_state={detail_record.get('state')}; "
                f"draw_state={detail_record.get('draw_state')}; transaction_id={detail_record.get('transaction_id')}"
            )
        order_id = await self.core.create_recharge_order(
            int(sender_qq),
            int(binding["website_user_id"]),
            amount,
            note,
        )
        if detail_status == "SUCCESS" and str(detail_record.get("state") or "") == "3":
            result = await self._auto_approve_recharge_order(
                event,
                order_id,
                int(binding["website_user_id"]),
                amount,
                f"QQ转账已收款 transId={trans_id}",
            )
            yield event.plain_result(
                "收到 QQ 转账信息，并检测到已确认收款，已自动入账。\n"
                f"订单号: {order_id}\n"
                f"网站ID: {binding['website_user_id']}\n"
                f"金额: {amount:.2f}\n"
                f"{result}"
            )
            event.stop_event()
            return

        yield event.plain_result(
            "收到 QQ 转账信息，已创建待确认充值单。\n"
            f"订单号: {order_id}\n"
            f"网站ID: {binding['website_user_id']}\n"
            f"金额: {amount:.2f}\n"
            f"状态: {payload.get('status') or '未知'}\n"
            "当前还没有完成 QQ 确认收款，确认后再次发送/触发这条转账消息即可自动入账；也可以由管理员手动确认充值。"
        )
        event.stop_event()

    async def _create_pending_llm_action(self, event: AstrMessageEvent, action: dict, summary: str) -> int:
        payload = dict(action)
        payload["_confirmed"] = True
        return await self.core.create_pending_action(
            int(event.get_sender_id()),
            str(action.get("action", "")),
            payload,
            summary,
            ttl_minutes=10,
        )

    def _normalize_llm_admin_action(self, action: dict) -> dict:
        if not isinstance(action, dict):
            return {"action": "help", "message": "我没有解析出可执行动作。"}
        normalized = dict(action)
        aliases = {
            "balance": "query_balance",
            "add_quota": "add_balance",
            "subtract_quota": "subtract_balance",
            "deduct_balance": "subtract_balance",
            "deduct_quota": "subtract_balance",
            "redeem_create": "create_redemption",
            "redemption_create": "create_redemption",
            "kb_query": "knowledge_query",
            "kb_add": "knowledge_add",
            "kb_list": "knowledge_list",
            "kb_delete": "knowledge_delete",
            "search": "web_search",
            "read_url": "read_webpage",
            "config": "config_view",
            "set_config": "config_set",
        }
        name = str(normalized.get("action", "")).strip()
        normalized["action"] = aliases.get(name, name)

        if "identifier" not in normalized:
            for key in ("website_user_id", "website_id", "site_user_id", "site_id", "user_id"):
                if key in normalized:
                    normalized["identifier"] = normalized[key]
                    break
        if "amount" not in normalized:
            for key in ("balance", "quota", "money", "value"):
                if key in normalized:
                    normalized["amount"] = normalized[key]
                    break
        if normalized.get("action") == "config_set":
            key = str(normalized.get("key", "")).strip()
            value = normalized.get("value", "")
            resolved = self._resolve_config_key(key)
            if resolved and resolved.endswith(".mode") and isinstance(value, str):
                try:
                    normalized["value"] = self._coerce_config_value(value, self._config_registry()[resolved][0])
                except Exception:
                    pass
        return normalized

    def _missing_llm_fields(self, action: dict) -> Optional[str]:
        name = str(action.get("action", "")).strip()
        required = {
            "query_balance": ("identifier",),
            "add_balance": ("identifier", "amount"),
            "subtract_balance": ("identifier", "amount"),
            "confirm_recharge": ("order_id",),
            "reject_recharge": ("order_id",),
            "create_redemption": ("name", "amount"),
            "knowledge_query": ("keyword",),
            "knowledge_add": ("question", "answer"),
            "knowledge_delete": ("item_id",),
            "web_search": ("query",),
            "read_webpage": ("url",),
            "binding_audit": ("qq_id",),
            "config_set": ("key", "value"),
            "mute": ("user_id", "seconds"),
            "unmute": ("user_id",),
        }
        labels = {
            "identifier": "网站ID或已绑定的QQ号",
            "amount": "余额金额",
            "order_id": "充值单ID",
            "name": "兑换码活动名",
            "keyword": "查询关键词",
            "question": "知识库问题",
            "answer": "知识库答案",
            "item_id": "知识库ID",
            "query": "搜索内容",
            "url": "网页链接",
            "qq_id": "QQ号",
            "key": "配置项",
            "value": "配置值",
            "user_id": "QQ号",
            "seconds": "禁言秒数",
        }
        missing = [field for field in required.get(name, ()) if action.get(field) in (None, "")]
        if missing:
            return "缺少：" + "、".join(labels.get(field, field) for field in missing)
        if name == "create_redemption" and action.get("count") in (None, ""):
            action["count"] = 1
        return None

    async def _execute_llm_admin_action(self, event: AstrMessageEvent, action: dict) -> str:
        action = self._normalize_llm_admin_action(action)
        name = str(action.get("action", "")).strip()
        if name == "disabled":
            return "LLM 自然语言管理目前未启用。"
        if name == "no_provider":
            return "当前没有可用的 LLM 模型提供商。"
        if name in {"help", "error", ""}:
            return action.get("message") or self._admin_help_text()
        missing = self._missing_llm_fields(action)
        if missing:
            return f"{missing}。\n你可以换成更明确的说法，例如：给网站ID 32 加余额 10，或把审批模式改成自动放行。"
        if name == "query_balance":
            return await self._query_api_balance_text(int(action["identifier"]))
        if name == "config_view":
            return self._config_summary_text(str(action.get("module", "")))
        if name == "config_set":
            return self._set_managed_config(str(action.get("key", "")), action.get("value", ""))
        if name == "help_menu":
            topic = str(action.get("topic", "")).lower()
            if topic in {"binding", "bind"}:
                return self._binding_help_menu_text()
            if topic in {"recharge", "pay"}:
                return self._recharge_help_text()
            if topic in {"redemption", "redeem"}:
                return self._redemption_help_text()
            if topic in {"knowledge", "kb"}:
                return self._knowledge_help_text(True)
            if topic in {"group", "moderation"}:
                return self._group_admin_help_text()
            return self._admin_help_text()
        if name == "usage_today":
            identifier = action.get("identifier")
            if identifier is None:
                binding = await self.core.get_user_by_qq(event.get_sender_id())
                if not binding:
                    return "你还没有绑定 NewAPI 网站账号，无法查询自己的今日消耗。"
                website_user_id = int(binding["website_user_id"])
            else:
                website_user_id = await self.core.resolve_website_user_id(int(identifier))
                if website_user_id is None:
                    return f"未找到 {identifier} 对应的绑定用户或网站用户。"
            start_ts, end_ts = self._today_range_timestamps()
            page_size, max_pages = self._usage_stats_settings()
            stats = await self.core.summarize_usage_logs(start_ts, end_ts, user_id=int(website_user_id), page_size=page_size, max_pages=max_pages)
            return self._format_usage_summary("今日消耗", stats, f"网站ID: {website_user_id}")
        if name == "usage_site_today":
            start_ts, end_ts = self._today_range_timestamps()
            page_size, max_pages = self._usage_stats_settings()
            stats = await self.core.summarize_usage_logs(start_ts, end_ts, page_size=page_size, max_pages=max_pages)
            return self._format_usage_summary("全站今日消耗", stats)
        if name == "usage_ranking":
            start_ts, end_ts = self._today_range_timestamps()
            page_size, max_pages = self._usage_stats_settings()
            stats = await self.core.summarize_usage_logs(start_ts, end_ts, page_size=page_size, max_pages=max_pages)
            users = stats.get("users", [])[:max(1, min(int(action.get("limit", 10)), 30))]
            if not users:
                return "今日暂无消耗记录。"
            lines = ["今日消耗排行", "--------------------"]
            for idx, user in enumerate(users, 1):
                amount = self._display_usage_amount(int(user.get("quota") or 0))
                lines.append(f"{idx}. {user.get('username')} (ID:{user.get('user_id')}) - {amount:.4f} / {user.get('requests')} 次")
            return "\n".join(lines)
        if name in {"add_balance", "subtract_balance"}:
            amount = abs(float(action["amount"]))
            if name == "subtract_balance":
                if not action.get("_confirmed"):
                    pending_id = await self._create_pending_llm_action(event, action, f"扣除 {action['identifier']} 的 NewAPI 余额 {amount}")
                    return f"高风险操作已创建待确认 #{pending_id}。\n将执行：扣除 {action['identifier']} 的 NewAPI 余额 {amount}\n请发送：/确认执行 {pending_id}"
                amount = -amount
            return await self._admin_adjust_quota(
                event,
                int(action["identifier"]),
                amount,
                str(action.get("reason", "LLM自然语言管理")),
            )
        if name == "confirm_recharge":
            order = await self.core.get_recharge_order(int(action["order_id"]))
            if not order:
                return "未找到该充值单。"
            if order.get('status') != 'PENDING':
                return f"该充值单已处理，当前状态：{order.get('status')}"
            rows = await self.core.mark_recharge_order(int(action["order_id"]), 'APPROVED', event.get_sender_id())
            if rows <= 0:
                return "确认失败：订单可能已被处理。"
            return await self._admin_adjust_quota(event, int(order['website_user_id']), float(order['amount']), f"充值单#{action['order_id']}")
        if name == "reject_recharge":
            if not action.get("_confirmed"):
                pending_id = await self._create_pending_llm_action(event, action, f"拒绝充值单 {action['order_id']}")
                return f"高风险操作已创建待确认 #{pending_id}。\n将执行：拒绝充值单 {action['order_id']}\n请发送：/确认执行 {pending_id}"
            rows = await self.core.mark_recharge_order(int(action["order_id"]), 'REJECTED', event.get_sender_id())
            return "已拒绝该充值单。" if rows > 0 else "拒绝失败：订单可能已被处理。"
        if name == "create_redemption":
            ok, details = await self.core.create_native_redemption_codes(str(action["name"]), float(action["amount"]), int(action.get("count", 1)))
            if not ok:
                return f"NewAPI 原生兑换码创建失败：{details.get('message', '未知错误')}"
            codes = [str(code) for code in details.get("codes", [])]
            return (
                "NewAPI 原生兑换码已创建。\n"
                f"活动名: {details['name']}\n"
                f"每张余额: {details['display_quota']:.2f}\n"
                f"数量: {len(codes)}\n"
                f"兑换地址: {self._redemption_site_hint()}\n"
                "--------------------\n"
                f"{chr(10).join(codes)}"
            )
        if name == "knowledge_query":
            rows = await self.core.search_knowledge_items(str(action["keyword"]), 3)
            if not rows:
                return f"知识库里暂时没有找到：{action['keyword']}"
            polished = await self._polish_knowledge_answer(str(action["keyword"]), rows)
            if polished:
                return polished
            return "\n\n".join([f"#{row['id']} {row['question']}\n{row['answer']}" for row in rows])
        if name == "knowledge_add":
            item_id = await self.core.add_knowledge_item(str(action["question"]), str(action["answer"]), str(action.get("keywords", "")), event.get_sender_id())
            return f"知识库已添加，ID: {item_id}"
        if name == "knowledge_list":
            rows = await self.core.list_knowledge_items(20)
            if not rows:
                return "知识库暂时为空。"
            return "知识库列表：\n" + "\n".join([f"{row['id']}. {row['question']}" for row in rows])
        if name == "knowledge_delete":
            if not action.get("_confirmed"):
                pending_id = await self._create_pending_llm_action(event, action, f"删除知识库 #{action['item_id']}")
                return f"高风险操作已创建待确认 #{pending_id}。\n将执行：删除知识库 #{action['item_id']}\n请发送：/确认执行 {pending_id}"
            rows = await self.core.delete_knowledge_item(int(action["item_id"]))
            return "知识库已删除。" if rows > 0 else "删除失败：没有找到这个 ID。"
        if name == "web_search":
            blocked = self._web_search_allowed(event)
            if blocked:
                return blocked
            search_conf = self.config.get('web_search_settings', {})
            results = await self.core.web_search(str(action["query"]), search_conf)
            if not results:
                return "没有搜索到结果，或搜索接口暂时不可用。"
            summary = await self._summarize_web_results(str(action["query"]), results)
            return summary or self._format_search_results(results)
        if name == "read_webpage":
            blocked = self._web_search_allowed(event)
            if blocked:
                return blocked
            search_conf = self.config.get('web_search_settings', {})
            text = await self.core.fetch_webpage_text(str(action["url"]), int(search_conf.get('max_page_chars', 6000)))
            if not text:
                return "网页读取失败，可能是页面禁止抓取、需要登录，或不是普通网页。"
            summary = await self._summarize_web_results(str(action["url"]), [{"title": action["url"], "url": action["url"], "content": text}])
            return summary or f"网页正文摘录：\n{text[:2000]}"
        if name == "binding_audit":
            bind = await self.core.get_last_binding_action(int(action["qq_id"]), "BIND_CONFIRMED")
            unbind = await self.core.get_last_binding_action(int(action["qq_id"]), "UNBIND_SELF")
            pending = await self.core.get_pending_binding(int(action["qq_id"]))
            lines = [f"绑定记录查询：{action['qq_id']}"]
            lines.append(f"最近绑定：网站ID {bind.get('website_user_id')}，时间 {bind.get('created_at')}" if bind else "最近绑定：无记录")
            lines.append(f"最近解绑：网站ID {unbind.get('website_user_id')}，时间 {unbind.get('created_at')}" if unbind else "最近解绑：无记录")
            if pending:
                lines.append(f"待确认：网站ID {pending.get('website_user_id')}，过期 {pending.get('expires_at')}")
            return "\n".join(lines)
        if name in {"mute", "unmute", "whole_ban"}:
            if not isinstance(event, AiocqhttpMessageEvent) or not self._is_group_event(event):
                return "这个群管动作只能在群里使用。"
            group_id = int(event.get_group_id())
            if name == "whole_ban":
                if not action.get("_confirmed"):
                    pending_id = await self._create_pending_llm_action(event, action, "开启/关闭全体禁言")
                    return f"高风险操作已创建待确认 #{pending_id}。\n将执行：{'开启' if action.get('enable', True) else '关闭'}全体禁言\n请发送：/确认执行 {pending_id}"
                enable = bool(action.get("enable", True))
                await event.bot.set_group_whole_ban(group_id=group_id, enable=enable)
                return "已开启全体禁言。" if enable else "已关闭全体禁言。"
            user_id = int(action["user_id"])
            duration = int(action.get("seconds", 0)) if name == "mute" else 0
            await event.bot.set_group_ban(group_id=group_id, user_id=user_id, duration=max(0, duration))
            return f"已禁言 {user_id}，时长 {max(0, duration)} 秒。" if name == "mute" else f"已解除 {user_id} 的禁言。"
        return action.get("message") or "我没能把这句话转换成安全的管理动作。你可以说：给网站ID 32 加余额 10，或确认充值单 5。"

    @filter.command("小鱼管理", alias={"自然管理", "自然语言管理", "AI管理"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_llm_admin_command(self, event: AstrMessageEvent):
        """管理员自然语言管理入口。"""
        text = self._normal_text(event)
        for prefix in ("/小鱼管理", "小鱼管理", "/自然管理", "自然管理", "/自然语言管理", "自然语言管理", "/AI管理", "AI管理"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        if not text:
            yield event.plain_result("你可以这样说：小鱼管理 给网站ID 32 加余额 10 备注补单")
            return
        action = await self._parse_llm_admin_action(event, text)
        reply = await self._execute_llm_admin_action(event, action or {})
        yield event.plain_result(reply)

    @filter.command("确认执行")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_confirm_pending_action(self, event: AstrMessageEvent, action_id: int):
        row = await self.core.get_pending_action(int(action_id), int(event.get_sender_id()))
        if not row:
            yield event.plain_result("没有找到这个待确认操作，或它已经处理/过期/不属于你。")
            return
        expires_at = row.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            await self.core.mark_pending_action(int(action_id), "EXPIRED")
            yield event.plain_result("这个待确认操作已经过期。")
            return
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            await self.core.mark_pending_action(int(action_id), "FAILED")
            yield event.plain_result("待确认操作数据损坏，已取消。")
            return
        reply = await self._execute_llm_admin_action(event, payload)
        await self.core.mark_pending_action(int(action_id), "CONFIRMED")
        yield event.plain_result(reply)

    @filter.command("取消执行")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_cancel_pending_action(self, event: AstrMessageEvent, action_id: int):
        row = await self.core.get_pending_action(int(action_id), int(event.get_sender_id()))
        if not row:
            yield event.plain_result("没有找到这个待确认操作，或它已经处理/过期/不属于你。")
            return
        await self.core.mark_pending_action(int(action_id), "CANCELLED")
        yield event.plain_result("已取消该待确认操作。")

    @filter.command("查询余额")
    @require_binding
    async def handle_query_balance(self, event: AstrMessageEvent):
        """允许已绑定用户查询网站余额。"""
        binding = event.binding
        website_user_id = binding['website_user_id']
        api_user_data = await self.core.get_api_user_data(website_user_id)

        if not api_user_data:
            result = await self._private_first_result(
                event,
                "查询失败，无法从网站获取您的余额信息。请稍后再试或联系管理员。",
                group_notice="余额查询失败，我把说明私聊你了。",
            )
            yield result
            return

        binding_conf = self.config.get('binding_settings', {})
        ratio = binding_conf.get('quota_display_ratio', 500000)
        display_quota = api_user_data.get("quota", 0) / ratio

        reply = f"""查询成功！
--------------------
您绑定的网站ID: {website_user_id}
当前 NewAPI 余额: {display_quota:.2f}"""

        result = await self._private_first_result(event, reply, group_notice="余额已私聊你了。")
        yield result

    @filter.command("绑定")
    async def handle_bind_command(self, event: AstrMessageEvent, website_user_id: Optional[int] = None):
        """处理用户绑定请求，并执行校验。"""
        user_qq_id = event.get_sender_id()

        if website_user_id is None:
            result = await self._private_first_result(
                event,
                self._binding_help_text(),
                group_notice="我把绑定说明私聊你了。",
            )
            yield result
            return

        error_message = (
            await self._check_self_binding(user_qq_id) or
            await self._check_bind_cooldown(user_qq_id) or
            await self._check_qq_level(event, user_qq_id) or
            await self._check_api_user_exists(website_user_id) or
            await self._check_id_uniqueness(website_user_id) or
            await self._check_pending_id_uniqueness(website_user_id, int(user_qq_id))
        )

        if error_message:
            result = await self._private_first_result(
                event,
                error_message,
                group_notice="绑定没有完成，具体原因我私聊你了。",
            )
            yield result
            return

        source_group_id = int(event.get_group_id()) if self._is_group_event(event) else None
        await self.core.create_pending_binding(int(user_qq_id), int(website_user_id), source_group_id, ttl_minutes=10)
        message = (
            f"绑定确认\n"
            f"你正在把当前 QQ 绑定到 NewAPI 网站 ID：{website_user_id}\n\n"
            "请再次确认这个 ID 是你自己的。\n"
            "确认后，后续查询余额、充值入账都会进入这个网站账号。\n"
            "如果 ID 填成别人的，充值也会充到别人账号上。\n\n"
            "10 分钟内发送：确认绑定\n"
            "如果填错了，重新发送 /绑定 正确网站ID 即可覆盖这次申请。"
        )
        result = await self._private_first_result(
            event,
            message,
            group_notice="绑定确认已私聊你了，请看清网站 ID 后再确认。",
        )
        yield result

    @filter.command("确认绑定", alias={"确定绑定"})
    async def handle_confirm_bind_command(self, event: AstrMessageEvent):
        """确认待处理的绑定申请。"""
        user_qq_id = int(event.get_sender_id())
        pending = await self.core.get_pending_binding(user_qq_id)
        if not pending:
            result = await self._private_first_result(
                event,
                "没有找到待确认的绑定申请。请先发送 /绑定 你的网站ID。",
                group_notice="没有待确认的绑定申请，我把说明私聊你了。",
            )
            yield result
            return

        expires_at = pending.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            await self.core.mark_pending_binding(int(pending["id"]), "EXPIRED")
            result = await self._private_first_result(
                event,
                "这次绑定申请已经超过 10 分钟，请重新发送 /绑定 你的网站ID。",
                group_notice="绑定申请已过期，我把说明私聊你了。",
            )
            yield result
            return

        website_user_id = int(pending["website_user_id"])
        error_message = (
            await self._check_self_binding(user_qq_id) or
            await self._check_bind_cooldown(user_qq_id) or
            await self._check_api_user_exists(website_user_id) or
            await self._check_id_uniqueness(website_user_id) or
            await self._check_pending_id_uniqueness(website_user_id, int(user_qq_id))
        )
        if error_message:
            await self.core.mark_pending_binding(int(pending["id"]), "CANCELLED")
            result = await self._private_first_result(
                event,
                error_message,
                group_notice="绑定没有完成，具体原因我私聊你了。",
            )
            yield result
            return

        success, message = await self._perform_binding_ritual(user_qq_id, website_user_id)
        await self.core.mark_pending_binding(int(pending["id"]), "CONFIRMED" if success else "FAILED")

        if success:
            await self.core.log_binding_action(
                user_qq_id,
                website_user_id,
                "BIND_CONFIRMED",
                pending.get("source_group_id"),
            )
            await self._send_success_pm(event, user_qq_id, website_user_id)

        result = await self._private_first_result(
            event,
            message,
            group_notice="绑定结果已私聊你了。",
        )
        yield result

    @filter.command("自助解绑", alias={"解除绑定", "取消绑定"})
    @require_binding
    async def handle_self_unbind_command(self, event: AstrMessageEvent):
        """允许用户解除自己的 QQ 与网站 ID 绑定。"""
        user_qq_id = event.get_sender_id()
        website_user_id = event.binding['website_user_id']
        rows = await self.core.delete_binding(qq_id=user_qq_id)
        if rows > 0:
            source_group_id = int(event.get_group_id()) if self._is_group_event(event) else None
            await self.core.log_binding_action(int(user_qq_id), int(website_user_id), "UNBIND_SELF", source_group_id)
            message = (
                f"已解除绑定。\n"
                f"当前 QQ 不再绑定 NewAPI 网站 ID {website_user_id}。\n"
                "后续查询余额、充值入账前，请重新使用 /绑定 网站ID。\n"
                "为防止误操作，解绑后短时间内不能反复换绑。"
            )
        else:
            message = "解绑失败：没有找到你的绑定记录，请稍后重试或联系管理员。"
        result = await self._private_first_result(event, message, group_notice="解绑结果已私聊你了。")
        yield result

    @filter.command("签到")
    @require_binding
    async def handle_check_in(self, event: AstrMessageEvent):
        """处理用户每日签到请求。"""
        user_qq_id = event.get_sender_id()
        
        status, details = await self.core.perform_check_in(user_qq_id, binding=event.binding)
        
        check_in_conf = self.config.get('check_in_settings', {})
        
        reply = ""
        match status:
            case "SUCCESS":
                first_bonus_enabled = check_in_conf.get('first_check_in_bonus_enabled', False)
                
                if details["is_first"] and first_bonus_enabled:
                    template = check_in_conf.get('first_check_in_success_template')
                elif details["is_doubled"]:
                    template = check_in_conf.get('check_in_doubled_template')
                else:
                    template = check_in_conf.get('check_in_success_template')
                
                reply = template.format(
                    display_added=f"{details['display_added']:.2f}", 
                    display_total=f"{details['display_total']:.2f}",
                    user_qq=details['user_qq'],
                    site_id=details['site_id']
                )
            case "DISABLED":
                reply = "抱歉，每日签到功能当前未开启。"
            case "DISABLED_BY_NEWAPI":
                reply = "抱歉，NewAPI 后台当前关闭了每日签到，QQ 签到已同步关闭。"
            case "ALREADY_CHECKED_IN":
                reply = "您今天已经签过到了，请明天再来吧！"
            case "API_USER_NOT_FOUND":
                reply = "签到失败：无法获取您的网站用户信息，请联系管理员。"
            case "API_UPDATE_FAILED":
                reply = "签到失败：向网站服务器更新余额时发生错误，请稍后再试。"
            case _:
                reply = "签到时发生未知错误，请联系管理员。"
        
        yield event.plain_result(reply)

    @filter.command("解绑")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_unbind_command(self, event: AstrMessageEvent, website_user_id: int):
        """(管理员) 强制解除指定网站ID的绑定。"""
        success, binding_info = await self.core.purge_user_binding(website_user_id)
        
        reply = ""
        if success:
            reply = (
                f"✅ 操作成功！\n"
                f"已将网站ID: {website_user_id}\n"
                f"从QQ用户: {binding_info['qq_id']} 的契约中解放。"
            )
        else:
            if binding_info is None:
                reply = f"❌ 操作无效：未找到网站ID {website_user_id} 的绑定记录。"
            else:
                reply = f"❌ 操作失败：在为网站ID {website_user_id} 执行净化时发生未知错误，请检查后台日志。"
                
        yield event.plain_result(reply)

    @filter.command("查询")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_universal_lookup(self, event: AstrMessageEvent, identifier: int):
        """(管理员) 智能查询，自动识别网站ID或QQ号。"""
        id_type, binding = await self.core.lookup_binding(identifier)
        
        reply = ""
        match id_type:
            case "WEBSITE_ID":
                reply = f"""✅ 查询成功！输入的是【网站ID】
--------------------
网站ID: {binding['website_user_id']}
已绑定至QQ: {binding['qq_id']}
绑定时间: {binding['binding_time'].strftime('%Y-%m-%d %H:%M:%S')}"""
            case "QQ_ID":
                reply = f"""✅ 查询成功！输入的是【QQ号】
--------------------
QQ号: {binding['qq_id']}
已绑定至网站ID: {binding['website_user_id']}
绑定时间: {binding['binding_time'].strftime('%Y-%m-%d %H:%M:%S')}"""
            case "NOT_FOUND":
                reply = f"❌ 查询失败：未在绑定记录中找到与 {identifier} 相关的任何信息。"
        
        yield event.plain_result(reply)

    async def _query_api_balance_text(self, identifier: int) -> str:
        website_user_id = await self.core.resolve_website_user_id(identifier)
        if website_user_id is None:
            return f"未找到 {identifier} 对应的绑定用户或网站用户。"
        api_user_data = await self.core.get_api_user_data(website_user_id)
        if not api_user_data:
            return f"无法从网站获取 ID {website_user_id} 的用户信息。"
        ratio = self.config.get('binding_settings.quota_display_ratio', 500000)
        display_quota = api_user_data.get("quota", 0) / ratio
        username = api_user_data.get("username", "未知")
        group = api_user_data.get("group", "未知")
        return (
            f"NewAPI 用户余额\n"
            f"网站ID: {website_user_id}\n"
            f"用户名: {username}\n"
            f"用户组: {group}\n"
            f"当前 NewAPI 余额: {display_quota:.2f}\n"
            f"内部 quota: {api_user_data.get('quota', 0)}\n"
            f"换算: 1 余额 = {ratio} quota"
        )

    async def _admin_adjust_quota(self, event: AstrMessageEvent, identifier: int, amount: float, reason: str = ""):
        status, details = await self.core.adjust_balance_by_identifier(identifier, amount)
        if status == "SUCCESS":
            await self.core.log_quota_adjustment(event.get_sender_id(), identifier, details['website_user_id'], amount, reason)
            action_text = "增加" if amount >= 0 else "减少"
            return (
                f"操作成功。\n"
                f"目标网站ID: {details['website_user_id']}\n"
                f"本次{action_text} NewAPI 余额: {abs(details.get('display_delta', amount)):.2f}\n"
                f"当前 NewAPI 余额: {details['new_display_quota']:.2f}"
            )
        if status == "USER_NOT_FOUND":
            return f"操作失败：未找到 {identifier} 对应的绑定用户或网站用户。"
        if status == "API_FETCH_FAILED":
            return f"操作失败：无法从网站获取 ID {details['website_user_id']} 的用户信息。"
        if status == "API_UPDATE_FAILED":
            return f"操作失败：向网站更新 ID {details['website_user_id']} 的余额时发生错误。"
        return "操作失败：未知错误。"

    @filter.command("查余额", alias={"查额度", "管理员查余额"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_admin_query_balance(self, event: AstrMessageEvent, identifier: int):
        """(管理员) 查询任意绑定用户或网站 ID 的余额。"""
        yield event.plain_result(await self._query_api_balance_text(identifier))

    @filter.command("调整余额")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_adjust_balance(self, event: AstrMessageEvent, identifier: int, display_adjustment: float, reason: str = ""):
        """(管理员) 智能识别ID，并调整用户 NewAPI 余额。"""
        yield event.plain_result(await self._admin_adjust_quota(event, identifier, display_adjustment, reason))

    @filter.command("加款", alias={"加额度", "加余额"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_add_quota(self, event: AstrMessageEvent, identifier: int, amount: float, reason: str = ""):
        """(管理员) 给用户增加 NewAPI 余额。"""
        yield event.plain_result(await self._admin_adjust_quota(event, identifier, abs(amount), reason))

    @filter.command("扣款", alias={"扣额度", "扣余额"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_subtract_quota(self, event: AstrMessageEvent, identifier: int, amount: float, reason: str = ""):
        """(管理员) 给用户减少 NewAPI 余额。"""
        yield event.plain_result(await self._admin_adjust_quota(event, identifier, -abs(amount), reason))

    def _redemption_site_hint(self) -> str:
        base_url = getattr(self.core, "api_base_url", "") or "你的 NewAPI 网站"
        return f"{base_url.rstrip('/')}/#/wallet" if base_url.startswith("http") else base_url

    @filter.command("生成兑换码", alias={"创建兑换码", "生成原生兑换码", "批量生成兑换码"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_create_redeem_code(self, event: AstrMessageEvent, name: str, amount: float, count: int = 1):
        """(管理员) 创建 NewAPI 原生兑换码。"""
        count = max(1, min(int(count), 100))
        ok, details = await self.core.create_native_redemption_codes(name, amount, count)
        if not ok:
            yield event.plain_result(f"NewAPI 原生兑换码创建失败：{details.get('message', '未知错误')}")
            return

        codes = [str(code) for code in details.get("codes", [])]
        if not codes:
            yield event.plain_result("NewAPI 返回成功，但没有返回兑换码列表。请到 NewAPI 后台确认。")
            return

        reply = (
            "NewAPI 原生兑换码已创建。\n"
            f"活动名: {details['name']}\n"
            f"每张余额: {details['display_quota']:.2f}\n"
            f"数量: {len(codes)}\n"
            f"兑换地址: {self._redemption_site_hint()}\n"
            "--------------------\n"
            f"{chr(10).join(codes)}"
        )
        result = await self._private_first_result(event, reply, group_notice="NewAPI 原生兑换码已生成，列表已私聊你。")
        yield result

    @filter.command("兑换", alias={"使用兑换码"})
    async def handle_redeem_code(self, event: AstrMessageEvent, code: str):
        """提示用户到 NewAPI 网站兑换原生兑换码。"""
        msg = (
            "现在只使用 NewAPI 原生兑换码体系。\n"
            "机器人不会代替用户兑换，避免两边数据库不一致。\n\n"
            f"你的兑换码: {code}\n"
            f"请到 NewAPI 网站钱包页面自行兑换：{self._redemption_site_hint()}"
        )
        result = await self._private_first_result(event, msg, group_notice="兑换说明已私聊你了。")
        yield result

    @filter.command("充值")
    @require_binding
    async def handle_recharge_order(self, event: AstrMessageEvent, amount: float, note: str = ""):
        """创建待审核充值单。OCR/支付截图后续会接入这个流程。"""
        order_id = await self.core.create_recharge_order(event.get_sender_id(), event.binding['website_user_id'], amount, note)
        msg = (
            f"充值单已创建，等待管理员确认。\n"
            f"订单号: {order_id}\n"
            f"网站ID: {event.binding['website_user_id']}\n"
            f"充值金额/入账余额: {amount:.2f}\n"
            "管理员确认后才会入账。"
        )
        result = await self._private_first_result(event, msg, group_notice="充值单已创建，详情已私聊你。")
        yield result

    @filter.command("确认充值")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_confirm_recharge(self, event: AstrMessageEvent, order_id: int):
        order = await self.core.get_recharge_order(order_id)
        if not order:
            yield event.plain_result("未找到该充值单。")
            return
        if order.get('status') != 'PENDING':
            yield event.plain_result(f"该充值单已处理，当前状态：{order.get('status')}")
            return
        rows = await self.core.mark_recharge_order(order_id, 'APPROVED', event.get_sender_id())
        if rows <= 0:
            yield event.plain_result("确认失败：订单可能已被处理。")
            return
        yield event.plain_result(await self._admin_adjust_quota(event, int(order['website_user_id']), float(order['amount']), f"充值单#{order_id}"))

    @filter.command("拒绝充值")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_reject_recharge(self, event: AstrMessageEvent, order_id: int):
        order = await self.core.get_recharge_order(order_id)
        if not order:
            yield event.plain_result("未找到该充值单。")
            return
        rows = await self.core.mark_recharge_order(order_id, 'REJECTED', event.get_sender_id())
        yield event.plain_result("已拒绝该充值单。" if rows > 0 else "拒绝失败：订单可能已被处理。")

    def _parse_knowledge_payload(self, payload: str, expected: int = 3) -> list[str]:
        return [p.strip() for p in re.split(r"\s*\|\s*", payload or "", maxsplit=expected - 1)]

    @filter.command("知识库添加", alias={"添加知识", "新增知识"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_knowledge_add(self, event: AstrMessageEvent):
        text = self._normal_text(event)
        for prefix in ("/知识库添加", "知识库添加", "/添加知识", "添加知识", "/新增知识", "新增知识"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        parts = self._parse_knowledge_payload(text, expected=3)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            yield event.plain_result("格式：/知识库添加 问题 | 答案 | 关键词")
            return
        question, answer = parts[0], parts[1]
        keywords = parts[2] if len(parts) >= 3 else ""
        item_id = await self.core.add_knowledge_item(question, answer, keywords, event.get_sender_id())
        yield event.plain_result(f"知识库已添加，ID: {item_id}")

    @filter.command("知识库修改", alias={"修改知识"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_knowledge_update(self, event: AstrMessageEvent):
        text = self._normal_text(event)
        for prefix in ("/知识库修改", "知识库修改", "/修改知识", "修改知识"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        parts = self._parse_knowledge_payload(text, expected=4)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1] or not parts[2]:
            yield event.plain_result("格式：/知识库修改 ID | 问题 | 答案 | 关键词")
            return
        keywords = parts[3] if len(parts) >= 4 else ""
        rows = await self.core.update_knowledge_item(int(parts[0]), parts[1], parts[2], keywords)
        yield event.plain_result("知识库已修改。" if rows > 0 else "修改失败：没有找到这个 ID。")

    @filter.command("知识库删除", alias={"删除知识"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_knowledge_delete(self, event: AstrMessageEvent, item_id: int):
        rows = await self.core.delete_knowledge_item(int(item_id))
        yield event.plain_result("知识库已删除。" if rows > 0 else "删除失败：没有找到这个 ID。")

    @filter.command("知识库列表", alias={"知识列表"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_knowledge_list(self, event: AstrMessageEvent):
        rows = await self.core.list_knowledge_items(20)
        if not rows:
            yield event.plain_result("知识库暂时为空。")
            return
        lines = ["知识库列表："]
        for row in rows:
            kw = f" [{row.get('keywords')}]" if row.get('keywords') else ""
            lines.append(f"{row['id']}. {row['question']}{kw}")
        yield event.plain_result("\n".join(lines))

    @filter.command("知识库查询", alias={"查知识", "知识查询"})
    async def handle_knowledge_query(self, event: AstrMessageEvent, keyword: str = ""):
        keyword = (keyword or "").strip()
        if not keyword:
            yield event.plain_result("格式：/知识库查询 关键词")
            return
        rows = await self.core.search_knowledge_items(keyword, 3)
        if not rows:
            result = await self._private_first_result(event, f"知识库里暂时没有找到：{keyword}", group_notice="知识库没查到，我把结果私聊你了。")
            yield result
            return
        polished = await self._polish_knowledge_answer(keyword, rows)
        if polished:
            msg = polished
        elif len(rows) == 1:
            row = rows[0]
            msg = f"知识库 #{row['id']}\n问题：{row['question']}\n答案：{row['answer']}"
        else:
            blocks = [f"#{row['id']} {row['question']}\n{row['answer']}" for row in rows]
            msg = "知识库匹配结果：\n--------------------\n" + "\n\n".join(blocks)
        result = await self._private_first_result(event, msg, group_notice="知识库结果已私聊你了。")
        yield result

    @filter.command("今日消耗", alias={"我的今日消耗", "今日用量"})
    async def handle_today_usage(self, event: AstrMessageEvent, identifier: Optional[int] = None):
        if identifier is None:
            binding = await self.core.get_user_by_qq(event.get_sender_id())
            if not binding:
                result = await self._private_first_result(
                    event,
                    "你还没有绑定 NewAPI 网站账号，无法查询自己的今日消耗。请先 /绑定 网站ID。",
                    group_notice="你还没绑定，我把说明私聊你了。",
                )
                yield result
                return
            website_user_id = int(binding["website_user_id"])
            target_text = f"网站ID: {website_user_id}"
        else:
            if not event.is_admin():
                yield event.plain_result("只有管理员可以查询指定用户消耗。")
                return
            website_user_id = await self.core.resolve_website_user_id(int(identifier))
            if website_user_id is None:
                yield event.plain_result(f"未找到 {identifier} 对应的绑定用户或网站用户。")
                return
            target_text = f"网站ID: {website_user_id}"
        start_ts, end_ts = self._today_range_timestamps()
        page_size, max_pages = self._usage_stats_settings()
        stats = await self.core.summarize_usage_logs(start_ts, end_ts, user_id=int(website_user_id), page_size=page_size, max_pages=max_pages)
        result = await self._private_first_result(event, self._format_usage_summary("今日消耗", stats, target_text), group_notice="今日消耗已私聊你了。")
        yield result

    @filter.command("全站今日消耗", alias={"今日全站消耗", "全站用量"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_site_today_usage(self, event: AstrMessageEvent):
        start_ts, end_ts = self._today_range_timestamps()
        page_size, max_pages = self._usage_stats_settings()
        stats = await self.core.summarize_usage_logs(start_ts, end_ts, page_size=page_size, max_pages=max_pages)
        yield event.plain_result(self._format_usage_summary("全站今日消耗", stats))

    @filter.command("今日排行", alias={"消耗排行", "今日消耗排行"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_today_usage_ranking(self, event: AstrMessageEvent, limit: int = 10):
        start_ts, end_ts = self._today_range_timestamps()
        page_size, max_pages = self._usage_stats_settings()
        stats = await self.core.summarize_usage_logs(start_ts, end_ts, page_size=page_size, max_pages=max_pages)
        users = stats.get("users", [])[:max(1, min(int(limit), 30))]
        if not users:
            yield event.plain_result("今日暂无消耗记录。")
            return
        lines = ["今日消耗排行", "--------------------"]
        for idx, user in enumerate(users, 1):
            amount = self._display_usage_amount(int(user.get("quota") or 0))
            lines.append(f"{idx}. {user.get('username')} (ID:{user.get('user_id')}) - {amount:.4f} / {user.get('requests')} 次")
        if stats.get("truncated"):
            lines.append("提示：日志较多，本次只统计了配置允许的最大页数，排行可能不完整。")
        yield event.plain_result("\n".join(lines))

    @filter.command("搜索", alias={"联网搜索", "web搜索"})
    async def handle_web_search(self, event: AstrMessageEvent, query: str = ""):
        query = (query or "").strip()
        if not query:
            yield event.plain_result("格式：/搜索 关键词")
            return
        blocked = self._web_search_allowed(event)
        if blocked:
            yield event.plain_result(blocked)
            return
        search_conf = self.config.get('web_search_settings', {})
        results = await self.core.web_search(query, search_conf)
        if not results:
            yield event.plain_result("没有搜索到结果，或搜索接口暂时不可用。")
            return
        if search_conf.get('fetch_pages', False):
            max_pages = int(search_conf.get('fetch_page_count', 3))
            max_chars = int(search_conf.get('max_page_chars', 6000))
            for item in results[:max_pages]:
                item["content"] = await self.core.fetch_webpage_text(item.get("url", ""), max_chars)
        summary = await self._summarize_web_results(query, results)
        msg = summary or self._format_search_results(results)
        result = await self._private_first_result(event, msg, group_notice="联网搜索结果已私聊你了。")
        yield result

    @filter.command("读网页", alias={"阅读网页"})
    async def handle_read_webpage(self, event: AstrMessageEvent, url: str = ""):
        url = (url or "").strip()
        if not url:
            yield event.plain_result("格式：/读网页 https://example.com")
            return
        blocked = self._web_search_allowed(event)
        if blocked:
            yield event.plain_result(blocked)
            return
        search_conf = self.config.get('web_search_settings', {})
        text = await self.core.fetch_webpage_text(url, int(search_conf.get('max_page_chars', 6000)))
        if not text:
            yield event.plain_result("网页读取失败，可能是页面禁止抓取、需要登录，或不是普通网页。")
            return
        summary = await self._summarize_web_results(url, [{"title": url, "url": url, "content": text}])
        msg = summary or f"网页正文摘录：\n{text[:2000]}"
        result = await self._private_first_result(event, msg, group_notice="网页阅读结果已私聊你了。")
        yield result

    @filter.command("查绑定记录")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_binding_audit_lookup(self, event: AstrMessageEvent, qq_id: int):
        """(管理员) 查看某个 QQ 最近一次绑定/解绑动作。"""
        bind = await self.core.get_last_binding_action(int(qq_id), "BIND_CONFIRMED")
        unbind = await self.core.get_last_binding_action(int(qq_id), "UNBIND_SELF")
        pending = await self.core.get_pending_binding(int(qq_id))
        lines = [f"绑定记录查询：{qq_id}"]
        if bind:
            lines.append(f"最近绑定：网站ID {bind.get('website_user_id')}，时间 {bind.get('created_at')}")
        else:
            lines.append("最近绑定：无记录")
        if unbind:
            lines.append(f"最近解绑：网站ID {unbind.get('website_user_id')}，时间 {unbind.get('created_at')}")
        else:
            lines.append("最近解绑：无记录")
        if pending:
            lines.append(f"待确认：网站ID {pending.get('website_user_id')}，过期 {pending.get('expires_at')}")
        yield event.plain_result("\n".join(lines))

    def _at_user_ids(self, event: AstrMessageEvent) -> list[int]:
        ids = []
        for seg in event.get_messages():
            if isinstance(seg, At):
                try:
                    ids.append(int(seg.qq))
                except Exception:
                    pass
        return ids

    @filter.command("禁言")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_group_ban(self, event: AstrMessageEvent, seconds: int, target: Optional[int] = None):
        """(管理员) 禁言群成员：/禁言 60 @用户"""
        if not isinstance(event, AiocqhttpMessageEvent) or not self._is_group_event(event):
            yield event.plain_result("这个命令只能在群里使用。")
            return
        targets = self._at_user_ids(event)
        if target:
            targets.append(int(target))
        targets = [uid for uid in dict.fromkeys(targets) if uid != int(event.get_self_id())]
        if not targets:
            yield event.plain_result("请 @ 要禁言的人，或提供 QQ 号。")
            return
        duration = max(0, int(seconds))
        for uid in targets:
            await event.bot.set_group_ban(group_id=int(event.get_group_id()), user_id=int(uid), duration=duration)
        yield event.plain_result(f"已禁言 {len(targets)} 人，时长 {duration} 秒。")

    @filter.command("解禁")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_group_unban(self, event: AstrMessageEvent, target: Optional[int] = None):
        """(管理员) 解除禁言：/解禁 @用户"""
        if not isinstance(event, AiocqhttpMessageEvent) or not self._is_group_event(event):
            yield event.plain_result("这个命令只能在群里使用。")
            return
        targets = self._at_user_ids(event)
        if target:
            targets.append(int(target))
        targets = [uid for uid in dict.fromkeys(targets) if uid != int(event.get_self_id())]
        if not targets:
            yield event.plain_result("请 @ 要解禁的人，或提供 QQ 号。")
            return
        for uid in targets:
            await event.bot.set_group_ban(group_id=int(event.get_group_id()), user_id=int(uid), duration=0)
        yield event.plain_result(f"已解除 {len(targets)} 人的禁言。")

    @filter.command("全体禁言")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_group_whole_ban(self, event: AstrMessageEvent):
        """(管理员) 开启全体禁言。"""
        if not isinstance(event, AiocqhttpMessageEvent) or not self._is_group_event(event):
            yield event.plain_result("这个命令只能在群里使用。")
            return
        await event.bot.set_group_whole_ban(group_id=int(event.get_group_id()), enable=True)
        yield event.plain_result("已开启全体禁言。")

    @filter.command("全体解禁", alias={"全员解禁"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def handle_group_whole_unban(self, event: AstrMessageEvent):
        """(管理员) 关闭全体禁言。"""
        if not isinstance(event, AiocqhttpMessageEvent) or not self._is_group_event(event):
            yield event.plain_result("这个命令只能在群里使用。")
            return
        await event.bot.set_group_whole_ban(group_id=int(event.get_group_id()), enable=False)
        yield event.plain_result("已关闭全体禁言。")

    @filter.command("打劫")
    async def handle_heist_command(self, event: AstrMessageEvent):
        """(娱乐) 对 @ 的目标发起打劫。"""
        robber_qq_id = event.get_sender_id()

        # 1. 提取目标QQ
        target_qq_ids = [
            seg.qq  # 从At消息段中提取qq号
            for seg in event.get_messages()
            if isinstance(seg, At) and seg.qq != int(event.get_self_id())
        ]

        # 2. 校验
        if not target_qq_ids:
            yield event.plain_result("🤔 打劫谁呢？请 @ 你要打劫的目标。" )
            return
        if len(target_qq_ids) > 1:
            yield event.plain_result("🏃‍♂️ 不要太贪心，一次只能打劫一个目标！" )
            return

        # 3. 获取受害者QQ号
        victim_qq_id = target_qq_ids[0]
        
        status, details = await self.heist_handler.execute_heist(robber_qq_id, victim_qq_id)
        
        # 4. 根据结果生成回复
        heist_conf = self.config.get('heist_settings', {})
        reply = ""

        # --- 缓存模板 ---
        success_template = heist_conf.get('success_template', "成功: +{gain:.2f}")
        critical_template = heist_conf.get('critical_template', "暴击: +{gain:.2f}")
        failure_template = heist_conf.get('failure_template', "失败: -{penalty:.2f}")
        disabled_template = heist_conf.get('disabled_template', "⚔️ 打劫活动尚未开启。" )
        robber_not_bound_template = heist_conf.get('robber_not_bound_template', "🤔 请先绑定账号。" )
        victim_not_found_template = heist_conf.get('victim_not_found_template', "💨 未找到目标 {victim_identifier}。" )
        cannot_rob_self_template = heist_conf.get('cannot_rob_self_template', "🤦‍♂️ 不能打劫自己。" )
        attempts_exceeded_template = heist_conf.get('attempts_exceeded_template', "🥵 次数用尽。" )
        defenses_exceeded_template = heist_conf.get('defenses_exceeded_template', "🛡️ 对方已有防备 (ID:{victim_id})。" )
        cooldown_template = heist_conf.get('cooldown_template', "⏳ 冷却中，剩余 {remaining_time} 秒。")
        # --- 缓存结束 ---

        match status:
            case "SUCCESS":
                reply = success_template.format(gain=details['gain'])
            case "CRITICAL":
                reply = critical_template.format(gain=details['gain'])
            case "FAILURE":
                reply = failure_template.format(penalty=details['penalty'])
            case "DISABLED":
                reply = disabled_template
            case "ROBBER_NOT_BOUND":
                reply = robber_not_bound_template
            case "VICTIM_NOT_FOUND":
                reply = victim_not_found_template.format(victim_identifier=f" @{victim_qq_id}")
            case "CANNOT_ROB_SELF":
                reply = cannot_rob_self_template
            case "ATTEMPTS_EXCEEDED":
                reply = attempts_exceeded_template
            case "DEFENSES_EXCEEDED":
                reply = defenses_exceeded_template.format(victim_id=details['victim_id'])
            case "COOLDOWN_ACTIVE":
                reply = cooldown_template.format(remaining_time=details['remaining_time'])
            case "API_ERROR":
                reply = "- 发生了一个API错误，请联系管理员。"
            case _:
                reply = "❓ 发生未知错误。"
        
        yield event.plain_result(reply)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_add_request(self, event: AstrMessageEvent):
        """按可配置规则处理入群申请。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return

        raw = event.message_obj.raw_message
        if not (
            isinstance(raw, dict)
            and raw.get("post_type") == "request"
            and raw.get("request_type") == "group"
            and raw.get("sub_type") == "add"
        ):
            return

        approval_conf = self.config.get('join_approval_settings', {})
        if not approval_conf.get('enabled', False):
            return

        group_id = int(raw.get("group_id", 0) or 0)
        user_id = int(raw.get("user_id", 0) or 0)
        flag = raw.get("flag", "")
        comment = str(raw.get("comment") or "")
        if not group_id or not user_id or not flag:
            return

        groups = [int(g) for g in approval_conf.get('group_list', []) if str(g).isdigit()]
        if groups and group_id not in groups:
            return

        mode = str(approval_conf.get('mode', 'auto_approve')).strip().lower()
        comment_lower = comment.lower()
        reject_reason = approval_conf.get('reject_reason', '入群申请未通过，请联系管理员。')
        decision: Optional[bool] = None
        reason = ""
        newapi_matched = False
        newapi_reason = ""

        blacklist_qq = {int(q) for q in approval_conf.get('blacklist_qq', []) if str(q).isdigit()}
        blacklist_keywords = [str(k).lower() for k in approval_conf.get('blacklist_keywords', []) if str(k).strip()]
        if user_id in blacklist_qq:
            decision, reason = False, "黑名单 QQ"
        elif any(k in comment_lower for k in blacklist_keywords):
            decision, reason = False, "命中黑名单关键词"
        elif mode == "newapi_user" or approval_conf.get('allow_newapi_identity_match', False):
            newapi_matched, newapi_reason = await self._match_newapi_identity_from_comment(comment)
            if newapi_matched:
                decision, reason = True, newapi_reason
            elif mode == "newapi_user":
                decision, reason = None, newapi_reason
        elif mode == "auto_approve":
            decision, reason = True, "自动放行"
        elif mode == "keyword":
            keywords = [str(k).lower() for k in approval_conf.get('approve_keywords', []) if str(k).strip()]
            decision = any(k in comment_lower for k in keywords) if keywords else None
            reason = "命中放行关键词" if decision else "等待管理员审批"
        elif mode == "manual":
            decision, reason = None, "等待管理员审批"
        elif mode == "reject":
            decision, reason = False, "配置为自动拒绝"
        else:
            decision, reason = None, f"未知审批模式: {mode}"

        nickname = str(user_id)
        try:
            info = await event.bot.get_stranger_info(user_id=user_id)
            nickname = info.get("nickname") or nickname
        except Exception:
            pass

        if decision is not None:
            try:
                await event.bot.set_group_add_request(
                    flag=flag,
                    sub_type="add",
                    approve=decision,
                    reason="" if decision else reject_reason,
                )
            except Exception as e:
                logger.warning(f"NewAPI 入群审批 set_group_add_request 失败: {e}")
                return

        notify_template = approval_conf.get(
            'notify_template',
            "入群申请：{decision_text}\n群号：{group_id}\n昵称：{nickname}\nQQ：{user_id}\n理由：{comment}\nflag：{flag}\n原因：{reason}"
        )
        decision_text = "已同意" if decision is True else "已拒绝" if decision is False else "待人工审批"
        notice = self._format_template(
            notify_template,
            decision_text=decision_text,
            group_id=group_id,
            nickname=nickname,
            user_id=user_id,
            comment=comment or "无",
            flag=flag,
            reason=reason,
        )

        notify_group = int(approval_conf.get('notify_group_id') or 0)
        notify_admins = approval_conf.get('notify_admin_private', False)
        if notify_group:
            try:
                await event.bot.send_group_msg(group_id=notify_group, message=notice)
            except Exception as e:
                logger.warning(f"发送入群审批群通知失败: {e}")
        if notify_admins:
            admin_ids = [int(q) for q in approval_conf.get('notify_admin_qq_list', []) if str(q).isdigit()]
            for admin_id in admin_ids:
                try:
                    await event.bot.send_private_msg(user_id=admin_id, message=notice)
                except Exception as e:
                    logger.warning(f"发送入群审批私聊通知失败({admin_id}): {e}")

        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=98)
    async def handle_relationship_request(self, event: AstrMessageEvent):
        """处理好友申请和邀请机器人进群，覆盖 relationship 插件的安全子集。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return

        raw = event.message_obj.raw_message
        if not (
            isinstance(raw, dict)
            and raw.get("post_type") == "request"
            and raw.get("request_type") in {"friend", "group"}
        ):
            return

        conf = self.config.get('relationship_request_settings', {})
        if not conf.get('enabled', True):
            return

        request_type = str(raw.get("request_type"))
        sub_type = str(raw.get("sub_type") or "")
        if request_type == "group" and sub_type != "invite":
            return

        user_id = int(raw.get("user_id", 0) or 0)
        group_id = int(raw.get("group_id", 0) or 0)
        flag = raw.get("flag", "")
        comment = str(raw.get("comment") or "")
        if not user_id or not flag:
            return

        decision: Optional[bool] = None
        reason = ""
        reject_reason = conf.get('reject_reason', '暂不接受该申请，请联系管理员。')

        if request_type == "friend":
            blacklist = {int(q) for q in conf.get('friend_blacklist_qq', []) if str(q).isdigit()}
            if user_id in blacklist:
                decision, reason = False, "命中好友黑名单"
            elif conf.get('auto_reject_friend', False):
                decision, reason = False, "配置为自动拒绝好友申请"
            elif conf.get('auto_agree_friend', False):
                decision, reason = True, "自动同意好友申请"
            else:
                decision, reason = None, "等待管理员处理好友申请"
        else:
            blacklist = {int(g) for g in conf.get('group_blacklist', []) if str(g).isdigit()}
            if group_id in blacklist:
                decision, reason = False, "命中群邀请黑名单"
            elif conf.get('auto_reject_group_invite', False):
                decision, reason = False, "配置为自动拒绝群邀请"
            elif conf.get('auto_agree_group_invite', False):
                decision, reason = True, "自动同意群邀请"
            else:
                decision, reason = None, "等待管理员处理群邀请"

        if decision is not None:
            try:
                if request_type == "friend":
                    await event.bot.set_friend_add_request(flag=flag, approve=decision)
                else:
                    await event.bot.set_group_add_request(
                        flag=flag,
                        sub_type="invite",
                        approve=decision,
                        reason="" if decision else reject_reason,
                    )
            except Exception as e:
                logger.warning(f"NewAPI 申请处理失败({request_type}): {e}")
                return

        request_label = "好友申请" if request_type == "friend" else "群邀请"
        decision_text = "已同意" if decision is True else "已拒绝" if decision is False else "待人工处理"
        template = conf.get(
            'notify_template',
            "{request_type}：{decision_text}\n群号：{group_id}\nQQ：{user_id}\n理由：{comment}\nflag：{flag}\n原因：{reason}"
        )
        notice = self._format_template(
            template,
            request_type=request_label,
            decision_text=decision_text,
            group_id=group_id or "无",
            user_id=user_id,
            comment=comment or "无",
            flag=flag,
            reason=reason,
        )

        if conf.get('notify_admin_private', True):
            admin_ids = [int(q) for q in conf.get('notify_admin_qq_list', []) if str(q).isdigit()]
            if not admin_ids:
                approval_conf = self.config.get('join_approval_settings', {})
                admin_ids = [int(q) for q in approval_conf.get('notify_admin_qq_list', []) if str(q).isdigit()]
            for admin_id in admin_ids:
                try:
                    await event.bot.send_private_msg(user_id=admin_id, message=notice)
                except Exception as e:
                    logger.warning(f"发送好友/群邀请通知失败({admin_id}): {e}")

        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_increase(self, event: AstrMessageEvent):
        """监听新成员入群，发送绑定提示。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return

        raw = event.message_obj.raw_message
        if not (
            isinstance(raw, dict)
            and raw.get("post_type") == "notice"
            and raw.get("notice_type") == "group_increase"
        ):
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        if not group_id or not user_id or int(user_id) == int(event.get_self_id()):
            return

        monitored_groups = self._monitored_group_ids()
        if monitored_groups and int(group_id) not in monitored_groups:
            return

        if await self.core.get_user_by_qq(int(user_id)):
            return

        welcome_conf = self.config.get('group_welcome_settings', {})
        if not welcome_conf.get('enabled', True):
            return

        at_text = f"[CQ:at,qq={user_id}] " if welcome_conf.get('at_new_member', True) else ""
        template = welcome_conf.get(
            'welcome_template',
            "{at}欢迎进群。\n如果你要使用 NewAPI 余额或充值入账，请先绑定网站账号。\n绑定方式：私聊机器人发送 /绑定 你的网站ID，然后发送 确认绑定。\n也可以在群里发“怎么绑定”，我会把说明私聊你。"
        )
        welcome = self._format_template(
            template,
            at=at_text,
            user_id=user_id,
            group_id=group_id,
            bot_id=event.get_self_id(),
        )
        try:
            await event.bot.send_group_msg(group_id=int(group_id), message=welcome)
        except Exception as e:
            logger.error(f"发送进群欢迎语失败: {e}", exc_info=True)

        if welcome_conf.get('send_private_message', False):
            pm_template = welcome_conf.get(
                'private_welcome_template',
                "欢迎进群。\n\n为了在 QQ 里查询余额、使用兑换码提醒、充值入账和接收站点通知，请先绑定你的 NewAPI 网站账号。\n\n绑定流程：\n1. 打开 NewAPI 网站，进入个人信息/账号页面，找到你的网站 ID。\n2. 私聊我发送：/绑定 你的网站ID\n   例如：/绑定 32\n3. 我会让你核对一次，确认无误后发送：确认绑定\n\n注意：请一定填写自己的网站 ID。如果绑成别人的 ID，后续充值或余额操作可能会进入别人的账号。\n\n常用命令：\n/查询余额\n/今日消耗\n/自助解绑"
            )
            pm = self._format_template(
                pm_template,
                user_id=user_id,
                group_id=group_id,
                bot_id=event.get_self_id(),
            )
            try:
                await event.bot.send_private_msg(user_id=int(user_id), message=pm)
            except Exception as e:
                msg = str(e)
                if "请先添加对方为好友" in msg or "result\": 16" in msg or "result': 16" in msg:
                    logger.info(f"新人 {user_id} 尚未添加机器人好友，已跳过私聊绑定提示。")
                else:
                    logger.warning(f"发送进群私聊绑定提示失败({user_id}): {e}")

        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_decrease(self, event: AstrMessageEvent):
        """监听群成员减少事件，执行解绑并发送通知。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return

        raw = event.message_obj.raw_message
        if not (
            isinstance(raw, dict)
            and raw.get("post_type") == "notice"
            and raw.get("notice_type") == "group_decrease"
        ):
            return
        
        group_id = raw.get("group_id")
        user_id = raw.get("user_id")

        monitored_groups = self._monitored_group_ids()

        if monitored_groups and int(group_id) not in monitored_groups:
            return

        binding = await self.core.get_user_by_qq(user_id)
        if not binding:
            logger.info(f"用户 {user_id} 退出了受监控的群 {group_id}，但其未被绑定，无需净化。" )
            return

        website_user_id = binding['website_user_id']
        success, _ = await self.core.purge_user_binding(website_user_id)

        if success:
            logger.info(f"用户 {user_id} (网站ID: {website_user_id}) 的退群净化仪式成功完成。" )
            
            try:
                sub_type = raw.get("sub_type")
                operator_id = raw.get("operator_id")
                bot = event.bot

                user_info = await bot.get_stranger_info(user_id=user_id, no_cache=True)
                user_nickname = user_info.get("nickname", str(user_id))

                announcement = ""
                if sub_type == "leave":
                    announcement = f"成员【{user_nickname}】({user_id}) 已主动退出群聊。\n其绑定的网站数据已自动解绑，用户组已重置。"
                elif sub_type == "kick":
                    operator_info = await bot.get_group_member_info(group_id=group_id, user_id=operator_id, no_cache=True)
                    operator_nickname = operator_info.get("card") or operator_info.get("nickname", str(operator_id))
                    announcement = f"成员【{user_nickname}】({user_id}) 已被管理员【{operator_nickname}】移出群聊。\n其绑定的网站数据已自动解绑，用户组已重置。"
                
                if announcement:
                    await bot.send_group_msg(group_id=group_id, message=announcement)

            except Exception as e:
                logger.error(f"在为用户 {user_id} 发送退群净化通告时发生错误: {e}", exc_info=True)
        
        event.stop_event()

    # --- 绑定功能辅助方法 ---

    async def _check_self_binding(self, user_qq_id: int) -> Optional[str]:
        """检查用户QQ是否已绑定。"""
        if binding := await self.core.get_user_by_qq(user_qq_id):
            return f"您好，您的QQ已经与网站ID {binding['website_user_id']} 签订了契约，无需重复绑定。"
        return None

    def _monitored_group_ids(self) -> list[int]:
        leave_conf = self.config.get('group_leave_settings', {})
        monitored_groups_str = leave_conf.get('group_monitoring_list', [])
        return [int(g) for g in monitored_groups_str if str(g).isdigit()]

    async def _check_bind_cooldown(self, user_qq_id: int) -> Optional[str]:
        binding_conf = self.config.get('binding_settings', {})
        cooldown_minutes = int(binding_conf.get('rebinding_cooldown_minutes', 30))
        if cooldown_minutes <= 0:
            return None
        last_unbind = await self.core.get_last_binding_action(int(user_qq_id), "UNBIND_SELF")
        if not last_unbind:
            return None
        created_at = last_unbind.get("created_at")
        if not created_at:
            return None
        available_at = created_at + timedelta(minutes=cooldown_minutes)
        if datetime.utcnow() < available_at:
            remaining = int((available_at - datetime.utcnow()).total_seconds() // 60) + 1
            return f"你刚刚解绑过账号，为防止误操作和乱换绑，请 {remaining} 分钟后再绑定。"
        return None

    async def _check_qq_level(self, event: AstrMessageEvent, user_qq_id: int) -> Optional[str]:
        binding_conf = self.config.get('binding_settings', {})
        min_level = binding_conf.get('min_qq_level', 16)
        try:
            stranger_info = await event.bot.get_stranger_info(user_id=user_qq_id, no_cache=True)

            raw_level = stranger_info.get('qqLevel') 

            if raw_level is not None:
                user_qq_level = int(raw_level)
                if user_qq_level < min_level:
                    return f"抱歉，您的QQ等级({user_qq_level})未达到所要求的 {min_level} 级，暂时无法绑定。"
            else:
                logger.warning(f"无法从API获取用户 {user_qq_id} 的QQ等级，将跳过此项检查。" )
        except Exception as e:
            logger.warning(f"获取QQ等级失败，跳过检查: {e}", exc_info=True)
        return None

    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        """检查网站用户ID是否存在。"""
        if not await self.core.get_api_user_data(website_user_id):
            return f"审核失败：网站中不存在ID为 {website_user_id} 的用户，请检查您的ID。"
        return None

    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        """检查网站用户ID是否已被他人绑定。"""
        if await self.core.get_user_by_website_id(website_user_id):
            return f"审核失败：ID {website_user_id} 已被另一位用户绑定，无法操作。"
        return None

    async def _check_pending_id_uniqueness(self, website_user_id: int, user_qq_id: int) -> Optional[str]:
        """检查网站用户ID是否已被他人挂起待确认。"""
        pending = await self.core.get_pending_binding_by_website_id(int(website_user_id))
        if pending and int(pending.get("qq_id")) != int(user_qq_id):
            return f"审核失败：ID {website_user_id} 正在被另一位用户确认绑定，请稍后再试或联系管理员。"
        return None

    async def _perform_binding_ritual(self, user_qq_id: int, website_user_id: int) -> Tuple[bool, str]:
        """
        执行最终的绑定操作，包含数据库写入和API更新，失败时回滚。
        """
        try:
            await self.core.insert_binding(user_qq_id, website_user_id)
            
            api_user_data = await self.core.get_api_user_data(website_user_id)
            binding_conf = self.config.get('binding_settings', {})
            target_group = binding_conf.get('binding_group', 'default')
            
            if api_user_data:
                api_user_data['group'] = target_group
                update_success = await self.core.update_api_user(api_user_data)
                if not update_success:
                    raise Exception("API group update failed.")
            else:
                raise Exception("API user data not found during binding ritual.")

            return True, f"""绑定成功。
你的 QQ 已绑定到 NewAPI 网站 ID：{website_user_id}
后续查询余额、充值入账都会进入这个网站账号。
已自动为你调整到【{target_group}】分组。"""
        
        except Exception as e:
            logger.error(f"绑定仪式中发生错误: {e}", exc_info=True)
            await self.core.delete_binding(qq_id=user_qq_id)
            return False, "绑定过程中发生未知错误，操作已自动撤销，请联系管理员。"

    async def _send_success_pm(self, event: AstrMessageEvent, user_qq_id: int, website_user_id: int):
        """如果配置允许，发送绑定成功私信。"""
        pm_conf = self.config.get('optional_pm_settings', {})
        if not pm_conf.get('enable_bind_success_pm'):
            return
        
        try:
            template = pm_conf.get('bind_success_pm_template', "绑定成功！")
            group = self.config.get('binding_settings.binding_group', 'default')

            user_nickname = str(user_qq_id)
            try:
                stranger_info = await event.bot.get_stranger_info(user_id=user_qq_id, no_cache=True)
                user_nickname = stranger_info.get("nickname", str(user_qq_id))
            except Exception as e:
                logger.warning(f"为私信模板获取QQ昵称失败: {e}", exc_info=True)

            site_username = "未知"
            api_user_data = await self.core.get_api_user_data(website_user_id)
            if api_user_data:
                site_username = api_user_data.get("username", "未知")

            content = template.format(
                id=website_user_id,
                group=group,
                user_qq=user_qq_id,
                user_nickname=user_nickname,
                site_username=site_username
            )
            
            await event.bot.send_private_msg(user_id=user_qq_id, message=content)
            logger.info(f"成功发送绑定成功私信至 {user_qq_id}。" )
        except Exception as e:
            logger.error(f"发送绑定成功私信失败: {e}", exc_info=True)
