"""
Allows the package to be invoked directly:
  python -m sms_bridge [args...]

This is used internally by the daemon launcher (sms-bridge start).
"""
from sms_bridge.cli import cli

if __name__ == "__main__":
    cli()
