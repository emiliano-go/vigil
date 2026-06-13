from github import Auth, Github
from contextlib import contextmanager
import clickhouse_connect

from app.core.config import settings

auth = Auth.Token(settings.github_user_token)

@contextmanager
def github_session():
    client = Github(auth=auth, per_page=100)
    try:
        yield client
    finally:
        client.close()

def get_repo_handle(client :  Github, repo_name : str):
    return client.get_repo(repo_name)

def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )
