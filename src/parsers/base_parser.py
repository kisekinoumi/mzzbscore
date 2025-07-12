"""
解析器基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging


class BaseParser(ABC):
    """解析器基类，定义解析器的通用接口"""
    
    def __init__(self, name: str):
        """
        初始化解析器
        Args:
            name: 解析器名称
        """
        self.name = name
        self.logger = logging.getLogger(f"Parser.{name}")
    
    @abstractmethod
    def parse(self, content: str) -> Dict[str, Any]:
        """
        解析内容
        Args:
            content: 待解析的内容
        Returns:
            dict: 解析结果
        """
        pass
    
    def log_info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
    
    def log_warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)
    
    def log_error(self, message: str):
        """记录错误日志"""
        self.logger.error(message)
    
    def log_debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)


class HtmlParser(BaseParser):
    """HTML解析器基类"""
    
    def __init__(self, name: str):
        super().__init__(name)
    
    def extract_with_regex(self, pattern: str, content: str, group: int = 1) -> Optional[str]:
        """
        使用正则表达式提取内容
        Args:
            pattern: 正则表达式模式
            content: 待提取的内容
            group: 匹配组编号
        Returns:
            str or None: 提取的内容，未找到返回None
        """
        import re
        match = re.search(pattern, content)
        if match:
            result = match.group(group).strip()
            self.log_debug(f"成功提取内容: {result}")
            return result
        else:
            self.log_warning(f"未找到匹配的内容: {pattern}")
            return None
    
    def extract_multiple_with_regex(self, pattern: str, content: str) -> list:
        """
        使用正则表达式提取多个内容
        Args:
            pattern: 正则表达式模式
            content: 待提取的内容
        Returns:
            list: 提取的内容列表
        """
        import re
        matches = re.findall(pattern, content)
        self.log_debug(f"提取到 {len(matches)} 个匹配项")
        return matches


class UrlParser(BaseParser):
    """URL解析器基类"""
    
    def __init__(self, name: str):
        super().__init__(name)
    
    def extract_id_from_url(self, url: str, pattern: str, group: int = 1) -> Optional[str]:
        """
        从URL中提取ID
        Args:
            url: URL字符串
            pattern: 正则表达式模式
            group: 匹配组编号
        Returns:
            str or None: 提取的ID，未找到返回None
        """
        if not url:
            self.log_warning("URL为空")
            return None
        
        import re
        match = re.search(pattern, url)
        if match:
            extracted_id = match.group(group)
            self.log_info(f"从URL提取到ID: {extracted_id}")
            return extracted_id
        else:
            self.log_warning(f"无法从URL提取ID: {url}")
            return None
    
    def validate_url_format(self, url: str, pattern: str) -> bool:
        """
        验证URL格式
        Args:
            url: URL字符串
            pattern: 正则表达式模式
        Returns:
            bool: 格式是否正确
        """
        if not url:
            return False
        
        import re
        return bool(re.match(pattern, url)) 