#!/usr/bin/env python3
"""Offline translator using argostranslate"""

import sys
import argostranslate.translate as translate

LANGS = {
    'es': 'Spanish',
    'de': 'German',
    'fr': 'French',
    'zh': 'Chinese',
    'nl': 'Dutch',
    'ru': 'Russian',
    'el': 'Greek',
    'en': 'English'
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help']:
        print("Offline Translator")
        print("-" * 30)
        print("Usage: translate [options] <text>")
        print()
        print("Options:")
        print("  -es  English → Spanish (default)")
        print("  -de  English → German")
        print("  -fr  English → French")
        print("  -zh  English → Chinese")
        print("  -nl  English → Dutch")
        print("  -ru  English → Russian")
        print("  -el  English → Greek")
        print("  -en  → English (auto-detect installed source)")
        print()
        print("Reverse (to English):")
        print("  -es-en  Spanish → English")
        print("  -de-en  German → English")
        print("  -fr-en  French → English")
        print("  -zh-en  Chinese → English")
        print("  -nl-en  Dutch → English")
        print("  -ru-en  Russian → English")
        print("  -el-en  Greek → English")
        print()
        print("Examples:")
        print('  translate "Hello world"           # → Spanish')
        print('  translate -de "Hello world"       # → German')
        print('  translate -fr-en "Bonjour monde"  # French → English')
        sys.exit(0)

    # Parse arguments
    from_lang = "en"
    to_lang = "es"  # default

    args = sys.argv[1:]

    if args[0].startswith('-'):
        flag = args[0][1:]  # remove leading dash
        args = args[1:]

        if '-' in flag:
            # e.g., "es-en"
            from_lang, to_lang = flag.split('-', 1)
        elif flag == 'en':
            # Translate TO English - need to detect source
            to_lang = 'en'
            from_lang = None  # will try to detect
        else:
            # e.g., "-de" means en -> de
            to_lang = flag
            from_lang = 'en'

    text = " ".join(args)

    if not text:
        print("No text provided")
        sys.exit(1)

    # If translating to English without specified source, try common ones
    if from_lang is None:
        for try_lang in ['es', 'de', 'fr', 'zh', 'nl', 'ru', 'el']:
            trans = translate.get_translation_from_codes(try_lang, 'en')
            if trans:
                result = trans.translate(text)
                # Simple heuristic: if result differs significantly, probably right language
                if result.lower() != text.lower():
                    print(result)
                    sys.exit(0)
        print("Could not detect source language")
        sys.exit(1)

    trans = translate.get_translation_from_codes(from_lang, to_lang)
    if not trans:
        print(f"Translation not available: {from_lang} → {to_lang}")
        sys.exit(1)

    print(trans.translate(text))

if __name__ == "__main__":
    main()
