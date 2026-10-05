"""All SDK-free message exports; no network, parser, Unicode asset or rights proof."""
import json
from telegram_patterns import (EntityKind, TextEntity, TextPayload, FormattedText, MessageBuilder,
    utf16_length, escape_html, escape_markdown_v2, split_formatted)

kind: EntityKind = 'bold'
value = MessageBuilder().text('😀 ').style('<b>literal</b>_*', kind).text('\n'+'text '*1000).build()
parts = split_formatted(value)
assert ''.join(p.text for p in parts) == value.text
assert value.entities[0].offset == 3
payload: TextPayload = parts[0].as_kwargs()
assert payload['parse_mode'] is None and payload['entities'][0]['offset'] == 3
assert all(utf16_length(p.text)<=4096 for p in parts)
raw = FormattedText('link', (TextEntity('text_link',0,4,url='https://example.com'),))
assert raw.as_kwargs()['entities'][0]['url']=='https://example.com'
assert escape_html('<b>&"')=='&lt;b&gt;&amp;&quot;'
assert escape_markdown_v2('_*')=='\\_\\*'
assert escape_markdown_v2('`\\',context='code')=='\\`\\\\'
assert escape_markdown_v2(')\\',context='link')=='\\)\\\\'
emoji=MessageBuilder().custom_emoji('👍','123456789').build()
assert emoji.as_kwargs()['entities']==[]
assert emoji.as_kwargs(custom_emoji_entitlement_verified=True)['entities'][0]['type']=='custom_emoji'
print(json.dumps({'case':'core_message_text','passed':True,'network':False,'chunks':len(parts)}))
