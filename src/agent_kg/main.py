"""Entry point module for the Knowledge Graph MCP server."""

import sys
import asyncio
import logging
import signal
from typing import NoReturn
from agent_kg.server import KnowledgeGraphServer

# Configure logging to match other modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("knowledge_graph_main")

def handle_shutdown(server: KnowledgeGraphServer) -> None:
    """Handle graceful shutdown of the server.
    
    Args:
        server: The running KnowledgeGraphServer instance
    """
    logger.info("Shutting down Knowledge Graph server...")
    try:
        # Close any open connections
        if hasattr(server, 'db'):
            server.db.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        sys.exit(1)

def main() -> NoReturn:
    """Entry point for the Knowledge Graph MCP server.
    
    This function initializes and runs the MCP server, handling startup,
    shutdown, and error conditions appropriately.
    
    Raises:
        ConnectionError: If database connection fails
        RuntimeError: If server initialization fails
        KeyboardInterrupt: If server is stopped by user
    """
    server = None
    try:
        logger.info("Starting Knowledge Graph MCP server")
        server = KnowledgeGraphServer()
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: handle_shutdown(server))
        
        # Run the server
        asyncio.run(server.run())
        
    except ConnectionError as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Server initialization failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        if server:
            handle_shutdown(server)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
