from utils.terminal_manager import TerminalManager
import sys
import asyncio
import json

async def main():
    login = int(sys.argv[1]) if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None
    server = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not login or not password or not server:
        print({
            "status": False,
            "message": "Invalid request"
        })

    terminal_manager = TerminalManager()
    data = await terminal_manager.get_account_data(login, password, server)
    print(json.dumps(data))
    
    return



if __name__ == "__main__":
    asyncio.run(main())