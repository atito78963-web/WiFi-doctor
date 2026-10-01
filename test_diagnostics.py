# -*- coding: utf-8 -*-
import sys
from diagnostics import DiagnosticEngine

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

engine = DiagnosticEngine()
print("Starting diagnostic scan test...")
results = engine.scan_all()

print(f"\nScan completed with {len(results)} items:")
for i, item in enumerate(results, 1):
    status_tag = "[存在隐患/可优化]" if item["has_issue"] else "[状态正常]"
    print(f"{i}. {item['title']} - {status_tag}")
    print(f"   当前状态: {item['current_val']}")
    print(f"   原因分析: {item['issue_desc'][:60]}...")
    print(f"   优化方案: {item['fix_action']}")
    print("-" * 60)

print("Diagnostics test passed without errors!")
