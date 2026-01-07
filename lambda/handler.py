"""Lambda handler for AI Updates Monitor."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import yaml

from services.fetcher import Fetcher
from services.state import StateManager
from services.notifier import Notifier
from services.fingerprint import compute_fingerprint
from adapters import get_adapter

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)


def load_sources() -> list[dict]:
    """Load sources configuration from bundled YAML file."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "sources.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("sources", [])


async def process_source(
    source: dict,
    fetcher: Fetcher,
    state_manager: StateManager,
) -> dict[str, Any] | None:
    """
    Process a single source: fetch, parse, fingerprint, compare.
    
    Returns change info if source has changed, None otherwise.
    """
    source_id = source["id"]
    adapter_type = source["adapter"]
    url = source["url"]
    
    try:
        # Get previous state
        prev_state = await state_manager.get_state(source_id)
        etag = prev_state.get("etag") if prev_state else None
        last_modified = prev_state.get("last_modified") if prev_state else None
        prev_fingerprint = prev_state.get("fingerprint") if prev_state else None
        
        # Fetch content
        fetch_result = await fetcher.fetch(url, etag=etag, last_modified=last_modified)
        
        # Handle 304 Not Modified
        if fetch_result.get("not_modified"):
            logger.debug(f"[{source_id}] Not modified (304)")
            return None
        
        if fetch_result.get("error"):
            logger.warning(f"[{source_id}] Fetch error: {fetch_result['error']}")
            return None
        
        content = fetch_result.get("content", "")
        new_etag = fetch_result.get("etag")
        new_last_modified = fetch_result.get("last_modified")
        
        # Get adapter and extract items
        adapter = get_adapter(adapter_type)
        items = adapter.extract(content, source)
        
        if not items:
            logger.debug(f"[{source_id}] No items extracted")
            return None
        
        # Compute fingerprint
        new_fingerprint = compute_fingerprint(items)
        
        # Compare fingerprints
        if new_fingerprint == prev_fingerprint:
            logger.debug(f"[{source_id}] No change (same fingerprint)")
            # Update validators even if content unchanged
            await state_manager.update_state(
                source_id=source_id,
                fingerprint=new_fingerprint,
                etag=new_etag,
                last_modified=new_last_modified,
            )
            return None
        
        # Content has changed!
        logger.info(f"[{source_id}] Changed! Old={prev_fingerprint[:8] if prev_fingerprint else 'None'}... New={new_fingerprint[:8]}...")
        
        # Update state
        await state_manager.update_state(
            source_id=source_id,
            fingerprint=new_fingerprint,
            etag=new_etag,
            last_modified=new_last_modified,
            last_item_key=items[0].get("id") or items[0].get("link") if items else None,
        )
        
        return {
            "source_id": source_id,
            "org": source.get("org", "Unknown"),
            "name": source.get("name", source_id),
            "url": url,
            "items": items[:5],  # Top 5 items for notification
            "is_new": prev_fingerprint is None,
        }
        
    except Exception as e:
        logger.error(f"[{source_id}] Error processing: {e}", exc_info=True)
        return None


async def run_monitor() -> dict[str, Any]:
    """Main monitoring logic."""
    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting AI Updates Monitor at {start_time.isoformat()}")
    
    # Load sources
    sources = load_sources()
    logger.info(f"Loaded {len(sources)} sources")
    
    # Initialize services
    fetcher = Fetcher(concurrency=10, timeout=20)
    state_manager = StateManager()
    notifier = Notifier()
    
    try:
        # Process all sources with limited concurrency
        semaphore = asyncio.Semaphore(10)
        
        async def process_with_semaphore(source):
            async with semaphore:
                return await process_source(source, fetcher, state_manager)
        
        tasks = [process_with_semaphore(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect changes
        changes = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.error(f"Task exception: {result}")
            elif result is not None:
                changes.append(result)
        
        # Send notification if there are changes
        if changes:
            await notifier.send_digest(changes)
            logger.info(f"Sent digest with {len(changes)} changes")
        else:
            logger.info("No changes detected")
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            "status": "success",
            "sources_checked": len(sources),
            "changes_detected": len(changes),
            "errors": errors,
            "duration_seconds": duration,
            "timestamp": end_time.isoformat(),
        }
        
        logger.info(f"Completed: {json.dumps(summary)}")
        return summary
        
    finally:
        await fetcher.close()


def lambda_handler(event: dict, context: Any) -> dict:
    """AWS Lambda entry point."""
    try:
        result = asyncio.get_event_loop().run_until_complete(run_monitor())
        return {
            "statusCode": 200,
            "body": json.dumps(result),
        }
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


# For local testing
if __name__ == "__main__":
    asyncio.run(run_monitor())
