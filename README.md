# Ordnance Survey MCP Server

A MCP server for accessing UK geospatial data through Ordnance Survey APIs.

## What it does

Query the OS Data Hub and return the results to the user.

Ask questions such as find me all cinemas in Leeds City Centre and it will return the results.

Use the prompts templates for more complex, speciifc use cases - relating to road networks, etc.

This MCP server enforces a 2 step workflow plan to ensure the user gets the best results - it must always produce a plan before making searches.

## Quick Start

### 1. Get an OS API Key

Register at [OS Data Hub](https://osdatahub.os.uk/) to get your free API key and set up a project.

### 2. Run with Docker and add to your Claude Desktop config (easiest)

```bash
Clone the repository:
git clone https://github.com/your-username/os-mcp-server.git
cd os-mcp-server
```

Then build the Docker image:

```bash
docker build -t os-mcp-server .
```

Add the following to your Claude Desktop config:

```json
{
  "mcpServers": {
    "os-mcp-server": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e",
        "OS_API_KEY=your_api_key_here",
        "-e",
        "STDIO_KEY=any_value",
        "os-mcp-server"
      ]
    }
  }
}
```

Open Claude Desktop and you show see all available tools, resources, and prompts.

## License

MIT License. This project does not have the endorsement of Ordnance Survey. This is a personal project and not affiliated with Ordnance Survey. This is not a commercial product. It is actively being worked on so expect breaking changes and bugs.
