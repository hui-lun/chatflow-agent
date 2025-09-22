import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List

# Use a dedicated, thread-safe lock for file access
_state_lock = asyncio.Lock()

# Define the state file path. This will be created in the root of the backend app.
STATE_FILE = Path("processing_state.json")

async def load_state() -> Dict[str, List[str]]:
    """Asynchronously loads the processing state from the JSON file."""
    async with _state_lock:
        if not STATE_FILE.exists():
            return {}
        try:
            # Use asyncio.to_thread to run sync file I/O in a separate thread
            def read_file():
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            return await asyncio.to_thread(read_file)
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Failed to load or parse state file {STATE_FILE}: {e}")
            return {}

async def save_state(state: Dict[str, List[str]]):
    """Asynchronously saves the processing state to the JSON file."""
    async with _state_lock:
        try:
            # Use asyncio.to_thread to run sync file I/O in a separate thread
            def write_file():
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=4, ensure_ascii=False)
            await asyncio.to_thread(write_file)
        except IOError as e:
            logging.error(f"Failed to save state to file {STATE_FILE}: {e}")

def is_file_processed(user_id: str, file_path: str, state: Dict[str, List[str]]) -> bool:
    """Checks if a file's absolute path is already in the user's processed list."""
    # In the context of the backend, file_path is the path inside the container
    abs_path = str(Path(file_path).resolve())
    return abs_path in state.get(user_id, [])

def mark_file_as_processed(user_id: str, file_path: str, state: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Marks a file as processed for a given user."""
    abs_path = str(Path(file_path).resolve())
    if user_id not in state:
        state[user_id] = []
    if abs_path not in state[user_id]:
        state[user_id].append(abs_path)
    return state
