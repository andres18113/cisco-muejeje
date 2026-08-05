# Device lifecycle

Creation, bootstrap, setup dialog, Return, EXEC prompt and configuration readiness are distinct states. Wait for the explicit operational prompt before IOS queries. PC command prompt and router/switch TerminalLine are different abstractions.

Boot timeout must be separate from show-command timeout.
