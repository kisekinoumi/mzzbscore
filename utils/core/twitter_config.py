# utils/core/twitter_config.py
# Twitter账号配置管理模块 - 交互式输入版本

import logging
import getpass
import asyncio
import time
from typing import Dict, Optional, Tuple


class TwitterInteractiveConfig:
    """Twitter交互式配置管理器"""
    
    def __init__(self):
        self.config = {
            'cookies': '',
            'is_enabled': False,
            'is_validated': False
        }
        self.validation_attempted = False
    
    def collect_user_input(self) -> bool:
        """
        交互式收集用户Twitter账号信息
        Returns:
            bool: 是否成功收集到有效配置
        """
        print("\n" + "="*60)
        print("[TWITTER] Twitter粉丝数获取功能配置")
        print("="*60)
        print("此功能可以自动获取动画相关Twitter账号的粉丝数")
        print("程序将默认启用此功能，请输入账号信息")
        print("如不需要此功能，可按 Ctrl+C 取消配置")
        print("-"*60)
        
        print("\n[INPUT] 请输入Twitter账号信息：")
        print("[WARNING] 使用Cookies方式获取Twitter粉丝数")
        print("[WARNING] 必填项：Cookies字符串")
        print("[INFO] 获取方式：登录Twitter后，从浏览器开发者工具复制Cookies")
        print("-"*60)
        
        # 收集Cookies（必填，为空则禁用功能）
        try:
            cookies = input("[COOKIE] Twitter Cookies字符串（必填，为空则禁用功能）: ").strip()
            if cookies:
                self.config['cookies'] = cookies
                self.config['is_enabled'] = True
                print("[SUCCESS] 已设置Cookies")
                print("\n[SUCCESS] Twitter账号信息收集完成")
                return True
            else:
                print("[STOP]  输入为空，将禁用Twitter粉丝数功能")
                self.config['is_enabled'] = False
                return False
            
        except KeyboardInterrupt:
            print("\n\n[STOP]  用户取消配置，将禁用Twitter粉丝数功能")
            self.config['is_enabled'] = False
            return False
        except Exception as e:
            logging.error(f"收集Twitter配置时出错: {e}")
            print(f"\n[ERROR] 配置过程中出现错误: {e}")
            print("将禁用Twitter粉丝数功能")
            self.config['is_enabled'] = False
            return False
    
    def validate_config(self) -> bool:
        """
        验证Twitter配置是否有效
        Returns:
            bool: 配置是否有效
        """
        if not self.config['is_enabled']:
            return False
        
        if self.validation_attempted:
            return self.config['is_validated']
        
        self.validation_attempted = True
        
        try:
            print("\n[SEARCH] 正在验证Twitter配置...")
            
            # 检查必填项
            if not self.config['cookies']:
                print("[ERROR] 缺少必填项（Cookies）")
                self.config['is_validated'] = False
                return False
            
            # 尝试导入 twscrape
            try:
                import twscrape
                print("[SUCCESS] twscrape库检查通过")
            except ImportError:
                print("[ERROR] twscrape库未安装，请运行: pip install twscrape")
                self.config['is_validated'] = False
                return False
            
            # 基本格式验证
            cookies = self.config['cookies']
            if len(cookies) < 50:  # Cookies通常很长
                print("[ERROR] Cookies长度过短，可能不完整")
                self.config['is_validated'] = False
                return False
            
            # 检查是否包含基本的Twitter Cookies字段
            required_fields = ['auth_token', 'ct0']
            missing_fields = []
            for field in required_fields:
                if field not in cookies:
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"[WARNING]  Cookies可能缺少关键字段: {', '.join(missing_fields)}")
                print("[INFO] 但仍会尝试使用，如果失败请检查Cookies完整性")
            
            print("[SUCCESS] 基本配置验证通过")
            print("[SEARCH] 正在进行实际连接测试...")
            
            # 进行真实的API连接测试
            if self._test_twitter_connection():
                print("[SUCCESS] Twitter连接测试成功，功能已启用")
                self.config['is_validated'] = True
                return True
            else:
                print("[ERROR] Twitter连接测试失败，功能已禁用")
                self.config['is_validated'] = False
                self.config['is_enabled'] = False
                return False
            
        except Exception as e:
            logging.error(f"验证Twitter配置时出错: {e}")
            print(f"[ERROR] 验证过程中出现错误: {e}")
            self.config['is_validated'] = False
            return False
    
    def _test_twitter_connection(self) -> bool:
        """
        进行真实的Twitter API连接测试
        Returns:
            bool: 连接测试是否成功
        """
        try:
            # 检查twscrape库可用性
            try:
                from twscrape import API
                import asyncio
                import time
                print("[SUCCESS] twscrape库导入成功")
            except ImportError:
                print("[ERROR] twscrape库导入失败")
                return False
            
            # 获取cookies
            cookies_str = self.config['cookies']
            
            # 检查cookies基本格式
            if '=' not in cookies_str or len(cookies_str) < 50:
                print("[ERROR] Cookies格式不正确")
                return False
            
            # 检查关键字段
            if 'auth_token' in cookies_str or 'ct0' in cookies_str:
                print("[SUCCESS] 发现关键Cookies字段")
            else:
                print("[WARNING]  未发现关键Cookies字段 (auth_token, ct0)")
            
            # 进行实际API连接测试
            print("[LOADING] 正在测试API连接...")
            
            async def test_api_connection():
                try:
                    api = API()
                    
                    # 创建测试账号
                    test_username = f"test_user_{int(time.time())}"
                    await api.pool.add_account(
                        username=test_username,
                        password="dummy_password",
                        email="dummy@example.com",
                        email_password="dummy_password",
                        cookies=cookies_str
                    )
                    print(f"[SUCCESS] 成功添加测试账号: {test_username}")
                    
                    # 测试查询 @naobou_official 的粉丝数（这是实际功能要做的事）
                    print("[SEARCH] 正在测试查询 @naobou_official...")
                    test_user = await api.user_by_login("naobou_official")
                    
                    if test_user and hasattr(test_user, 'followersCount'):
                        followers_count = test_user.followersCount
                        print(f"[SUCCESS] 连接测试成功！@naobou_official 粉丝数: {followers_count:,}")
                        return True
                    else:
                        print("[ERROR] 无法获取 @naobou_official 的粉丝数")
                        print(f"[SEARCH] 用户对象: {test_user}")
                        if test_user:
                            print(f"[SEARCH] 用户对象属性: {dir(test_user)}")
                        return False
                        
                except Exception as e:
                    print(f"[ERROR] API连接测试失败: {e}")
                    return False
            
            # 运行异步测试
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有事件循环在运行，在新线程中测试
                    import threading
                    result = [False]
                    exception = [None]
                    
                    def run_test():
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            result[0] = new_loop.run_until_complete(test_api_connection())
                            new_loop.close()
                        except Exception as e:
                            exception[0] = e
                    
                    thread = threading.Thread(target=run_test)
                    thread.start()
                    thread.join(timeout=30)  # 30秒超时
                    
                    if thread.is_alive():
                        print("[ERROR] API连接测试超时")
                        return False
                    
                    if exception[0]:
                        raise exception[0]
                    
                    return result[0]
                else:
                    return loop.run_until_complete(test_api_connection())
                    
            except RuntimeError:
                # 没有事件循环，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(test_api_connection())
                finally:
                    loop.close()
            
        except Exception as e:
            logging.error(f"Twitter连接测试失败: {e}")
            print(f"[ERROR] 连接测试出现错误: {e}")
            return False

    def _test_twitter_basic(self) -> bool:
        """
        基础Twitter配置测试（不进行实际连接）
        Returns:
            bool: 基础测试是否通过
        """
        try:
            # 检查twscrape库可用性
            try:
                from twscrape import API
                print("[SUCCESS] twscrape库导入成功")
            except ImportError:
                print("[ERROR] twscrape库导入失败")
                return False
            
            # 检查Cookies格式
            cookies_str = self.config['cookies']
            if '=' not in cookies_str or ';' not in cookies_str:
                print("[WARNING]  Cookies格式可能不标准，但将继续尝试")
            else:
                print("[SUCCESS] Cookies格式检查通过")
            
            # 检查关键字段
            if 'auth_token' in cookies_str or 'ct0' in cookies_str:
                print("[SUCCESS] 发现关键Cookies字段")
            else:
                print("[WARNING]  未发现标准Cookies字段，但将继续尝试")
            
            return True
            
        except Exception as e:
            logging.error(f"Twitter基础测试失败: {e}")
            print(f"[ERROR] 基础测试出现错误: {e}")
            return False
    
    def _test_twitter_authentication(self) -> bool:
        """测试Twitter认证配置并预初始化API"""
        try:
            print("[SEARCH] 正在测试Twitter配置...")
            
            # 基本导入测试
            try:
                from twscrape import API
                import asyncio
                import time
                print("[SUCCESS] twscrape库导入成功")
            except ImportError:
                print("[ERROR] twscrape库导入失败")
                return False
            
            # 创建异步测试函数
            async def test_and_initialize_api():
                api = API()
                
                # 获取Cookies
                cookies_str = self.config['cookies']
                
                try:
                    # 基本Cookies格式检查
                    if '=' in cookies_str and len(cookies_str) >= 50:
                        print("[SUCCESS] Cookies格式检查通过")
                    else:
                        print("[ERROR] Cookies格式不正确，应为 name1=value1; name2=value2 格式")
                        return False
                    
                    # 检查关键的Twitter cookies字段
                    essential_cookies = ['ct0', 'auth_token']
                    found_essential = False
                    for cookie_name in essential_cookies:
                        if cookie_name in cookies_str:
                            found_essential = True
                            break
                    
                    if found_essential:
                        print("[SUCCESS] 发现关键Cookies字段")
                    else:
                        print("[WARNING]  未发现关键Cookies字段 (ct0, auth_token)，但将继续")
                    
                    # 进行实际的API初始化测试
                    print("[LOADING] 正在初始化Twitter API...")
                    
                    # 创建cookies账号
                    cookies_username = f"cookies_user_{int(time.time())}"
                    
                    try:
                        # 使用twscrape的正确方式：在add_account时直接提供cookies
                        await api.pool.add_account(
                            username=cookies_username,
                            password="dummy_password",
                            email="dummy@example.com",
                            email_password="dummy_password",
                            cookies=cookies_str
                        )
                        print(f"[SUCCESS] 成功添加Cookies账号: {cookies_username}")
                        
                        # 进行简单的API调用测试
                        print("[LOADING] 正在测试API连接...")
                        
                        # 测试获取一个简单的用户信息（Twitter官方账号）
                        test_user = await api.user_by_login("twitter")
                        if test_user and hasattr(test_user, 'username'):
                            print("[SUCCESS] Twitter API连接测试成功")
                            print("[SUCCESS] Twitter配置测试和初始化完成")
                            
                            # 预初始化TwitterFollowersAPI
                            from src.extractors.twitter import TwitterFollowersHelper
                            # 重置实例以确保使用新的配置
                            TwitterFollowersHelper.reset_instance()
                            # 获取实例，这将触发初始化
                            helper_api = TwitterFollowersHelper.get_api_instance()
                            # 设置已初始化标志
                            helper_api.is_initialized = True
                            helper_api.api = api
                            print("[SUCCESS] Twitter粉丝数API已预初始化")
                            
                            return True
                        else:
                            print("[WARNING]  API连接测试失败，但配置可能仍然有效")
                            print("[INFO] 将在实际使用时重新验证")
                            return True
                            
                    except Exception as e:
                        print(f"[WARNING]  API初始化测试失败: {e}")
                        print("[INFO] 基本配置已验证，将在实际使用时重新尝试")
                        return True  # 仍然返回True，允许程序继续
                        
                except Exception as e:
                    print(f"[ERROR] Cookies测试失败: {e}")
                    return False
            
            # 运行异步测试
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有事件循环在运行，在新线程中测试
                    import threading
                    result = [False]
                    exception = [None]
                    
                    def run_test():
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            result[0] = new_loop.run_until_complete(test_and_initialize_api())
                            new_loop.close()
                        except Exception as e:
                            exception[0] = e
                    
                    thread = threading.Thread(target=run_test)
                    thread.start()
                    thread.join(timeout=60)  # 增加到60秒超时，给API测试足够时间
                    
                    if thread.is_alive():
                        print("[ERROR] API初始化测试超时")
                        return False
                    
                    if exception[0]:
                        raise exception[0]
                    
                    return result[0]
                else:
                    return loop.run_until_complete(test_and_initialize_api())
                    
            except RuntimeError:
                # 没有事件循环，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(test_and_initialize_api())
                finally:
                    loop.close()
                    
        except Exception as e:
            logging.error(f"Twitter API初始化测试失败: {e}")
            print(f"[ERROR] API初始化测试出现错误: {e}")
            return False
    
    def get_config(self) -> Dict:
        """获取配置信息"""
        return self.config.copy()
    
    def is_enabled(self) -> bool:
        """检查是否启用Twitter功能"""
        return self.config.get('is_enabled', False) and self.config.get('is_validated', False)
    
    def get_account_info(self) -> Optional[Dict]:
        """
        获取账号信息（用于twscrape）
        Returns:
            dict or None: 账号信息，如果未启用返回None
        """
        if not self.is_enabled():
            return None
        
        return {
            'cookies': self.config['cookies']
        }
    
    def disable_with_reason(self, reason: str) -> None:
        """
        禁用Twitter功能并记录原因
        Args:
            reason: 禁用原因
        """
        self.config['is_enabled'] = False
        self.config['is_validated'] = False
        logging.warning(f"Twitter功能已禁用: {reason}")
        print(f"[WARNING]  Twitter粉丝数功能已禁用: {reason}")
        print("程序将继续运行其他功能")
        
        # 重置TwitterFollowersHelper实例以确保立即生效
        try:
            from src.extractors.twitter import TwitterFollowersHelper
            TwitterFollowersHelper.reset_instance()
        except ImportError:
            pass  # 如果模块未导入则忽略
    
    def show_final_status(self) -> None:
        """显示最终配置状态"""
        print("\n" + "="*60)
        if self.is_enabled():
            print("[SUCCESS] Twitter粉丝数功能已启用")
            print(f"[COOKIE] Cookies配置: {'已设置' if self.config['cookies'] else '未设置'}")
            print(f"📏 Cookies长度: {len(self.config['cookies'])} 字符")
        else:
            print("[ERROR] Twitter粉丝数功能已禁用")
            print("   程序将继续运行其他评分数据获取功能")
        print("="*60 + "\n")


# 全局配置实例
_twitter_config = None

def get_twitter_config() -> TwitterInteractiveConfig:
    """获取全局Twitter配置实例"""
    global _twitter_config
    if _twitter_config is None:
        _twitter_config = TwitterInteractiveConfig()
    return _twitter_config

def setup_twitter_config() -> bool:
    """
    设置Twitter配置（在程序启动时调用）
    Returns:
        bool: 是否成功配置
    """
    config = get_twitter_config()
    
    # 收集用户输入
    if not config.collect_user_input():
        config.show_final_status()
        return False
    
    # 验证配置
    if not config.validate_config():
        config.disable_with_reason("配置验证失败")
        config.show_final_status()
        return False
    
    config.show_final_status()
    return True 