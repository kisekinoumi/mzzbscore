# utils/core/twitter_config.py
# Twitter账号配置管理模块 — 基于 Scweet，输入完整 Cookie 串，内部自动提取 auth_token

import logging
from typing import Dict, Optional
from utils.network.proxy_config import get_global_proxy


class TwitterInteractiveConfig:
    """Twitter 交互式配置管理器（Scweet 版本）"""

    def __init__(self):
        """初始化 Twitter 配置"""
        self.config: Dict = {
            'cookies': '',       # 完整 Cookie 字符串（浏览器复制）
            'is_enabled': False,
            'is_validated': False,
        }
        self.validation_attempted = False

        # 设置交互式 logger（无时间戳，直接输出）
        from utils.core.logger import setup_interactive_logger
        self.logger = setup_interactive_logger()

        # 屏蔽 Scweet 内部日志，避免干扰用户交互输出
        logging.getLogger('Scweet').setLevel(logging.ERROR)

    # ------------------------------------------------------------------
    # Cookie 解析工具
    # ------------------------------------------------------------------

    @staticmethod
    def extract_auth_token(cookies_str: str) -> Optional[str]:
        """
        从完整 Cookie 字符串中提取 auth_token 的值。
        支持格式：'key1=val1; key2=val2; ...' 或 'key1=val1;key2=val2;...'
        Args:
            cookies_str: 浏览器复制的完整 Cookie 字符串
        Returns:
            str or None: auth_token 的值，找不到时返回 None
        """
        if not cookies_str:
            return None
        for part in cookies_str.split(';'):
            part = part.strip()
            if '=' not in part:
                continue
            key, _, value = part.partition('=')
            if key.strip() == 'auth_token':
                return value.strip()
        return None

    # ------------------------------------------------------------------
    # 用户交互
    # ------------------------------------------------------------------

    def collect_user_input(self) -> bool:
        """
        交互式收集用户完整 Twitter/X Cookie 字符串
        Returns:
            bool: 是否成功收集到有效配置
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("[TWITTER] Twitter粉丝数获取功能配置")
        self.logger.info("=" * 60)
        self.logger.info("此功能可以自动获取动画相关Twitter账号的粉丝数")
        self.logger.info("需要提供您的 Twitter/X 账号的完整 Cookie 字符串")
        self.logger.info("如不需要此功能，直接按 Enter 跳过，或按 Ctrl+C 取消")
        self.logger.info("-" * 60)
        self.logger.info("")
        self.logger.info("[获取方式]")
        self.logger.info("  1. 在浏览器中登录 x.com")
        self.logger.info("  2. 按 F12 打开开发者工具")
        self.logger.info("  3. 进入 Application → Cookies → https://x.com")
        self.logger.info("  4. 找到所有 Cookie 条目，将其整体复制为一行字符串")
        self.logger.info("     格式示例：auth_token=abc123; ct0=xyz456; ...")
        self.logger.info("-" * 60)

        try:
            cookies = input("[INPUT] 请输入完整 Cookie 字符串（留空则跳过此功能）: ").strip()

            if not cookies:
                self.logger.info("[SKIP] 未输入 Cookie，将跳过Twitter粉丝数功能")
                self.config['is_enabled'] = False
                return False

            self.config['cookies'] = cookies
            self.config['is_enabled'] = True
            self.logger.info(f"[OK] 已接收 Cookie 字符串（长度: {len(cookies)} 字符）")
            return True

        except KeyboardInterrupt:
            self.logger.info("\n\n[SKIP] 用户取消配置，将跳过Twitter粉丝数功能")
            self.config['is_enabled'] = False
            return False
        except Exception as e:
            logging.error(f"收集Twitter配置时出错: {e}")
            self.logger.info(f"\n[ERROR] 配置过程中出现错误: {e}")
            self.logger.info("将跳过Twitter粉丝数功能")
            self.config['is_enabled'] = False
            return False

    # ------------------------------------------------------------------
    # 配置验证
    # ------------------------------------------------------------------

    def validate_config(self) -> bool:
        """
        验证 Twitter 配置是否有效（含真实连接测试）
        Returns:
            bool: 配置是否有效
        """
        if not self.config['is_enabled']:
            return False

        if self.validation_attempted:
            return self.config['is_validated']

        self.validation_attempted = True

        try:
            self.logger.info("\n[SEARCH] 正在验证Twitter配置...")

            # 基本格式校验：Cookie 串整体长度
            cookies = self.config['cookies']
            if not cookies or len(cookies) < 20:
                self.logger.info("[ERROR] Cookie 字符串为空或过短，可能不完整")
                self.config['is_validated'] = False
                return False

            # 从 Cookie 串中提取 auth_token
            auth_token = self.extract_auth_token(cookies)
            if not auth_token:
                self.logger.info("[ERROR] 在 Cookie 字符串中未找到 auth_token 字段")
                self.logger.info("        请确认格式为：auth_token=xxx; ct0=yyy; ...")
                self.config['is_validated'] = False
                return False

            token_display = auth_token[:8] + "..."
            self.logger.info(f"[OK] 成功提取 auth_token: {token_display}")

            # 检查 Scweet 库是否可用
            try:
                from Scweet import Scweet, ScweetConfig
                self.logger.info("[OK] Scweet库导入成功")
            except ImportError:
                self.logger.info("[ERROR] Scweet库未安装，请运行: pip install -U Scweet")
                self.config['is_validated'] = False
                return False

            # 进行真实连接测试
            self.logger.info("[LOADING] 正在进行Twitter连接测试...")
            if self._test_twitter_connection():
                self.logger.info("[OK] Twitter连接测试成功，功能已启用")
                self.config['is_validated'] = True
                return True
            else:
                self.logger.info("[ERROR] Twitter连接测试失败，功能已禁用")
                self.config['is_validated'] = False
                self.config['is_enabled'] = False
                return False

        except Exception as e:
            logging.error(f"验证Twitter配置时出错: {e}")
            self.logger.info(f"[ERROR] 验证过程中出现错误: {e}")
            self.config['is_validated'] = False
            return False

    def _test_twitter_connection(self) -> bool:
        """
        使用 Scweet 进行真实连接测试（查询一个已知账号）
        Returns:
            bool: 连接测试是否成功
        """
        try:
            from Scweet import Scweet, ScweetConfig
            from Scweet import ScweetError, AuthError, AccountPoolExhausted

            auth_token = self.extract_auth_token(self.config['cookies'])
            if not auth_token:
                self.logger.info("[ERROR] 无法从 Cookie 中提取 auth_token")
                return False

            # 获取代理配置
            proxy_config = get_global_proxy()
            proxy_url = None
            if proxy_config:
                proxy_url = proxy_config.get('http')
                self.logger.info(f"[PROXY] 测试将使用代理: {proxy_url}")

            # 构建 Scweet 实例，提高日限额防止误判
            config_kwargs = {
                'daily_requests_limit': 5000,
                'requests_per_min': 100
            }
            if proxy_url:
                config_kwargs['proxy'] = proxy_url

            config = ScweetConfig(**config_kwargs)
            s = Scweet(auth_token=auth_token, config=config)

            # 测试查询 @naobou_official（动漫相关账号，几乎必然存在）
            self.logger.info("[SEARCH] 正在测试查询 @naobou_official 的粉丝数...")
            results = s.get_user_info(["naobou_official"])

            if results:
                user_info = results[0]
                followers_count = user_info.get('followers_count')
                if followers_count is not None:
                    self.logger.info(
                        f"[OK] 连接测试成功！@naobou_official 粉丝数: {int(followers_count):,}"
                    )
                    # 将已验证的 Scweet 实例预传给 TwitterFollowersHelper
                    self._preload_api_instance(s)
                    return True
                else:
                    self.logger.info("[ERROR] 获取到用户信息，但 followers_count 字段缺失")
                    return False
            else:
                self.logger.info("[ERROR] 连接测试返回空结果")
                return False

        except AuthError as e:
            self.logger.info(f"[ERROR] 认证失败，请确认 auth_token 正确且未过期: {e}")
            return False
        except AccountPoolExhausted as e:
            self.logger.info(f"[WARN] 账号达到限额，但配置本身有效，将在后续使用中重试: {e}")
            # 账号限额不代表 token 无效，允许继续
            return True
        except Exception as e:
            self.logger.info(f"[ERROR] 连接测试失败: {e}")
            return False

    def _preload_api_instance(self, scweet_instance) -> None:
        """
        将测试时已初始化的 Scweet 实例预加载到 TwitterFollowersAPI 单例中，
        避免后续重复初始化。
        """
        try:
            from src.extractors.twitter import TwitterFollowersHelper, TwitterFollowersAPI
            TwitterFollowersHelper.reset_instance()
            api = TwitterFollowersHelper.get_api_instance()
            api._scweet = scweet_instance
            api.is_initialized = True
            self.logger.info("[OK] Scweet API 实例已预加载，无需重复初始化")
        except Exception as e:
            logging.warning(f"预加载 Scweet 实例失败（无影响，会在首次使用时重新初始化）: {e}")

    # ------------------------------------------------------------------
    # 状态查询 / 控制
    # ------------------------------------------------------------------

    def get_config(self) -> Dict:
        """获取配置信息（副本）"""
        return self.config.copy()

    def is_enabled(self) -> bool:
        """检查 Twitter 功能是否已启用且验证通过"""
        return self.config.get('is_enabled', False) and self.config.get('is_validated', False)

    def get_account_info(self) -> Optional[Dict]:
        """
        获取账号信息（供 TwitterFollowersAPI 使用）
        Returns:
            dict or None: 包含 auth_token 的字典，未启用时返回 None
        """
        if not self.is_enabled():
            return None
        auth_token = self.extract_auth_token(self.config['cookies'])
        if not auth_token:
            return None
        return {'auth_token': auth_token}

    def disable_with_reason(self, reason: str) -> None:
        """
        禁用 Twitter 功能并记录原因
        Args:
            reason: 禁用原因
        """
        self.config['is_enabled'] = False
        self.config['is_validated'] = False
        logging.warning(f"Twitter功能已禁用: {reason}")
        self.logger.info(f"[WARN] Twitter粉丝数功能已禁用: {reason}")
        self.logger.info("程序将继续运行其他功能")

        # 重置 TwitterFollowersHelper 实例以立即生效
        try:
            from src.extractors.twitter import TwitterFollowersHelper
            TwitterFollowersHelper.reset_instance()
        except ImportError:
            pass

    def show_final_status(self) -> None:
        """显示最终配置状态"""
        self.logger.info("\n" + "=" * 60)
        if self.is_enabled():
            self.logger.info("[OK] Twitter粉丝数功能已启用")
            cookies = self.config.get('cookies', '')
            self.logger.info(f"[COOKIE] Cookie 长度: {len(cookies)} 字符")
            auth_token = self.extract_auth_token(cookies)
            if auth_token:
                self.logger.info(f"[TOKEN] auth_token: {auth_token[:8]}...")
        else:
            self.logger.info("[SKIP] Twitter粉丝数功能已跳过")
            self.logger.info("   程序将继续运行其他评分数据获取功能")
        self.logger.info("=" * 60 + "\n")


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------

_twitter_config: Optional[TwitterInteractiveConfig] = None


def get_twitter_config() -> TwitterInteractiveConfig:
    """获取全局 Twitter 配置实例（单例）"""
    global _twitter_config
    if _twitter_config is None:
        _twitter_config = TwitterInteractiveConfig()
    return _twitter_config


def setup_twitter_config() -> bool:
    """
    设置 Twitter 配置（程序启动时调用一次）
    Returns:
        bool: 是否成功配置并验证
    """
    config = get_twitter_config()

    # 1. 收集用户输入
    if not config.collect_user_input():
        config.show_final_status()
        return False

    # 2. 验证配置（含真实连接测试）
    if not config.validate_config():
        config.disable_with_reason("配置验证失败")
        config.show_final_status()
        return False

    config.show_final_status()
    return True