import os
import asyncio
import httpx
import aiomysql
import random
import re
import json
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import quote_plus, urlencode
from typing import Optional, Any, Dict, Tuple
from dotenv import load_dotenv, find_dotenv

from astrbot.api import logger, AstrBotConfig

class NewApiCore:
    """
    NewAPI 核心工具类 (最终 .env 混合模式架构)。
    """
    def __init__(self, config: AstrBotConfig):
        self.config = config
        self.db_pool: Optional[aiomysql.Pool] = None
        self.api_base_url = None
        self.api_access_token = None
        self.api_admin_user_id = "1"
        self.api_credential_source = "unset"
        self.bot_account_check: Dict[str, Any] = {
            "ok": False,
            "message": "尚未检查",
            "checks": {},
        }
        logger.info("[NewAPI Utils] 核心工具类已实例化，等待异步初始化...")

    async def initialize(self) -> bool:
        """异步初始化，从 .env 加载核心配置、连接数据库并自动建表。"""
        logger.info("[NewAPI Utils] 开始执行异步初始化...")
        
        load_dotenv()
        self.api_base_url = os.getenv("BOT_API_BASE_URL") or os.getenv("API_BASE_URL")
        self.api_access_token = os.getenv("BOT_API_ACCESS_TOKEN") or os.getenv("API_ACCESS_TOKEN")
        self.api_admin_user_id = os.getenv("BOT_API_ADMIN_USER_ID") or os.getenv("API_ADMIN_USER_ID", "1")
        if os.getenv("BOT_API_ACCESS_TOKEN") or os.getenv("BOT_API_ADMIN_USER_ID"):
            self.api_credential_source = "BOT_*"
        else:
            self.api_credential_source = "legacy API_*"

        if not self.api_base_url or not self.api_access_token:
            logger.error("[NewAPI Utils] .env 文件中 API 配置不完整！初始化失败。")
            return False

        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT")
        db_user = os.getenv("DB_USER")
        db_pass = os.getenv("DB_PASS")
        db_name = os.getenv("DB_NAME")
        
        if not all([db_host, db_port, db_user, db_name]):
            logger.error("[NewAPI Utils] .env 文件中数据库配置不完整！初始化失败。")
            return False
            
        try:
            self.db_pool = await aiomysql.create_pool(
                host=db_host, port=int(db_port),
                user=db_user, password=db_pass,
                db=db_name, autocommit=True
            )
            logger.info("[NewAPI Utils] 数据库连接池已根据 .env 配置成功建立。")

            # 【修改】召唤数据库管家，执行建表仪式
            if not await self._ensure_tables_exist():
                return False
            await self.seed_builtin_knowledge()

            self.bot_account_check = await self.check_bot_admin_account()
            if self.bot_account_check.get("ok"):
                logger.info(f"[NewAPI Utils] 机器人专用 NewAPI 管理账号自检通过：网站ID {self.api_admin_user_id}。")
            else:
                logger.warning(f"[NewAPI Utils] 机器人专用 NewAPI 管理账号自检未完全通过：{self.bot_account_check.get('message')}")

            return True
        except Exception as e:
            logger.error(f"[NewAPI Utils] 数据库初始化失败: {e}", exc_info=True)
            self.db_pool = None
            return False

    # 【新增】数据库自动建表管家
    async def _ensure_tables_exist(self):
        """在初始化时检查并确保核心数据表存在。"""
        logger.info("[NewAPI Utils] 数据库管家开始检查并创建数据表...")
        try:
            # 1. 用户绑定信息表
            bindings_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_bindings` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `qq_id` bigint(20) NOT NULL,
              `website_user_id` int(11) NOT NULL,
              `binding_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `last_check_in_time` timestamp NULL DEFAULT NULL,
              PRIMARY KEY (`id`),
              UNIQUE KEY `qq_id` (`qq_id`),
              UNIQUE KEY `website_user_id` (`website_user_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(bindings_sql)

            binding_pending_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_binding_pending` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `qq_id` bigint(20) NOT NULL,
              `website_user_id` int(11) NOT NULL,
              `source_group_id` bigint(20) DEFAULT NULL,
              `status` varchar(16) NOT NULL DEFAULT 'PENDING',
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `expires_at` timestamp NOT NULL,
              `confirmed_at` timestamp NULL DEFAULT NULL,
              PRIMARY KEY (`id`),
              KEY `idx_qq_status` (`qq_id`, `status`),
              KEY `idx_site_status` (`website_user_id`, `status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(binding_pending_sql)

            binding_audit_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_binding_audit_logs` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `qq_id` bigint(20) NOT NULL,
              `website_user_id` int(11) DEFAULT NULL,
              `action` varchar(32) NOT NULL,
              `source_group_id` bigint(20) DEFAULT NULL,
              `note` varchar(255) DEFAULT '',
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`),
              KEY `idx_qq_created` (`qq_id`, `created_at`),
              KEY `idx_site_created` (`website_user_id`, `created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(binding_audit_sql)
            
            # 2. 每日打劫日志表
            heist_log_sql = """
            CREATE TABLE IF NOT EXISTS `daily_heist_log` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `robber_qq_id` bigint(20) NOT NULL,
              `victim_website_id` int(11) NOT NULL,
              `heist_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `outcome` varchar(10) NOT NULL COMMENT 'SUCCESS, CRITICAL, FAILURE',
              `amount` int(11) NOT NULL COMMENT '涉及的原始 quota 数额',
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(heist_log_sql)
            
            redeem_codes_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_redeem_codes` (
              `code` varchar(64) NOT NULL,
              `display_quota` decimal(18,4) NOT NULL,
              `max_uses` int(11) NOT NULL DEFAULT 1,
              `used_count` int(11) NOT NULL DEFAULT 0,
              `enabled` tinyint(1) NOT NULL DEFAULT 1,
              `created_by` bigint(20) DEFAULT NULL,
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`code`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(redeem_codes_sql)

            redeem_logs_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_redeem_logs` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `code` varchar(64) NOT NULL,
              `qq_id` bigint(20) NOT NULL,
              `website_user_id` int(11) NOT NULL,
              `display_quota` decimal(18,4) NOT NULL,
              `used_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`),
              UNIQUE KEY `uniq_code_qq` (`code`, `qq_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(redeem_logs_sql)

            quota_logs_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_quota_adjust_logs` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `admin_qq` bigint(20) NOT NULL,
              `target_identifier` varchar(64) NOT NULL,
              `website_user_id` int(11) NOT NULL,
              `display_delta` decimal(18,4) NOT NULL,
              `reason` varchar(255) DEFAULT '',
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(quota_logs_sql)

            recharge_orders_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_recharge_orders` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `qq_id` bigint(20) NOT NULL,
              `website_user_id` int(11) NOT NULL,
              `amount` decimal(18,4) NOT NULL,
              `status` varchar(16) NOT NULL DEFAULT 'PENDING',
              `note` varchar(255) DEFAULT '',
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `handled_by` bigint(20) DEFAULT NULL,
              `handled_at` timestamp NULL DEFAULT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(recharge_orders_sql)

            knowledge_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_knowledge_base` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `question` varchar(255) NOT NULL,
              `answer` text NOT NULL,
              `keywords` varchar(255) DEFAULT '',
              `enabled` tinyint(1) NOT NULL DEFAULT 1,
              `created_by` bigint(20) DEFAULT NULL,
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `updated_at` timestamp NULL DEFAULT NULL,
              PRIMARY KEY (`id`),
              KEY `idx_enabled` (`enabled`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(knowledge_sql)

            pending_actions_sql = """
            CREATE TABLE IF NOT EXISTS `newapi_pending_actions` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `admin_qq` bigint(20) NOT NULL,
              `action` varchar(64) NOT NULL,
              `payload` text NOT NULL,
              `summary` varchar(255) NOT NULL,
              `status` varchar(16) NOT NULL DEFAULT 'PENDING',
              `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `expires_at` timestamp NOT NULL,
              `confirmed_at` timestamp NULL DEFAULT NULL,
              PRIMARY KEY (`id`),
              KEY `idx_admin_status` (`admin_qq`, `status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            await self.execute_query(pending_actions_sql)

            logger.info("✅ [NewAPI Utils] 数据表结构已确认就绪。")
            return True
        except Exception as e:
            logger.error(f"❌ [NewAPI Utils] 自动创建数据表时发生严重错误: {e}", exc_info=True)
            return False

    async def execute_query(self, query: str, args: Optional[Tuple] = None, fetch: Optional[str] = None) -> Any:
        if self.db_pool is None:
            logger.error("[NewAPI Utils] 数据库未连接，无法执行查询。")
            return None
        async with self.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor if fetch else aiomysql.Cursor) as cur:
                await cur.execute(query, args)
                if fetch == 'one':
                    return await cur.fetchone()
                elif fetch == 'all':
                    return await cur.fetchall()
                return cur.rowcount

    async def api_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Optional[Dict]:
        if not self.api_base_url or not self.api_access_token:
            logger.error("[NewAPI Utils] API 配置未在初始化时成功加载，请求中止。")
            return None
        
        url = f"{self.api_base_url}{endpoint}"
        headers = { "Authorization": self.api_access_token, "New-Api-User": self.api_admin_user_id }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, json=json_data, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"[NewAPI Utils] API 请求异常: {e}", exc_info=True)
            return None

    async def check_bot_admin_account(self) -> Dict[str, Any]:
        checks = {
            "base_url": bool(self.api_base_url),
            "access_token": bool(self.api_access_token),
            "admin_user_id": bool(self.api_admin_user_id),
            "read_self_user": False,
            "read_status": False,
            "read_options": False,
            "read_logs": False,
        }
        if not all([checks["base_url"], checks["access_token"], checks["admin_user_id"]]):
            return {
                "ok": False,
                "message": "BOT_API_BASE_URL / BOT_API_ACCESS_TOKEN / BOT_API_ADMIN_USER_ID 配置不完整。",
                "checks": checks,
                "credential_source": self.api_credential_source,
                "admin_user_id": self.api_admin_user_id,
            }

        user = await self.get_api_user_data(int(self.api_admin_user_id))
        checks["read_self_user"] = bool(user)

        status = await self.get_newapi_status()
        checks["read_status"] = bool(status)

        options = await self.get_newapi_options()
        checks["read_options"] = bool(options)

        logs = await self.get_usage_logs_page(0, 1, 0, int(datetime.utcnow().timestamp()))
        checks["read_logs"] = isinstance(logs, dict) and "items" in logs

        required_ok = checks["read_self_user"] and checks["read_status"]
        optional_missing = [name for name in ("read_options", "read_logs") if not checks.get(name)]
        if required_ok and not optional_missing:
            message = "机器人账号可用，常用管理读取权限正常。"
        elif required_ok:
            message = "机器人账号可用，但部分扩展读取权限不可用：" + "、".join(optional_missing)
        else:
            message = "机器人账号不可用或权限不足：无法读取自身用户或站点状态。"

        return {
            "ok": bool(required_ok),
            "message": message,
            "checks": checks,
            "credential_source": self.api_credential_source,
            "admin_user_id": self.api_admin_user_id,
        }

    async def get_usage_logs_page(self, page: int, page_size: int, start_ts: int, end_ts: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        endpoint = f"/api/log/?p={int(page)}&page_size={int(page_size)}&start_timestamp={int(start_ts)}&end_timestamp={int(end_ts)}"
        if user_id is not None:
            endpoint += f"&user_id={int(user_id)}"
        response = await self.api_request("GET", endpoint)
        if response and response.get("data"):
            return response.get("data")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    async def get_newapi_options(self) -> Dict[str, str]:
        response = await self.api_request("GET", "/api/option/")
        data = response.get("data") if response and response.get("success") else None
        if not isinstance(data, list):
            return {}
        options = {}
        for item in data:
            if isinstance(item, dict) and "key" in item:
                options[str(item.get("key"))] = str(item.get("value", ""))
        return options

    async def get_newapi_status(self) -> Dict[str, Any]:
        response = await self.api_request("GET", "/api/status")
        data = response.get("data") if response and response.get("success") else None
        return data if isinstance(data, dict) else {}

    async def get_checkin_settings_from_newapi(self) -> Dict[str, Any]:
        options = await self.get_newapi_options()
        status = await self.get_newapi_status()

        def parse_bool(value: Any, default: bool = False) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"true", "1", "yes", "on", "开启", "启用"}

        def parse_int(value: Any, default: int = 0) -> int:
            try:
                return int(float(str(value).strip()))
            except Exception:
                return default

        quota_per_unit = parse_int(status.get("quota_per_unit"), self.config.get('binding_settings.quota_display_ratio', 500000))
        return {
            "enabled": parse_bool(options.get("checkin_setting.enabled"), parse_bool(status.get("checkin_enabled"), False)),
            "min_raw_quota": parse_int(options.get("checkin_setting.min_quota"), 0),
            "max_raw_quota": parse_int(options.get("checkin_setting.max_quota"), 0),
            "quota_per_unit": quota_per_unit,
            "source": "NewAPI",
        }

    async def summarize_usage_logs(self, start_ts: int, end_ts: int, user_id: Optional[int] = None, page_size: int = 100, max_pages: int = 20) -> Dict[str, Any]:
        users: Dict[int, Dict[str, Any]] = {}
        total_quota = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_requests = 0
        total_available = None
        for page in range(int(max_pages)):
            data = await self.get_usage_logs_page(page, page_size, start_ts, end_ts, user_id=user_id)
            items = data.get("items") or []
            if total_available is None:
                total_available = int(data.get("total") or 0)
            if not items:
                break
            for item in items:
                uid = int(item.get("user_id") or 0)
                quota = int(item.get("quota") or 0)
                prompt_tokens = int(item.get("prompt_tokens") or 0)
                completion_tokens = int(item.get("completion_tokens") or 0)
                total_quota += quota
                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                total_requests += 1
                if uid not in users:
                    users[uid] = {
                        "user_id": uid,
                        "username": item.get("username") or str(uid),
                        "quota": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "requests": 0,
                    }
                users[uid]["quota"] += quota
                users[uid]["prompt_tokens"] += prompt_tokens
                users[uid]["completion_tokens"] += completion_tokens
                users[uid]["requests"] += 1
            if len(items) < int(page_size):
                break
        ranking = sorted(users.values(), key=lambda x: x["quota"], reverse=True)
        return {
            "total_quota": total_quota,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_requests": total_requests,
            "total_available": total_available or 0,
            "users": ranking,
            "truncated": bool(total_available and total_requests < total_available),
        }

    async def tavily_search(self, query: str, api_key: str, result_count: int = 5) -> list[Dict]:
        payload = {
            "query": query,
            "max_results": int(result_count),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            results = []
            for item in data.get("results", []) or []:
                results.append({
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "snippet": item.get("content") or "",
                })
            return results
        except Exception as e:
            logger.error(f"Tavily 搜索失败: {e}", exc_info=True)
            return []

    async def brave_search(self, query: str, api_key: str, result_count: int = 5) -> list[Dict]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }
        params = f"q={quote_plus(query)}&count={int(result_count)}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"https://api.search.brave.com/res/v1/web/search?{params}", headers=headers)
                resp.raise_for_status()
                data = resp.json()
            results = []
            for item in ((data.get("web") or {}).get("results") or []):
                results.append({
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "snippet": item.get("description") or "",
                })
            return results
        except Exception as e:
            logger.error(f"Brave 搜索失败: {e}", exc_info=True)
            return []

    async def web_search(self, query: str, settings: Dict) -> list[Dict]:
        provider = str(settings.get("provider", "tavily")).lower()
        result_count = int(settings.get("result_count", 5))
        if provider == "brave":
            return await self.brave_search(query, settings.get("brave_api_key", ""), result_count)
        return await self.tavily_search(query, settings.get("tavily_api_key", ""), result_count)

    async def fetch_webpage_text(self, url: str, max_chars: int = 6000) -> str:
        if not str(url).startswith(("http://", "https://")):
            return ""
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 AstrBot-NewAPI-KB/1.0"})
                resp.raise_for_status()
                html = resp.text
            html = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav).*?>.*?</\1>", " ", html)
            html = re.sub(r"(?is)<br\s*/?>", "\n", html)
            html = re.sub(r"(?is)</p>|</div>|</section>|</article>|</h[1-6]>", "\n", html)
            text = re.sub(r"(?is)<[^>]+>", " ", html)
            text = unescape(text)
            text = re.sub(r"[ \t\r\f\v]+", " ", text)
            text = re.sub(r"\n\s*\n+", "\n", text).strip()
            return text[:int(max_chars)]
        except Exception as e:
            logger.warning(f"抓取网页正文失败({url}): {e}")
            return ""

    # --- 以下所有高级助手方法保持不变 ---
    async def get_user_by_qq(self, qq_id: int) -> Optional[Dict]: return await self.execute_query("SELECT * FROM newapi_bindings WHERE qq_id = %s", (qq_id,), fetch='one')
    async def get_user_by_website_id(self, website_user_id: int) -> Optional[Dict]: return await self.execute_query("SELECT * FROM newapi_bindings WHERE website_user_id = %s", (website_user_id,), fetch='one')
    async def get_api_user_data(self, user_id: int) -> Optional[Dict]:
        response = await self.api_request("GET", f"/api/user/{user_id}")
        if response and response.get("success"): return response.get("data")
        return None
    async def search_api_users(self, keyword: str) -> list[Dict]:
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        response = await self.api_request("GET", f"/api/user/search?keyword={keyword}")
        if response and response.get("success") and isinstance(response.get("data"), list):
            return response.get("data")
        return []
    async def find_api_user_by_username(self, username: str) -> Optional[Dict]:
        username = (username or "").strip()
        if not username:
            return None
        users = await self.search_api_users(username)
        username_lower = username.lower()
        for user in users:
            if str(user.get("username", "")).lower() == username_lower:
                return user
        for user in users:
            if str(user.get("display_name", "")).lower() == username_lower:
                return user
        return None
    async def update_api_user(self, user_profile: Dict) -> bool:
        response = await self.api_request("PUT", "/api/user/", json_data=user_profile)
        return response and response.get("success", False)
    async def create_native_redemption_codes(self, name: str, display_quota: float, count: int, expired_time: int = 0) -> Tuple[bool, Dict[str, Any]]:
        ratio = self.config.get('binding_settings.quota_display_ratio', 500000)
        payload = {
            "name": name[:20],
            "count": int(count),
            "quota": int(float(display_quota) * ratio),
            "expired_time": int(expired_time or 0),
        }
        response = await self.api_request("POST", "/api/redemption/", json_data=payload)
        if response and response.get("success"):
            return True, {
                "codes": response.get("data") or [],
                "display_quota": float(display_quota),
                "raw_quota": payload["quota"],
                "count": int(count),
                "name": payload["name"],
            }
        return False, {
            "message": (response or {}).get("message", "NewAPI 原生兑换码创建失败"),
            "response": response,
        }
    async def insert_binding(self, qq_id: int, website_user_id: int) -> int: return await self.execute_query("INSERT INTO newapi_bindings (qq_id, website_user_id) VALUES (%s, %s)", (qq_id, website_user_id))
    async def delete_binding(self, *, qq_id: Optional[int] = None, website_user_id: Optional[int] = None) -> int:
        if qq_id: return await self.execute_query("DELETE FROM newapi_bindings WHERE qq_id = %s", (qq_id,))
        if website_user_id: return await self.execute_query("DELETE FROM newapi_bindings WHERE website_user_id = %s", (website_user_id,))
        return 0
    async def log_binding_action(self, qq_id: int, website_user_id: Optional[int], action: str, source_group_id: Optional[int] = None, note: str = "") -> int:
        query = "INSERT INTO newapi_binding_audit_logs (qq_id, website_user_id, action, source_group_id, note) VALUES (%s, %s, %s, %s, %s)"
        return await self.execute_query(query, (qq_id, website_user_id, action, source_group_id, note[:255]))
    async def get_last_binding_action(self, qq_id: int, action: str) -> Optional[Dict]:
        query = "SELECT * FROM newapi_binding_audit_logs WHERE qq_id=%s AND action=%s ORDER BY created_at DESC LIMIT 1"
        return await self.execute_query(query, (qq_id, action), fetch='one')
    async def create_pending_binding(self, qq_id: int, website_user_id: int, source_group_id: Optional[int] = None, ttl_minutes: int = 10) -> int:
        await self.execute_query("UPDATE newapi_binding_pending SET status='CANCELLED' WHERE qq_id=%s AND status='PENDING'", (qq_id,))
        expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        query = "INSERT INTO newapi_binding_pending (qq_id, website_user_id, source_group_id, expires_at) VALUES (%s, %s, %s, %s)"
        await self.execute_query(query, (qq_id, website_user_id, source_group_id, expires_at))
        row = await self.execute_query("SELECT LAST_INSERT_ID() AS id", fetch='one')
        await self.log_binding_action(qq_id, website_user_id, "BIND_PENDING", source_group_id, f"ttl={ttl_minutes}m")
        return int(row['id']) if row else 0
    async def get_pending_binding(self, qq_id: int) -> Optional[Dict]:
        query = "SELECT * FROM newapi_binding_pending WHERE qq_id=%s AND status='PENDING' ORDER BY id DESC LIMIT 1"
        return await self.execute_query(query, (qq_id,), fetch='one')
    async def get_pending_binding_by_website_id(self, website_user_id: int) -> Optional[Dict]:
        query = "SELECT * FROM newapi_binding_pending WHERE website_user_id=%s AND status='PENDING' AND expires_at>%s ORDER BY id DESC LIMIT 1"
        return await self.execute_query(query, (website_user_id, datetime.utcnow()), fetch='one')
    async def mark_pending_binding(self, pending_id: int, status: str) -> int:
        query = "UPDATE newapi_binding_pending SET status=%s, confirmed_at=%s WHERE id=%s AND status='PENDING'"
        return await self.execute_query(query, (status, datetime.utcnow(), pending_id))
    async def set_check_in_time(self, qq_id: int) -> int:
        query = "UPDATE newapi_bindings SET last_check_in_time = %s WHERE qq_id = %s"
        return await self.execute_query(query, (datetime.utcnow(), qq_id))
    async def revert_user_group(self, website_user_id: int) -> bool:
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data:
            logger.warning(f"无法获取网站ID {website_user_id} 的用户数据，跳过用户组恢复操作。")
            return False
        leave_conf = self.config.get('group_leave_settings', {})
        revert_group = leave_conf.get('revert_group_on_leave', 'default')
        if api_user_data.get('group') != revert_group:
            api_user_data['group'] = revert_group
            update_success = await self.update_api_user(api_user_data)
            if update_success:
                logger.info(f"成功将网站用户 {website_user_id} 恢复至用户组: {revert_group}")
            else:
                logger.error(f"尝试恢复网站用户 {website_user_id} 至用户组 {revert_group} 时失败。")
            return update_success
        logger.info(f"网站用户 {website_user_id} 已在目标恢复组 {revert_group} 中，无需操作。")
        return True
    async def perform_check_in(self, qq_id: int, binding: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        check_in_conf = self.config.get('check_in_settings', {})
        sync_from_newapi = check_in_conf.get('sync_from_newapi', True)
        newapi_checkin_conf: Dict[str, Any] = {}
        if sync_from_newapi:
            newapi_checkin_conf = await self.get_checkin_settings_from_newapi()
            if not newapi_checkin_conf.get("enabled", False):
                return "DISABLED_BY_NEWAPI", newapi_checkin_conf
        elif not check_in_conf.get('enabled', False):
            return "DISABLED", {}

        if not binding:
            binding = await self.get_user_by_qq(qq_id)
        if not binding:
            return "NOT_BOUND", {}

        # --- 缓存配置值 ---
        offset_hours = check_in_conf.get('timezone_offset_hours', 0)
        first_bonus_enabled = check_in_conf.get('first_check_in_bonus_enabled', False)
        first_bonus_display_quota = check_in_conf.get('first_check_in_bonus_display_quota', 0)
        double_chance = check_in_conf.get('double_chance', 0.0)
        ratio = int(newapi_checkin_conf.get("quota_per_unit") or self.config.get('binding_settings.quota_display_ratio', 500000))
        if sync_from_newapi:
            min_display_q = int(newapi_checkin_conf.get("min_raw_quota", 0)) / ratio
            max_display_q = int(newapi_checkin_conf.get("max_raw_quota", 0)) / ratio
        else:
            min_display_q = check_in_conf.get('min_display_quota', 0)
            max_display_q = check_in_conf.get('max_display_quota', 0)
        # --- 缓存结束 ---

        time_delta = timedelta(hours=offset_hours)
        local_today = (datetime.utcnow() + time_delta).date()
        last_check_in_time = binding.get('last_check_in_time')
        is_first_check_in = last_check_in_time is None

        if not is_first_check_in:
            local_last_check_in_date = (last_check_in_time + time_delta).date()
            if local_last_check_in_date == local_today:
                return "ALREADY_CHECKED_IN", {}

        bonus_quota = 0
        is_doubled = False
        if is_first_check_in and first_bonus_enabled:
            bonus_quota = int(first_bonus_display_quota * ratio)
        else:
            is_doubled = random.random() < double_chance
        
        base_display_quota = random.uniform(min_display_q, max_display_q)
        base_quota = int(base_display_quota * ratio)
        regular_quota = base_quota * 2 if is_doubled else base_quota
        final_quota = regular_quota + bonus_quota

        website_user_id = binding['website_user_id']
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data:
            return "API_USER_NOT_FOUND", {}

        current_quota = api_user_data.get("quota", 0)
        api_user_data["quota"] = current_quota + final_quota
        
        if not await self.update_api_user(api_user_data):
            return "API_UPDATE_FAILED", {}
            
        await self.set_check_in_time(qq_id)
        
        display_added = final_quota / ratio
        display_total = (current_quota + final_quota) / ratio

        return "SUCCESS", {
            "is_first": is_first_check_in,
            "is_doubled": is_doubled,
            "display_added": display_added,
            "display_total": display_total,
            "user_qq": qq_id,
            "site_id": website_user_id
        }
    async def purge_user_binding(self, website_user_id: int) -> Tuple[bool, Optional[Dict]]:
        binding_info = await self.get_user_by_website_id(website_user_id)
        if not binding_info:
            logger.warning(f"净化请求失败：未找到网站ID {website_user_id} 的绑定记录。")
            return False, None
        try:
            logger.info(f"开始净化网站ID {website_user_id} (QQ: {binding_info['qq_id']})...")
            await self.revert_user_group(website_user_id)
            rows_affected = await self.delete_binding(website_user_id=website_user_id)
            if rows_affected > 0:
                logger.info(f"净化成功：已删除网站ID {website_user_id} 的绑定记录。")
                return True, binding_info
            else:
                logger.error(f"净化异常：记录存在但删除失败，数据库影响行数为0。")
                return False, binding_info
        except Exception as e:
            logger.error(f"执行净化网站ID {website_user_id} 的过程中发生未知错误: {e}", exc_info=True)
            return False, binding_info
    async def lookup_binding(self, identifier: int) -> Tuple[str, Optional[Dict]]:
        binding = await self.get_user_by_website_id(identifier)
        if binding:
            return "WEBSITE_ID", binding
        binding = await self.get_user_by_qq(identifier)
        if binding:
            return "QQ_ID", binding
        return "NOT_FOUND", None
    async def resolve_website_user_id(self, identifier: int) -> Optional[int]:
        id_type, binding = await self.lookup_binding(identifier)
        if id_type != "NOT_FOUND" and binding:
            return int(binding["website_user_id"])
        if await self.get_api_user_data(identifier):
            return int(identifier)
        return None

    async def log_quota_adjustment(self, admin_qq: int, target_identifier: int, website_user_id: int, display_delta: float, reason: str = "") -> int:
        query = "INSERT INTO newapi_quota_adjust_logs (admin_qq, target_identifier, website_user_id, display_delta, reason) VALUES (%s, %s, %s, %s, %s)"
        return await self.execute_query(query, (admin_qq, str(target_identifier), website_user_id, display_delta, reason[:255]))

    async def create_redeem_code(self, code: str, display_quota: float, max_uses: int, created_by: int) -> bool:
        query = "INSERT INTO newapi_redeem_codes (code, display_quota, max_uses, created_by) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE display_quota=VALUES(display_quota), max_uses=VALUES(max_uses), enabled=1"
        return (await self.execute_query(query, (code, display_quota, max_uses, created_by))) is not None

    async def redeem_code(self, code: str, qq_id: int, website_user_id: int) -> Tuple[str, Dict[str, Any]]:
        code = code.strip()
        row = await self.execute_query("SELECT * FROM newapi_redeem_codes WHERE code=%s", (code,), fetch='one')
        if not row or not row.get('enabled'):
            return "NOT_FOUND", {}
        if int(row.get('used_count') or 0) >= int(row.get('max_uses') or 0):
            return "EXHAUSTED", {}
        used = await self.execute_query("SELECT id FROM newapi_redeem_logs WHERE code=%s AND qq_id=%s", (code, qq_id), fetch='one')
        if used:
            return "ALREADY_USED", {}
        amount = float(row['display_quota'])
        status, details = await self.adjust_balance_by_identifier(website_user_id, amount)
        if status != "SUCCESS":
            return "API_FAILED", {}
        await self.execute_query("INSERT INTO newapi_redeem_logs (code, qq_id, website_user_id, display_quota) VALUES (%s, %s, %s, %s)", (code, qq_id, website_user_id, amount))
        await self.execute_query("UPDATE newapi_redeem_codes SET used_count=used_count+1 WHERE code=%s", (code,))
        return "SUCCESS", {"amount": amount, "new_display_quota": details.get("new_display_quota", 0)}

    async def create_recharge_order(self, qq_id: int, website_user_id: int, amount: float, note: str = "") -> int:
        await self.execute_query("INSERT INTO newapi_recharge_orders (qq_id, website_user_id, amount, note) VALUES (%s, %s, %s, %s)", (qq_id, website_user_id, amount, note[:255]))
        row = await self.execute_query("SELECT LAST_INSERT_ID() AS id", fetch='one')
        return int(row['id']) if row else 0

    async def find_recharge_order_by_note_keyword(self, keyword: str) -> Optional[Dict]:
        return await self.execute_query(
            "SELECT * FROM newapi_recharge_orders WHERE note LIKE %s ORDER BY id DESC LIMIT 1",
            (f"%{keyword[:120]}%",),
            fetch='one',
        )

    def _tenpay_token(self, key: str) -> int:
        value = 5381
        for ch in key or "":
            value += (value << 5) + ord(ch)
        return value & 0x7fffffff

    async def query_tenpay_transfer_detail(
        self,
        trans_id: str,
        cookie: str,
        self_uin: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """查询 QQ 钱包转账详情。cookie 由 NapCat get_cookies(mqq.tenpay.com) 提供。"""
        def parse_cookie(raw: str) -> Dict[str, str]:
            parsed: Dict[str, str] = {}
            for part in (raw or "").split(";"):
                if "=" in part:
                    key, value = part.strip().split("=", 1)
                    parsed[key] = value
            return parsed

        cookies = parse_cookie(cookie)
        skey = cookies.get("skey", "")
        pskey = cookies.get("p_skey", "")
        if not trans_id or not skey or not pskey or not self_uin:
            return "MISSING_AUTH", {}

        headers = {
            "User-Agent": "Mozilla/5.0 QQ/9.9 MQQBrowser/10.0",
            "Referer": "https://mqq.tenpay.com/v2/hybrid/www/mobile_qq/payment/receive_result.shtml",
            "Cookie": cookie,
            "Accept": "application/json,text/javascript,*/*;q=0.01",
        }
        login_params = {
            "uin": str(self_uin),
            "skey": skey,
            "pskey": pskey,
            "skey_type": "2",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                login_resp = await client.get(
                    f"https://mqq.tenpay.com/cgi-bin/hongbao/qpay_hb_login.cgi?{urlencode(login_params)}",
                    headers=headers,
                )
                login_data = login_resp.json()
                if str(login_data.get("retcode")) != "0" or not login_data.get("skey"):
                    return "LOGIN_FAILED", {"retmsg": login_data.get("retmsg"), "retcode": login_data.get("retcode")}

                qpayskey = str(login_data["skey"])
                cft_cookie = f"{cookie}; qpayskey={qpayskey}; user_type={login_data.get('user_type', '')}"
                detail_params = {
                    "uin": str(self_uin),
                    "skey": qpayskey,
                    "pskey": pskey,
                    "skey_type": "0",
                    "g_tk": str(self._tenpay_token(pskey)),
                    "listid": trans_id,
                    "_t": str(int(datetime.utcnow().timestamp() * 1000)),
                }
                detail_resp = await client.get(
                    f"https://mqq.tenpay.com/cgi-bin/qwallet_app/qpayment_trans_detail.cgi?{urlencode(detail_params)}",
                    headers={**headers, "Cookie": cft_cookie},
                )
                detail_data = detail_resp.json()
                if str(detail_data.get("retcode")) != "0":
                    return "QUERY_FAILED", {"retmsg": detail_data.get("retmsg"), "retcode": detail_data.get("retcode")}
                records = detail_data.get("records") or []
                if not records:
                    return "NOT_FOUND", detail_data
                return "SUCCESS", records[0]
        except Exception as e:
            logger.warning(f"[NewAPI Utils] 查询 QQ 钱包转账详情失败: {e}", exc_info=True)
            return "ERROR", {"error": str(e)}

    async def get_recharge_order(self, order_id: int) -> Optional[Dict]:
        return await self.execute_query("SELECT * FROM newapi_recharge_orders WHERE id=%s", (order_id,), fetch='one')

    async def mark_recharge_order(self, order_id: int, status: str, admin_qq: int) -> int:
        return await self.execute_query("UPDATE newapi_recharge_orders SET status=%s, handled_by=%s, handled_at=%s WHERE id=%s AND status='PENDING'", (status, admin_qq, datetime.utcnow(), order_id))

    async def add_knowledge_item(self, question: str, answer: str, keywords: str, created_by: int) -> int:
        query = "INSERT INTO newapi_knowledge_base (question, answer, keywords, created_by) VALUES (%s, %s, %s, %s)"
        await self.execute_query(query, (question[:255], answer, keywords[:255], created_by))
        row = await self.execute_query("SELECT LAST_INSERT_ID() AS id", fetch='one')
        return int(row['id']) if row else 0

    def _builtin_api_knowledge_items(self) -> list[Dict[str, str]]:
        return [
            {
                "question": "NewAPI 怎么调用接口？",
                "answer": (
                    "NewAPI 通常兼容 OpenAI API 调用方式。最关键的两项配置是：\n"
                    "1. base_url 填你的 NewAPI 站点地址，并以 /v1 结尾，例如：https://你的域名/v1\n"
                    "2. api_key 填用户在 NewAPI 后台创建的令牌，格式一般是 sk- 开头。\n\n"
                    "常用聊天接口是 POST /v1/chat/completions。请求头使用 Authorization: Bearer 你的令牌，"
                    "请求体里至少要有 model 和 messages。"
                ),
                "keywords": "builtin_api,api调用,接口调用,newapi,base_url,api_key,/v1,chat/completions",
            },
            {
                "question": "OpenAI SDK 怎么接入 NewAPI？",
                "answer": (
                    "如果项目原来用 OpenAI SDK，一般只需要改两处：api_key 和 base_url。\n\n"
                    "Python 示例：\n"
                    "from openai import OpenAI\n"
                    "client = OpenAI(api_key=\"sk-你的令牌\", base_url=\"https://你的域名/v1\")\n"
                    "resp = client.chat.completions.create(\n"
                    "    model=\"模型名称\",\n"
                    "    messages=[{\"role\":\"user\",\"content\":\"你好\"}],\n"
                    ")\n"
                    "print(resp.choices[0].message.content)\n\n"
                    "注意：base_url 通常填到 /v1，不要再手动加 /chat/completions，SDK 会自动拼接接口路径。"
                ),
                "keywords": "builtin_api,openai sdk,python,base_url,api_key,client.chat.completions.create",
            },
            {
                "question": "curl 怎么调用 NewAPI 聊天接口？",
                "answer": (
                    "curl 示例：\n"
                    "curl https://你的域名/v1/chat/completions \\\n"
                    "  -H \"Authorization: Bearer sk-你的令牌\" \\\n"
                    "  -H \"Content-Type: application/json\" \\\n"
                    "  -d '{\n"
                    "    \"model\": \"模型名称\",\n"
                    "    \"messages\": [\n"
                    "      {\"role\": \"user\", \"content\": \"你好\"}\n"
                    "    ]\n"
                    "  }'\n\n"
                    "如果要流式输出，在 JSON 里加 \"stream\": true。"
                ),
                "keywords": "builtin_api,curl,chat/completions,authorization,bearer,stream",
            },
            {
                "question": "Node.js 怎么调用 NewAPI？",
                "answer": (
                    "Node.js 使用 OpenAI SDK 的示例：\n"
                    "import OpenAI from \"openai\";\n\n"
                    "const client = new OpenAI({\n"
                    "  apiKey: \"sk-你的令牌\",\n"
                    "  baseURL: \"https://你的域名/v1\",\n"
                    "});\n\n"
                    "const resp = await client.chat.completions.create({\n"
                    "  model: \"模型名称\",\n"
                    "  messages: [{ role: \"user\", content: \"你好\" }],\n"
                    "});\n\n"
                    "console.log(resp.choices[0].message.content);\n\n"
                    "注意 Node SDK 参数名通常是 baseURL，Python SDK 参数名通常是 base_url。"
                ),
                "keywords": "builtin_api,nodejs,javascript,typescript,openai sdk,baseURL,chat.completions",
            },
            {
                "question": "NewAPI 令牌应该填在哪里？",
                "answer": (
                    "NewAPI 令牌就是 API Key。用户需要在 NewAPI 网站后台创建令牌，然后在程序里填到 api_key。"
                    "HTTP 请求时放在请求头：Authorization: Bearer sk-你的令牌。\n\n"
                    "不要把令牌发到群里，也不要写进前端网页源码。令牌泄露后，别人可能会消耗你的余额。"
                ),
                "keywords": "builtin_api,令牌,token,api key,sk,authorization,bearer,安全",
            },
            {
                "question": "怎么查看 NewAPI 可用模型？",
                "answer": (
                    "一般可以在 NewAPI 网站的模型列表、渠道页面或令牌可用模型里查看。"
                    "调用接口时，model 字段必须填写站点支持的模型名称。\n\n"
                    "如果报 model not found、model unavailable、无可用渠道，通常是模型名写错、令牌无权限、渠道没配置好，"
                    "或者该模型当前没有可用额度/可用渠道。"
                ),
                "keywords": "builtin_api,模型列表,model,model not found,无可用渠道,渠道",
            },
            {
                "question": "NewAPI 余额和 quota 是什么关系？",
                "answer": (
                    "NewAPI 底层常用 quota 作为内部计量单位，站点前台通常展示为余额。"
                    "本群机器人会按站长配置的换算比例展示为 NewAPI 余额，避免直接暴露内部 quota。\n\n"
                    "如果你看到后台和机器人显示有差异，优先看站长配置的 quota_display_ratio 或站点自己的倍率设置。"
                ),
                "keywords": "builtin_api,余额,quota,额度,换算,quota_display_ratio",
            },
            {
                "question": "API 调用常见报错怎么排查？",
                "answer": (
                    "常见排查顺序：\n"
                    "1. 401/unauthorized：检查 API Key 是否正确，Authorization 是否是 Bearer sk-xxx。\n"
                    "2. 404/not found：检查 base_url 是否填到 /v1，接口路径是否是 /chat/completions。\n"
                    "3. model not found：检查模型名称是否在站点可用模型里。\n"
                    "4. insufficient quota/余额不足：检查账户余额、令牌额度限制、分组倍率。\n"
                    "5. timeout/网络错误：检查站点域名、反代、Cloudflare、渠道状态。\n\n"
                    "如果是在第三方软件里配置，base_url 通常填 https://你的域名/v1，API Key 填 sk-令牌。"
                ),
                "keywords": "builtin_api,报错,401,404,unauthorized,model not found,余额不足,timeout,排查",
            },
            {
                "question": "第三方软件里 NewAPI 地址怎么填？",
                "answer": (
                    "大多数第三方软件选择 OpenAI 或 OpenAI Compatible，然后这样填：\n"
                    "API 地址 / Base URL：https://你的域名/v1\n"
                    "API Key：sk-你的 NewAPI 令牌\n"
                    "模型：填写站点支持的模型名称。\n\n"
                    "常见错误是把 Base URL 填成完整接口 https://你的域名/v1/chat/completions。"
                    "多数客户端只需要填到 /v1，后面的接口路径由客户端自动拼。"
                ),
                "keywords": "builtin_api,第三方软件,OpenAI Compatible,base url,api地址,Cherry Studio,Chatbox,One API",
            },
        ]

    async def seed_builtin_knowledge(self) -> int:
        """Insert or refresh built-in API usage knowledge without creating duplicates."""
        inserted_or_updated = 0
        for item in self._builtin_api_knowledge_items():
            question = item["question"][:255]
            answer = item["answer"]
            keywords = item["keywords"][:255]
            row = await self.execute_query(
                "SELECT id, keywords FROM newapi_knowledge_base WHERE question=%s LIMIT 1",
                (question,),
                fetch='one',
            )
            if row:
                existing_keywords = str(row.get("keywords") or "")
                if "builtin_api" in existing_keywords:
                    await self.execute_query(
                        "UPDATE newapi_knowledge_base SET answer=%s, keywords=%s, enabled=1, updated_at=%s WHERE id=%s",
                        (answer, keywords, datetime.utcnow(), int(row["id"])),
                    )
                    inserted_or_updated += 1
                continue
            await self.execute_query(
                "INSERT INTO newapi_knowledge_base (question, answer, keywords, created_by) VALUES (%s, %s, %s, %s)",
                (question, answer, keywords, 0),
            )
            inserted_or_updated += 1
        if inserted_or_updated:
            logger.info(f"[NewAPI Utils] 已同步 {inserted_or_updated} 条内置 API 调用知识库。")
        return inserted_or_updated

    async def update_knowledge_item(self, item_id: int, question: str, answer: str, keywords: str) -> int:
        query = "UPDATE newapi_knowledge_base SET question=%s, answer=%s, keywords=%s, updated_at=%s WHERE id=%s"
        return await self.execute_query(query, (question[:255], answer, keywords[:255], datetime.utcnow(), item_id))

    async def delete_knowledge_item(self, item_id: int) -> int:
        return await self.execute_query("UPDATE newapi_knowledge_base SET enabled=0, updated_at=%s WHERE id=%s", (datetime.utcnow(), item_id))

    async def list_knowledge_items(self, limit: int = 20) -> list[Dict]:
        query = "SELECT id, question, keywords, created_at FROM newapi_knowledge_base WHERE enabled=1 ORDER BY id DESC LIMIT %s"
        rows = await self.execute_query(query, (int(limit),), fetch='all')
        return list(rows or [])

    async def get_knowledge_item(self, item_id: int) -> Optional[Dict]:
        return await self.execute_query("SELECT * FROM newapi_knowledge_base WHERE id=%s AND enabled=1", (item_id,), fetch='one')

    async def search_knowledge_items(self, keyword: str, limit: int = 3) -> list[Dict]:
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        like = f"%{keyword}%"
        query = """
        SELECT * FROM newapi_knowledge_base
        WHERE enabled=1 AND (question LIKE %s OR answer LIKE %s OR keywords LIKE %s)
        ORDER BY
          CASE
            WHEN question LIKE %s THEN 0
            WHEN keywords LIKE %s THEN 1
            ELSE 2
          END,
          id DESC
        LIMIT %s
        """
        rows = await self.execute_query(query, (like, like, like, like, like, int(limit)), fetch='all')
        return list(rows or [])

    async def create_pending_action(self, admin_qq: int, action: str, payload: Dict[str, Any], summary: str, ttl_minutes: int = 10) -> int:
        query = "INSERT INTO newapi_pending_actions (admin_qq, action, payload, summary, expires_at) VALUES (%s, %s, %s, %s, %s)"
        await self.execute_query(query, (admin_qq, action[:64], json.dumps(payload, ensure_ascii=False), summary[:255], datetime.utcnow() + timedelta(minutes=ttl_minutes)))
        row = await self.execute_query("SELECT LAST_INSERT_ID() AS id", fetch='one')
        return int(row['id']) if row else 0

    async def get_pending_action(self, action_id: int, admin_qq: Optional[int] = None) -> Optional[Dict]:
        if admin_qq is None:
            return await self.execute_query("SELECT * FROM newapi_pending_actions WHERE id=%s AND status='PENDING'", (action_id,), fetch='one')
        return await self.execute_query("SELECT * FROM newapi_pending_actions WHERE id=%s AND admin_qq=%s AND status='PENDING'", (action_id, admin_qq), fetch='one')

    async def mark_pending_action(self, action_id: int, status: str) -> int:
        return await self.execute_query("UPDATE newapi_pending_actions SET status=%s, confirmed_at=%s WHERE id=%s AND status='PENDING'", (status, datetime.utcnow(), action_id))

    async def adjust_balance_by_identifier(self, identifier: int, display_adjustment: float) -> Tuple[str, Optional[Dict]]:
        website_user_id = await self.resolve_website_user_id(identifier)
        if website_user_id is None:
            return "USER_NOT_FOUND", None
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data:
            return "API_FETCH_FAILED", {"website_user_id": website_user_id}
        ratio = self.config.get('binding_settings.quota_display_ratio', 500000)
        raw_quota_adjustment = int(display_adjustment * ratio)
        current_raw_quota = api_user_data.get("quota", 0)
        new_total_raw_quota = current_raw_quota + raw_quota_adjustment
        if new_total_raw_quota < 0:
            new_total_raw_quota = 0
            logger.warning(f"为用户 {website_user_id} 调整余额后会导致负数，已自动修正为 0。")
        actual_raw_delta = new_total_raw_quota - current_raw_quota
        actual_display_delta = actual_raw_delta / ratio
        api_user_data["quota"] = new_total_raw_quota
        if not await self.update_api_user(api_user_data):
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
        new_display_quota = new_total_raw_quota / ratio
        return "SUCCESS", {
            "website_user_id": website_user_id,
            "new_display_quota": new_display_quota,
            "raw_quota_delta": actual_raw_delta,
            "display_delta": actual_display_delta,
            "raw_quota_total": new_total_raw_quota,
            "quota_per_unit": ratio,
        }

    async def get_today_heist_counts_by_qq(self, robber_qq_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM daily_heist_log WHERE robber_qq_id = %s AND DATE(heist_time) = CURDATE()"
        result = await self.execute_query(query, (robber_qq_id,), fetch='one')
        return result['count'] if result else 0
    async def get_today_defenses_count_by_id(self, victim_website_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM daily_heist_log WHERE victim_website_id = %s AND DATE(heist_time) = CURDATE() AND outcome IN ('SUCCESS', 'CRITICAL')"
        result = await self.execute_query(query, (victim_website_id,), fetch='one')
        return result['count'] if result else 0

    async def get_last_heist_time_by_qq(self, robber_qq_id: int) -> Optional[datetime]:
        """获取指定用户最近一次打劫的时间。"""
        query = "SELECT MAX(heist_time) as last_time FROM daily_heist_log WHERE robber_qq_id = %s"
        result = await self.execute_query(query, (robber_qq_id,), fetch='one')
        return result['last_time'] if result and result['last_time'] else None
    async def log_heist_attempt(self, robber_qq_id: int, victim_website_id: int, outcome: str, amount: int) -> int:
        query = "INSERT INTO daily_heist_log (robber_qq_id, victim_website_id, heist_time, outcome, amount) VALUES (%s, %s, %s, %s, %s)"
        return await self.execute_query(query, (robber_qq_id, victim_website_id, datetime.utcnow(), outcome, amount))
    async def transfer_display_quota(self, from_user_id: int, to_user_id: int, display_amount: float, allow_partial: bool = False) -> Tuple[bool, float, int]:
        ratio = self.config.get('binding_settings.quota_display_ratio', 500000)
        raw_amount = int(display_amount * ratio)
        transfer_success, actual_raw_amount = await self._transfer_quota(from_user_id=from_user_id, to_user_id=to_user_id, raw_amount=raw_amount, allow_partial=allow_partial)
        actual_display_amount = actual_raw_amount / ratio
        return transfer_success, actual_display_amount, actual_raw_amount
    async def _transfer_quota(self, from_user_id: int, to_user_id: int, raw_amount: int, allow_partial: bool = False) -> Tuple[bool, int]:
        from_user = await self.get_api_user_data(from_user_id)
        to_user = await self.get_api_user_data(to_user_id)
        if not from_user or not to_user:
            return False, 0
        from_balance = from_user.get("quota", 0)
        actual_amount = raw_amount
        if from_balance < raw_amount:
            if allow_partial:
                actual_amount = from_balance
            else:
                return False, 0
        if actual_amount <= 0:
            return True, 0
        from_user["quota"] -= actual_amount
        update_from_success = await self.update_api_user(from_user)
        if not update_from_success:
            return False, 0
        to_user["quota"] += actual_amount
        update_to_success = await self.update_api_user(to_user)
        if not update_to_success:
            logger.error(f"Quota transfer failed at receiving end (to_user_id: {to_user_id}). Attempting to roll back deduction for from_user_id: {from_user_id}.")
            from_user["quota"] += actual_amount
            rollback_update_success = await self.update_api_user(from_user)
            if not rollback_update_success:
                logger.critical(f"CRITICAL FAILURE: Rollback for from_user_id {from_user_id} FAILED. User has lost {actual_amount} quota. Manual intervention required.")
            return False, 0
        return True, actual_amount
