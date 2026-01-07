"""SNS notification service for sending update digests."""

import os
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class Notifier:
    """Sends notification digests via SNS."""
    
    def __init__(self, topic_arn: str | None = None):
        """
        Initialize notifier.
        
        Args:
            topic_arn: SNS topic ARN (defaults to SNS_TOPIC_ARN env var)
        """
        self.topic_arn = topic_arn or os.environ.get("SNS_TOPIC_ARN")
        self._sns = boto3.client("sns")
    
    async def send_digest(self, changes: list[dict[str, Any]]) -> bool:
        """
        Send a digest notification with all detected changes.
        
        Args:
            changes: List of change dicts, each containing:
                - source_id: Source identifier
                - org: Organization name
                - name: Source name
                - url: Source URL
                - items: List of new items
                - is_new: Whether this is first time seeing source
        
        Returns:
            True if notification sent successfully, False otherwise
        """
        if not changes:
            logger.info("No changes to notify")
            return True
        
        if not self.topic_arn:
            logger.error("SNS_TOPIC_ARN not configured")
            return False
        
        # Build digest message
        subject = self._build_subject(changes)
        message = self._build_message(changes)
        
        try:
            self._sns.publish(
                TopicArn=self.topic_arn,
                Subject=subject,
                Message=message,
            )
            logger.info(f"Sent digest notification with {len(changes)} changes")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    def _build_subject(self, changes: list[dict[str, Any]]) -> str:
        """Build email subject line."""
        count = len(changes)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        if count == 1:
            org = changes[0].get("org", "Unknown")
            return f"AI Updates: {org} has new content ({timestamp})"
        else:
            return f"AI Updates: {count} sources have new content ({timestamp})"
    
    def _build_message(self, changes: list[dict[str, Any]]) -> str:
        """Build email body with change details."""
        lines = [
            "=" * 60,
            "AI/ML UPDATES DIGEST",
            "=" * 60,
            "",
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Sources with changes: {len(changes)}",
            "",
        ]
        
        # Group changes by organization
        by_org: dict[str, list[dict]] = {}
        for change in changes:
            org = change.get("org", "Unknown")
            if org not in by_org:
                by_org[org] = []
            by_org[org].append(change)
        
        # Build sections for each org
        for org in sorted(by_org.keys()):
            org_changes = by_org[org]
            lines.append("-" * 60)
            lines.append(f"📢 {org}")
            lines.append("-" * 60)
            
            for change in org_changes:
                name = change.get("name", change.get("source_id", "Unknown"))
                url = change.get("url", "")
                is_new = change.get("is_new", False)
                items = change.get("items", [])
                
                status = "[NEW SOURCE]" if is_new else "[UPDATED]"
                lines.append(f"\n{status} {name}")
                lines.append(f"URL: {url}")
                
                if items:
                    lines.append("\nLatest items:")
                    for i, item in enumerate(items[:5], 1):
                        title = item.get("title", "Untitled")
                        link = item.get("link", "")
                        date = item.get("date", "")
                        
                        lines.append(f"  {i}. {title}")
                        if link:
                            lines.append(f"     Link: {link}")
                        if date:
                            lines.append(f"     Date: {date}")
                
                lines.append("")
        
        lines.extend([
            "=" * 60,
            "This is an automated notification from AI Updates Monitor.",
            "To unsubscribe, manage your SNS subscription in AWS Console.",
            "=" * 60,
        ])
        
        return "\n".join(lines)
