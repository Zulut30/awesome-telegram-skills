"""Search the installed SDK or validate a request locally; this CLI NEVER sends it."""
import argparse
import json
from telegram_patterns.aiogram import build_request, method_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('search', nargs='?', default='')
    parser.add_argument('--parameters', help='JSON file for exact method name; only constructs a request')
    args = parser.parse_args()
    if args.parameters:
        from pathlib import Path
        from telegram_patterns.aiogram import InvalidAPIRequest
        try:
            request = build_request(args.search, json.loads(Path(args.parameters).read_text(encoding='utf-8')))
        except (InvalidAPIRequest, ValueError, OSError):
            raise SystemExit('Invalid method/parameters file; payload values are not printed') from None
        print(json.dumps({'method': request.__api_method__, 'sdk_class': type(request).__name__, 'network': False}))
        return
    found = [item for item in method_catalog() if args.search.lower() in item.name.lower()]
    print(json.dumps([{'method': item.name, 'required': item.required, 'fields': item.fields, 'source': item.url} for item in found], indent=2))


if __name__ == '__main__': main()
