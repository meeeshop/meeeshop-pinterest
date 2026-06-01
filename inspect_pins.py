import sys
import os
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from secrets_manager import inject_to_env
    inject_to_env()
except Exception as e:
    print(f"Bypassing secrets_manager inject_to_env: {e}")

from pinterest_client import PinterestClient

def main():
    client = PinterestClient()
    if not client.login():
        print("Login failed")
        return
        
    boards = client.fetch_boards()
    if not boards:
        print("No boards found")
        return
        
    print(f"Found {len(boards)} boards. Fetching pins for the first 5 boards...")
    for board in boards[:5]:
        board_id = board['id']
        board_name = board['name']
        print(f"\n--- Board: {board_name} (ID: {board_id}) ---")
        try:
            board_pins = client.client.board_feed(board_id=board_id, page_size=10)
            if not board_pins:
                print("No pins found or board_feed returned empty.")
                continue
            print(f"Found {len(board_pins)} pins.")
            for i, pin in enumerate(board_pins[:3]):
                print(f"Pin {i+1}:")
                print(f"  id: {pin.get('id')}")
                print(f"  created_at: {pin.get('created_at')}")
                print(f"  created_time: {pin.get('created_time')}")
                print(f"  pin_join -> created_at: {(pin.get('pin_join') or {}).get('created_at')}")
                print(f"  link: {pin.get('link')}")
                print(f"  url: {pin.get('url')}")
                print(f"  repin_count: {pin.get('repin_count')}")
                print(f"  save_count: {pin.get('save_count')}")
                print(f"  aggregated_pin_data -> saves: {pin.get('aggregated_pin_data', {}).get('saves')}")
                print(f"  pin_metrics -> saves: {pin.get('pin_metrics', {}).get('saves')}")
        except Exception as e:
            print(f"Error fetching board {board_name}: {e}")

if __name__ == '__main__':
    main()
