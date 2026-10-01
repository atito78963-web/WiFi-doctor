# -*- coding: utf-8 -*-
"""
WiFi Doctor - GUI Automated Verification Test
Tests GUI initialization, tree population, event bindings, and destruction.
"""

import sys
import tkinter as tk
from main import WiFiDoctorApp
from utils import Logger

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("Starting GUI automated test...")
root = tk.Tk()
root.withdraw()  # Don't show window on screen during test

app = WiFiDoctorApp(root)
print("GUI App instantiated successfully.")

# Run scan synchronously for test
print("Simulating scan...")
results = app.diag_engine.scan_all()
app._on_scan_completed(results)

# Check tree children
children = app.tree.get_children()
print(f"Treeview has {len(children)} items populated.")
assert len(children) > 0, "Treeview should have items!"

# Simulate selection of each item to verify detail panel does not crash
for cid in children:
    item_obj = next((x for x in app.scan_items if x["id"] == cid), None)
    app._show_item_detail(item_obj)
    detail_content = app.txt_detail.get("1.0", "end")
    assert len(detail_content) > 20, f"Detail content empty for {cid}"
    print(f"Verified detail panel for item: {cid}")

# Test select all and select none
app.select_all_items()
print("Select all passed.")
app.select_no_items()
print("Select none passed.")
app.select_only_issues()
print("Select only issues passed.")

root.update()
root.destroy()
print("GUI test completed successfully with 0 errors!")
