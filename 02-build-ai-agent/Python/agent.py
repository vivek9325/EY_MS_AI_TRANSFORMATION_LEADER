import os
from pathlib import Path

from dotenv import load_dotenv

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    CodeInterpreterTool,
    FilePurpose,
    ListSortOrder,
    MessageRole,
)
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential


def main() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    load_dotenv()

    project_endpoint = os.getenv("PROJECT_ENDPOINT")
    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")
    api_key = os.getenv("AZURE_API_KEY")

    script_dir = Path(__file__).parent
    file_path = script_dir / "data.txt"

    with file_path.open("r", encoding="utf-8") as file:
        data = file.read() + "\n"
        print(data)

    if api_key:
        credential = AzureKeyCredential(api_key)
    else:
        credential = DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True,
        )

    agent_client = AgentsClient(endpoint=project_endpoint, credential=credential)

    with agent_client:
        file = agent_client.files.upload_and_poll(
            file_path=file_path,
            purpose=FilePurpose.AGENTS,
        )
        print(f"Uploaded {file.filename}")

        code_interpreter = CodeInterpreterTool(file_ids=[file.id])

        agent = agent_client.create_agent(
            model=model_deployment,
            name="data-agent",
            instructions=(
                "You are an AI agent that analyzes the data in the file that has been uploaded. "
                "If the user requests a chart, create it and save it as a .png file."
            ),
            tools=code_interpreter.definitions,
            tool_resources=code_interpreter.resources,
        )
        print(f"Using agent: {agent.name}")

        thread = agent_client.threads.create()

        while True:
            user_prompt = input("Enter a prompt (or type 'quit' to exit): ")
            if user_prompt.lower() == "quit":
                break
            if len(user_prompt) == 0:
                print("Please enter a prompt.")
                continue

            agent_client.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_prompt,
            )
            run = agent_client.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id,
            )

            if run.status == "failed":
                print(f"Run failed: {run.last_error}")

            last_msg = agent_client.messages.get_last_message_text_by_role(
                thread_id=thread.id,
                role=MessageRole.AGENT,
            )
            if last_msg:
                print(f"Last Message: {last_msg.text.value}")

        print("\nConversation Log:\n")
        messages = agent_client.messages.list(
            thread_id=thread.id,
            order=ListSortOrder.ASCENDING,
        )
        for message in messages:
            if message.text_messages:
                last_msg = message.text_messages[-1]
                print(f"{message.role}: {last_msg.text.value}\n")

        for msg in messages:
            for img in msg.image_contents:
                file_id = img.image_file.file_id
                file_name = f"{file_id}_image_file.png"
                agent_client.files.save(file_id=file_id, file_name=file_name)
                print(f"Saved image file to: {Path.cwd() / file_name}")

        agent_client.delete_agent(agent.id)


if __name__ == "__main__":
    main()