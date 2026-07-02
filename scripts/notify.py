import os
import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def send_digest(journal_path):
    """Send today's journal as an email digest via SendGrid."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
    except ImportError:
        print("sendgrid not installed — run: pip install sendgrid")
        sys.exit(1)

    with open(journal_path, "r", encoding="utf-8") as f:
        content = f.read()

    filename = Path(journal_path).name
    sg = sendgrid.SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
    message = Mail(
        from_email=os.getenv("NOTIFY_FROM_EMAIL", "agent@yourdomain.com"),
        to_emails=os.getenv("NOTIFY_EMAIL"),
        subject=f"Trading Agent Report — {filename}",
        plain_text_content=content,
    )
    response = sg.send(message)
    print(f"Email sent: status {response.status_code}")
    return response.status_code


def write_heartbeat(status="ok", note=""):
    """Write heartbeat.json to the project root with current timestamp and status."""
    project_root = Path(__file__).parent.parent
    heartbeat = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": status,
        "note": note,
    }
    path = project_root / "heartbeat.json"
    path.write_text(json.dumps(heartbeat, indent=2), encoding="utf-8")
    print(f"Heartbeat written: {path} — {status}")
    return str(path)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "heartbeat"

    if action == "digest" and len(sys.argv) > 2:
        send_digest(sys.argv[2])
    elif action == "heartbeat":
        note = sys.argv[2] if len(sys.argv) > 2 else ""
        write_heartbeat(status="ok", note=note)
    elif action == "error" and len(sys.argv) > 2:
        write_heartbeat(status="error", note=sys.argv[2])
    else:
        print("Usage:")
        print("  python scripts/notify.py digest journal/YYYY-MM-DD.md")
        print("  python scripts/notify.py heartbeat")
        print("  python scripts/notify.py error 'reason'")
