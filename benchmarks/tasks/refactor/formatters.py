def article_path(text):
    return '/articles/' + text.strip().lower().replace(' ', '-')

def tag_path(text):
    return '/tags/' + text.strip().lower().replace(' ', '-')
