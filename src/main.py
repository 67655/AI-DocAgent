#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-DocAgent 主程序入口
通用AI文档结构化处理框架 - CLI命令行工具
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# 确保 src 在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config import config
from src.utils.logger import get_logger, log_manager
from src.utils.md5_utils import deduplicator
from src.parser import parser_factory, ParseResult
from src.extractor import InfoExtractor, llm_factory
from src.converter import converter, OutputSchema
from src.validator import quality_validator, RuleValidator
from src.scheduler import scheduler as task_scheduler
from src.plugins import plugin_manager
from src import __version__

logger = get_logger("main")


def cmd_parse(args):
    """解析文档命令"""
    file_path = args.file
    output = args.output
    fmt = args.format

    logger.info(f"开始解析文档: {file_path}")

    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        sys.exit(1)

    result = parser_factory.parse(file_path)
    if not result.success:
        logger.error(f"解析失败: {result.error}")
        sys.exit(1)

    if fmt == "json":
        output_data = result.to_dict()
        # 包含完整文本内容
        output_data["text"] = result.text
        output_data["paragraphs"] = result.paragraphs[:20]  # 只保留前20段预览
        output_data["full_text_length"] = len(result.text)
        output_str = json.dumps(output_data, ensure_ascii=False, indent=2)
    elif fmt == "text":
        output_str = result.get_full_text()
    else:
        output_str = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_str)
        logger.info(f"解析结果已保存: {output}")
    else:
        print(output_str[:5000])  # 控制台输出限制5000字

    # 统计信息
    logger.info(
        f"解析完成: {len(result.paragraphs)}段落, "
        f"{len(result.tables)}表格, {len(result.text)}字符"
    )


def cmd_extract(args):
    """信息抽取命令"""
    text = args.text
    text_file = args.file
    provider = args.provider or config.DEFAULT_LLM_PROVIDER
    output = args.output
    prompt_name = args.prompt

    # 从文件读取文本
    if text_file:
        if not os.path.exists(text_file):
            logger.error(f"文件不存在: {text_file}")
            sys.exit(1)
        parse_result = parser_factory.parse(text_file)
        if parse_result.success:
            text = parse_result.get_full_text()
        else:
            logger.error(f"文件解析失败: {parse_result.error}")
            sys.exit(1)

    if not text:
        logger.error("请提供待抽取的文本 (--text 或 --file)")
        sys.exit(1)

    logger.info(f"开始LLM信息抽取 (provider={provider})...")

    # 创建抽取器
    extractor = InfoExtractor(provider=provider)

    # 加载已启用的Prompt插件
    prompt_plugins = plugin_manager.get_prompt_plugins()
    for pp in prompt_plugins:
        extractor.register_prompt(pp.plugin_name, pp.get_prompt_template())
        logger.debug(f"加载Prompt插件: {pp.plugin_name}")

    result = extractor.extract(text, prompt_name=prompt_name)

    if result["success"]:
        # 通过converter标准化输出
        standardized = converter.convert_llm_response(result, source_file=text_file or "cli_input")

        output_str = converter.to_json(standardized)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_str)
            logger.info(f"抽取结果已保存: {output}")
        else:
            print(output_str[:5000])
        logger.info("抽取成功")
    else:
        logger.error(f"抽取失败: {result['error']}")
        sys.exit(1)


def cmd_validate(args):
    """数据校验命令"""
    input_file = args.file
    output = args.output
    schema_file = args.schema

    if not os.path.exists(input_file):
        logger.error(f"文件不存在: {input_file}")
        sys.exit(1)

    # 加载数据
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data_list = data if isinstance(data, list) else [data]
    logger.info(f"开始校验 {len(data_list)} 条数据...")

    # 如果指定了Schema文件，从文件加载自定义Schema
    validator = quality_validator
    validator.clear()

    if schema_file and os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_data = json.load(f)
        custom_schema = OutputSchema.from_dict(schema_data)
        from src.converter import Converter
        custom_converter = Converter(custom_schema)
        from src.validator import QualityValidator
        rv = RuleValidator()
        for field_name, rule in custom_schema.fields.items():
            if rule.required:
                rv.add_required_rule(field_name)
        validator = QualityValidator(rule_validator=rv)

    # 加载清洗插件
    validator._error_archive = []
    validator._recheck_queue = []

    summary = validator.validate_batch(data_list)
    logger.info(
        f"校验完成: {summary['passed']}/{summary['total']}通过 "
        f"({summary['pass_rate']}%)"
    )

    if validator.get_error_archive():
        archive_path = output or "error_archive.json"
        validator.export_error_archive(archive_path)
        logger.info(f"异常数据已归档: {archive_path}")

    print(json.dumps({
        "summary": {k: v for k, v in summary.items() if k != "detailed_results"},
        "recheck_count": len(validator.get_recheck_queue()),
    }, ensure_ascii=False, indent=2))


