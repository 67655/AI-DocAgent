#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-DocAgent 主程序入口
通用AI文档结构化处理框架 - CLI命令行工具

用法示例:
  python -m src.main parse resume.pdf -o result.json
  python -m src.main extract --file resume.pdf --mock
  python -m src.main pipeline resume.pdf --mock
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# ============================
# 路径初始化：确保 src/ 的父目录在 sys.path 中
# ============================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _get_logger(name: str = "main"):
    """延迟导入，避免循环依赖"""
    from src.utils.logger import get_logger
    return get_logger(name)


def cmd_parse(args):
    """解析文档命令"""
    from src.parser import parser_factory

    logger = _get_logger("parse")
    file_path = args.file
    output = args.output
    fmt = args.format

    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        sys.exit(1)

    logger.info(f"开始解析文档: {file_path}")
    result = parser_factory.parse(file_path)

    if not result.success:
        logger.error(f"解析失败: {result.error}")
        sys.exit(1)

    # 构建输出
    text_preview = result.text[:2000] if result.text else ""
    output_data = {
        "success": True,
        "file_path": result.file_path,
        "file_type": result.file_type,
        "file_size": result.file_size,
        "text_length": len(result.text) if result.text else 0,
        "paragraphs_count": len(result.paragraphs),
        "tables_count": len(result.tables),
        "images_count": len(result.images),
        "metadata": result.metadata,
        "paragraphs_preview": result.paragraphs[:5] if result.paragraphs else [],
        "text_preview": text_preview,
    }

    if fmt == "text":
        output_str = result.get_full_text()
    else:
        output_str = json.dumps(output_data, ensure_ascii=False, indent=2)

    if output:
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_str)
        logger.info(f"解析结果已保存: {output}")
    else:
        # 截断控制台输出
        print(output_str[:10000] if len(output_str) > 10000 else output_str)

    logger.info(f"解析完成: {output_data['paragraphs_count']}段落, {output_data['text_length']}字符")


def cmd_extract(args):
    """信息抽取命令"""
    from src.parser import parser_factory
    from src.extractor import InfoExtractor

    logger = _get_logger("extract")
    text = args.text
    text_file = args.file
    provider = args.provider or "qwen"
    output = args.output
    prompt_name = args.prompt
    mock_mode = getattr(args, "mock", False)

    # 从文件读取文本
    if text_file and not text:
        if not os.path.exists(text_file):
            logger.error(f"文件不存在: {text_file}")
            sys.exit(1)
        parse_result = parser_factory.parse(text_file)
        if parse_result.success:
            text = parse_result.get_full_text()
            logger.info(f"从文件提取文本: {len(text)}字符")
        else:
            logger.error(f"文件解析失败: {parse_result.error}")
            sys.exit(1)

    if not text:
        logger.error("请提供待抽取的文本 (--text 或 --file)")
        sys.exit(1)

    # Mock模式：不调用真实API，返回模拟结果
    if mock_mode:
        logger.info("Mock模式: 不调用LLM API，生成模拟抽取结果")
        result = _mock_extract(text, prompt_name)
    else:
        logger.info(f"调用LLM API: provider={provider}, prompt={prompt_name or 'default'}")
        extractor = InfoExtractor(provider=provider)
        result = extractor.extract(text, prompt_name=prompt_name)

    if result.get("success"):
        from src.converter import converter
        standardized = converter.convert_llm_response(
            result,
            doc_id=os.path.basename(text_file) if text_file else "cli_input",
            source_file=text_file or "cli_input",
        )
        output_str = converter.to_json(standardized)
        if output:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_str)
            logger.info(f"抽取结果已保存: {output}")
        else:
            print(output_str[:10000] if len(output_str) > 10000 else output_str)
        logger.info("抽取完成")
    else:
        logger.error(f"抽取失败: {result.get('error', 'unknown')}")
        if not mock_mode:
            sys.exit(1)
        # Mock模式失败也输出
        print(json.dumps({"error": result.get("error")}, ensure_ascii=False, indent=2))


