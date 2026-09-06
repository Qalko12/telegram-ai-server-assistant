from server.diagnostics import full_server_diagnostic


async def test_full_server_diagnostic_contains_key_sections() -> None:
    report = await full_server_diagnostic()

    assert "🖥 SERVER" in report
    assert "CPU:" in report
    assert "RAM:" in report
    assert "Disk:" in report
    assert "Uptime:" in report
    assert "TOP PROCESSES" in report
