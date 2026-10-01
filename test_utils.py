# -*- coding: utf-8 -*-
import utils

print("Is admin:", utils.is_admin())
code, out, err = utils.run_cmd("echo 编码测试：中文字符与WiFi诊断正常")
print("Cmd test output:", out)
code2, out2, err2 = utils.run_native("netsh", ["interface", "show", "interface"])
print("Native test code:", code2, "len:", len(out2))

utils.BackupManager.save_item_snapshot("test_item", "测试网卡项", "原值Enabled", "新值Disabled", {"type": "dummy"})
backup = utils.BackupManager.load_backup()
print("Backup loaded title:", backup["items"]["test_item"]["title"])
utils.BackupManager.clear_all()
print("All utils unit checks passed successfully!")
