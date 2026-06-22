@echo off
REM Use environment variable for workspace directory, fallback to current directory
if defined DEVIN_ORCHESTRATOR_ROOT (
    cd /d "%DEVIN_ORCHESTRATOR_ROOT%"
) else (
    cd /d "%~dp0.."
)

REM Use environment variable for devin CLI path, fallback to default
if defined DEVIN_CLI_PATH (
    set DEVIN_EXE=%DEVIN_CLI_PATH%
) else (
    set DEVIN_EXE=devin.exe
)

echo {"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{"fs":{"readTextFile":true,"writeTextFile":true},"terminal":false},"clientInfo":{"name":"test-client","title":"Test Client","version":"1.0.0"}},"id":"0"} | "%DEVIN_EXE%" acp