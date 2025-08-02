import asyncio
import subprocess
import sys
import os
import time
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent


def extract_text_from_result(result) -> str:
    """Safely extract text from MCP tool result"""
    if not result.content:
        return "No content"

    for item in result.content:
        if isinstance(item, TextContent):
            return item.text

    content_types = [type(item).__name__ for item in result.content]
    return f"Non-text content: {', '.join(content_types)}"


async def test_stdio_rate_limiting():
    """Test STDIO rate limiting - should block after 1 request per minute"""
    env = os.environ.copy()
    env["STDIO_KEY"] = "test-stdio-key"
    env["OS_API_KEY"] = os.environ.get("OS_API_KEY", "dummy-key-for-testing")
    env["PYTHONPATH"] = "src"

    print("Starting STDIO server subprocess...")

    server_process = subprocess.Popen(
        [sys.executable, "src/server.py", "--transport", "stdio", "--debug"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=0,
    )

    try:
        print("Connecting to STDIO server...")

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["src/server.py", "--transport", "stdio", "--debug"],
            env=env,
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                print("Initializing session...")
                await session.initialize()

                print("Listing available tools...")
                tools = await session.list_tools()
                print(f"   Found {len(tools.tools)} tools")

                print("\nRAPID FIRE TEST (should hit rate limit)")
                print("-" * 50)

                results = []
                for i in range(3):
                    try:
                        start_time = time.time()
                        print(f"Request #{i + 1}: ", end="", flush=True)

                        result = await session.call_tool(
                            "hello_world", {"name": f"TestUser{i + 1}"}
                        )
                        elapsed = time.time() - start_time

                        result_text = extract_text_from_result(result)

                        if "rate limit" in result_text.lower() or "429" in result_text:
                            print(f"BLOCKED ({elapsed:.1f}s) - {result_text}")
                            results.append(("BLOCKED", elapsed, result_text))
                        else:
                            print(f"SUCCESS ({elapsed:.1f}s) - {result_text}")
                            results.append(("SUCCESS", elapsed, result_text))

                    except Exception as e:
                        elapsed = time.time() - start_time
                        print(f"ERROR ({elapsed:.1f}s) - {e}")
                        results.append(("ERROR", elapsed, str(e)))

                    if i < 2:
                        await asyncio.sleep(0.1)

                print("\nRESULTS ANALYSIS")
                print("-" * 50)

                success_count = sum(1 for r in results if r[0] == "SUCCESS")
                blocked_count = sum(1 for r in results if r[0] == "BLOCKED")
                error_count = sum(1 for r in results if r[0] == "ERROR")

                print(f"Successful requests: {success_count}")
                print(f"Rate limited requests: {blocked_count}")
                print(f"Error requests: {error_count}")

                print("\nVISUAL TIMELINE:")
                timeline = ""
                for i, (status, elapsed, _) in enumerate(results):
                    if status == "SUCCESS":
                        timeline += "OK"
                    elif status == "BLOCKED":
                        timeline += "XX"
                    else:
                        timeline += "ER"

                    if i < len(results) - 1:
                        timeline += "--"

                print(f"   {timeline}")
                print("   Request: 1   2   3")

                print("\nTEST VERDICT")
                print("-" * 50)

                if success_count == 1 and blocked_count >= 1:
                    print("PASS: Rate limiting works correctly!")
                    print("   First request succeeded")
                    print("   Subsequent requests blocked")
                elif success_count > 1:
                    print("FAIL: Rate limiting too permissive!")
                    print(f"   {success_count} requests succeeded (expected 1)")
                else:
                    print("FAIL: No requests succeeded!")
                    print("   Check authentication or server issues")

                print("\nWAITING FOR RATE LIMIT RESET...")
                print("   (Testing if limit resets after window)")
                print("   Waiting 10 seconds...")

                for countdown in range(10, 0, -1):
                    print(f"   {countdown}s remaining...", end="\r", flush=True)
                    await asyncio.sleep(1)

                print("\nTesting after rate limit window...")
                try:
                    result = await session.call_tool(
                        "hello_world", {"name": "AfterWait"}
                    )
                    result_text = extract_text_from_result(result)

                    if "rate limit" not in result_text.lower():
                        print("SUCCESS: Rate limit properly reset!")
                    else:
                        print("Rate limit still active (might need longer wait)")

                except Exception as e:
                    print(f"Error after wait: {e}")

    except Exception as e:
        print(f"Test failed with error: {e}")

    finally:
        print("\nCleaning up server process...")
        server_process.terminate()
        try:
            await asyncio.wait_for(
                asyncio.create_task(asyncio.to_thread(server_process.wait)), timeout=5.0
            )
            print("Server terminated gracefully")
        except asyncio.TimeoutError:
            print("Force killing server...")
            server_process.kill()
            server_process.wait()


if __name__ == "__main__":
    print("STDIO Rate Limit Test Suite")
    print("Testing if STDIO middleware properly blocks > 1 request/minute")
    print()

    if not os.environ.get("OS_API_KEY"):
        print("Warning: OS_API_KEY not set, using dummy key for testing")
        print("   (This is OK for rate limit testing)")
        print()

    asyncio.run(test_stdio_rate_limiting())
