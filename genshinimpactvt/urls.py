from urllib.parse import urlsplit

def normalize_url(value):
    value = value.strip()
    if not value:
        raise ValueError('请输入网址')
    if '://' not in value:
        if ':' in value and not (value.rsplit(':', 1)[-1].split('/')[0].isdigit()):
            raise ValueError('??? HTTP ? HTTPS ??')
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname or any(c.isspace() for c in value):
        raise ValueError('请输入有效的 HTTP 或 HTTPS 网址')
    return value
