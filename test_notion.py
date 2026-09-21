from pathlib import Path
from dotenv import dotenv_values
from notion_client import Client

env = dotenv_values(Path(__file__).parent / ".env")
notion = Client(auth=env["NOTION_TOKEN"])
notion.pages.create(
    parent={"database_id": env["NOTION_DATABASE_ID"]},
    properties={"Name": {"title": [{"text": {"content": "Test entry"}}]}},
)
print("Row created")