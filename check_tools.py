import sys
sys.path.insert(0, "/app")

from app.di import build_tool_registry

registry = build_tool_registry()
tools = [t["name"] for t in registry.to_anthropic_tools()]

print(f"Total tools: {len(tools)}")
print(f"send_file_to_chat registered: {'send_file_to_chat' in tools}")

if 'send_file_to_chat' in tools:
    spec = registry.get('send_file_to_chat')
    print(f"  security_level: {spec.security_level}")
    print(f"  description: {spec.description[:100]}...")