def _mock_extract(text: str, prompt_name: str = None) -> Dict[str, Any]:
    """Mock抽取器：生成模拟的抽取结果，用于离线测试管道"""
    import re
    from src.utils.md5_utils import deduplicator

    # 尝试从文本中提取一些基本信息
    lines = text.strip().split("\n")[:50]
    text_sample = " ".join(lines[:10])

    # 简单关键词提取
    keywords = []
    for word in ["Python", "Java", "AI", "机器学习", "深度学习", "NLP", "前端", "后端",
                 "本科", "硕士", "博士", "工程师", "经理", "总监",
                 "项目", "产品", "设计", "开发", "测试", "运维",
                 "React", "Vue", "Django", "Spring", "TensorFlow"]:
        if word in text:
            keywords.append(word)

    # 尝试提取邮箱和电话
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    phones = re.findall(r'1[3-9]\d{9}', text)

    # 取前几行作为潜在标题
    potential_title = lines[0].strip() if lines and len(lines[0]) < 100 else ""

    mock_data = {
        "title": potential_title or "文档标题（Mock）",
        "summary": text_sample[:200] + ("..." if len(text) > 200 else ""),
        "keywords": keywords[:10] if keywords else ["文档", "AI-DocAgent"],
        "entities": [
            {"name": e, "type": "email"} for e in emails[:3]
        ] + [
            {"name": p, "type": "phone"} for p in phones[:3]
        ],
        "word_count": len(text),
        "extraction_note": "Mock模式 - 非真实LLM抽取结果",
    }

    return {
        "success": True,
        "data": mock_data,
        "raw_response": json.dumps(mock_data, ensure_ascii=False),
        "error": None,
        "content_md5": deduplicator.compute_md5(text),
    }


def cmd_validate(args):
    """数据校验命令"""
    logger = _get_logger("validate")
    input_file = args.file
    output = args.output

    if not os.path.exists(input_file):
        logger.error(f"文件不存在: {input_file}")
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data_list = data if isinstance(data, list) else [data]
    logger.info(f"开始校验 {len(data_list)} 条数据...")

    from src.validator import quality_validator, RuleValidator

    validator = quality_validator
    validator.clear()

    # 注册基本规则
    validator.rule_validator.add_required_rule("doc_id")
    validator.rule_validator.add_required_rule("title")

    summary = validator.validate_batch(data_list)
    logger.info(f"校验完成: {summary['passed']}/{summary['total']}通过 ({summary['pass_rate']}%)")

    if validator.get_error_archive():
        archive_path = output or "output/error_archive.json"
        validator.export_error_archive(archive_path)
        logger.info(f"异常数据已归档: {archive_path}")

    summary_out = {k: v for k, v in summary.items() if k != "detailed_results"}
    summary_out["recheck_count"] = len(validator.get_recheck_queue())
    print(json.dumps(summary_out, ensure_ascii=False, indent=2))


def cmd_batch(args):
    """批量任务调度命令"""
    logger = _get_logger("batch")
    input_dir = args.dir
    input_file = args.file
    shard_size = args.shard_size or 10
    mock_mode = getattr(args, "mock", False)

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

    logger.info(f"批量处理 {len(files)} 个文件 (分片大小={shard_size})")

    from src.parser import parser_factory
    from src.extractor import InfoExtractor
    from src.converter import converter
    from src.scheduler import scheduler as task_scheduler

    if mock_mode:
        logger.info("Mock模式: 使用模拟LLM抽取")

    def process_file(file_path: str) -> Optional[Dict[str, Any]]:
        logger.info(f"处理: {file_path}")
        parse_result = parser_factory.parse(file_path)
        if not parse_result.success:
            return None
        text = parse_result.get_full_text()
        if not text.strip():
            return None

        if mock_mode:
            extract_result = _mock_extract(text)
        else:
            extractor = InfoExtractor()
            extract_result = extractor.extract(text)

        if extract_result.get("success"):
            return converter.convert_llm_response(
                extract_result,
                doc_id=os.path.basename(file_path),
                source_file=file_path,
            )
        return None

    result = task_scheduler.create_and_run(
        items=files,
        process_func=process_file,
        batch_name=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        shard_size=shard_size,
    )
    logger.info(f"批量完成: {result['completed']}/{result['total']} ({result['progress_pct']}%)")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_status(args):
    """任务状态查询命令"""
    from src.scheduler import scheduler as task_scheduler
    from src.utils.config import config

    status_file = args.status_file or config.TASK_STATUS_FILE
    if not os.path.exists(status_file):
        print(json.dumps({"status": "no_status_file", "file": status_file}, ensure_ascii=False))
        return

    status = task_scheduler.load_status(status_file)
    print(json.dumps(status.get_progress(), ensure_ascii=False, indent=2))


