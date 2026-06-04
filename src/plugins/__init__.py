# 插件系统模块 - 自定义Prompt/清洗规则/解析插件
from .base_plugin import (
    BasePlugin, PluginType, PluginStatus,
    ExtractionPromptPlugin, CleanRulePlugin, DocParserPlugin,
)
from .plugin_manager import PluginManager, plugin_manager
from .builtin_plugins import (
    WhitespaceNormalizerPlugin,
    URLNormalizerPlugin,
    HTMLTagStripperPlugin,
    SensitiveDataMaskerPlugin,
    GenericEntityExtractionPrompt,
    KeyValueExtractionPrompt,
    SummaryGenerationPrompt,
    CSVTableParserPlugin,
)

__all__ = [
    "BasePlugin",
    "PluginType",
    "PluginStatus",
    "ExtractionPromptPlugin",
    "CleanRulePlugin",
    "DocParserPlugin",
    "PluginManager",
    "plugin_manager",
    "WhitespaceNormalizerPlugin",
    "URLNormalizerPlugin",
    "HTMLTagStripperPlugin",
    "SensitiveDataMaskerPlugin",
    "GenericEntityExtractionPrompt",
    "KeyValueExtractionPrompt",
    "SummaryGenerationPrompt",
    "CSVTableParserPlugin",
]
