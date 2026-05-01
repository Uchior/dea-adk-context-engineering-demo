"""Create an Agent Engine instance with structured memory profiles.

Run once to set up Memory Bank:
    python setup_memory_bank.py

Then add the printed AGENT_ENGINE_ID to demo_agent/.env.
"""

import os

import vertexai
from dotenv import load_dotenv

from demo_agent.tools.memory_tools import PROFILE_SCHEMAS

load_dotenv("demo_agent/.env")

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("DATAFORM_LOCATION", "us-central1")


def main():
    client = vertexai.Client(project=PROJECT_ID, location=LOCATION)

    schema_configs = [
        {
            "id": s["id"],
            "memory_schema": s["memory_schema"],
        }
        for s in PROFILE_SCHEMAS
    ]

    agent_engine = client.agent_engines.create(
        config={
            "display_name": "bq-pipeline-demo-memory",
            "context_spec": {
                "memory_bank_config": {
                    "structured_memory_configs": [
                        {"schema_configs": schema_configs}
                    ],
                }
            },
        }
    )

    engine_id = agent_engine.api_resource.name.split("/")[-1]
    print(f"\nAgent Engine created successfully!")
    print(f"AGENT_ENGINE_ID={engine_id}")
    print(f"\nAdd to demo_agent/.env:")
    print(f"  AGENT_ENGINE_ID={engine_id}")
    print(f"\nStart with:")
    print(f"  adk web --memory_service_uri=agentengine://{engine_id} .")


if __name__ == "__main__":
    main()
