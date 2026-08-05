# IOS terminal evidence

Use Device.getCommandLine and its TerminalLine for routers and switches. Use Pc.getCommandPrompt only for PCs. Each typed query must capture the current echo, isolate the output delta/window and parse only that window.

Never use stale getOutput history as current evidence. Register a parser only after observing the actual Packet Tracer output for the active build.
