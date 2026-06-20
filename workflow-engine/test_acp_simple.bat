@echo off
cd /d "C:\Users\<username>\OneDrive\Documents\Work\devin-orchestrator"
echo {"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{"fs":{"readTextFile":true,"writeTextFile":true},"terminal":false},"clientInfo":{"name":"test-client","title":"Test Client","version":"1.0.0"}},"id":"0"} | "C:\Users\<username>\AppData\Local\devin\cli\bin\devin.exe" acp