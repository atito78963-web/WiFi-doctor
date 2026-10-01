# -*- coding: utf-8 -*-
import sys
from diagnostics import DiagnosticEngine
from fixer import FixerEngine
from utils import BackupManager

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("Testing Fixer and Rollback...")
engine = DiagnosticEngine()
adapter = engine.find_wifi_adapter()
fixer = FixerEngine(adapter)

# Test with DNS & ARP item (safe)
test_item = {
    "id": "flush_dns_arp",
    "title": "陈旧 DNS 缓存与 ARP 邻居表清理",
    "selected": True,
    "raw_val": {}
}

res = fixer.apply_fixes([test_item])
print("Fix result:", res["success"] == 1)

# Verify backup manager works
BackupManager.save_item_snapshot("dummy_test", "测试项", "旧值", "新值", {"type": "dummy"})
backup = BackupManager.load_backup()
print("Backup has dummy:", "dummy_test" in backup.get("items", {}))

# Rollback test
rb = FixerEngine.rollback_all()
print("Rollback executed:", rb["total"] >= 1)
print("Backup cleared after rollback:", len(BackupManager.load_backup().get("items", {})) == 0)

print("Fixer & Rollback test completed successfully!")
