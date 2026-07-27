/**
 * pi-sandbox-bridge — Pi extension 转发 8 工具到 Poirot SpecialistMcpServer.
 *
 * 决策 1（设计文档 46 §10.5）：强制走 Poirot SpecialistMcpServer。
 * pi --no-builtin-tools 禁用自带 read/write/edit/bash，
 * 此 extension 注册 8 个 poirot_* 工具，全部通过 stdio MCP 转发到
 * Poirot SpecialistMcpServer（POIROT_SANDBOX_MCP_ENDPOINT env 指定）。
 *
 * 经过 PathTranslator + SecurityGuard（与 codex/claude 统一沙箱访问）。
 * 物理无隔离，pi 写的文件 lead agent 立即可见。
 */

import { Type } from "@sinclair/typebox";

// 8 个工具名（与 Poirot SpecialistMcpServer 暴露的接口一致）
const POIROT_TOOLS = [
  "bash",
  "read_file",
  "write_file",
  "list_dir",
  "str_replace",
  "glob",
  "grep",
  "download_file",
] as const;

/**
 * Extension entry point.
 *
 * pi 加载此 extension 后，agent 看到 poirot_read / poirot_write / poirot_bash 等 8 个工具。
 * 所有工具通过 stdio MCP 协议调 Poirot SpecialistMcpServer。
 */
export default function (pi: any) {
  for (const toolName of POIROT_TOOLS) {
    const poirotToolName = `poirot_${toolName}`;
    pi.registerTool({
      name: poirotToolName,
      label: `Poirot ${toolName}`,
      description: `Poirot sandbox ${toolName} (security-guarded, delegates to SpecialistMcpServer)`,
      parameters: Type.Object({
        // 透传所有参数（pi extension 不解析参数，原样转发给 MCP server）
        args: Type.Record(Type.String(), Type.Unknown(), {
          description: `Arguments for ${toolName} (passed through to Poirot SpecialistMcpServer)`,
        }),
      }),
      execute: async (_toolCallId: string, params: { args: Record<string, unknown> }) => {
        const result = await callPoirotMcp(toolName, params.args);
        return {
          content: [{ type: "text", text: result }],
          details: {},
        };
      },
    });
  }
}

/**
 * 通过 stdio MCP 协议调 Poirot SpecialistMcpServer.
 *
 * POIROT_SANDBOX_MCP_ENDPOINT env 由 PiRuntime._build_env 注入，
 * 格式：python -m poirot.backend.agents.multiagent.mcp.specialist_mcp_server --sandbox-id <id>
 *
 * 此函数启动 SpecialistMcpServer 子进程，通过 stdio MCP JSON-RPC 调用指定 tool。
 *
 * MVP：每次调用启动新子进程（与 codex/claude 的 SpecialistMcpServer 调用模式一致）。
 * 进阶：可改为持久 MCP client 连接。
 */
async function callPoirotMcp(tool: string, args: Record<string, unknown>): Promise<string> {
  const endpoint = process.env.POIROT_SANDBOX_MCP_ENDPOINT;
  if (!endpoint) {
    throw new Error(
      "POIROT_SANDBOX_MCP_ENDPOINT not set. PiRuntime._build_env should inject it."
    );
  }

  // MVP: 用 MCP stdio 协议调 SpecialistMcpServer
  // endpoint 格式: "python -m poirot.backend.agents.multiagent.mcp.specialist_mcp_server --sandbox-id <id>"
  const cmdParts = endpoint.split(" ");

  // 启动 SpecialistMcpServer 子进程
  const { spawn } = await import("child_process");
  const proc = spawn(cmdParts[0], cmdParts.slice(1), {
    stdio: ["pipe", "pipe", "pipe"],
  });

  return new Promise((resolve, reject) => {
    let stdoutBuffer = "";
    let stderrBuffer = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdoutBuffer += data.toString();
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderrBuffer += data.toString();
    });

    proc.on("error", (err: Error) => {
      reject(new Error(`SpecialistMcpServer spawn failed: ${err.message}`));
    });

    proc.on("close", (code: number) => {
      if (code !== 0) {
        reject(
          new Error(
            `SpecialistMcpServer exited with code ${code}: ${stderrBuffer}`
          )
        );
        return;
      }
      // 尝试解析 stdout 作为 tool result
      // MVP: 直接返 stdout（实际 MCP 协议需 JSON-RPC 解析，此处简化）
      resolve(stdoutBuffer || "(empty result)");
    });

    // MVP: 发送 MCP initialize + callTool 请求
    // 实际 MCP 协议需 JSON-RPC over stdio，此处简化为直接发 tool 调用
    const request = {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: tool,
        arguments: args,
      },
    };
    proc.stdin.write(JSON.stringify(request) + "\n");
    proc.stdin.end();
  });
}
