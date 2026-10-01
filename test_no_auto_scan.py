# -*- coding: utf-8 -*-
import sys
import tkinter as tk
from main import WiFiDoctorApp

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

root = tk.Tk()
root.withdraw()

app = WiFiDoctorApp(root)
root.update()

# At launch, scan_items should be empty because we did not click scan!
print("Scan items count at launch:", len(app.scan_items))
assert len(app.scan_items) == 0, "Scan items should be 0 before clicking scan!"

print("Verified: App does NOT scan automatically on startup!")
root.destroy()
