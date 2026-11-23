#!/usr/bin/env python
import os
import sys


def main():
    # En Vercel (variable VERCEL=1) se usa producción; en tu PC, desarrollo.
    default = "config.settings.prod" if os.environ.get("VERCEL") else "config.settings.dev"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
