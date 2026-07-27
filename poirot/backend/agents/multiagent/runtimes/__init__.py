"""Multi-Agent Runtime 层 — specialist 裸执行实现。

CodexRuntime（ACP）/ ClaudeCodeRuntime（CLI）/ PiRuntime（RPC mode）/ SubagentRuntime（进程内）。
sync only MVP（INV#5），每次 invoke 启动 + 完成关闭（不做 pool）。
"""
