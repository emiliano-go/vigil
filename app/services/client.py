from contextlib import contextmanager

from github import Auth, Github

import clickhouse_connect

from app.core.config import settings

@contextmanager
def github_session():
    if settings.github_user_token:
        client = Github(auth=Auth.Token(settings.github_user_token), per_page=100)
    else:
        client = Github(per_page=100)
    try:
        yield client
    finally:
        client.close()

def get_repo_handle(client: Github, repo_name: str):
    return client.get_repo(repo_name)

def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
        connect_timeout=10,
        settings={"async_insert": 1, "wait_for_async_insert": 1},
    )