def cmd_plugins(args):
    """插件管理命令"""
    from src.plugins import plugin_manager

    action = args.action

    if action == "list":
        plugins_info = plugin_manager.list_all()
        if not plugins_info:
            print("暂无已注册插件")
        for info in plugins_info:
            status_icon = "[ENABLED]" if info["status"] == "enabled" else "[DISABLED]"
            print(f"  {status_icon} [{info['type']}] {info['name']} v{info['version']}")
            if info.get("description"):
                print(f"         {info['description']}")

    elif action in ("enable", "disable"):
        name = args.plugin_name
        if not name:
            print(f"请提供插件名称: docagent plugins {action} <name>")
            sys.exit(1)
        if action == "enable":
            ok = plugin_manager.enable(name)
        else:
            ok = plugin_manager.disable(name)
        print(f"插件 '{name}' {'已' + action if ok else action + '失败'}")

    elif action == "save":
        path = args.config_file or "conf/plugins.json"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        plugin_manager.save_config(path)
        print(f"插件配置已保存: {path}")


def cmd_pipeline(args):
    """
    全流程一键处理：解析 → 抽取 → 转换 → 校验
    最常用的端到端命令
    """
    logger = _get_logger("pipeline")
    file_path = args.file
    output = args.output
    mock_mode = getattr(args, "mock", False)
    provider = args.provider if hasattr(args, 'provider') else "qwen"

    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        sys.exit(1)

    # 确保输出目录
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    if not output:
        output = f"output/{base_name}_result.json"
    errors_output = f"output/{base_name}_errors.json"
    os.makedirs("output", exist_ok=True)

    logger.info(f"=== AI-DocAgent 全流程处理 ===")
    logger.info(f"输入: {file_path}")
    logger.info(f"输出: {output}")
    logger.info(f"模式: {'Mock(离线)' if mock_mode else f'LLM({provider})'}")

    # Step 1: 解析
    logger.info("[Step 1/4] 文档解析...")
    from src.parser import parser_factory
    parse_result = parser_factory.parse(file_path)
    if not parse_result.success:
        logger.error(f"解析失败: {parse_result.error}")
        sys.exit(1)

    text = parse_result.get_full_text()
    logger.info(f"  解析成功: {len(text)}字符, {len(parse_result.paragraphs)}段落")

    # Step 2: 抽取
    logger.info("[Step 2/4] LLM信息抽取...")
    if mock_mode:
        extract_result = _mock_extract(text, args.prompt if hasattr(args, 'prompt') else None)
    else:
        from src.extractor import InfoExtractor
        extractor = InfoExtractor(provider=provider)
        extract_result = extractor.extract(text, prompt_name=args.prompt if hasattr(args, 'prompt') else None)

    if not extract_result.get("success"):
        logger.error(f"抽取失败: {extract_result.get('error')}")
        if not mock_mode:
            sys.exit(1)

    logger.info(f"  抽取成功" + (" (Mock)" if mock_mode else ""))

    # Step 3: 转换
    logger.info("[Step 3/4] 结构化转换...")
    from src.converter import converter
    standardized = converter.convert_llm_response(
        extract_result,
        doc_id=base_name,
        source_file=file_path,
    )
    json_output = converter.to_json(standardized)
    with open(output, "w", encoding="utf-8") as f:
        f.write(json_output)
    logger.info(f"  结果已保存: {output}")

    # Step 4: 校验
    logger.info("[Step 4/4] 质量校验...")
    from src.validator import quality_validator
    quality_validator.clear()
    quality_validator.rule_validator.add_required_rule("doc_id")
    quality_validator.rule_validator.add_required_rule("title")

    report = quality_validator.validate(standardized, doc_id=base_name)
    status_str = "PASS" if report["pass"] else "FAIL"
    logger.info(f"  校验结果: {status_str}")

    if not report["pass"]:
        quality_validator.export_error_archive(errors_output)
        logger.info(f"  异常归档: {errors_output}")

    # 打印摘要
    print("\n" + "=" * 60)
    print(f"  处理完成: {file_path}")
    print(f"  输出文件: {output}")
    print(f"  校验状态: {status_str}")
    print(f"  文本长度: {len(text)}字符")
    print(f"  段落数量: {len(parse_result.paragraphs)}")
    if report.get("needs_recheck"):
        print(f"  需要复检: 是 ({report.get('recheck_reason', '')})")
    print("=" * 60 + "\n")

    # 打印输出摘要
    print("--- 输出内容预览 ---")
    print(json.dumps(standardized, ensure_ascii=False, indent=2)[:3000])


