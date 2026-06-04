# -*- coding: utf-8 -*-
"""
插件基类
定义三类插件接口：抽取Prompt插件、清洗规则插件、文档解析插件
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    """插件类型枚举"""
    EXTRACTION_PROMPT = "extraction_prompt"     # 抽取Prompt插件
    CLEAN_RULE = "clean_rule"                   # 清洗规则插件
    DOC_PARSER = "doc_parser"                   # 文档解析插件
    CUSTOM = "custom"                           # 自定义通用插件


class PluginStatus(str, Enum):
    """插件状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class BasePlugin(ABC):
    """
    插件抽象基类
    所有插件必须继承此基类并实现对应接口
    """

    plugin_type: PluginType = PluginType.CUSTOM
    plugin_name: str = "base_plugin"
    plugin_version: str = "1.0"
    plugin_description: str = ""
    plugin_author: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: 插件配置字典
        """
        self.config = config or {}
        self.status = PluginStatus.DISABLED
        self._error_message: Optional[str] = None

    def on_enable(self):
        """插件启用时的回调（子类可重写）"""
        self.status = PluginStatus.ENABLED
        self._error_message = None

    def on_disable(self):
        """插件禁用时的回调（子类可重写）"""
        self.status = PluginStatus.DISABLED

    def on_error(self, error: str):
        """插件异常时的回调"""
        self.status = PluginStatus.ERROR
        self._error_message = error

    def is_enabled(self) -> bool:
        return self.status == PluginStatus.ENABLED

    def get_info(self) -> Dict[str, Any]:
        """获取插件信息"""
        return {
            "name": self.plugin_name,
            "type": self.plugin_type.value,
            "version": self.plugin_version,
            "description": self.plugin_description,
            "author": self.plugin_author,
            "status": self.status.value,
            "error": self._error_message,
        }


# ============================
# 三类插件抽象基类
# ============================

class ExtractionPromptPlugin(BasePlugin, ABC):
    """抽取Prompt插件基类"""

    plugin_type = PluginType.EXTRACTION_PROMPT

    @abstractmethod
    def get_prompt_template(self) -> str:
        """
        返回Prompt模板字符串
        可用占位符: {text}, {context}, {schema}
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """返回System Prompt"""
        pass

    def get_output_schema_hint(self) -> Optional[str]:
        """返回期望输出格式提示（可选）"""
        return None


class CleanRulePlugin(BasePlugin, ABC):
    """清洗规则插件基类"""

    plugin_type = PluginType.CLEAN_RULE

    @abstractmethod
    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对数据进行清洗转换

        Args:
            data: 原始数据字典

        Returns:
            清洗后的数据字典
        """
        pass

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        校验数据是否满足清洗条件（可选）

        Args:
            data: 数据字典

        Returns:
            是否需要清洗
        """
        return True


class DocParserPlugin(BasePlugin, ABC):
    """文档解析插件基类"""

    plugin_type = PluginType.DOC_PARSER
    supported_extensions: List[str] = []

    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        解析文档文件

        Args:
            file_path: 文件路径
            **kwargs: 扩展参数

        Returns:
            解析结果字典，至少包含:
            - text: 文本内容
            - paragraphs: 段落列表
            - metadata: 元数据字典
        """
        pass

    def can_parse(self, file_path: str) -> bool:
        """判断是否能解析该文件"""
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        return ext in self.supported_extensions
