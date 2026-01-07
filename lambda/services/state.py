"""DynamoDB state manager for source fingerprints and validators."""

import os
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StateManager:
    """Manages source state in DynamoDB for deduplication."""
    
    def __init__(self, table_name: str | None = None):
        """
        Initialize state manager.
        
        Args:
            table_name: DynamoDB table name (defaults to STATE_TABLE_NAME env var)
        """
        self.table_name = table_name or os.environ.get("STATE_TABLE_NAME", "ai_updates_state")
        self._dynamodb = boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(self.table_name)
    
    async def get_state(self, source_id: str) -> dict[str, Any] | None:
        """
        Get state for a source.
        
        Args:
            source_id: Unique source identifier
        
        Returns:
            State dict with fingerprint, etag, last_modified, etc. or None if not found
        """
        try:
            response = self._table.get_item(Key={"source_id": source_id})
            item = response.get("Item")
            if item:
                return {
                    "source_id": item.get("source_id"),
                    "fingerprint": item.get("fingerprint"),
                    "etag": item.get("etag"),
                    "last_modified": item.get("last_modified"),
                    "last_seen_utc": item.get("last_seen_utc"),
                    "last_item_key": item.get("last_item_key"),
                }
            return None
        except ClientError as e:
            logger.error(f"Error getting state for {source_id}: {e}")
            return None
    
    async def update_state(
        self,
        source_id: str,
        fingerprint: str,
        etag: str | None = None,
        last_modified: str | None = None,
        last_item_key: str | None = None,
    ) -> bool:
        """
        Update state for a source.
        
        Args:
            source_id: Unique source identifier
            fingerprint: Content fingerprint hash
            etag: HTTP ETag header value
            last_modified: HTTP Last-Modified header value
            last_item_key: Key of the most recent item (e.g., RSS GUID)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            item = {
                "source_id": source_id,
                "fingerprint": fingerprint,
                "last_seen_utc": datetime.now(timezone.utc).isoformat(),
            }
            
            if etag:
                item["etag"] = etag
            if last_modified:
                item["last_modified"] = last_modified
            if last_item_key:
                item["last_item_key"] = last_item_key
            
            self._table.put_item(Item=item)
            return True
            
        except ClientError as e:
            logger.error(f"Error updating state for {source_id}: {e}")
            return False
    
    async def batch_get_states(self, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        """
        Get states for multiple sources in batch.
        
        Args:
            source_ids: List of source identifiers
        
        Returns:
            Dict mapping source_id to state dict
        """
        if not source_ids:
            return {}
        
        try:
            # DynamoDB batch_get_item has a limit of 100 items
            results = {}
            for i in range(0, len(source_ids), 100):
                batch = source_ids[i:i + 100]
                response = self._dynamodb.batch_get_item(
                    RequestItems={
                        self.table_name: {
                            "Keys": [{"source_id": sid} for sid in batch]
                        }
                    }
                )
                
                for item in response.get("Responses", {}).get(self.table_name, []):
                    results[item["source_id"]] = {
                        "source_id": item.get("source_id"),
                        "fingerprint": item.get("fingerprint"),
                        "etag": item.get("etag"),
                        "last_modified": item.get("last_modified"),
                        "last_seen_utc": item.get("last_seen_utc"),
                        "last_item_key": item.get("last_item_key"),
                    }
            
            return results
            
        except ClientError as e:
            logger.error(f"Error batch getting states: {e}")
            return {}
