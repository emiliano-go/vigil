
def extract_commit_data(commit) -> dict:
    return {
        "sha": commit.sha,
        "author_name": commit.commit.author.name,
        "author_email": commit.commit.author.email,
        "author_login": commit.author.login if commit.author and commit.author.login else "",
        "committed_at": commit.commit.author.date,
        "message": commit.commit.message,
        "is_merge": len(commit.parents) > 1,
    }
