#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-DocAgent 端到端演示脚本
用法: python demo.py [文档路径]
默认使用 src/resume.pdf 进行演示
"""
import json
import os
import sys

# 确保项目根目录在 path 中
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

print("=" * 70)
print("  AI-DocAgent v0.1.0 — 端到端演示")
print("=" * 70)

# 确定测试文件
if len(sys.argv) > 1:
    test_file = sys.argv[1]
else:
    test_file = os.path.join(_PROJECT_ROOT, "src", "resume.pdf")

if not os.path.exists(test_file):
    print(f"\n[ERROR] 文件不存在: {test_file}")
    print(f"用法: python demo.py <文档路径>")
    sys.exit(1)

print(f"\n📄 测试文档: {test_file}")
print(f"📏 文件大小: {os.path.getsize(test_file):,} bytes")
print()

# ============================
# Step 1: 文档解析
# ============================
print("[Step 1/4] 文档解析...")
from src.parser import parser_factory

parse_result = parser_factory.parse(test_file)
if not parse_result.success:
    print(f"  ❌ 解析失败: {parse_result.error}")
    sys.exit(1)

text = parse_result.get_full_text()
print(f"  ✅ 解析成功")
print(f"     - 文本长度: {len(text):,} 字符")
print(f"     - 段落数量: {len(parse_result.paragraphs)}")
print(f"     - 表格数量: {len(parse_result.tables)}")
print(f"     - 文件类型: {parse_result.file_type}")
if parse_result.metadata:
    for k, v in parse_result.metadata.items():
        print(f"     - {k}: {v}")
print(f"     - 内容预览: {text[:150]}...")
print()

# ============================
# Step 2: LLM信息抽取 (Mock模式)
# ============================
print("[Step 2/4] LLM信息抽取 (Mock离线模式)...")

# 使用Mock抽取器
import re
from src.utils.md5_utils import deduplicator

lines = text.strip().split("\n")
keywords = []
keyword_list = ["Python", "Java", "AI", "机器学习", "深度学习", "NLP", "前端", "后端",
                "本科", "硕士", "博士", "工程师", "经理", "总监",
                "项目", "产品", "设计", "开发", "测试", "运维",
                "React", "Vue", "Django", "Spring", "TensorFlow", "PyTorch",
                "SQL", "MySQL", "MongoDB", "Redis", "Docker", "Kubernetes",
                "AWS", "Azure", "Linux", "Git", "CI/CD", "Agile"]
for kw in keyword_list:
    if kw.lower() in text.lower():
        keywords.append(kw)

emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
phones = re.findall(r'1[3-9]\d{9}', text)
potential_title = lines[0].strip() if lines and len(lines[0]) < 100 else ""

extract_result = {
    "success": True,
    "data": {
        "title": potential_title or "文档标题",
        "summary": text[:300] + ("..." if len(text) > 300 else ""),
        "keywords": keywords[:15] if keywords else ["文档"],
        "entities": (
            [{"name": e, "type": "email"} for e in emails[:5]] +
            [{"name": p, "type": "phone"} for p in phones[:5]]
        ),
        "text_length": len(text),
    },
    "raw_response": "",
    "error": None,
    "content_md5": deduplicator.compute_md5(text),
}

print(f"  ✅ Mock抽取完成")
print(f"     - 提取关键词: {keywords[:8]}")
print(f"     - 提取邮箱: {emails[:3]}")
print(f"     - 提取电话: {phones[:2]}")
print()

# ============================
# Step 3: 结构化转换
# ============================
print("[Step 3/4] 结构化转换...")
from src.converter import converter

standardized = converter.convert_llm_response(
    extract_result,
    doc_id=os.path.basename(test_file),
    source_file=test_file,
)
json_str = converter.to_json(standardized)

output_dir = os.path.join(_PROJECT_ROOT, "output")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "demo_result.json")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(json_str)

print(f"  ✅ 转换完成")
print(f"     - 输出文件: {output_path}")
print(f"     - Schema字段: {list(standardized.keys())}")
print()

# ============================
# Step 4: 质量校验
# ============================
print("[Step 4/4] 质量校验...")
from src.validator import quality_validator

quality_validator.clear()
quality_validator.rule_validator.add_required_rule("doc_id")
quality_validator.rule_validator.add_required_rule("title")

report = quality_validator.validate(standardized, doc_id="resume")
status = "✅ PASS" if report["pass"] else "⚠️ FAIL"

print(f"  {status}")
print(f"     - 校验详情: {report['rule_results']}")

if report.get("dedup_result"):
    print(f"     - 去重检测: {'重复' if report['dedup_result']['is_duplicate'] else '唯一'}")
    print(f"     - MD5指纹: {report['dedup_result'].get('fingerprint', '')[:16]}...")

# ============================
# 打印最终输出
# ============================
print()
print("=" * 70)
print("  🎉 全流程演示完成！")
print("=" * 70)
print(f"\n📋 最终输出文件: {output_path}")
print(f"\n📊 输出内容预览:")
print(json.dumps(standardized, ensure_ascii=False, indent=2)[:2000])
print()

# 显示统计
print(f"📈 处理统计:")
print(f"   输入文件大小: {os.path.getsize(test_file):,} bytes")
print(f"   提取文本量: {len(text):,} 字符")
print(f"   段落数: {len(parse_result.paragraphs)}")
print(f"   输出JSON大小: {len(json_str):,} 字节")
print()
