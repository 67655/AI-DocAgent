# -*- coding: utf-8 -*-
"""plugins 模块单元测试"""
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.base_plugin import (
    BasePlugin, PluginType, PluginStatus,
    ExtractionPromptPlugin, CleanRulePlugin, DocParserPlugin,
)
from plugins.plugin_manager import PluginManager, plugin_manager
from plugins.builtin_plugins import (
    WhitespaceNormalizerPlugin,
    URLNormalizerPlugin,
    HTMLTagStripperPlugin,
    SensitiveDataMaskerPlugin,
    GenericEntityExtractionPrompt,
    KeyValueExtractionPrompt,
    SummaryGenerationPrompt,
    CSVTableParserPlugin,
)


# ============================
# 插件基类测试
# ============================
class TestBasePlugin:
    def test_plugin_lifecycle(self):
        """测试插件生命周期"""

        class TestPlugin(BasePlugin):
            plugin_name = "test_lifecycle"
            plugin_type = PluginType.CUSTOM

        p = TestPlugin()
        assert p.is_enabled() is False
        assert p.status == PluginStatus.DISABLED

        p.on_enable()
        assert p.is_enabled() is True

        p.on_disable()
        assert p.is_enabled() is False

    def test_plugin_info(self):
        class TestPlugin(BasePlugin):
            plugin_name = "my_plugin"
            plugin_version = "2.0"
            plugin_description = "测试插件"
            plugin_author = "测试者"

        p = TestPlugin(config={"key": "val"})
        p.on_enable()
        info = p.get_info()
        assert info["name"] == "my_plugin"
        assert info["version"] == "2.0"
        assert info["status"] == "enabled"

    def test_plugin_on_error(self):
        class TestPlugin(BasePlugin):
            plugin_name = "error_test"

        p = TestPlugin()
        p.on_error("发生致命错误")
        assert p.status == PluginStatus.ERROR
        assert "致命错误" in p.get_info()["error"]

    def test_extraction_prompt_plugin(self):
        class MyPrompt(ExtractionPromptPlugin):
            plugin_name = "my_prompt"

            def get_prompt_template(self):
                return "分析: {text}"

            def get_system_prompt(self):
                return "你是助手"

        p = MyPrompt()
        assert p.plugin_type == PluginType.EXTRACTION_PROMPT
        assert "{text}" in p.get_prompt_template()

    def test_clean_rule_plugin(self):
        class MyCleaner(CleanRulePlugin):
            plugin_name = "my_cleaner"

            def clean(self, data):
                data["cleaned"] = True
                return data

        p = MyCleaner()
        result = p.clean({"raw": "data"})
        assert result["cleaned"] is True

    def test_doc_parser_plugin(self):
        class MyParser(DocParserPlugin):
            plugin_name = "my_parser"
            supported_extensions = ["xyz"]

            def parse(self, file_path, **kwargs):
                return {"text": "parsed", "paragraphs": ["p1"], "metadata": {}}

        p = MyParser()
        assert p.can_parse("test.xyz") is True
        assert p.can_parse("test.pdf") is False
        result = p.parse("test.xyz")
        assert result["text"] == "parsed"


