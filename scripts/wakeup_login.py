"""Wake-up campus network auto-login — called by Windows Task Scheduler."""
import sys, os
os.environ.setdefault("PYTHONPATH", r"D:\Projects\court-bot\src")
sys.path.insert(0, r"D:\Projects\court-bot\src")

from court_bot.core.campus_net import campus_network_login

if __name__ == "__main__":
    import yaml
    with open(r"D:\Projects\court-bot\config\config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    auth = cfg.get("auth", {})
    student_id = auth.get("student_id", "")
    password = auth.get("password", "")

    campus_network_login(username=student_id, password=password)
    print("Done")