def main():
    parser = argparse.ArgumentParser(
        prog="docagent",
        description="AI-DocAgent - 通用AI文档结构化处理框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Pipeline全流程一行命令（推荐，离线测试用--mock）
  python -m src.main pipeline resume.pdf --mock
  python -m src.main pipeline resume.pdf --provider qwen

  # 分步执行
  python -m src.main parse doc.pdf -o result.json
  python -m src.main extract --file doc.txt --mock
  python -m src.main validate --file extracted.json
  python -m src.main status
  python -m src.main plugins list
        """,
    )
    parser.add_argument("-v", "--version", action="version",
                        version=f"AI-DocAgent v0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # pipeline 全流程（最常用）
    p_pipe = subparsers.add_parser("pipeline", help="全流程一键处理（解析→抽取→转换→校验）")
    p_pipe.add_argument("file", help="文档路径")
    p_pipe.add_argument("-o", "--output", help="输出文件路径")
    p_pipe.add_argument("--provider", default="qwen", choices=["qwen", "zhipu", "openai"])
    p_pipe.add_argument("--prompt", help="Prompt模板名称")
    p_pipe.add_argument("--mock", action="store_true", help="离线Mock模式（不调用API）")

    # parse
    p_parse = subparsers.add_parser("parse", help="解析文档")
    p_parse.add_argument("file", help="文档路径")
    p_parse.add_argument("-o", "--output", help="输出文件路径")
    p_parse.add_argument("-f", "--format", choices=["json", "text"], default="json")

    # extract
    p_extract = subparsers.add_parser("extract", help="LLM信息抽取")
    p_extract.add_argument("--text", help="待抽取文本")
    p_extract.add_argument("--file", help="从文件读取文本")
    p_extract.add_argument("--provider", choices=["qwen", "zhipu", "openai"], default="qwen")
    p_extract.add_argument("--prompt", help="Prompt模板名称")
    p_extract.add_argument("-o", "--output", help="输出文件路径")
    p_extract.add_argument("--mock", action="store_true", help="离线Mock模式")

    # validate
    p_val = subparsers.add_parser("validate", help="数据质量校验")
    p_val.add_argument("--file", required=True, help="待校验的JSON文件")
    p_val.add_argument("-o", "--output", help="异常数据归档路径")

    # batch
    p_batch = subparsers.add_parser("batch", help="批量任务处理")
    p_batch.add_argument("--dir", help="文档目录")
    p_batch.add_argument("--file", help="包含文件路径列表的文本文件")
    p_batch.add_argument("--shard-size", type=int, default=10, help="分片大小")
    p_batch.add_argument("-o", "--output", help="输出文件路径")
    p_batch.add_argument("--mock", action="store_true", help="离线Mock模式")

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

    command_map = {
        "pipeline": cmd_pipeline,
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
            print("\n用户中断", file=sys.stderr)
            sys.exit(130)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n[ERROR] {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