# ============================
# PluginManager 测试
# ============================
class TestPluginManager:
    def setup_method(self):
        self.pm = PluginManager()

    def test_register(self):
        class P(BasePlugin):
            plugin_name = "register_test"

        self.pm.register(P, auto_enable=True)
        assert self.pm.get("register_test") is not None
        assert self.pm.get("register_test").is_enabled()

    def test_enable_disable(self):
        class P(BasePlugin):
            plugin_name = "toggle_test"

        self.pm.register(P, auto_enable=False)
        assert not self.pm.get("toggle_test").is_enabled()

        self.pm.enable("toggle_test")
        assert self.pm.get("toggle_test").is_enabled()

        self.pm.disable("toggle_test")
        assert not self.pm.get("toggle_test").is_enabled()

    def test_unregister(self):
        class P(BasePlugin):
            plugin_name = "remove_me"

        self.pm.register(P)
        assert self.pm.get("remove_me") is not None
        self.pm.unregister("remove_me")
        assert self.pm.get("remove_me") is None

    def test_get_enabled_filtered(self):
        class ExtPrompt(ExtractionPromptPlugin):
            plugin_name = "ext1"
            def get_prompt_template(self): return "{text}"
            def get_system_prompt(self): return "sys"

        class Cleaner(CleanRulePlugin):
            plugin_name = "cln1"
            def clean(self, data): return data

        self.pm.register(ExtPrompt, auto_enable=True)
        self.pm.register(Cleaner, auto_enable=True)

        prompts = self.pm.get_enabled(PluginType.EXTRACTION_PROMPT)
        assert len(prompts) == 1
        assert isinstance(prompts[0], ExtractionPromptPlugin)

    def test_list_all(self):
        class P1(BasePlugin):
            plugin_name = "p1"
        class P2(BasePlugin):
            plugin_name = "p2"

        self.pm.register(P1, auto_enable=True)
        self.pm.register(P2, auto_enable=False)

        all_info = self.pm.list_all()
        assert len(all_info) == 2
        statuses = {i["name"]: i["status"] for i in all_info}
        assert statuses["p1"] == "enabled"
        assert statuses["p2"] == "disabled"

    def test_save_and_load_config(self):
        class P(BasePlugin):
            plugin_name = "cfg_plugin"

        self.pm.register(P, auto_enable=True)

        tmp = tempfile.mkdtemp()
        cfg_path = os.path.join(tmp, "plugins.json")
        try:
            self.pm.save_config(cfg_path)
            assert os.path.exists(cfg_path)

            # 修改状态后加载
            self.pm.disable("cfg_plugin")
            self.pm.load_config(cfg_path)
            assert self.pm.get("cfg_plugin").is_enabled()
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_get_prompt_plugins(self):
        class P(ExtractionPromptPlugin):
            plugin_name = "prompt_p"
            def get_prompt_template(self): return "t"
            def get_system_prompt(self): return "s"

        self.pm.register(P, auto_enable=True)
        result = self.pm.get_prompt_plugins()
        assert len(result) == 1

    def test_get_clean_plugins(self):
        class C(CleanRulePlugin):
            plugin_name = "clean_c"
            def clean(self, data): return data

        self.pm.register(C, auto_enable=True)
        result = self.pm.get_clean_plugins()
        assert len(result) == 1

    def test_apply_clean_pipeline(self):
        """测试清洗管道依次执行"""
        class C1(CleanRulePlugin):
            plugin_name = "c1"
            def clean(self, data):
                data["step1"] = True
                return data

        class C2(CleanRulePlugin):
            plugin_name = "c2"
            def clean(self, data):
                data["step2"] = True
                return data

        self.pm.register(C1, auto_enable=True)
        self.pm.register(C2, auto_enable=True)

        result = self.pm.apply_clean_pipeline({"raw": "data"})
        assert result["step1"] is True
        assert result["step2"] is True

    def test_get_doc_parser_for_file(self):
        class P(DocParserPlugin):
            plugin_name = "xyz_parser"
            supported_extensions = ["xyz"]
            def parse(self, path, **kw):
                return {"text": "", "paragraphs": [], "metadata": {}}

        self.pm.register(P, auto_enable=True)
        found = self.pm.get_doc_parser_for_file("test.xyz")
        assert found is not None
        assert found.plugin_name == "xyz_parser"

        not_found = self.pm.get_doc_parser_for_file("test.pdf")
        assert not_found is None


# ============================
# 内置插件测试
# ============================
class TestBuiltinPlugins:
    def test_whitespace_normalizer(self):
        p = WhitespaceNormalizerPlugin()
        p.on_enable()
        result = p.clean({"text": "hello   world\n\n\nbye", "num": 123})
        assert result["text"] == "hello world\n\nbye"
        assert result["num"] == 123

    def test_url_normalizer(self):
        p = URLNormalizerPlugin()
        p.on_enable()
        result = p.clean({"link": "https://example.com?page=1&utm_source=fb&id=5"})
        assert "utm_source" not in result["link"]
        assert "id=5" in result["link"]

    def test_html_tag_stripper(self):
        p = HTMLTagStripperPlugin()
        p.on_enable()
        result = p.clean({"content": "<div>Hello <b>World</b></div>"})
        assert result["content"] == "Hello World"

    def test_sensitive_data_masker(self):
        p = SensitiveDataMaskerPlugin()
        p.on_enable()
        result = p.clean({"info": "手机13800138000，邮箱test@example.com"})
        assert "13800138000" not in result["info"]
        assert "****" in result["info"]
        assert "test@example.com" not in result["info"]

    def test_generic_entity_prompt(self):
        p = GenericEntityExtractionPrompt()
        assert "{text}" in p.get_prompt_template()
        assert "系统" in p.get_system_prompt() or "system" in p.get_system_prompt().lower()

    def test_kv_extraction_prompt(self):
        p = KeyValueExtractionPrompt()
        assert "{text}" in p.get_prompt_template()
        assert "snake_case" in p.get_prompt_template()

    def test_summary_prompt(self):
        p = SummaryGenerationPrompt()
        assert "{text}" in p.get_prompt_template()
        assert "summary" in p.get_prompt_template().lower()

    def test_csv_parser(self):
        p = CSVTableParserPlugin()
        p.on_enable()
        assert p.can_parse("data.csv") is True

        tmp = tempfile.mkdtemp()
        try:
            csv_path = os.path.join(tmp, "test.csv")
            with open(csv_path, "w") as f:
                f.write("name,age\nAlice,30\nBob,25")
            result = p.parse(csv_path)
            assert result["text"] != ""
            assert "records" in result
            assert len(result["records"]) == 2
            assert result["records"][0]["name"] == "Alice"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)


# ============================
# 全局单例测试
# ============================
class TestGlobalPluginManager:
    def test_singleton(self):
        pm1 = PluginManager()
        pm2 = PluginManager()
        assert pm1 is pm2

    def test_global_instance(self):
        assert isinstance(plugin_manager, PluginManager)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
