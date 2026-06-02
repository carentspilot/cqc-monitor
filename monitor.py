import requests
from bs4 import BeautifulSoup
import json
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

LISTING_URL = "https://www.cqc.org.uk/care-services/local-authority-assessment-reports"
BASE_URL = "https://www.cqc.org.uk"
SEEN_FILE = "seen_assessments.json"
RATINGS = ["Requires improvement", "Good", "Outstanding", "Inadequate"]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return None  # None = first run, initialise without alerting


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def get_all_assessments():
    r = requests.get(LISTING_URL, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    assessments = {}
    pattern = re.compile(r"/care-services/local-authority-assessment-reports/([^/]+)$")
    for link in soup.find_all("a", href=True):
        m = pattern.match(link["href"])
        if m:
            slug = m.group(1)
            name = link.get_text(strip=True).replace(": local authority assessment", "")
            assessments[slug] = {
                "name": name,
                "url": BASE_URL + link["href"],
            }
    return assessments


def get_rating(council_url):
    try:
        r = requests.get(council_url + "/summary", timeout=30)
        text = r.text
        for rating in RATINGS:
            if rating in text:
                return rating
    except Exception:
        pass
    return "Unknown"


def send_alert(council_name, rating, url):
    msg = MIMEMultipart()
    msg["From"] = os.environ["SMTP_USERNAME"]
    msg["To"] = os.environ["ALERT_EMAIL"]
    msg["Subject"] = f"CQC Alert: {council_name} — {rating}"

    body = f"""New CQC Local Authority Assessment

Council: {council_name}
Rating: {rating}
Published: {datetime.today().strftime('%d %B %Y')}

Full report: {url}/summary

This council has been rated "{rating}" by the CQC. This is likely a good moment for Carents to make contact, as the council will be under pressure to improve support for unpaid carers.

Suggested angle: reference the CQC findings on unpaid carer experience and position Carents as a resource to help them meet their obligations.
"""
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)
    print(f"Alert sent for {council_name}")


def main():
    seen = load_seen()
    current = get_all_assessments()
    first_run = seen is None

    if first_run:
        print(f"First run — seeding {len(current)} existing assessments (no alerts sent)")
        seen = {}
        for slug, data in current.items():
            rating = get_rating(data["url"])
            seen[slug] = {**data, "rating": rating, "first_seen": datetime.now().isoformat()}
        save_seen(seen)
        return

    new_slugs = set(current.keys()) - set(seen.keys())
    print(f"Found {len(new_slugs)} new assessment(s)")

    for slug in new_slugs:
        data = current[slug]
        rating = get_rating(data["url"])
        seen[slug] = {**data, "rating": rating, "first_seen": datetime.now().isoformat()}
        print(f"  {data['name']}: {rating}")

        if rating == "Requires improvement":
            send_alert(data["name"], rating, data["url"])

    save_seen(seen)


if __name__ == "__main__":
    main()
