#!/usr/bin/env python3
"""Report interface-string keys that nothing in the frontend refers to any more.

Read-only: it never edits a file. Run from anywhere:  python3 scripts/find_unused_lang_keys.py
Exit code is always 0; the output is a list to assess, not a failure.

A key counts as used when its exact text appears as a quoted string anywhere in
frontend/*.js or frontend/*.html, except as a definition in the inline English
fallback block of app.js ('key':'text', where the quote is followed by a colon).
That also catches T(ok ? 'a.b' : 'c.d') and keys listed in arrays. Keys built
from pieces at run time (T('stage.' + name), or a template string) cannot be
seen, so every key under such a prefix is treated as used. The list can
therefore miss some unused keys, but it should not invent any.

Delete candidates only after reading each one: a key can still be built from
data (for example a slug from the database) in a way this scan cannot see.
"""
import glob, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
LANGS = ['en', 'ar', 'de', 'es', 'fr', 'ru', 'vi', 'zh']

def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()

src = ''.join(read(p) for p in glob.glob(os.path.join(ROOT, '*.js')) + glob.glob(os.path.join(ROOT, '*.html')))
QUOTED = re.compile(r"""['"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"](\s*:)?""")
used = {m.group(1) for m in QUOTED.finditer(src) if not m.group(2)}
used |= set(re.findall(r"""data-i18n[a-z-]*=['"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"]""", src))
prefixes = set(re.findall(r"""\b[Tt]\(\s*['"]([A-Za-z0-9_.]+\.)['"]\s*\+""", src))
prefixes |= set(re.findall(r"""\b[Tt]\(\s*`([A-Za-z0-9_.]+\.)\$\{""", src))

langs = {}
for code in LANGS:
    p = os.path.join(ROOT, 'lang', code + '.json')
    if os.path.exists(p):
        langs[code] = json.loads(read(p))
en = langs['en']

unused = sorted(k for k in en if k not in used and not any(k.startswith(p) for p in prefixes))
print(f'{len(en)} keys in en.json, {len(unused)} not referenced by any T()/t() call or data-i18n attribute.')
if prefixes:
    print('Dynamic prefixes treated as used:', ', '.join(sorted(prefixes)))
for k in unused:
    print(f'  {k}  =>  {en[k][:70]!r}')

missing = {c: sorted(k for k in en if k not in d) for c, d in langs.items() if c != 'en'}
for c, ks in missing.items():
    if ks:
        print(f'\n{c}.json is missing {len(ks)} key(s) that en.json has: {", ".join(ks[:8])}{" ..." if len(ks) > 8 else ""}')
extra = {c: sorted(k for k in d if k not in en) for c, d in langs.items() if c != 'en'}
for c, ks in extra.items():
    if ks:
        print(f'\n{c}.json has {len(ks)} key(s) that en.json lacks: {", ".join(ks[:8])}{" ..." if len(ks) > 8 else ""}')