def cmd_batch(args):
    """批量任务调度命令"""
    input_dir = args.dir
    input_file = args.file
    output = args.output
    shard_size = args.shard_size or 10
    provider = args.provider or config.DEFAULT_LLM_PROVIDER

    # 收集待处理文件
    if input_dir:
        files = [
            os.path.join(input_dir, f) for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ]
    elif input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            files = [line.strip() for line in f if line.strip()]
    else:
        logger.error("请提供 --dir 或 --file 指定输入源")
        sys.exit(1)

    logger.info(f"批量处理 {len(files)} 个文件 (分片大小={shard_size})...")

    def process_file(file_path: str) -> Optional[Dict[str, Any]]:
        """处理单个文件：解析 → 抽取 → 转换"""
        logger.info(f"处理: {file_path}")

        # 解析
        parse_result = parser_factory.parse(file_path)
        if not parse_result.success:
            logger.error(f"解析失败: {file_path} - {parse_result.error}")
            return None

        text = parse_result.get_full_text()
        if not text.strip():
            return None

        # 抽取
        extractor = InfoExtractor(provider=provider)
        extract_result = extractor.extract(text)

        if extract_result["success"]:
            return converter.convert_llm_response(
                extract_result,
                doc_id=os.path.basename(file_path),
                source_file=file_path,
            )
        return None

    # 调度执行
    result = task_scheduler.create_and_run(
        items=files,
        process_func=process_file,
        batch_name=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        shard_size=shard_size,
    )

    logger.info(
        f"批量处理完成: {result['completed']}/{result['total']}"
        f" ({result['progress_pct']}%)"
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_status(args):
    """任务状态查询命令"""
    status_file = args.status_file or config.TASK_STATUS_FILE
    if not os.path.exists(status_file):
        print(json.dumps({"status": "no_status_file", "file": status_file}, ensure_ascii=False))
        return

    status = task_scheduler.load_status(status_file)
    progress = status.get_progress()
    print(json.dumps(progress, ensure_ascii=False, indent=2))


def cmd_plugins(args):
    """插件管理命令"""
    action = args.action

    if action == "list":
        plugins_info = plugin_manager.list_all()
        if not plugins_info:
            print("暂无已注册插件")
        for info in plugins_info:
            status_icon = "✅" if info["status"] == "enabled" else "❌"
            print(f"  {status_icon} [{info['type']}] {info['name']} v{info['version']}")
            if info.get("description"):
                print(f"     {info['description']}")

    elif action == "enable":
        name = args.plugin_name
        if plugin_manager.enable(name):
            print(f"插件 '{name}' 已启用")
        else:
            print(f"启用失败: 插件 '{name}' 不存在")

    elif action == "disable":
        name = args.plugin_name
        if plugin_manager.disable(name):
            print(f"插件 '{name}' 已禁用")
        else:
            print(f"禁用失败: 插件 '{name}' 不存在")

    elif action == "save":
        path = args.config_file or "conf/plugins.json"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        plugin_manager.save_config(path)
        print(f"插件配置已保存: {path}")


def main():
    parser = argparse.ArgumentParser(
        prog="docagent",
        description="AI-DocAgent - 通用AI文档结构化处理框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  docagent parse doc.pdf -o result.json
  docagent extract --text "需要抽取的文本..."
  docagent extract --file doc.txt --prompt generic_entity_extraction
  docagent batch --dir ./docs/ -o output.jsonl
  docagent validate --file extracted.json
  docagent status
  docagent plugins list
        """,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # parse
    p_parse = subparsers.add_parser("parse", help="解析文档")
    p_parse.add_argument("file", help="文档路径")
    p_parse.add_argument("-o", "--output", help="输出文件路径")
    p_parse.add_argument("-f", "--format", choices=["json", "text"], default="json", help="输出格式")

    # extract
    p_extract = subparsers.add_parser("extract", help="LLM信息抽取")
    p_extract.add_argument("--text", help="待抽取文本")
    p_extract.add_argument("--file", help="从文件读取文本")
    p_extract.add_argument("--provider", choices=["qwen", "zhipu", "openai"], help="LLM厂商")
    p_extract.add_argument("--prompt", help="Prompt模板名称")
    p_extract.add_argument("-o", "--output", help="输出文件路径")

    # validate
    p_val = subparsers.add_parser("validate", help="数据质量校验")
    p_val.add_argument("--file", required=True, help="待校验的JSON文件")
    p_val.add_argument("--schema", help="自定义Schema文件")
    p_val.add_argument("-o", "--output", help="异常数据归档路径")

    # batch
    p_batch = subparsers.add_parser("batch", help="批量任务处理")
    p_batch.add_argument("--dir", help="文档目录")
    p_batch.add_argument("--file", help="包含文件路径列表的文本文件")
    p_batch.add_argument("--provider", choices=["qwen", "zhipu", "openai"], help="LLM厂商")
    p_batch.add_argument("--shard-size", type=int, default=10, help="分片大小")
    p_batch.add_argument("-o", "--output", help="输出文件路径")

    # status
    p_status = subparsers.add_parser("status", help="任务状态查询")
    p_status.add_argument("--status-file", help="状态文件路径")

    # plugins
    p_plugins = subparsers.add_parser("plugins", help="插件管理")
    p_plugins.add_argument("action", choices=["list", "enable", "disable", "save"], help="操作")
    p_plugins.add_argument("plugin_name", nargs="?", help="插件名称")
    p_plugins.add_argument("--config-file", help="配置文件路径")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # 加载插件配置
    plugin_config = "conf/plugins.json"
    if os.path.exists(plugin_config):
        plugin_manager.load_config(plugin_config)
        logger.debug(f"已加载插件配置: {plugin_config}")

    command_map = {
        "parse": cmd_parse,
        "extract": cmd_extract,
        "validate": cmd_validate,
        "batch": cmd_batch,
        "status": cmd_status,
        "plugins": cmd_plugins,
    }

    func = command_map.get(args.command)
    if func:
        try:
            func(args)
        except KeyboardInterrupt:
            logger.warning("用户中断操作")
            sys.exit(130)
        except Exception as e:
            logger.error(f"命令执行异常: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
