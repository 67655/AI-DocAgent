# -*- coding: utf-8 -*-
"""
插件管理器
负责插件的注册、加载、启用/禁用、配置管理
"""
import json
import importlib
import os
from typing import Any, Dict, List, Optional, Type

from .base_plugin import (
    BasePlugin, PluginType, PluginStatus,
    ExtractionPromptPlugin, CleanRulePlugin, DocParserPlugin,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PluginManager:
    """
    插件管理器（单例模式）
    统一管理所有插件的注册、发现、启用/禁用
    """

    _instance: Optional["PluginManager"] = None

    def __new__(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_classes: Dict[str, Type[BasePlugin]] = {}
        self._config_file: Optional[str] = None

    # ============================
    # 注册
    # ============================
    def register(self, plugin_class: Type[BasePlugin], config: Optional[Dict] = None,
                 auto_enable: bool = False):
        """
        注册插件类并实例化

        Args:
            plugin_class: 插件类（需继承BasePlugin）
            config: 插件配置
            auto_enable: 是否自动启用
        """
        temp_instance = plugin_class(config=config)
        name = temp_instance.plugin_name

        if name in self._plugins:
            logger.warning(f"插件 '{name}' 已存在，将被覆盖")

        instance = plugin_class(config=config)
        self._plugins[name] = instance
        self._plugin_classes[name] = plugin_class

        if auto_enable:
            self.enable(name)
        else:
            instance.status = PluginStatus.DISABLED

        logger.info(f"插件已注册: {name} (类型: {instance.plugin_type.value}) [{instance.status.value}]")

    def unregister(self, plugin_name: str):
        """注销插件"""
        if plugin_name in self._plugins:
            self.disable(plugin_name)
            del self._plugins[plugin_name]
            self._plugin_classes.pop(plugin_name, None)
            logger.info(f"插件已注销: {plugin_name}")

    # ============================
    # 启用/禁用
    # ============================
    def enable(self, plugin_name: str) -> bool:
        """启用插件"""
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            logger.error(f"插件不存在: {plugin_name}")
            return False
        try:
            plugin.on_enable()
            logger.info(f"插件已启用: {plugin_name}")
            return True
        except Exception as e:
            plugin.on_error(str(e))
            logger.error(f"插件启用失败 {plugin_name}: {e}")
            return False

    def disable(self, plugin_name: str) -> bool:
        """禁用插件"""
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return False
        try:
            plugin.on_disable()
            logger.info(f"插件已禁用: {plugin_name}")
            return True
        except Exception as e:
            plugin.on_error(str(e))
            logger.error(f"插件禁用失败 {plugin_name}: {e}")
            return False

    def enable_all(self) -> int:
        """启用所有插件，返回成功数量"""
        count = 0
        for name in self._plugins:
            if self.enable(name):
                count += 1
        return count

    def disable_all(self):
        """禁用所有插件"""
        for name in self._plugins:
            self.disable(name)

    # ============================
    # 查询
    # ============================
    def get(self, plugin_name: str) -> Optional[BasePlugin]:
        """获取指定插件实例"""
        return self._plugins.get(plugin_name)

    def get_enabled(self, plugin_type: Optional[PluginType] = None) -> List[BasePlugin]:
        """
        获取所有已启用的插件

        Args:
            plugin_type: 按类型过滤（None返回全部）

        Returns:
            已启用的插件列表
        """
        plugins = [p for p in self._plugins.values() if p.is_enabled()]
        if plugin_type:
            plugins = [p for p in plugins if p.plugin_type == plugin_type]
        return plugins

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已注册的插件信息"""
        return [p.get_info() for p in self._plugins.values()]

    def list_by_type(self, plugin_type: PluginType) -> List[Dict[str, Any]]:
        """列出指定类型的插件信息"""
        return [
            p.get_info() for p in self._plugins.values()
            if p.plugin_type == plugin_type
        ]

    def get_prompt_plugins(self) -> List[ExtractionPromptPlugin]:
        """获取所有已启用的Prompt插件"""
        return [
            p for p in self.get_enabled(PluginType.EXTRACTION_PROMPT)
            if isinstance(p, ExtractionPromptPlugin)
        ]

    def get_clean_plugins(self) -> List[CleanRulePlugin]:
        """获取所有已启用的清洗插件"""
        return [
            p for p in self.get_enabled(PluginType.CLEAN_RULE)
            if isinstance(p, CleanRulePlugin)
        ]

    def get_parser_plugins(self) -> List[DocParserPlugin]:
        """获取所有已启用的解析插件"""
        return [
            p for p in self.get_enabled(PluginType.DOC_PARSER)
            if isinstance(p, DocParserPlugin)
        ]

    # ============================
    # 配置管理
    # ============================
    def save_config(self, file_path: str):
        """
        保存插件配置到JSON文件

        Args:
            file_path: 配置文件路径
        """
        config_data = {
            "version": "1.0",
            "plugins": {}
        }
        for name, plugin in self._plugins.items():
            config_data["plugins"][name] = {
                "enabled": plugin.is_enabled(),
                "config": plugin.config,
                "class_path": f"{plugin.__class__.__module__}.{plugin.__class__.__name__}",
            }

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        self._config_file = file_path
        logger.info(f"插件配置已保存: {file_path}")

    def load_config(self, file_path: str):
        """
        从JSON文件加载插件配置并启用对应插件

        Args:
            file_path: 配置文件路径
        """
        if not os.path.exists(file_path):
            logger.warning(f"插件配置文件不存在: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        plugins_cfg = config_data.get("plugins", {})
        for name, cfg in plugins_cfg.items():
            if name in self._plugins:
                # 更新已有插件的配置
                plugin = self._plugins[name]
                plugin.config.update(cfg.get("config", {}))
                if cfg.get("enabled", False):
                    self.enable(name)
                else:
                    self.disable(name)

        self._config_file = file_path
        logger.info(f"插件配置已加载: {file_path} ({len(plugins_cfg)}个插件)")

    # ============================
    # 插件管道执行
    # ============================
    def apply_clean_pipeline(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        依次执行所有已启用的清洗插件

        Args:
            data: 待清洗的数据

        Returns:
            清洗后的数据
        """
        result = data
        for plugin in self.get_clean_plugins():
            try:
                if plugin.validate(result):
                    result = plugin.clean(result)
            except Exception as e:
                logger.error(f"清洗插件 {plugin.plugin_name} 执行失败: {e}")
                plugin.on_error(str(e))
        return result

    def get_doc_parser_for_file(self, file_path: str) -> Optional[DocParserPlugin]:
        """
        根据文件路径自动匹配已启用的解析插件

        Args:
            file_path: 文件路径

        Returns:
            匹配的解析插件，无匹配返回None
        """
        for plugin in self.get_parser_plugins():
            if plugin.can_parse(file_path):
                return plugin
        return None


# 全局插件管理器实例
plugin_manager = PluginManager()
